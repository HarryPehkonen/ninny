"""What the model may do, and how a reply turns into actions.

Five actions, and no more unless a measured failure justifies one: `edit_file` earned its place
because on `tasks/dogfood-stamp` three of three arms reached for a shell heredoc to change part of
a file that `write_file` would have had to regenerate whole, and every one of those writes was
caught by the bypass detector afterwards. The measured failure was a missing tool, not a missing
wall:

    bash         run a shell command in the working tree
    write_file   write a file, creating parent directories
    edit_file    replace one exact occurrence of text in an existing file
    read_file    read a file, optionally a line range
    run_tests    run the task's own test command and report its exit status

`run_tests` is what makes a RED observation a harness event instead of a guess at
the model's shell history. A non-zero exit from it is unambiguous, and the
test-first state machine (ninny/tdd.py) is built on exactly that event.

Tool calls are preferred. A model that cannot emit one can write the same actions
as fenced blocks, which is what the legacy /completions wire relies on:

    ```bash
    ls -la
    ```

    ```write_file src/thing.cpp
    ...file content...
    ```
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ninny import SUBMIT_SENTINEL

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the working directory. Every action runs in a fresh shell.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "The shell command to run."}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file, creating parent directories. Use this instead of a heredoc. This replaces the whole file: to change part of a file you did not just write, use edit_file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."},
                    "content": {"type": "string", "description": "The complete file content."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Change part of an existing file: replace old_string with new_string. old_string "
                "must appear exactly once, so copy it from read_file with its whitespace intact and "
                "include enough context to be unique. Zero or several matches is refused, and the "
                "file is left alone."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."},
                    "old_string": {"type": "string", "description": "The exact text to replace; must appear exactly once."},
                    "new_string": {"type": "string", "description": "What to put in its place."},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the working tree, optionally a line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."},
                    "start": {"type": "integer", "description": "First line, 1-based, inclusive."},
                    "end": {"type": "integer", "description": "Last line, 1-based, inclusive."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "Run your own test suite and see the result. A non-zero exit means the tests "
                "failed, which is the expected result before the implementation exists."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

ACTION_NAMES = ("bash", "write_file", "edit_file", "read_file", "run_tests")

#: Every action that writes into the tree. ONE definition, because the gate, the seal and the
#: write bookkeeping all have to agree about what counts as a write: a new tool that writes and
#: is not on this list is a new way around all three.
WRITE_ACTIONS = ("write_file", "edit_file")

_FENCE = re.compile(r"```([a-zA-Z_]+)([^\n]*)\n(.*?)```", re.DOTALL)
_JSON_ACTION = re.compile(r"\{\s*\"name\"\s*:\s*\"(\w+)\"\s*,\s*\"(?:arguments|args)\"\s*:\s*(\{.*?\})\s*\}", re.DOTALL)


@dataclass
class Action:
    name: str
    args: dict = field(default_factory=dict)
    source: str = "tool_call"  # "tool_call" | "text"
    malformed: str = ""        # why this action could not be understood, if so

    @property
    def command(self) -> str:
        return str(self.args.get("command", ""))

    @property
    def path(self) -> str:
        return str(self.args.get("path", ""))

    @property
    def content(self) -> str:
        return str(self.args.get("content", ""))

    def is_submit(self) -> bool:
        return self.name == "bash" and SUBMIT_SENTINEL in self.command

    def describe(self) -> str:
        if self.name == "bash":
            return f"bash: {self.command.splitlines()[0][:120] if self.command else '(empty)'}"
        if self.name == "write_file":
            return f"write_file: {self.path} ({len(self.content)} bytes)"
        if self.name == "edit_file":
            old = str(self.args.get("old_string", ""))
            new = str(self.args.get("new_string", ""))
            return f"edit_file: {self.path} ({len(old)} -> {len(new)} chars)"
        if self.name == "read_file":
            return f"read_file: {self.path}"
        return f"{self.name}: {json.dumps(self.args)[:120]}"


def actions_from_tool_calls(calls) -> list[Action]:
    actions: list[Action] = []
    for call in calls:
        args = call.arguments if isinstance(call.arguments, dict) else {}
        if "__unparsed__" in args:
            actions.append(
                Action(name=call.name or "?", args={}, source="tool_call",
                       malformed=f"arguments were not valid JSON: {args['__unparsed__'][:200]}")
            )
            continue
        actions.append(Action(name=call.name or "", args=args, source="tool_call"))
    return actions


def actions_from_text(text: str) -> list[Action]:
    """Recover actions from a reply that used fenced blocks instead of tool calls.

    Four actions here, not five, and that is a property of the wire rather than an oversight: a
    fence carries one body, so it can express `bash`, `run_tests`, a whole-file `write_file` or a
    `read_file` path, but it cannot carry the three arguments `edit_file` needs. On this wire the
    model edits by rewriting the file. The tool-call wire offers all five.
    """
    actions: list[Action] = []
    for match in _FENCE.finditer(text):
        lang = match.group(1).lower()
        tail = (match.group(2) or "").strip()
        body = match.group(3)
        if lang in ("bash", "sh", "shell"):
            actions.append(Action(name="bash", args={"command": body.strip()}, source="text"))
        elif lang in ("run_tests", "tests", "test"):
            actions.append(Action(name="run_tests", args={}, source="text"))
        elif lang in ("write_file", "file", "create"):
            if tail:
                actions.append(Action(name="write_file", args={"path": tail, "content": body}, source="text"))
            else:
                actions.append(Action(name="write_file", args={}, source="text",
                                      malformed="write_file needs the path on the fence line, e.g. ```write_file src/a.cpp"))
        elif lang in ("read_file", "read"):
            if tail:
                actions.append(Action(name="read_file", args={"path": tail}, source="text"))
            else:
                actions.append(Action(name="read_file", args={}, source="text",
                                      malformed="read_file needs the path on the fence line"))
    if not actions:
        for match in _JSON_ACTION.finditer(text):
            try:
                args = json.loads(match.group(2))
            except json.JSONDecodeError:
                continue
            actions.append(Action(name=match.group(1), args=args, source="text"))
    return actions


def parse_reply(response) -> tuple[list[Action], str]:
    """Turn a model reply into actions. Returns (actions, note)."""
    if response.tool_calls:
        return actions_from_tool_calls(response.tool_calls), ""
    text_actions = actions_from_text(response.text or "")
    if text_actions:
        return text_actions, "actions recovered from fenced blocks (no tool call was emitted)"
    return [], ""


def validate(action: Action) -> str:
    """Return '' if the action is usable, else the format error to send back."""
    if action.malformed:
        return action.malformed
    if action.name not in ACTION_NAMES:
        return (
            f"unknown action {action.name!r}. Use one of: " + ", ".join(ACTION_NAMES)
        )
    if action.name == "bash" and not action.command.strip():
        return "bash needs a non-empty 'command'."
    if action.name in ("write_file", "edit_file", "read_file") and not action.path.strip():
        return f"{action.name} needs a 'path'."
    if action.name == "write_file" and "content" not in action.args:
        return "write_file needs 'content' (the complete file)."
    if action.name == "edit_file" and not str(action.args.get("old_string", "")):
        return "edit_file needs 'old_string' (the exact text to replace)."
    if action.name == "edit_file" and "new_string" not in action.args:
        return "edit_file needs 'new_string'."
    return ""
