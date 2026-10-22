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

    @property
    def red_ok(self) -> bool:
        """A failing test has been observed, and a test file exists to fail."""
        return self.red_step is not None and self.first_test_step is not None and self.red_step >= self.first_test_step

    @property
    def red_before_code(self) -> bool:
        return self.red_step is not None and (self.first_src_step is None or self.red_step < self.first_src_step)

    def verdict(self) -> str:
        if not self.test_files:
            return "no-tests"
        if self.red_step is None:
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
            if path.is_file():
                try:
                    out[str(path.relative_to(workdir))] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    continue
    return out


class TDDPolicy:
    def __init__(self, mode: str, task, workdir: str | Path):
        if mode not in MODES:
            raise ValueError(f"unknown tdd mode {mode!r}; expected one of {', '.join(MODES)}")
        self.mode = mode
        self.task = task
        self.workdir = Path(workdir).resolve()
        self._baseline_src = snapshot(self.workdir, task.src_globs)

    def new_state(self) -> TDDState:
        return TDDState(mode=self.mode, phase="impl" if self.mode in ("off", "reverse") else "test")

    def _rel(self, path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            try:
                return candidate.resolve().relative_to(self.workdir).as_posix()
            except ValueError:
                return candidate.as_posix()
        return candidate.as_posix().lstrip("./")

    # ---------------------------------------------------------------------- gate
    def gate(self, action, state: TDDState, step: int, src_write_suspect: str = "") -> str:
        """Return a refusal message to send back to the model, or '' to allow."""
        protected = ""
        if action.name == "write_file":
            rel = self._rel(action.path)
            if self.task.is_protected(rel):
                protected = rel
        elif action.name == "bash" and src_write_suspect:
            rel = self._rel(src_write_suspect)
            if self.task.is_protected(rel):
                protected = rel
        if protected:
            state.refusals.append([step, f"protected: {protected}"])
            return self._protected_message(protected)

        if self.mode != "enforce" or state.phase != "test":
            return ""
        if action.name == "write_file":
            rel = self._rel(action.path)
            if self.task.is_src_path(rel) and not state.red_ok:
                state.refusals.append([step, rel])
                return self._refusal_message(rel)
        if action.name == "bash" and src_write_suspect and not state.red_ok:
            state.refusals.append([step, f"bash -> {src_write_suspect}"])
            return self._refusal_message(src_write_suspect, via_shell=True)
        if self.mode == "enforce" and action.is_submit() and not state.red_ok:
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
                if self.mode == "enforce" and state.red_ok:
                    state.phase = "impl"
        elif action.name == "run_tests":
            state.test_runs.append([step, observation.exit_code if observation.exit_code is not None else -1])
            if observation.exit_code not in (0, None) and state.red_step is None:
                state.red_step = step
            if self.mode == "enforce" and state.red_ok:
                state.phase = "impl"
        elif action.is_submit():
            state.phase = "done"

    def observe_tree(self, state: TDDState, step: int) -> None:
        current = snapshot(self.workdir, self.task.src_globs)
        if state.phase == "test":
            for path, signature in current.items():
                if self._baseline_src.get(path) != signature:
                    entry = [step, path]
                    if entry not in state.bypass_detected:
                        state.bypass_detected.append(entry)
        self._baseline_src = current
