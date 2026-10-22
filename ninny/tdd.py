"""Test-first, as a state machine rather than a sentence.

Every harness we measured *asks* for tests first, in prose, and gets it 0 times
out of 27 runs. Ninny enforces it, and records enough to tell the difference
between enforcement working and enforcement being worked around.

Three modes beyond `off`:

    request   never refuse anything, just record. The control condition, and
              exactly what the other harnesses do.
    enforce   refuse a write into the source tree until a test file exists AND a
              run_tests action has come back non-zero. The intervention.
    reverse   allow the code first and require tests before the run may submit.
              The control that makes the claim about ORDER rather than about how
              many tests happened to get written.

Enforcement is not trusted on its own. After every action the source tree is
hashed, and any change while the run is still in the test phase is recorded as a
bypass -- so a model that finds a route around the gate is visible in the
trajectory instead of quietly winning.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ninny.artifacts import is_ignored

MODES = ("off", "request", "enforce", "reverse")


@dataclass
class TDDState:
    mode: str
    phase: str = "test"
    test_files: list[str] = field(default_factory=list)
    first_test_step: int | None = None
    first_src_step: int | None = None
    red_step: int | None = None
    test_runs: list[list[int]] = field(default_factory=list)
    refusals: list[list] = field(default_factory=list)
    bypass_detected: list[list] = field(default_factory=list)
    submit_refusals: int = 0
    red_submit_refusals: int = 0

    @property
    def own_gate_red(self) -> bool:
        """The arm's own test command was last seen failing."""
        return bool(self.test_runs) and self.test_runs[-1][1] != 0

    @property
    def red_ok(self) -> bool:
        """A failing test has been observed, and a test file exists to fail."""
        return self.red_step is not None and self.first_test_step is not None and self.red_step >= self.first_test_step

    @property
    def red_before_code(self) -> bool:
        """A RED was seen, and it happened before the first source write."""
        return self.red_ok and (self.first_src_step is None or self.red_step < self.first_src_step)

    def verdict(self) -> str:
        if not self.test_files:
            return "no-tests"
        if not self.red_ok:
            return "no-red"
        if self.first_src_step is None:
            return "red-no-impl"
        return "red-first" if self.red_step < self.first_src_step else "red-after-code"

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "phase": self.phase,
            "verdict": self.verdict(),
            "test_files": self.test_files,
            "first_test_step": self.first_test_step,
            "first_src_step": self.first_src_step,
            "red_step": self.red_step,
            "red_before_code": self.red_before_code,
            "test_runs": self.test_runs,
            "refusals": self.refusals,
            "bypass_detected": self.bypass_detected,
            "submit_refusals": self.submit_refusals,
            "red_submit_refusals": self.red_submit_refusals,
            "own_gate_red": self.own_gate_red,
        }


