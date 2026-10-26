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

from ninny.actions import WRITE_ACTIONS
from ninny.artifacts import is_ignored
from ninny.env import FAILED_EXIT, NOTHING_RAN_EXIT, PASSED_EXIT

MODES = ("off", "request", "enforce", "reverse", "split")


# The phases the run moves through, named so the MODEL is told where it is. The state has
# carried `phase` since the beginning and never said so out loud; these are the words for it,
# and they are the same words in the prompt, in a refusal, and in the observation after an
# action -- one definition, three readers.
PHASE_ORDER = ("test", "impl", "done")
PHASE_LABELS = {"test": "RED-FIRST", "impl": "GREEN", "done": "HAND BACK"}
PHASE_JOBS = {
    "test": "write a test that RUNS and fails",
    "impl": "implement until the suite passes",
    "done": "submit; the record must show the red before the source",
}
# A test that never ran is not a red. A build error, an import error or an empty collection
# is exit 2, and a model that has just read `cc1plus: fatal error` reads that as a failure it
# earned. This sentence is the one that has to reach it, at the moment it happens.
NOT_A_RED = (
    "A test that never ran is not a red: a build error, an import error or a suite\n"
    "that collects nothing is exit 2 -- nothing ran -- and the harness does not bank\n"
    "it. Make it compile and assert something that is wrong, then run it again."
)

# Round two, said at the moment it becomes true. Every sentence here used to be a paragraph in
# the preamble, read before the model knew what any of it referred to: the seal is live now, the
# files it names are the ones that just failed, and the rule about handing back a suite nobody
# ran applies to the tree in front of it. The text moved to where it is true; nothing was added.
ROUND_TWO = {
    "split": (
        "\n\nThe suite is sealed from here. Writing under the test globs is refused, and the "
        "files that were red are read-only in the shell too, so what you hand back has to be "
        "the tests that failed. If a sealed test is wrong and the code cannot satisfy it, say "
        "so in your final message -- that is the one case where handing back red is right, and "
        "never because the implementation is inconvenient. You may still ADD test files; the "
        "record counts them separately. And never hand back a suite you have not run since "
        "your last change."
    ),
}


def phase_line(phase: str) -> str:
    """`1/3 RED-FIRST -- write a test that RUNS and fails`."""
    phase = phase if phase in PHASE_LABELS else PHASE_ORDER[0]
    return (
        f"{PHASE_ORDER.index(phase) + 1}/{len(PHASE_ORDER)} {PHASE_LABELS[phase]}"
        f" -- {PHASE_JOBS[phase]}"
    )


def phases_line() -> str:
    """The sequence, for the plan line a human reads before the run starts."""
    return " -> ".join(PHASE_LABELS[p] for p in PHASE_ORDER)


def phases_block() -> str:
    """The sequence, for the prompt."""
    return "\n".join(
        f"{index}. {PHASE_LABELS[p]} -- {PHASE_JOBS[p]}"
        for index, p in enumerate(PHASE_ORDER, 1)
    )


