"""The test-first state machine, including the ways it could be fooled.

These are the tests that matter most, because the whole claim of the project is
that this record can be trusted: a RED observation has to mean a test ran and
failed, and a run that finds a way around the gate has to show up as one.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.actions import Action
from ninny.config import Task
from ninny.env import Observation
from ninny.tdd import MODES, TDDPolicy, snapshot


def build_task(root: Path) -> Task:
    return Task(
        root=root,
        name="tiny",
        spec="",
        tree_src=root / "tree",
        oracle_dir=None,
        test_cmd="true",
        oracle_cmd=None,
        test_globs=["tests/own/**"],
        src_globs=["src/**"],
        protected_globs=["tools/**"],
        preflight=[],
        step_limit=5,
        timeout_s=5,
        test_timeout_s=5,
    )


def observation(exit_code: int) -> Observation:
    return Observation(ok=exit_code == 0, exit_code=exit_code, output="", note="")


class TDDBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        (self.work / "src").mkdir()
        (self.work / "src" / "thing.py").write_text("value = 0\n")
        (self.work / "tests" / "own").mkdir(parents=True)
        (self.work / "tools").mkdir()
        (self.work / "tools" / "run.sh").write_text("#!/bin/sh\nexit 0\n")
        self.task = build_task(self.work)

    def tearDown(self):
        self._tmp.cleanup()

    def policy_for(self, mode: str) -> TDDPolicy:
        return TDDPolicy(mode, self.task, self.work)

    @staticmethod
    def write(path: str, content: str = "x") -> Action:
        return Action(name="write_file", args={"path": path, "content": content})

    @staticmethod
    def run_tests() -> Action:
        return Action(name="run_tests", args={})

    @staticmethod
    def submit() -> Action:
        from ninny import SUBMIT_SENTINEL

        return Action(name="bash", args={"command": f"echo {SUBMIT_SENTINEL}"})

    @staticmethod
    def allow(policy: TDDPolicy, state, action, suspect: str = "") -> bool:
        return policy.gate(action, state, 1, suspect) == ""

    @staticmethod
    def apply(policy: TDDPolicy, state, action, exit_code: int = 0, step: int = 1) -> None:
        policy.observe(action, observation(exit_code), state, step)


class EnforceTests(TDDBase):
    def setUp(self):
        super().setUp()
        self.policy = self.policy_for("enforce")
        self.state = self.policy.new_state()

    def test_a_source_write_is_refused_before_anything(self):
        self.assertFalse(self.allow(self.policy, self.state, self.write("src/thing.py")))
        self.assertEqual(len(self.state.refusals), 1)

    def test_a_test_file_may_be_written(self):
        self.assertTrue(self.allow(self.policy, self.state, self.write("tests/own/test_thing.py")))

    def test_a_test_file_alone_does_not_unlock_the_source(self):
        self.apply(self.policy, self.state, self.write("tests/own/test_thing.py"))
        self.assertTrue(self.state.test_files)
        self.assertFalse(self.allow(self.policy, self.state, self.write("src/thing.py")))

    def test_tests_that_PASS_are_not_a_red_observation(self):
        self.apply(self.policy, self.state, self.write("tests/own/test_thing.py"))
        self.apply(self.policy, self.state, self.run_tests(), exit_code=0)
        self.assertIsNone(self.state.red_step)
        self.assertFalse(self.allow(self.policy, self.state, self.write("src/thing.py")))

    def test_a_failing_test_unlocks_the_source(self):
        self.apply(self.policy, self.state, self.write("tests/own/test_thing.py"))
        self.apply(self.policy, self.state, self.run_tests(), exit_code=1)
        self.assertEqual(self.state.red_step, 1)
        self.assertTrue(self.allow(self.policy, self.state, self.write("src/thing.py")))

    def test_the_phase_moves_to_implementation_only_after_red(self):
        self.assertEqual(self.state.phase, "test")
        self.apply(self.policy, self.state, self.write("tests/own/test_thing.py"))
        self.apply(self.policy, self.state, self.run_tests(), exit_code=1)
        self.assertEqual(self.state.phase, "impl")

    def test_a_shell_write_into_the_source_is_refused_too(self):
        self.assertFalse(self.allow(self.policy, self.state, self.submit(), suspect="src/thing.py"))
        self.assertTrue(self.state.refusals)

    def test_submitting_without_any_tests_is_refused_once(self):
        self.assertFalse(self.allow(self.policy, self.state, self.submit()))
        self.assertEqual(self.state.submit_refusals, 1)


class ProtectedPathTests(TDDBase):
    def test_the_instrument_is_off_limits_in_every_mode(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                policy = self.policy_for(mode)
                state = policy.new_state()
                self.assertFalse(self.allow(policy, state, self.write("tools/run.sh")))
                self.assertTrue(state.refusals)

    def test_a_shell_write_to_the_instrument_is_refused(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                policy = self.policy_for(mode)
                state = policy.new_state()
                self.assertFalse(self.allow(policy, state, self.submit(), suspect="tools/run.sh"))


class BypassTests(TDDBase):
    def test_sneaking_a_source_change_in_is_detected(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        (self.work / "src" / "thing.py").write_text("value = 1\n")  # not through the gate
        policy.observe_tree(state, step=3)
        self.assertEqual(state.bypass_detected, [[3, "src/thing.py"]])

    def test_changes_after_red_are_not_reported_as_bypasses(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"))
        self.apply(policy, state, self.run_tests(), exit_code=1)
        self.assertEqual(state.phase, "impl")
        (self.work / "src" / "thing.py").write_text("value = 2\n")
        policy.observe_tree(state, step=4)
        self.assertEqual(state.bypass_detected, [])

    def test_request_mode_does_not_call_an_ungated_write_a_bypass(self):
        """A bypass means the gate was walked around. In `request` there is no gate,
        so calling an allowed write a bypass is a false accusation -- and this is the
        control arm of the comparison, which must not be quietly labelled a cheater."""
        policy = self.policy_for("request")
        state = policy.new_state()
        (self.work / "src" / "thing.py").write_text("value = 3\n")
        policy.observe_tree(state, step=2)
        self.assertEqual(state.bypass_detected, [])

    def test_request_mode_still_ends_its_test_phase_at_red(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"))
        self.apply(policy, state, self.run_tests(), exit_code=1)
        self.assertEqual(state.phase, "impl")
        (self.work / "src" / "thing.py").write_text("value = 4\n")
        policy.observe_tree(state, step=5)
        self.assertEqual(state.bypass_detected, [])


class PathLandingTests(TDDBase):
    """A path is classified by where it LANDS, not by how it is spelled.

    `tests/../src/thing.py` is a source write that starts with `tests/`, and
    `../../etc/passwd` never lands in the working tree at all. The gate used to
    compare the string as written, so both walked straight past it.
    """

    def test_a_path_can_walk_out_of_the_tests_directory_into_the_source(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.assertTrue(policy.gate(self.write("tests/../src/thing.py"), state, 1))
        self.assertTrue(policy.gate(self.write("tests/own/../../src/thing.py"), state, 1))

    def test_a_path_that_leaves_the_tree_entirely_is_refused(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.assertTrue(policy.gate(self.write("../outside.py"), state, 1))
        self.assertTrue(policy.gate(self.write("../../etc/passwd"), state, 1))

    def test_ordinary_paths_are_unaffected(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.assertFalse(policy.gate(self.write("tests/own/test_x.py"), state, 1))
        self.assertTrue(policy.gate(self.write("src/thing.py"), state, 1))

    def test_a_resolving_source_path_is_allowed_once_red_has_been_seen(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"))
        self.apply(policy, state, self.run_tests(), exit_code=1)
        self.assertFalse(policy.gate(self.write("tests/../src/thing.py"), state, 3))

    def test_the_instrument_cannot_be_reached_by_walking_around_it(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.assertTrue(policy.gate(self.write("tests/../tools/run_own_tests.sh"), state, 1))


class ModeTests(TDDBase):
    def test_request_never_refuses_but_still_records(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.assertTrue(self.allow(policy, state, self.write("src/thing.py")))
        self.apply(policy, state, self.write("src/thing.py"), step=1)
        self.assertEqual(state.first_src_step, 1)
        self.assertEqual(state.verdict(), "no-tests")

    def test_off_and_reverse_start_in_the_implementation_phase(self):
        for mode in ("off", "reverse"):
            with self.subTest(mode=mode):
                self.assertEqual(self.policy_for(mode).new_state().phase, "impl")

    def test_reverse_requires_tests_after_the_code_before_submitting(self):
        policy = self.policy_for("reverse")
        state = policy.new_state()
        self.apply(policy, state, self.write("src/thing.py"), step=1)
        self.assertTrue(policy.gate_submit_reverse(state, 2))
        self.assertEqual(state.submit_refusals, 1)
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=3)
        self.assertEqual(policy.gate_submit_reverse(state, 4), "")


class SourceRecordTests(TDDBase):
    """The tree is the ground truth, not the action log.

    A model can change a source file through a route the action record cannot see --
    a shell heredoc, sed, a script. The record must still notice, or `first_src_step`
    is missing and the verdict silently becomes `red-no-impl` instead of
    `red-after-code`.
    """

    def test_a_source_change_the_action_log_never_saw_still_counts(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        (self.work / "src" / "thing.py").write_text("value = 9\n")  # as a shell would
        policy.observe_tree(state, step=2)
        self.assertEqual(state.first_src_step, 2)

    def test_a_shell_source_change_before_the_test_is_not_reported_as_red_first(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        (self.work / "src" / "thing.py").write_text("value = 9\n")
        policy.observe_tree(state, step=2)
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=3)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=4)
        self.assertEqual(state.verdict(), "red-after-code")

    def test_a_shell_source_change_is_still_a_bypass_under_enforce(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        (self.work / "src" / "thing.py").write_text("value = 9\n")
        policy.observe_tree(state, step=2)
        self.assertEqual(state.bypass_detected, [[2, "src/thing.py"]])


class RedObservationTests(TDDBase):
    """A failing run only counts as RED if there was a test file to fail.

    The own-test runner fails on purpose when there are no tests, so a model that
    runs the test command early -- before writing anything -- would otherwise bank
    an early `red_step` and be reported as red-first without ever having seen a test
    fail. That is a false positive on the headline number, and it would let the
    unenforced control arm look as good as the enforced one.
    """

    def test_a_failing_run_with_no_test_file_is_not_a_red_observation(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.run_tests(), exit_code=1)
        self.assertIsNone(state.red_step)

    def test_an_early_failure_cannot_be_reported_as_red_first(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.run_tests(), exit_code=1, step=1)  # nothing written yet
        self.apply(policy, state, self.write("src/thing.py"), step=2)
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=3)
        self.assertEqual(state.verdict(), "no-red")
        self.assertFalse(state.red_before_code)

    def test_a_real_red_is_still_recorded_and_still_red_first(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=2)
        self.assertEqual(state.red_step, 2)
        self.apply(policy, state, self.write("src/thing.py"), step=3)
        self.assertEqual(state.verdict(), "red-first")


class RedMustHaveRunTests(TDDBase):
    """A RED observation has to be a test that RAN and then failed.

    A suite that does not compile also exits non-zero, so the old rule banked a RED the
    moment the compiler refused -- with nothing executed and nothing observed. The C++
    task's own runner said exactly this in prose ("a build error is not a RED") and then
    exited 1, which is the code Ninny counted as the RED event. The live C++ arm was
    reported `red-first` off that: its banked red was the build error at step 4, its
    first source write was step 7, and its first test that actually ran and failed was
    step 8.

    The contract is the task's own exit code, which keeps this language-agnostic and lets
    Ninny stay out of the business of parsing compiler output:

        0  the tests ran and passed
        1  the tests ran and failed          -> a RED observation
        2  the tests could not run at all    -> not an observation of anything
    """

    def test_a_suite_that_could_not_run_is_not_a_red_observation(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=2, step=2)
        self.assertIsNone(state.red_step)
        self.assertEqual(state.verdict(), "no-red")

    def test_a_suite_that_cannot_compile_does_not_unlock_the_source_gate(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=2, step=2)
        self.assertFalse(self.allow(policy, state, self.write("src/thing.py")))

    def test_the_run_that_could_not_run_is_still_in_the_record(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=2, step=2)
        self.assertEqual(state.test_runs, [[2, 2]])

    def test_a_test_that_really_failed_still_banks_a_red(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=2)
        self.assertEqual(state.red_step, 2)

    def test_the_code_of_the_red_is_kept(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=2)
        self.assertEqual(state.red_exit, 1)
        self.assertEqual(state.as_dict()["red_exit"], 1)

    def test_a_build_error_then_a_stub_then_a_real_red_reads_as_red_after_code(self):
        # The shape of the live C++ arm, once the build error stops counting.
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=2, step=2)   # cannot compile
        self.apply(policy, state, self.write("src/thing.py"), step=3)      # stubs
        self.apply(policy, state, self.run_tests(), exit_code=1, step=4)   # a real failure
        self.assertEqual(state.red_step, 4)
        self.assertEqual(state.verdict(), "red-after-code")

    def test_the_summary_line_names_the_code_the_red_came_from(self):
        from ninny.agent import RunResult

        result = RunResult(tdd={"verdict": "no-red", "mode": "request", "red_step": None,
                                "red_exit": None, "first_src_step": None})
        self.assertIn("red_step", result.summary())
        result.tdd.update({"verdict": "red-after-code", "red_step": 4, "red_exit": 1})
        self.assertIn("red_step=4", result.summary())
        self.assertIn("exit 1", result.summary())


class GreenTreeRuleTests(TDDBase):
    """A run must not hand back a tree its own tests say is broken.

    Test-first asks whether a test was seen to fail before the code. This asks a
    different and simpler question: is the thing being handed back actually green?
    A run that submits on a red suite has not finished, whatever it wrote.
    """

    def test_submitting_with_the_own_tests_failing_is_refused(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=2)
        refusal = policy.gate(self.submit(), state, 3)
        self.assertTrue(refusal)
        self.assertIn("failing", refusal.lower())

    def test_submitting_once_the_tests_go_green_is_allowed(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=2)
        self.apply(policy, state, self.write("src/thing.py"), step=3)
        self.apply(policy, state, self.run_tests(), exit_code=0, step=4)
        self.assertEqual(policy.gate(self.submit(), state, 5), "")

    def test_a_run_that_never_ran_its_tests_is_not_accused_of_a_red_tree(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.assertEqual(policy.gate(self.submit(), state, 2), "")

    def test_the_refusal_is_not_a_trap(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.run_tests(), exit_code=1, step=1)
        self.assertTrue(policy.gate(self.submit(), state, 2))
        self.assertEqual(policy.gate(self.submit(), state, 3), "")

    def test_the_red_tree_is_visible_in_the_record(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.run_tests(), exit_code=1, step=1)
        self.assertTrue(state.as_dict()["own_gate_red"])
        policy.gate(self.submit(), state, 2)
        self.assertIn("red tree", " ".join(str(r) for r in state.refusals))

    def test_a_task_can_turn_the_rule_off(self):
        policy = TDDPolicy("request", self.task, self.work, require_green=False)
        state = policy.new_state()
        self.apply(policy, state, self.run_tests(), exit_code=1, step=1)
        self.assertEqual(policy.gate(self.submit(), state, 2), "")


class SnapshotNoiseTests(TDDBase):
    """Running the tests must not look like editing the source.

    The test command imports the package under `src_globs`, so running it writes
    `__pycache__`. While pycache counted as source, the act of running the suite set
    `first_src_step` -- and a textbook red-first run (test at 8, red at 9, fix at 10)
    was reported as "red-after-code". Three batch arms were misreported that way, and
    this is the one number in the project that must never be wrong.
    """

    def noise(self, text: str = "noise") -> Path:
        """What a test run leaves behind when it imports the source."""
        d = self.work / "src" / "__pycache__"
        d.mkdir(parents=True, exist_ok=True)
        path = d / "thing.cpython-313.pyc"
        path.write_bytes(text.encode())
        return path

    def test_a_pycache_write_is_not_a_source_change(self):
        before = snapshot(self.work, self.task.src_globs)
        self.noise()
        self.assertEqual(snapshot(self.work, self.task.src_globs), before)

    def test_running_the_tests_does_not_set_first_src_step(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.noise()  # the test run imported the package
        policy.observe_tree(state, 2)
        self.assertIsNone(state.first_src_step)

    def test_pycache_churn_is_not_a_bypass(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.noise("first")
        policy.observe_tree(state, 1)
        self.noise("second")
        policy.observe_tree(state, 2)
        self.assertEqual(state.bypass_detected, [])

    def test_a_real_source_edit_is_still_a_change(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        (self.work / "src" / "thing.py").write_text("value = 1\n")
        policy.observe_tree(state, 4)
        self.assertEqual(state.first_src_step, 4)

    def test_a_red_run_before_the_fix_still_reads_as_red_first(self):
        # The end-to-end shape of the three misreported arms.
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=8)
        self.noise()
        self.apply(policy, state, self.run_tests(), exit_code=1, step=9)
        policy.observe_tree(state, 9)
        (self.work / "src" / "thing.py").write_text("value = 1\n")
        policy.observe_tree(state, 10)
        self.assertEqual(state.first_src_step, 10)
        self.assertEqual(state.verdict(), "red-first")


class VerdictTests(TDDBase):
    def test_no_tests_at_all(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.assertEqual(state.verdict(), "no-tests")

    def test_tests_but_never_seen_to_fail(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"))
        self.apply(policy, state, self.run_tests(), exit_code=0)
        self.assertEqual(state.verdict(), "no-red")

    def test_red_before_the_implementation(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=1)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=2)
        self.apply(policy, state, self.write("src/thing.py"), step=3)
        self.assertEqual(state.verdict(), "red-first")
        self.assertTrue(state.red_before_code)

    def test_red_only_after_the_implementation(self):
        policy = self.policy_for("request")
        state = policy.new_state()
        self.apply(policy, state, self.write("src/thing.py"), step=1)
        self.apply(policy, state, self.write("tests/own/test_thing.py"), step=2)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=3)
        self.assertEqual(state.verdict(), "red-after-code")
        self.assertFalse(state.red_before_code)

    def test_the_verdict_travels_in_the_state_dict(self):
        policy = self.policy_for("enforce")
        payload = policy.new_state().as_dict()
        self.assertEqual(payload["verdict"], "no-tests")
        self.assertEqual(payload["mode"], "enforce")


if __name__ == "__main__":
    unittest.main()
