"""The observation gap: was the suite ever run against the code being handed back?

`red-first` describes the ORDER of the writes. It says nothing about whether the suite was
observed after the code it is supposed to describe, and a run can go red at step 8, write for
twenty more steps, and hand back a tree nobody has run since.

Three live `bits` arms did exactly that, with implementations the acceptance corpus passed.
One RED early made `own_gate_red` true for the rest of the run, so the record said "the suite
is failing" when the truth was "nobody has looked since step 8". These tests pin the
distinction, and the fact that the harness now takes that observation itself.
"""

import unittest

from tests.test_tdd import TDDBase

TEST_FILE = "tests/own/test_thing.py"
SRC = "src/thing.py"


class StaleBase(TDDBase):
    def setUp(self):
        super().setUp()
        self.policy = self.policy_for("enforce")
        self.state = self.policy.new_state()

    def bank_a_red(self, step: int = 4) -> None:
        self.apply(self.policy, self.state, self.write(TEST_FILE), step=3)
        self.apply(self.policy, self.state, self.run_tests(), exit_code=1, step=step)

    def write_src(self, step: int) -> None:
        self.apply(self.policy, self.state, self.write(SRC), step=step)

    def run_suite(self, step: int, exit_code: int) -> None:
        self.apply(self.policy, self.state, self.run_tests(), exit_code=exit_code, step=step)


class TheGapIsVisible(StaleBase):
    def test_nothing_observed_is_stale_and_not_green(self):
        self.assertTrue(self.state.suite_stale)
        self.assertIsNone(self.state.green_after_last_write)

    def test_a_run_after_the_write_is_fresh(self):
        self.write_src(3)
        self.run_suite(4, exit_code=0)
        self.assertFalse(self.state.suite_stale)
        self.assertIs(self.state.green_after_last_write, True)

    def test_a_write_after_the_run_makes_it_stale_again(self):
        self.write_src(3)
        self.run_suite(4, exit_code=0)
        self.write_src(5)
        self.assertTrue(self.state.suite_stale)
        self.assertIsNone(self.state.green_after_last_write)

    def test_a_fresh_red_run_is_not_green(self):
        self.bank_a_red()
        self.write_src(6)
        self.run_suite(7, exit_code=1)
        self.assertFalse(self.state.suite_stale)
        self.assertIs(self.state.green_after_last_write, False)

    def test_a_run_and_a_write_in_the_same_step_is_not_stale(self):
        # The order within one step is not recorded. Calling this stale would invent a fact
        # the record does not have, and would make every batched arm look unfinished.
        self.write_src(5)
        self.run_suite(5, exit_code=0)
        self.assertFalse(self.state.suite_stale)

    def test_a_source_change_the_log_cannot_see_still_makes_it_stale(self):
        # The tree is the ground truth: a shell heredoc is a source change too.
        self.write_src(3)
        self.run_suite(4, exit_code=0)
        (self.work / SRC).write_text("value = 99\n")
        self.policy.observe_tree(self.state, 5)
        self.assertTrue(self.state.suite_stale)

    def test_the_live_bits_shape(self):
        # bits arm 1: red at 6, red at 8, then twenty-one steps of implementation and a
        # submit. Nothing in the record could see that the suite was never run again.
        self.bank_a_red(step=6)
        self.run_suite(8, exit_code=1)
        for step in range(9, 30):
            self.write_src(step)
        self.assertTrue(self.state.suite_stale)
        self.assertIsNone(self.state.green_after_last_write)


class TheHarnessTakesItsOwnObservation(StaleBase):
    def test_the_harness_run_is_recorded_as_the_harness_s(self):
        self.bank_a_red()
        self.write_src(20)
        self.assertTrue(self.state.suite_stale)
        self.policy.note_harness_run(self.state, 21, 1)
        self.assertEqual(self.state.harness_runs, [[21, 1]])
        # It lands in test_runs as well: every later question -- is it green, is it stale --
        # is about the most recent observation, whoever took it.
        self.assertEqual(self.state.test_runs[-1], [21, 1])
        self.assertFalse(self.state.suite_stale)

    def test_the_handback_fact_survives_a_green_harness_run(self):
        # The arm still handed back a tree it had not run. That is worth recording even when
        # the harness finds it green, because the model did not know that.
        self.write_src(3)
        self.policy.note_harness_run(self.state, 4, 0)
        self.assertTrue(self.state.suite_stale_at_submit)
        self.assertIs(self.state.green_after_last_write, True)

    def test_the_record_carries_the_gap(self):
        self.bank_a_red()
        self.write_src(20)
        self.policy.note_harness_run(self.state, 21, 1)
        record = self.state.as_dict()
        self.assertEqual(record["last_run_step"], 21)
        self.assertEqual(record["last_src_step"], 20)
        self.assertTrue(record["suite_stale_at_submit"])
        self.assertEqual(record["harness_runs"], [[21, 1]])
        self.assertIs(record["green_after_last_write"], False)

    def test_a_red_with_nothing_written_after_it_is_a_seen_failure(self):
        # Not an absence of observation: the suite was seen failing against exactly this
        # tree, and nothing has changed since. None is reserved for the case where the code
        # moved on after the last look -- which is the case that was invisible.
        self.bank_a_red()
        self.assertIs(self.state.as_dict()["green_after_last_write"], False)


if __name__ == "__main__":
    unittest.main()
