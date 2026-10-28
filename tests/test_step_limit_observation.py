"""The observation at the step limit, and the note that comes just before it.

Post 33 on harrisbook.ca: an arm on a 126-translation-unit repository spent 40 of 40 steps, wrote 15
files, never ran the acceptance command once, and left a tree that did not compile -- a deleted
`struct Coord {` and a call site the signature change had not reached. `ninny verdict` could say only
`no-handback`. The record could not say WHY: whether the tree built, whether the suite ran, or what
either answered.

So the handback rule is applied at the other exit. Ninny already runs the suite itself when a
handback is stale; at `StepLimit` it now runs the task's declared cheap check and its acceptance
command in the tree the arm left behind, and the record carries both exit codes and how long each
took. Observation only: the run is over, no model behaviour changes, no tokens are spent.

And the model is TOLD, once, at the mark post 33 asked for -- nearly out of steps with nothing green.
No rule is broken when a model writes a seventh file without compiling; a budget is being spent,
which is the same ground the other two notes stand on.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.tdd import TDDState, budget_note
from ninny.tdd import run_at_limit


def state_after(test_runs, told=None):
    """A state that has been through a few suite runs, and maybe a note or two."""
    st = TDDState(mode="enforce")
    st.test_runs = list(test_runs)
    st.write_steps = [5]  # a run that WROTE; otherwise the silence note fires first and wins
    st.told = list(told or [])
    return st


class TheNoteBeforeTheLimit(unittest.TestCase):
    """Told, not blocked -- and only when the fact is new."""

    def test_nearly_out_of_steps_with_nothing_green_says_what_to_do(self):
        note = budget_note(60, state_after([[9, 1]]), 55)

        assert note is not None, "a run with a red and no green must be told something"
        kind, text = note
        self.assertEqual(kind, "verify")
        self.assertIn("acceptance", text.lower())

    def test_a_green_suite_means_the_verification_note_is_not_needed(self):
        note = budget_note(60, state_after([[9, 1], [31, 0]]), 55)

        # Not "no note": the generic end-of-budget warning still applies, and should. What must not
        # happen is being told to verify a tree that has already been verified.
        self.assertTrue(note is None or note[0] == "budget", f"got {note!r}")

    def test_a_verification_note_is_said_once(self):
        note = budget_note(60, state_after([[9, 1]]), 55)
        assert note is not None
        said = state_after([[9, 1]], told=[[55, note[0]]])

        self.assertIsNone(budget_note(60, said, 56))

    def test_only_one_of_the_end_of_run_notes_fires_at_that_mark(self):
        """The two stand on the same step, so a run cannot be lectured twice in a row."""
        note = budget_note(60, state_after([[9, 1]]), 55)

        assert note is not None
        self.assertEqual(note[0], "verify", "the specific note wins over the generic warning")
        self.assertIsNone(budget_note(60, state_after([[9, 1]], told=[[55, "verify"]]), 56),
                          "and once it is said, the generic one does not follow it")

    def test_step_limits_that_are_nowhere_near_the_end_say_nothing(self):
        self.assertIsNone(budget_note(60, state_after([[3, 1]]), 10))


class TheRecordKeepsWhatWasObserved(unittest.TestCase):
    def test_a_limit_run_lands_in_the_record_with_its_duration(self):
        st = TDDState(mode="enforce")
        st.record_limit_run(step=40, kind="check", exit_code=2, seconds=4.25)

        self.assertEqual(st.as_dict()["limit_runs"], [[40, "check", 2, 4.2]])

    def test_a_finished_run_with_no_limit_runs_says_so_with_an_empty_list(self):
        self.assertEqual(TDDState(mode="enforce").as_dict()["limit_runs"], [])


class WhatGetsRunAtTheLimit(unittest.TestCase):
    """The cheap check first, then the acceptance command -- both by declaration."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def test_the_check_and_the_suite_are_each_run_and_measured(self):
        runs = run_at_limit(check_cmd="true", suite_cmd="true", workdir=self.work, timeout_s=30)

        self.assertEqual([r[1] for r in runs], ["check", "suite"])
        self.assertEqual([r[2] for r in runs], [0, 0])
        self.assertTrue(all(r[3] >= 0 for r in runs))

    def test_a_failing_check_is_recorded_as_the_red_it_is(self):
        runs = run_at_limit(check_cmd="false", suite_cmd="true", workdir=self.work, timeout_s=30)

        self.assertEqual(runs[0][1:3], ["check", 1], "a check that ran and failed is exit 1")

    def test_a_check_that_never_ran_is_not_a_red(self):
        runs = run_at_limit(check_cmd="no-such-tool-anywhere",
                             suite_cmd="true", workdir=self.work, timeout_s=30)

        self.assertEqual(runs[0][1:3], ["check", 127],
                         "the shell's not-found code means nothing was observed")

    def test_no_declared_check_means_only_the_suite_runs(self):
        runs = run_at_limit(check_cmd=None, suite_cmd="true", workdir=self.work, timeout_s=30)

        self.assertEqual([r[1] for r in runs], ["suite"])

    def test_the_commands_run_in_the_tree_the_arm_left_behind(self):
        marker = self.work / "ran-here"
        run_at_limit(check_cmd=f"touch {marker}", suite_cmd="true",
                      workdir=self.work, timeout_s=30)

        self.assertTrue(marker.is_file())


if __name__ == "__main__":
    unittest.main()
