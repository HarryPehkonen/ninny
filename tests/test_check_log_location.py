"""Where the oracle log lands, and why it matters.

The staging directory is where the oracle runs, and it is under TMPDIR. Writing the log only
there made "every run leaves an oracle log" false: a graded arm in runs/<subject>/<arm>/ held a
diff, a record and its tree, and the evidence for its verdict sat in a scratch directory that
prunes idle entries. A control that grades an arm has to outlive the machine's cleaning schedule.

A found case, not a designed one: a delegate read this repository's own documentation, ran a
benchmark arm, went looking for the promised oracle.log and reported that it was not there.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.cli import _live_oracle_log


class TheLogOutlivesTheStagingDirectory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.work = self.root / "staging"
        self.work.mkdir()
        (self.work / "oracle.log").write_text("the oracle ran here")

    def _tree(self, name: str, in_a_run: bool) -> Path:
        arm = self.root / name
        (arm / "tree").mkdir(parents=True)
        if in_a_run:
            (arm / "result.json").write_text("{}")
        return arm / "tree"

    def test_a_tree_inside_a_run_directory_gets_the_log_beside_it(self):
        tree = self._tree("runs/roman/arm1", in_a_run=True)
        where = _live_oracle_log(tree, self.work, "ACCEPTANCE: 9 checked, 0 failed")

        self.assertEqual(where, tree.parent / "oracle.log")
        self.assertEqual(where.read_text(), "ACCEPTANCE: 9 checked, 0 failed")
        self.assertTrue(where.is_file())

    def test_a_tree_nowhere_near_a_run_keeps_the_staging_path(self):
        tree = self._tree("somewhere/fixed", in_a_run=False)
        where = _live_oracle_log(tree, self.work, "nothing to keep")

        self.assertEqual(where, self.work / "oracle.log")
        self.assertFalse((tree.parent / "oracle.log").exists())

    def test_a_read_only_run_directory_falls_back_rather_than_losing_the_output(self):
        tree = self._tree("runs/roman/arm2", in_a_run=True)
        arm = tree.parent
        arm.chmod(0o500)  # a run directory nobody can write to
        self.addCleanup(arm.chmod, 0o700)

        where = _live_oracle_log(tree, self.work, "still not lost")

        self.assertEqual(where, self.work / "oracle.log")
        self.assertTrue((self.work / "oracle.log").is_file())


if __name__ == "__main__":
    unittest.main()
