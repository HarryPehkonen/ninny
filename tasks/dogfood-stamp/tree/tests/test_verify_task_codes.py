"""verify-task must not read "the oracle never ran" as "the oracle failed".

The control that matters is "the oracle is RED on the starting tree". RED means the oracle
RAN and said no. A missing interpreter, a typo'd script name or a 127 means it never ran at
all, and counting that as RED would verify a task whose oracle is broken -- the exact
illusory-green failure this harness exists to prevent.

The distinction is the same one the exit-code contract makes for a task's own suite:
    0   ran, passed
    1   ran, failed        <- a real RED
    2   could not run      <- nothing observed
    126 the command is not executable
    127 the command is not found
"""

import unittest
from pathlib import Path
from unittest import mock

from ninny import cli

# Codes that mean "the oracle ran and said no", against codes that mean "it never ran".
RAN_AND_FAILED = (1, 3, 8, 101)
NEVER_RAN = (2, 126, 127)


def _task(tmp: Path):
    """A task whose oracle is a script with a given exit status."""
    oracle = tmp / "oracle"
    oracle.mkdir(parents=True)
    return oracle


class OracleExitClassificationTests(unittest.TestCase):
    def test_a_failing_oracle_is_red(self):
        for code in RAN_AND_FAILED:
            with self.subTest(code=code):
                self.assertTrue(cli._oracle_said_no(code), f"exit {code} means the oracle ran and failed")

    def test_an_oracle_that_never_ran_is_not_red(self):
        for code in NEVER_RAN:
            with self.subTest(code=code):
                self.assertFalse(cli._oracle_said_no(code), f"exit {code} means nothing was observed")

    def test_the_verdict_names_why_a_run_never_happened(self):
        said = cli._oracle_exit_note(127)
        self.assertIn("127", said)
        self.assertIn("did not run", said.lower())

    def test_the_verdict_for_a_failure_is_plain(self):
        self.assertEqual("exit 1", cli._oracle_exit_note(1))


if __name__ == "__main__":
    unittest.main()
