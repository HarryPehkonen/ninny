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
from ninny.tdd import MODES, TDDPolicy


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
