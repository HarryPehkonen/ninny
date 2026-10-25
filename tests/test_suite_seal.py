"""The seal: was the suite handed back the suite that went red?

`red-first` says a red was observed before the first source write. It does not say the tests
that shipped are the tests that failed. A run can bank a real red and then rewrite the suite
that red came from -- the verdict stays `red-first`, and the artifact a reader assumes was
proven is not the artifact that was proven.

These tests pin the seal, including the case it exists for: a rewrite the action log never
saw, because the verdict is read from the tree rather than from the log.
"""

import unittest

from ninny.tdd import TDDPolicy
from tests.test_tdd import TDDBase

TEST_FILE = "tests/own/test_thing.py"


class SealBase(TDDBase):
    def setUp(self):
        super().setUp()
        self.policy = self.policy_for("enforce")
        self.state = self.policy.new_state()

    def on_disk(self, path: str, content: str) -> None:
        """Write the file for real: the seal reads bytes, not the action log."""
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def bank_a_red(self, step: int = 4) -> None:
        self.on_disk(TEST_FILE, "assert False\n")
        self.apply(self.policy, self.state, self.write(TEST_FILE, "assert False\n"), step=3)
        self.apply(self.policy, self.state, self.run_tests(), exit_code=1, step=step)

    def seal(self) -> None:
        self.policy.close_seal(self.state)


class TheSuiteIsSealedAtTheRed(SealBase):
    def test_a_suite_left_alone_is_frozen(self):
        self.bank_a_red()
        self.on_disk("src/thing.py", "value = 1\n")
        self.apply(self.policy, self.state, self.write("src/thing.py", "value = 1\n"), step=5)
        self.seal()
        self.assertTrue(self.state.suite_frozen_since_red)
        self.assertEqual(self.state.suite_changed_after_red, [])
        self.assertEqual(self.state.seal_step, 4)

    def test_a_suite_rewritten_after_the_red_is_not_frozen(self):
        self.bank_a_red()
        self.on_disk("src/thing.py", "value = 1\n")
        self.apply(self.policy, self.state, self.write("src/thing.py", "value = 1\n"), step=5)
        # The run passes the gate, then rewrites the very suite the red came from.
        self.on_disk(TEST_FILE, "assert True\n")
        self.apply(self.policy, self.state, self.write(TEST_FILE, "assert True\n"), step=6)
        self.seal()
        self.assertFalse(self.state.suite_frozen_since_red)
        self.assertEqual(self.state.suite_changed_after_red, [TEST_FILE])

    def test_the_verdict_is_still_red_first_when_the_suite_moved(self):
        # The point of the seal: `red-first` stays true. Without it the record has no way to
        # say the artifact and the claim came apart.
        self.bank_a_red()
        self.on_disk("src/thing.py", "value = 1\n")
        self.apply(self.policy, self.state, self.write("src/thing.py", "value = 1\n"), step=5)
        self.on_disk(TEST_FILE, "assert True\n")
        self.seal()
        self.assertEqual(self.state.verdict(), "red-first")
        self.assertFalse(self.state.suite_frozen_since_red)

    def test_a_rewrite_the_action_log_never_saw_still_counts(self):
        # Through a shell heredoc, sed, a script: the gate and the log see nothing. The tree
        # is the ground truth, which is why the seal is taken and read from bytes.
        self.bank_a_red()
        self.on_disk(TEST_FILE, "assert False or True\n")
        self.seal()
        self.assertFalse(self.state.suite_frozen_since_red)
        self.assertEqual(self.state.suite_changed_after_red, [TEST_FILE])

    def test_a_test_file_added_after_the_red_is_not_frozen(self):
        self.bank_a_red()
        self.on_disk("tests/own/test_more.py", "assert False\n")
        self.seal()
        self.assertFalse(self.state.suite_frozen_since_red)
        self.assertEqual(self.state.suite_changed_after_red, ["tests/own/test_more.py"])

    def test_a_test_file_deleted_after_the_red_is_not_frozen(self):
        self.bank_a_red()
        (self.work / TEST_FILE).unlink()
        self.seal()
        self.assertFalse(self.state.suite_frozen_since_red)
        self.assertEqual(self.state.suite_changed_after_red, [TEST_FILE])

    def test_editing_a_protected_file_is_not_a_suite_change(self):
        # tools/ is neither the suite nor the source. Only tests/own/** is sealed.
        self.bank_a_red()
        self.on_disk("tools/run.sh", "#!/bin/sh\nexit 1\n")
        self.seal()
        self.assertTrue(self.state.suite_frozen_since_red)


class ThereIsNothingToSealWithoutARed(SealBase):
    def test_no_red_means_no_claim(self):
        # Never ran the tests.
        self.seal()
        self.assertIsNone(self.state.suite_frozen_since_red,
                          "a run with no red must not report a suite guarantee it never earned")

    def test_a_suite_that_could_not_run_is_not_a_red_and_does_not_seal(self):
        # Exit 2 is the contract's "nothing ran". A C++ build error used to be banked here.
        self.on_disk(TEST_FILE, "assert False\n")
        self.apply(self.policy, self.state, self.write(TEST_FILE, "assert False\n"), step=3)
        self.apply(self.policy, self.state, self.run_tests(), exit_code=2, step=4)
        self.seal()
        self.assertIsNone(self.state.suite_frozen_since_red)

    def test_a_suite_that_passed_is_not_a_red_and_does_not_seal(self):
        self.on_disk(TEST_FILE, "assert True\n")
        self.apply(self.policy, self.state, self.write(TEST_FILE, "assert True\n"), step=3)
        self.apply(self.policy, self.state, self.run_tests(), exit_code=0, step=4)
        self.seal()
        self.assertIsNone(self.state.suite_frozen_since_red)


class TheSealIsInTheRecord(SealBase):
    def test_the_record_carries_the_seal(self):
        self.bank_a_red()
        self.on_disk(TEST_FILE, "assert True\n")
        self.seal()
        record = self.state.as_dict()
        self.assertFalse(record["suite_frozen_since_red"])
        self.assertEqual(record["suite_changed_after_red"], [TEST_FILE])
        self.assertEqual(record["seal_step"], 4)

    def test_the_record_says_nothing_when_there_is_nothing_to_seal(self):
        record = self.state.as_dict()
        self.assertIsNone(record["suite_frozen_since_red"])
        self.assertEqual(record["suite_changed_after_red"], [])


class TheSummaryLineSaysIt(SealBase):
    def test_the_printed_line_reports_the_seal(self):
        from ninny.agent import RunResult

        self.bank_a_red()
        self.seal()
        result = RunResult()
        result.tdd = self.state.as_dict()
        self.assertIn("suite_frozen=yes (sealed at step 4)", result.summary())

    def test_the_printed_line_names_the_files_when_the_suite_moved(self):
        from ninny.agent import RunResult

        self.bank_a_red()
        self.on_disk(TEST_FILE, "assert True\n")
        self.seal()
        result = RunResult()
        result.tdd = self.state.as_dict()
        line = result.summary()
        self.assertIn("suite_frozen=no (1 test file(s) changed after the red", line)
        self.assertIn(TEST_FILE, line)

    def test_the_printed_line_says_n_a_without_a_red(self):
        from ninny.agent import RunResult

        result = RunResult()
        result.tdd = self.state.as_dict()
        self.assertIn("suite_frozen=n/a (no red)", result.summary())


if __name__ == "__main__":
    unittest.main()