def snapshot(workdir: Path, globs: list[str]) -> dict[str, str]:
    """Content hash of the files matching `globs`, for change detection.

    mtime is not enough. Two writes inside the same filesystem timestamp tick are
    indistinguishable, and a fast bypass would go unnoticed -- which this
    detector discovered for itself when its own test did exactly that.
    """
    out: dict[str, str] = {}
    for pattern in globs:
        base = pattern[:-3] if pattern.endswith("/**") else pattern
        root = workdir / base
        paths = [root] if root.is_file() else (sorted(root.rglob("*")) if root.is_dir() else [])
        for path in paths:
            rel = path.relative_to(workdir)
            # Bytecode caches are not source. Running the tests creates them, so
            # counting them made the suite's own run look like a source edit.
            if path.is_file() and not is_ignored(rel):
                try:
                    out[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    continue
    return out


class TDDPolicy:
    def __init__(self, mode: str, task, workdir: str | Path, require_green: bool = True):
        if mode not in MODES:
            raise ValueError(f"unknown tdd mode {mode!r}; expected one of {', '.join(MODES)}")
        self.mode = mode
        self.task = task
        self.workdir = Path(workdir).resolve()
        self.require_green = require_green
        self._baseline_src = snapshot(self.workdir, task.src_globs)

    def new_state(self) -> TDDState:
        return TDDState(mode=self.mode, phase="impl" if self.mode in ("off", "reverse") else "test")

    def _rel(self, path: str) -> str:
        """Where a spelled path lands, relative to the working tree.

        Follows `..`, `.` and absolute prefixes the way a real write does, so the
        gate classifies the destination and not the spelling. Returns the empty
        string when the path lands outside the working tree — nothing the file
        tools may write is ever spelled that way.
        """
        candidate = Path(path)
        target = candidate if candidate.is_absolute() else (self.workdir / candidate)
        try:
            resolved = target.resolve()
        except OSError:
            resolved = target
        try:
            return resolved.relative_to(self.workdir).as_posix()
        except ValueError:
            return ""

    def _lands_outside(self, path: str) -> bool:
        return self._rel(path) == ""

    # ---------------------------------------------------------------------- gate
    def gate(self, action, state: TDDState, step: int, src_write_suspect: str = "") -> str:
        """Return a refusal message to send back to the model, or '' to allow."""
        path = action.path if action.name == "write_file" else src_write_suspect
        rel = self._rel(path) if path else ""
        if rel and self.task.is_protected(rel):
            state.refusals.append([step, f"protected: {rel}"])
            return self._protected_message(rel)

        # Handing back a tree its own tests say is broken is not a finished run, and
        # that holds in every mode: this is not test-first, it is "is it green?".
        # Refused once and then let through, like the no-RED submit rule, so a run
        # cannot be trapped in a loop it cannot win.
        if action.is_submit() and self.require_green and state.own_gate_red:
            state.red_submit_refusals += 1
            if state.red_submit_refusals <= 1:
                state.refusals.append([step, "submit on a red tree"])
                return self._red_tree_message()

        if self.mode != "enforce":
            return ""

        # A path that never lands inside the working tree cannot be a legitimate
        # write, in the test phase or after it.
        if path and self._lands_outside(path):
            state.refusals.append([step, f"outside: {path}"])
            return self._refusal_message(path)

        if state.phase != "test":
            return ""
        if action.name == "write_file":
            if self.task.is_src_path(rel) and not state.red_ok:
                state.refusals.append([step, rel])
                return self._refusal_message(rel)
        if action.name == "bash" and src_write_suspect and not state.red_ok:
            if rel and self.task.is_src_path(rel):
                state.refusals.append([step, f"bash -> {src_write_suspect}"])
                return self._refusal_message(src_write_suspect, via_shell=True)
        if action.is_submit() and not state.red_ok:
            state.submit_refusals += 1
            if state.submit_refusals <= 1:
                state.refusals.append([step, "submit"])
                return self._refusal_message("the whole task", on_submit=True)
        return ""

    def gate_submit_reverse(self, state: TDDState, step: int) -> str:
        """In reverse mode, tests are required before submitting -- the control."""
        if self.mode != "reverse":
            return ""
        if state.first_test_step is None or (
            state.first_src_step is not None and state.first_test_step <= state.first_src_step
        ):
            state.submit_refusals += 1
            if state.submit_refusals <= 2:
                state.refusals.append([step, "submit (reverse: no tests after the code)"])
                return (
                    "Refused: the implementation exists but no tests were written after it. "
                    "Write tests for it using write_file under "
                    f"{', '.join(self.task.test_globs)}, run them with run_tests, then submit."
                )
        return ""

    def _red_tree_message(self) -> str:
        return (
            "Refused: your own tests are failing -- the last run_tests run exited non-zero -- "
            "so this is not finished. Fix the code or the test, run it again with run_tests, "
            "and submit when it is green. A handover on a red tree is not a result."
        )

    def _protected_message(self, rel: str) -> str:
        return (
            f"Refused: {rel} is part of the instrument that measures this run, not the work. "
            "Edit it and the record stops meaning anything. Implement the task in "
            f"{', '.join(self.task.src_globs)} and write your tests under "
            f"{', '.join(self.task.test_globs)}."
        )

    def _refusal_message(self, rel: str, via_shell: bool = False, on_submit: bool = False) -> str:
        how = "A shell command tried to write" if via_shell else "That write"
        return (
            f"Refused (test-first is enforced in this run). {how} to {rel} before any test "
            "has been seen to fail.\n"
            f"1. write a test under {', '.join(self.task.test_globs)} with write_file\n"
            "2. run it with run_tests and look at the failure\n"
            "3. then write the implementation\n"
            "This is not a hint about style: the run records whether a failing test was seen "
            "first, and it cannot be recorded if it did not happen."
        )

    # ------------------------------------------------------------------- observe
    def observe(self, action, observation, state: TDDState, step: int) -> None:
        if action.name == "write_file":
            rel = self._rel(action.path)
            if self.task.is_test_path(rel) and observation.ok:
                if rel not in state.test_files:
                    state.test_files.append(rel)
                if state.first_test_step is None:
                    state.first_test_step = step
            elif self.task.is_src_path(rel) and observation.ok:
                if state.first_src_step is None:
                    state.first_src_step = step
                if state.red_ok:
                    state.phase = "impl"
        elif action.name == "run_tests":
            state.test_runs.append([step, observation.exit_code if observation.exit_code is not None else -1])
            # A failing run is only a RED observation if there was a test file to
            # fail. The own-test runner fails on purpose when the suite is empty, so
            # without this a run could bank an early red_step just by running the
            # test command before writing anything -- and be reported as red-first.
            had_a_test_to_fail = observation.exit_code not in (0, None) and state.first_test_step is not None
            if had_a_test_to_fail and state.red_step is None:
                state.red_step = step
            if state.red_ok:
                state.phase = "impl"
        elif action.is_submit():
            state.phase = "done"

    def observe_tree(self, state: TDDState, step: int) -> None:
        """Reconcile the record against the tree, which is the ground truth.

        A source change made through a route the action log cannot see -- a shell
        heredoc, sed, a script -- still counts as a source change, so the first one
        sets `first_src_step`. Without this the verdict can silently read
        `red-no-impl` for a run that wrote its code first.

        A bypass is only a bypass where the gate was supposed to refuse. In the other
        modes nothing was gated, so recording one would mislabel the control arm of a
        comparison as a run that cheated.
        """
        current = snapshot(self.workdir, self.task.src_globs)
        changed = [path for path, signature in current.items() if self._baseline_src.get(path) != signature]
        if changed and state.first_src_step is None:
            state.first_src_step = step
        if self.mode == "enforce" and state.phase == "test":
            for path in changed:
                entry = [step, path]
                if entry not in state.bypass_detected:
                    state.bypass_detected.append(entry)
        self._baseline_src = current
