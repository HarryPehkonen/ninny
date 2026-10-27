"""A run that wrote nothing is not a run that skipped the test.

The record's first word was `no-tests` for both. In a benchmark that word means "you wrote no test
file" -- it presumes the run entered the test-first loop and skipped a step. A run that wrote
nothing never entered it, so `refusals=0` and `bypasses=0` are true of it and say nothing about
compliance.

Hit for real 2026-10-27: `protekt-shotgun-1` spent 40 steps and 706 seconds reading a 123-TU C++
repository, wrote nothing, and its summary read `refusals=0, bypasses=0` beside a verdict of
`no-tests`. Nothing in the record was false; the vocabulary simply had no word for it.
"""

import unittest

from ninny.agent import RunResult
from ninny.tdd import TDDState


class TheFirstWordSaysWhetherAnythingHappened(unittest.TestCase):
    def test_a_run_that_wrote_nothing_is_reported_no_write(self):
        state = TDDState(mode="enforce")
        self.assertTrue(state.wrote_nothing)
        self.assertEqual(state.verdict(), "no-write")
        self.assertNotEqual(state.verdict(), "no-tests")

    def test_writing_a_test_file_moves_it_on_to_no_red(self):
        """The boundary. One write reached the tree, so the gate's phase was entered and
        `no-tests` -- nothing written that the globs call a test -- is the honest word. The
        two states only stopped sharing a word with this change."""
        state = TDDState(mode="enforce")
        state.write_steps.append([3, "tests/own/test_x.py"])
        state.test_files.append("tests/own/test_x.py")
        state.first_test_step = 3
        self.assertFalse(state.wrote_nothing)
        self.assertEqual(state.verdict(), "no-red")

    def test_the_summary_prints_the_write_count_beside_the_word(self):
        result = RunResult(exit_status="StepLimit", steps=40, api_calls=40)
        result.tdd = {"mode": "enforce", "verdict": "no-write", "write_steps": [],
                      "refusals": [], "bypass_detected": []}
        line = result.summary()
        self.assertIn("test-first: no-write", line)
        self.assertIn("writes=0", line)

    def test_a_run_that_wrote_once_prints_one(self):
        result = RunResult(exit_status="Submitted", steps=7, api_calls=7)
        result.tdd = {"mode": "enforce", "verdict": "red-first", "write_steps": [[2, "a.py"]],
                      "refusals": [], "bypass_detected": []}
        self.assertIn("writes=1", result.summary())


if __name__ == "__main__":
    unittest.main()