@dataclass
class TDDState:
    mode: str
    phase: str = "test"
    # The once-only line the model is told when the phase moves, so a phase change
    # is never silent. Deliberately not serialised: it is a message, not a measurement
    # (the trajectory stores the message itself).
    phase_news: str = ""
    test_files: list[str] = field(default_factory=list)
    first_test_step: int | None = None
    first_src_step: int | None = None
    red_step: int | None = None
    red_exit: int | None = None
    test_runs: list[list[int]] = field(default_factory=list)
    # The counts the runner reported, as [step, count], for the runs that reported one.
    # Kept beside test_runs rather than inside it so the documented shape of test_runs
    # (step, exit code) does not change under anyone reading the record.
    test_counts: list[list[int]] = field(default_factory=list)
    # The observation gap. `red-first` describes the ORDER of the writes; this describes
    # whether the suite was observed at all after the code it is supposed to describe.
    # Three live `bits` arms handed back a correct implementation and a suite nobody had run
    # for twenty-plus steps, and the record could not see it: one RED at step 8 made
    # `own_gate_red` true for the rest of the run.
    last_run_step: int | None = None
    last_src_step: int | None = None
    #: Runs the HARNESS made, not the model: [step, exit]. A submit arrived without an
    #: observation of the tree being handed back, so the harness took one and said so here.
    harness_runs: list[list[int]] = field(default_factory=list)
    suite_stale_at_submit: bool = False
    refusals: list[list] = field(default_factory=list)
    bypass_detected: list[list] = field(default_factory=list)
    submit_refusals: int = 0
    red_submit_refusals: int = 0
    # The test suite as it was at the RED observation, {relpath: sha256}, and the step the
    # seal was taken. The order of the writes is one claim; the provenance of the artifact
    # is another. A run can bank a real red and then rewrite the suite that red came from,
    # and `red-first` stays true while the tests that ship are not the tests that failed.
    sealed: dict[str, str] | None = None
    seal_step: int | None = None
    suite_frozen_since_red: bool | None = None
    suite_changed_after_red: list[str] = field(default_factory=list)
    #: Test files that appeared after the red. Not a broken seal -- the red suite is still
    #: in there, unchanged -- but a reader should not have to diff to find them.
    tests_added_after_red: list[str] = field(default_factory=list)
    #: Whether the sealed files were made read-only (the sandbox enforces it) or only
    #: refused by the gate (nothing stops the shell). "Reported" and "enforced" differ.
    sealed_readonly: bool = False
    #: Which rule applied to the red: a test file the model wrote (benchmark), or any observed
    #: failure of the tree's own suite (a repository). Copied from the task when the state is
    #: created so the record can be read without the task, and so `verdict` agrees with it.
    require_test_file: bool = True

    @property
    def own_gate_red(self) -> bool:
        """The arm's own test command was last seen failing."""
        return bool(self.test_runs) and self.test_runs[-1][1] != 0

    @property
    def suite_stale(self) -> bool:
        """No test run has been observed since the last source change.

        A run at the same step as the write counts as fresh: the order within one step is
        not recorded, and reading it as stale would invent a fact the record does not have.
        """
        if self.last_run_step is None:
            return True
        return self.last_src_step is not None and self.last_src_step > self.last_run_step

    @property
    def green_after_last_write(self) -> bool | None:
        """Whether the shipped tree was last observed green; None when nothing covers it.

        None is not a failure and not a pass: it means the suite was never run against the
        code that is being handed back, and a reader should be told that rather than shown
        a green light nobody earned.
        """
        if self.last_run_step is None or self.suite_stale:
            return None
        return bool(self.test_runs) and self.test_runs[-1][1] == PASSED_EXIT

    @property
    def red_ok(self) -> bool:
        """A failing test has been observed, and something exists to fail.

        In a benchmark that something is a test file the model wrote; in a repository it is the
        suite that was already there, and `require_test_file` says which. Either way exit 2 is
        not a red -- a run that collected nothing did not fail, it did not happen.
        """
        if self.red_step is None:
            return False
        if not self.require_test_file:
            return True
        return self.first_test_step is not None and self.red_step >= self.first_test_step

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
            #: Which rule decided the red. A record can then be read without its task, and a
            #: repository run is not graded against a benchmark's claim about its suite.
            "require_test_file": self.require_test_file,
            "test_files": self.test_files,
            "first_test_step": self.first_test_step,
            "first_src_step": self.first_src_step,
            "red_step": self.red_step,
            "red_exit": self.red_exit,
            "red_before_code": self.red_before_code,
            "test_runs": self.test_runs,
            # The case counts the runner reported, [step, count] per run that reported one.
            # A suite that shrank asserts less without failing, and this is the only trace.
            "test_counts": self.test_counts,
            "last_run_step": self.last_run_step,
            "last_src_step": self.last_src_step,
            "suite_stale_at_submit": self.suite_stale_at_submit,
            # Who ran the suite at handback, and what the tree it was run against looked
            # like: None = never observed, True = seen green, False = seen failing.
            "green_after_last_write": self.green_after_last_write,
            "harness_runs": self.harness_runs,
            "refusals": self.refusals,
            "bypass_detected": self.bypass_detected,
            "submit_refusals": self.submit_refusals,
            "red_submit_refusals": self.red_submit_refusals,
            "own_gate_red": self.own_gate_red,
            "seal_step": self.seal_step,
            "suite_frozen_since_red": self.suite_frozen_since_red,
            "suite_changed_after_red": self.suite_changed_after_red,
            "tests_added_after_red": self.tests_added_after_red,
            "sealed_readonly": self.sealed_readonly,
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
        # Copied from the task rather than read off it later: the state is the record, and a
        # record that cannot be read without its task is not much of one. getattr keeps the
        # doubles in the existing tests working.
        return TDDState(
            mode=self.mode,
            phase="impl" if self.mode in ("off", "reverse") else "test",
            require_test_file=getattr(self.task, "require_test_file", True),
        )

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
        path = action.path if action.name in WRITE_ACTIONS else src_write_suspect
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

        if self.mode not in ("enforce", "split"):
            return ""

        # A path that never lands inside the working tree cannot be a legitimate
        # write, in the test phase or after it.
        if path and self._lands_outside(path):
            state.refusals.append([step, f"outside: {path}"])
            return self._refusal_message(path, phase=state.phase)

        # `split`: two rounds are the protocol. Once a red is banked the suite is sealed, so
        # the tests that ship have to be the tests that went red -- a guarantee `enforce`
        # cannot give, because it orders the writes and says nothing about the artifact.
        #
        # Sealed PER FILE, not per directory. What went red is what gets frozen; a NEW test
        # file is still allowed, because the suite the red came from is still in there,
        # unchanged, and adding to it is usually good work.
        #
        # NO DOOR, and that is deliberate. There used to be one -- a suite that could not RUN
        # (exit 2) could be edited again, on the reasoning that nobody can be held to a suite
        # that does not run. A live arm walked through it: it broke its own source until the
        # suite would not import (exit 2 at step 26), was refused at step 24, and was ALLOWED at
        # step 28 -- and the write landed, because the file tool writes from this process, and
        # the read-only bind only reaches inside the bash sandbox. Two layers, two paths, and
        # the door was the gap between them. A sealed file provably RAN (the seal is taken at a
        # run that returned 1), so a later exit 2 comes from a new unsealed file or from the
        # model's own source edits -- both of which it can still fix. There is nothing left that
        # needs the door, and a sealed file now has no write path at all.
        if self.mode == "split" and state.phase != "test" and state.sealed:
            if action.name in WRITE_ACTIONS and rel in state.sealed:
                state.refusals.append([step, f"sealed: {rel}"])
                return self._sealed_message(rel, state.seal_step)

        if state.phase != "test":
            return ""
        if action.name in WRITE_ACTIONS:
            if self.task.is_src_path(rel) and not self.task.is_test_path(rel) and not state.red_ok:
                state.refusals.append([step, rel])
                return self._refusal_message(rel, phase=state.phase)
        if action.name == "bash" and src_write_suspect and not state.red_ok:
            if rel and self.task.is_src_path(rel) and not self.task.is_test_path(rel):
                state.refusals.append([step, f"bash -> {src_write_suspect}"])
                return self._refusal_message(src_write_suspect, via_shell=True, phase=state.phase)
        if action.is_submit() and not state.red_ok:
            state.submit_refusals += 1
            if state.submit_refusals <= 1:
                state.refusals.append([step, "submit"])
                return self._refusal_message("the whole task", on_submit=True, phase=state.phase)
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

    def _enter(self, state: TDDState, phase: str, step: int) -> None:
        """Move the phase, and say so once.

        The news is one-shot because it is guidance rather than state: the model is told the
        red is banked and the next phase has begun, and after that the prompt is the reminder.
        """
        if state.phase == phase:
            return
        state.phase = phase
        if phase == "impl":
            state.phase_news = (
                f"Red banked at step {step} -- the suite ran and failed, which is the "
                f"observation this gate wanted. Now {phase_line('impl')}."
                + ROUND_TWO.get(self.mode, "")
            )
        else:
            state.phase_news = f"Phase: {phase_line(phase)}."

    def note_for(self, action, observation, state: TDDState) -> str:
        """The one line the model is told after an action ran, or "".

        Two moments earn an interruption, and they are the two ways a run goes wrong in
        silence: the phase moved (a red was banked, so implementation is allowed now), or the
        suite reported that NOTHING RAN. A model that has just read `cc1plus: fatal error`
        reads exit 2 as a failure it earned; saying otherwise at that moment is the whole
        reason for naming the phases at all.
        """
        if state.phase_news:
            news, state.phase_news = state.phase_news, ""
            return news
        if action.name != "run_tests" or state.red_ok:
            return ""
        if observation.exit_code == NOTHING_RAN_EXIT:
            return "Nothing ran (exit 2), so nothing was observed and no red was banked. " + NOT_A_RED
        return ""

    def _refusal_message(
        self, rel: str, via_shell: bool = False, on_submit: bool = False, phase: str = "test"
    ) -> str:
        how = "A shell command tried to write" if via_shell else "That write"
        # The first step has to fit the run. A benchmark declares its test globs, so naming
        # them says exactly which files count. A repository without `--test-glob` declares
        # none, and `', '.join([])` renders as an empty gap -- "write a test under  with
        # write_file" -- an instruction with the destination missing, which is how a model
        # ends up guessing. With no globs, say the true thing instead: the suite already
        # there is what has to fail first.
        if self.task.test_globs:
            first_step = (
                f"1. write a test under {', '.join(self.task.test_globs)} with write_file\n"
            )
        else:
            first_step = (
                "1. the repository's own suite has to fail first: write a test file (or make "
                "an existing one fail) with write_file, or run the suite as it stands with "
                "run_tests if it is already red\n"
            )
        return (
            f"Refused (test-first is enforced in this run). {how} to {rel} before any test "
            "has been seen to fail.\n"
            f"You are in {phase_line(phase)}.\n"
            + first_step
            +
            "2. run it with run_tests and look at the failure it reports\n"
            "3. then write the implementation\n"
            + NOT_A_RED
            + "\n"
            "This is not a hint about style: the run records whether a failing test was seen "
            "first, and it cannot be recorded if it did not happen."
        )

    def _sealed_message(self, rel: str, sealed_at) -> str:
        return (
            f"Refused ({rel} was sealed at step {sealed_at}). A red was banked, and from that "
            "point the files that failed are frozen: the tests that ship have to be the tests "
            "that were red, and this run is recorded as to whether they are.\n"
            "This file has no write path left -- the shell cannot rewrite, delete or move it, "
            "and neither can this tool, whatever state the suite is in.\n"
            "Write the implementation and run the suite as often as you like. You may still ADD "
            "new test files; the record notes them separately. If a sealed test is wrong and the "
            "implementation cannot satisfy it, say so in your final message instead of editing "
            "it. Handing back a red suite is allowed, and a truthful one is worth more than a "
            "green one."
        )

    # ------------------------------------------------------------------- observe
    def observe(self, action, observation, state: TDDState, step: int) -> None:
        if action.name in WRITE_ACTIONS:
            rel = self._rel(action.path)
            if self.task.is_test_path(rel) and observation.ok:
                if rel not in state.test_files:
                    state.test_files.append(rel)
                if state.first_test_step is None:
                    state.first_test_step = step
            elif self.task.is_src_path(rel) and observation.ok:
                if state.first_src_step is None:
                    state.first_src_step = step
                state.last_src_step = step
                if state.red_ok:
                    self._enter(state, "impl", step)
        elif action.name == "run_tests":
            code = observation.exit_code if observation.exit_code is not None else -1
            state.test_runs.append([step, code])
            state.last_run_step = step
            # The count, when the task's runner reported one. It is what makes a suite
            # getting smaller visible: nothing fails, it just asserts less.
            count = getattr(observation, "tests", None)
            if count is not None:
                state.test_counts.append([step, count])
            # A failing run is only a RED observation if there was a test file to
            # fail. The own-test runner fails on purpose when the suite is empty, so
            # without this a run could bank an early red_step just by running the
            # test command before writing anything -- and be reported as red-first.
            #
            # And it is only an observation if the suite RAN. Exit 2 is the contract's
            # "could not run" -- a build error, an import error, a suite with nothing to
            # collect -- where nothing was executed and therefore nothing was observed.
            # The code used to be indistinguishable from a failure, which is how a C++
            # build error became the banked RED of a run reported `red-first` off it.
            # The run still lands in `test_runs` with its code, so the evidence stays.
            ran_and_failed = code not in (PASSED_EXIT, NOTHING_RAN_EXIT) and code != -1
            had_a_test_to_fail = ran_and_failed and state.first_test_step is not None
            if had_a_test_to_fail and state.red_step is None:
                state.red_step = step
                state.red_exit = code
                # Seal the suite where it went red. Read back from the tree at handback,
                # not from the action log, so that a rewrite the log cannot see -- a shell
                # heredoc, sed, a script -- counts exactly like one through write_file.
                state.sealed = snapshot(self.workdir, self.task.test_globs)
                state.seal_step = step
            if state.red_ok:
                self._enter(state, "impl", step)
        elif action.is_submit():
            self._enter(state, "done", step)

    def note_harness_run(self, state: TDDState, step: int, exit_code: int) -> None:
        """Record a run the HARNESS made, because the model's submit came without one.

        It lands in `test_runs` too, because every later question -- is it green, is it
        stale -- is about the most recent observation, whoever took it. It lands in
        `harness_runs` as well, so a reader can always tell whose step it was, and
        `suite_stale_at_submit` keeps the fact that the model handed back a tree it had
        not run, whether or not the harness then found it green.
        """
        state.test_runs.append([step, exit_code])
        state.harness_runs.append([step, exit_code])
        state.last_run_step = step
        state.suite_stale_at_submit = True
        if state.red_ok:
            self._enter(state, "impl", step)

    def close_seal(self, state: TDDState) -> None:
        """Was the suite handed back the suite that was red?

        The verdict is read from the tree, never from the action log, so a test file
        rewritten through a route the log cannot see -- a shell heredoc, sed, a script --
        counts the same as one rewritten with write_file.

        `suite_frozen_since_red` stays None when no red was ever banked: there is nothing
        to seal, and reporting `yes` there would claim a guarantee the run never earned.
        """
        if state.sealed is None:
            return
        current = snapshot(self.workdir, self.task.test_globs)
        # Two different facts, kept apart on purpose. A file that was red and changed is the
        # seal broken -- the tests that shipped are not the tests that failed. A file ADDED
        # after the red is usually good work: the suite the red came from is still in there,
        # unchanged, and still passing. Collapsing them into one `changed` list threw away
        # that distinction, and made `frozen=no` mean two things at once.
        state.suite_changed_after_red = sorted(
            path for path in state.sealed if state.sealed.get(path) != current.get(path)
        )
        state.tests_added_after_red = sorted(path for path in current if path not in state.sealed)
        state.suite_frozen_since_red = not state.suite_changed_after_red

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
        if changed:
            if state.first_src_step is None:
                state.first_src_step = step
            # The tree is the ground truth for the observation gap as well: a source change
            # through a route the action log cannot see still makes the last run stale.
            state.last_src_step = step
        if self.mode == "enforce" and state.phase == "test":
            for path in changed:
                entry = [step, path]
                if entry not in state.bypass_detected:
                    state.bypass_detected.append(entry)
        self._baseline_src = current
