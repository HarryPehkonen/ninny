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
        observation.note = (
            f"ran: {self.test_cmd}  ->  exit {observation.exit_code}"
            + ("  (tests FAILED, as they must before the implementation exists)"
               if observation.exit_code else "  (tests PASSED)")
        )
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
