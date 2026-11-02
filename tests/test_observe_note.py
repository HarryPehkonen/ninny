"""The note a run gets at half its budget when it has written but never observed anything.

harrisbook post 37: a repository run wrote nine files across 40 steps, never ran its acceptance command
at all (`tdd.test_runs == []`), and was told to verify at step 35 of 40 -- five steps from the cliff,
being asked to run a command it had never run. Being told to go and get ground truth when you can no
longer act on it is not a recoverable instruction, which is the whole of the defect.

The silence note already fires at half the budget when nothing has been WRITTEN. This is its mirror:
something written, nothing ever OBSERVED. The two cannot both speak, because one requires `write_steps`
to be empty and the other requires it not to be.
"""

import unittest

from ninny.tdd import TDDState, budget_note


def state(writes=(), runs=(), told=()):
    st = TDDState(mode="request")
    st.write_steps = [list(w) for w in writes]
    st.test_runs = [list(r) for r in runs]
    st.told = [list(t) for t in told]
    return st


class TheNoteAtHalfTheBudget(unittest.TestCase):
    def test_a_run_that_wrote_but_never_observed_is_told_at_halfway(self):
        note = budget_note(40, state(writes=[[12, "tools/route.py"]]), 21)
        self.assertIsNotNone(note)
        self.assertEqual(note[0], "verify")
        self.assertIn("acceptance", note[1])

    def test_a_run_that_has_observed_something_is_left_alone(self):
        note = budget_note(40, state(writes=[[12, "a.py"]], runs=[[15, 1]]), 20)
        self.assertTrue(note is None or note[0] != "verify", f"got {note!r}")

    def test_it_is_said_once(self):
        st = state(writes=[[12, "a.py"]], told=[[20, "verify"]])
        note = budget_note(40, st, 21)
        self.assertTrue(note is None or note[0] != "verify", f"got {note!r}")

    def test_it_does_not_speak_before_halfway(self):
        note = budget_note(40, state(writes=[[12, "a.py"]]), 10)
        self.assertTrue(note is None or note[0] != "verify", f"got {note!r}")

    def test_a_run_that_has_written_nothing_still_gets_silence(self):
        # The mirror image, unchanged: nothing written at halfway is its own note.
        self.assertEqual(budget_note(40, state(), 21)[0], "silence")


if __name__ == "__main__":
    unittest.main()
