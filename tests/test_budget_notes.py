"""Telling the model about its own budget, and about its own silence.

Two live repository runs spent their whole budget reading -- 40 of 40 steps and 30 of 30, zero writes,
zero tests -- against a brief whose own text ordered the reading ("Read these before writing anything …
re-check every name"). Nothing in the loop told them the budget existed. These notes are the
told-not-blocked axis: they intervene when a budget is being spent, not when a rule is broken.
"""

import unittest

from ninny.tdd import TDDState, budget_note


class TheModelIsToldBeforeItDiesSilently(unittest.TestCase):
    def state(self) -> TDDState:
        return TDDState(mode="enforce")

    def notice(self, step_limit: int, step: int, state: TDDState | None = None) -> tuple[str, str]:
        """The note at this point, asserted to exist -- so a test that expects one reads cleanly
        and a missing one fails here rather than three lines later."""
        found = budget_note(step_limit, state if state is not None else self.state(), step)
        assert found is not None, f"expected a note at step {step} of {step_limit}"
        return found

    def test_nothing_is_said_early(self):
        self.assertIsNone(budget_note(40, self.state(), 3))

    def test_silence_at_the_halfway_point_when_nothing_has_been_written(self):
        kind, text = self.notice(40, 21)
        self.assertEqual(kind, "silence")
        self.assertIn("written nothing", text)

    def test_a_write_silences_the_silence_note(self):
        """A model that is working -- even on a test file -- is not nagged."""
        state = self.state()
        state.write_steps.append([4, "tests/own/test_x.py"])
        self.assertIsNone(budget_note(40, state, 21))

    def test_each_note_is_said_once(self):
        state = self.state()
        kind, _ = self.notice(40, 21, state)
        state.told.append([21, kind])
        self.assertIsNone(budget_note(40, state, 22))

    def test_the_budget_note_arrives_near_the_end(self):
        state = self.state()
        state.write_steps.append([2, "src/protekt/sim/spec.hpp"])  # it has been working, so the
        self.assertIsNone(budget_note(40, state, 30))              # silence note is not in play
        kind, text = self.notice(40, 37, state)
        self.assertEqual(kind, "verify")
        self.assertIn("steps remain", text)

    def test_both_notes_can_arrive_in_one_run(self):
        state = self.state()
        kind, _ = self.notice(40, 21, state)
        state.told.append([21, kind])
        self.assertEqual(self.notice(40, 38, state)[0], "verify")

    def test_a_short_budget_still_gets_both_notes(self):
        """A 10-step run must not be so short that neither note can fire."""
        state = self.state()
        kind, _ = self.notice(10, 6, state)
        self.assertEqual(kind, "silence")
        state.told.append([6, kind])
        self.assertEqual(self.notice(10, 9, state)[0], "verify")


if __name__ == "__main__":
    unittest.main()
