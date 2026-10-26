"""The executor: what an action does, and what it is allowed to touch.

The file tools are confined to the working tree, always, by resolving the path
and refusing anything that lands outside it. That single check is what a public
harness needs and what mini-swe-agent has no equivalent of: an arm that can write
anywhere on the host is an arm that can, and did, write into the staging
directory of the next arm.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ninny.actions import Action
from ninny.sandbox import Sandbox

# The task's test command is the contract, and these are the codes it means. This module
# runs that command, so this is where the contract is written down; `ninny/tdd.py` reads
# the same constants to decide whether a RED was observed, and the shipped tasks
# implement them. Ninny never reads compiler output: a task that cannot tell "the tests
# failed" from "nothing ran" cannot produce a trustworthy red.
PASSED_EXIT = 0
FAILED_EXIT = 1
NOTHING_RAN_EXIT = 2

# And this is the second half of the contract, the one a code cannot carry: how many cases
# the runner actually counted. A task's own runner prints one line when it can:
#
#     NINNY_TESTS: 12
#
# It is optional and it is never compared against anything -- the number of cases a task
# ought to have is not something the harness knows. It exists because a suite can get
# SMALLER without anything failing: a build file that stops compiling a test source, a
# discovery pattern that matches one file instead of six, a test file that loads and
# asserts nothing. All of those exit 0. The count is the only evidence, and in the
# observation text alone it is only visible to someone reading prose carefully.
TEST_COUNT_PREFIX = "NINNY_TESTS:"
_TEST_COUNT_LINE = re.compile(
    r"^" + re.escape(TEST_COUNT_PREFIX) + r"[ \t]*([0-9]+)[ \t]*$", re.MULTILINE
)


def reported_test_count(output: str) -> int | None:
    """The case count a runner reported, or None when it did not report one."""
    matches = _TEST_COUNT_LINE.findall(output or "")
    return int(matches[-1]) if matches else None


def describe_test_exit(code: int | None, command: str, tests: int | None = None) -> str:
    """The sentence the model reads about a test run, in the code's own terms.

    The words have to match the number, because this sentence is what the model uses to
    decide what to do next. A live C++ arm was told "tests FAILED, as they must before the
    implementation exists" on a `cc1plus: fatal error`, where nothing had run at all --
    so the harness misled the model and then banked that run as its RED.

    The count rides along when the runner reported one, so a model whose suite shrank sees
    the number in the same sentence that tells it the tests failed.
    """
    if code == PASSED_EXIT:
        verdict = "tests PASSED"
    elif code == NOTHING_RAN_EXIT:
        verdict = "the suite did not run, so nothing was observed"
    elif code == FAILED_EXIT:
        verdict = "tests FAILED, as they must before the implementation exists"
    else:
        verdict = "outcome unclear from the code alone"
    counted = f"; {tests} cases" if tests is not None else ""
    return f"ran: {command}  ->  exit {code}  ({verdict}{counted})"


# Conservative detector for a shell command that writes into the source tree.
# It exists so an enforcement bypass is at least visible; it is not a guarantee.
_SRC_WRITE_HINTS = [
    re.compile(r">>?\s*['\"]?(?P<p>[\w./-]*src/[\w./-]+)"),
    re.compile(r"\btee\s+(?:-a\s+)?['\"]?(?P<p>[\w./-]*src/[\w./-]+)"),
    re.compile(r"\bsed\s+-i\b[^|;]*['\"]?(?P<p>[\w./-]*src/[\w./-]+)"),
    re.compile(r"\b(?:cp|mv|install)\b[^|;|]*\s['\"]?(?P<p>[\w./-]*src/[\w./-]+)"),
]


class ActionError(Exception):
    """The action was refused before it ran."""


@dataclass
class Observation:
    ok: bool
    exit_code: int | None
    output: str
    note: str = ""
    tests: int | None = None

    def render(self) -> str:
        head = self.note or ("ok" if self.ok else "failed")
        return f"{head}\n{self.output}".rstrip()


class Environment:
    def __init__(
        self,
        workdir: str | Path,
        sandbox: Sandbox,
        timeout: int = 120,
        test_cmd: str = "",
        test_timeout: int = 120,
        allow_outside: bool = False,
        output_limit: int = 30000,
    ):
        self.workdir = Path(workdir).resolve()
        self.sandbox = sandbox
        self.timeout = timeout
        self.test_cmd = test_cmd
        self.test_timeout = test_timeout
        self.allow_outside = allow_outside
        self.output_limit = output_limit

    # ------------------------------------------------------------------ dispatch
    def execute(self, action: Action) -> Observation:
        try:
            if action.name == "bash":
                return self.bash(action.command)
            if action.name == "write_file":
                return self.write_file(action.path, action.content)
            if action.name == "edit_file":
                return self.edit_file(
                    action.path, action.args.get("old_string", ""), action.args.get("new_string", "")
                )
            if action.name == "read_file":
                return self.read_file(action.path, action.args.get("start"), action.args.get("end"))
            if action.name == "run_tests":
                return self.run_tests()
            raise ActionError(f"unknown action {action.name!r}")
        except ActionError as exc:
            return Observation(ok=False, exit_code=None, output=str(exc), note="refused")

    # ---------------------------------------------------------------------- bash
    def bash(self, command: str, timeout: int | None = None) -> Observation:
        if not command.strip():
            return Observation(ok=False, exit_code=2, output="empty command", note="refused")
        try:
            done = self.sandbox.run(command, self.workdir, timeout or self.timeout)
        except subprocess.TimeoutExpired:
            return Observation(ok=False, exit_code=124, output=f"timed out after {timeout or self.timeout}s",
                               note="timeout")
        except OSError as exc:
            return Observation(ok=False, exit_code=126, output=f"{type(exc).__name__}: {exc}", note="exec error")
        output = (done.stdout or "") + (done.stderr or "")
        return Observation(ok=done.returncode == 0, exit_code=done.returncode, output=self.limit(output))

    def looks_like_src_write(self, command: str) -> str:
        for pattern in _SRC_WRITE_HINTS:
            match = pattern.search(command)
            if match:
                return match.group("p")
        return ""

    # ---------------------------------------------------------------- file tools
    def write_file(self, path: str, content: str) -> Observation:
        target = self.resolve(path, for_write=True)
        if target.is_dir():
            raise ActionError(f"{path!r} is a directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        rel = target.relative_to(self.workdir)
        lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
        return Observation(ok=True, exit_code=0, output=f"wrote {rel} ({len(content)} bytes, {lines} lines)",
                           note="ok")

    def edit_file(self, path: str, old_string: str, new_string: str) -> Observation:
        """Replace one exact occurrence. Zero or several is a refusal, never a guess.

        A wrong guess about *which* occurrence to change silently corrupts a file, and the model
        has read_file: it can copy the text. So the only edit this tool performs is the one where
        the text it was given appears exactly once.
        """
        target = self.resolve(path, for_write=True)
        if target.is_dir():
            raise ActionError(f"{path!r} is a directory")
        if not target.is_file():
            raise ActionError(
                f"{path!r} does not exist -- edit_file changes a file that is there; "
                "use write_file to create one"
            )
        if not old_string:
            raise ActionError("edit_file needs a non-empty 'old_string'")
        text = target.read_text(errors="replace")
        found = text.count(old_string)
        if found == 0:
            raise ActionError(
                f"old_string does not appear in {path!r} -- read_file it and copy the text "
                "exactly, whitespace included"
            )
        if found > 1:
            raise ActionError(
                f"old_string appears {found} times in {path!r} -- include more of the "
                "surrounding text so the match is unique"
            )
        target.write_text(text.replace(old_string, new_string, 1))
        rel = target.relative_to(self.workdir)
        return Observation(ok=True, exit_code=0,
                           output=f"edited {rel} (1 replacement, {len(old_string)} -> {len(new_string)} chars)",
                           note="ok")

    def read_file(self, path: str, start=None, end=None) -> Observation:
        target = self.resolve(path, for_write=False)
        if not target.is_file():
            raise ActionError(f"{path!r} does not exist")
        text = target.read_text(errors="replace")
        lines = text.splitlines()
        if start or end:
            first = max(int(start or 1), 1)
            last = min(int(end or len(lines)), len(lines))
            body = "\n".join(f"{i:>6}  {lines[i - 1]}" for i in range(first, last + 1))
            return Observation(ok=True, exit_code=0, output=self.limit(body), note=f"{path} lines {first}-{last}")
        numbered = "\n".join(f"{i:>6}  {line}" for i, line in enumerate(lines, 1))
        return Observation(ok=True, exit_code=0, output=self.limit(numbered), note=f"{path} ({len(lines)} lines)")

    # ------------------------------------------------------------------ test loop
    def run_tests(self, timeout: int | None = None) -> Observation:
        if not self.test_cmd:
            raise ActionError("this task declares no test_cmd, so there is nothing to run")
        observation = self.bash(self.test_cmd, timeout=timeout or self.test_timeout)
        observation.tests = reported_test_count(observation.output)
        observation.note = describe_test_exit(observation.exit_code, self.test_cmd, observation.tests)
        return observation

    # ------------------------------------------------------------------- helpers
    def resolve(self, raw: str, for_write: bool) -> Path:
        if not str(raw).strip():
            raise ActionError("empty path")
        candidate = Path(raw)
        target = candidate if candidate.is_absolute() else (self.workdir / candidate)
        resolved = target.resolve()
        inside = resolved == self.workdir or self.workdir in resolved.parents
        if not inside and not self.allow_outside:
            raise ActionError(
                f"{raw!r} is outside the working tree. The file tools only touch paths inside "
                f"{self.workdir}. Use bash for anything else."
            )
        if not inside and for_write:
            raise ActionError(f"refusing to write {raw!r} outside the working tree")
        return resolved

    def limit(self, text: str) -> str:
        if len(text) <= self.output_limit:
            return text
        head = int(self.output_limit * 0.6)
        tail = self.output_limit - head
        omitted = len(text) - self.output_limit
        return f"{text[:head]}\n... [{omitted} bytes omitted by the harness] ...\n{text[-tail:]}"
