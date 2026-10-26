"""Round two is said at the moment it becomes true.

The two-round protocol used to be one long paragraph in the preamble: the seal, the rule about
handing back a suite nobody ran, and the report-a-wrong-test case -- all read before the model
knew what any of them referred to. Now the preamble says what round one is, and the harness says
what round two is, at the red, when every sentence of it is true.

These tests pin both halves: the block stays short, and the text that left it arrives where it
belongs.
"""

import unittest

from ninny.prompt import TDD_BLOCKS, render_instance
from tests.test_tdd import TDDBase, observation

TEST_FILE = "tests/own/test_thing.py"


class ThePreambleIsShort(TDDBase):
    def test_the_split_block_fits_in_a_dozen_lines(self):
        body = TDD_BLOCKS["split"]
        self.assertLessEqual(
            len(body.splitlines()), 12, "the block grew back: move the new text to round two"
        )

    def test_the_block_keeps_the_promise_and_drops_the_mechanics(self):
        body = TDD_BLOCKS["split"]
        self.assertIn("sealed", body)
        self.assertIn("no write path left", body)
        # The elaboration moved to where it applies.
        self.assertNotIn("read-only in the shell", body)

    def test_the_rendered_testing_section_is_shorter_than_the_old_one(self):
        # The old section rendered at 29 lines; the pre-registered target was about fourteen.
        text = render_instance(self.task, str(self.work), "split", "sandbox note")
        section = text[text.index("## Testing"):text.index("## Working rules")]
        self.assertLessEqual(len(section.splitlines()), 14)


class RoundTwoIsSaidAtTheRed(TDDBase):
    def setUp(self):
        super().setUp()
        self.policy = self.policy_for("split")
        self.state = self.policy.new_state()

    def bank_a_red(self, step: int = 4) -> None:
        self.apply(self.policy, self.state, self.write(TEST_FILE), step=3)
        self.apply(self.policy, self.state, self.run_tests(), exit_code=1, step=step)

    def the_note(self, policy=None, state=None) -> str:
        return (policy or self.policy).note_for(
            self.run_tests(), observation(1), state or self.state
        )

    def test_the_message_arrives_with_the_red(self):
        self.bank_a_red()
        note = self.the_note()
        self.assertIn("Red banked at step 4", note)
        self.assertIn("sealed", note)
        self.assertIn("final message", note)
        self.assertIn("never hand back a suite you have not run", note)

    def test_it_is_said_once(self):
        self.bank_a_red()
        self.assertIn("sealed from here", self.the_note())
        self.assertEqual(self.the_note(), "")

    def test_enforce_keeps_its_own_wording(self):
        # enforce has no two rounds: no seal gate, no round-two script.
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.apply(policy, state, self.write(TEST_FILE), step=3)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=4)
        note = self.the_note(policy, state)
        self.assertIn("Red banked at step 4", note)
        self.assertNotIn("sealed from here", note)


if __name__ == "__main__":
    unittest.main()
