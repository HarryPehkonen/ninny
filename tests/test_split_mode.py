"""The two-round protocol: round 1 is the tests, round 2 is the implementation.

`enforce` guarantees the ORDER of the writes. `split` guarantees the ARTIFACT: from the moment
a red is banked the suite is sealed, so the tests handed back have to be the tests that failed.
These tests pin the boundary, the one door through it, and the invariant that keeps the mode
vocabulary and the prompt from drifting apart.
"""

import unittest

from ninny.prompt import TDD_BLOCKS
from ninny.tdd import MODES, TDDPolicy
from tests.test_tdd import TDDBase

TEST_FILE = "tests/own/test_thing.py"
SRC_FILE = "src/thing.py"


class SplitBase(TDDBase):
    def setUp(self):
        super().setUp()
        self.policy = self.policy_for("split")
        self.state = self.policy.new_state()

    def on_disk(self, path: str, content: str = "x") -> None:
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def allow_at(self, step: int, action) -> bool:
        return self.policy.gate(action, self.state, step) == ""

    def bank_a_red(self, step: int = 4) -> None:
        self.on_disk(TEST_FILE, "assert False\n")
        self.apply(self.policy, self.state, self.write(TEST_FILE, "assert False\n"), step=3)
        self.apply(self.policy, self.state, self.run_tests(), exit_code=1, step=step)

    def run_suite(self, exit_code: int, step: int) -> None:
        self.apply(self.policy, self.state, self.run_tests(), exit_code=exit_code, step=step)


class RoundOne(SplitBase):
    def test_a_test_file_may_be_written(self):
        self.assertTrue(self.allow_at(1, self.write(TEST_FILE)))

    def test_the_source_is_refused(self):
        self.assertFalse(self.allow_at(1, self.write(SRC_FILE)))
        self.assertEqual(self.state.refusals[-1][1], SRC_FILE)

    def test_the_starting_phase_is_the_test_round(self):
        self.assertEqual(self.state.phase, "test")


class RoundTwo(SplitBase):
    def test_the_source_is_allowed_once_the_red_is_banked(self):
        self.bank_a_red()
        self.assertTrue(self.allow_at(5, self.write(SRC_FILE, "value = 1\n")))

    def test_the_red_moves_the_run_into_the_implementation_phase(self):
        self.bank_a_red()
        self.assertEqual(self.state.phase, "impl")

    def test_the_suite_is_sealed_once_the_red_is_banked(self):
        self.bank_a_red()
        self.assertFalse(self.allow_at(5, self.write(TEST_FILE, "assert True\n")))
        self.assertEqual(self.state.refusals[-1][1], f"sealed: {TEST_FILE}")

    def test_the_refusal_explains_the_seal_and_the_door(self):
        self.bank_a_red()
        message = self.policy.gate(self.write(TEST_FILE), self.state, 5)
        self.assertIn("sealed", message)
        self.assertIn("exit 2", message)
        self.assertIn("closed", message)


class TheOneDoor(SplitBase):
    def test_a_suite_that_cannot_run_may_be_edited(self):
        self.bank_a_red()
        self.run_suite(2, step=5)              # exit 2: nothing ran
        self.assertTrue(self.allow_at(6, self.write(TEST_FILE, "assert False\n")))

    def test_the_unlock_is_recorded(self):
        self.bank_a_red()
        self.run_suite(2, step=5)
        self.allow_at(6, self.write(TEST_FILE, "assert False\n"))
        self.assertEqual(self.state.seal_unlocks, [[6, TEST_FILE]],
                         "a frozen suite means less if the door was opened, so the door is recorded")

    def test_a_suite_that_ran_and_FAILED_is_closed(self):
        self.bank_a_red()
        self.run_suite(1, step=5)
        self.assertFalse(self.allow_at(6, self.write(TEST_FILE, "assert True\n")))
        self.assertEqual(self.state.seal_unlocks, [])


class TheSuiteTheShippedIsTheSuiteThatWentRed(SplitBase):
    def test_a_run_that_leaves_the_suite_alone_is_frozen(self):
        self.bank_a_red()
        self.policy.close_seal(self.state)
        self.assertTrue(self.state.suite_frozen_since_red)

    def test_a_suite_rewritten_through_the_shell_is_still_caught(self):
        # The gate only sees write_file; a heredoc goes around it. The seal is read from bytes,
        # so it does not matter how the change arrived -- which is why the refusal is not the
        # whole guarantee.
        self.bank_a_red()
        self.on_disk(TEST_FILE, "assert True\n")
        self.policy.close_seal(self.state)
        self.assertFalse(self.state.suite_frozen_since_red)
        self.assertEqual(self.state.suite_changed_after_red, [TEST_FILE])

    def test_the_verdict_still_reads_red_first(self):
        self.bank_a_red()
        self.on_disk(SRC_FILE, "value = 1\n")
        self.apply(self.policy, self.state, self.write(SRC_FILE, "value = 1\n"), step=5)
        self.on_disk(TEST_FILE, "assert True\n")
        self.policy.close_seal(self.state)
        self.assertEqual(self.state.verdict(), "red-first")
        self.assertFalse(self.state.suite_frozen_since_red,
                         "red-first is about the order and stays true; the seal is the other claim")


class TheModeVocabularyHoldsTogether(unittest.TestCase):
    def test_split_is_a_mode(self):
        self.assertIn("split", MODES)

    def test_every_mode_tells_the_model_what_it_is(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertIn(mode, TDD_BLOCKS,
                              f"mode {mode!r} has no prompt block: the model would be told nothing")

    def test_the_split_block_promises_the_seal(self):
        self.assertIn("sealed", TDD_BLOCKS["split"])
        self.assertIn("exit 2", TDD_BLOCKS["split"])


if __name__ == "__main__":
    unittest.main()
