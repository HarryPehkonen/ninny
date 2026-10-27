"""A slow suite must not look like a suite nobody ran.

`Environment` defaults the per-bash-action timeout to 120 s and `cli.py` passed it through
untouched, while passing the *test* timeout separately. On a repository whose gate is slower than
120 s -- PROTEKT's `tools/ci.sh fast` is 121 s -- a delegate that runs the suite through bash (which
is how both live repository runs ran it, rather than through `run_tests`) gets a silent kill at the
worst possible moment, and the record afterwards says only that no test was observed.
"""

import unittest

from ninny.config import bash_timeout_for


class TheShellTimeoutNeverUndercutsTheSuite(unittest.TestCase):
    def test_a_slow_declared_suite_raises_the_floor(self):
        self.assertEqual(bash_timeout_for(600), 600)

    def test_a_fast_declared_suite_leaves_the_default_alone(self):
        """A benchmark declares 120 s and gets 120 s -- nothing changes for the corpus."""
        self.assertEqual(bash_timeout_for(120), 120)
        self.assertEqual(bash_timeout_for(0), 120)

    def test_an_explicit_timeout_wins(self):
        """A caller who names a number means it, even a small one."""
        self.assertEqual(bash_timeout_for(600, explicit=30), 30)
        self.assertEqual(bash_timeout_for(120, explicit=400), 400)


if __name__ == "__main__":
    unittest.main()
