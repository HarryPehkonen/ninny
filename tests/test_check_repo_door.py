"""`check` on the repository door: independent validation of a repository's artifact.

harrisbook post 35, finding 1: a repository run printed "next, BY HAND: ninny check --task <repo>
--tree <tree>", and running exactly that gives `ninny: no task.toml in <repo>`. One of the three was
wrong -- the hint, the documented line that "verdict and check both work on either door", or check
itself. The hint was wrong AND check could not do the job: in repository mode nothing independently
validates the artifact at all, because `verdict` grades the handback and the only acceptance evidence
was what the harness recorded about itself.

So the door exists: `check --repo <path> --test-cmd <cmd> --tree <tree>` re-runs the declared command
in the tree the arm left behind and reports it in the same exit-code contract as everything else.
Exit 2, 126 and 127 stay "nothing was observed" -- never a failing test.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_check(tree: Path, test_cmd: str):
    return subprocess.run(
        ["python3", "-m", "ninny", "check", "--repo", str(REPO), "--test-cmd", test_cmd,
         "--tree", str(tree)],
        cwd=str(REPO), capture_output=True, text=True)


class TheRepositoryDoor(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "a.txt").write_text("hi\n")

    def test_a_passing_command_is_a_pass(self):
        done = run_check(self.dir, "echo 3 checks, 0 failed")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("GATE PASSED", done.stdout)

    def test_a_failing_command_is_a_failure(self):
        done = run_check(self.dir, "exit 1")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)

    def test_a_command_that_never_started_is_never_a_red(self):
        done = run_check(self.dir, "definitely-not-a-real-command-xyz")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("NOTHING OBSERVED", done.stdout)

    def test_the_command_runs_in_the_tree_it_was_given(self):
        done = run_check(self.dir, "test -f a.txt")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
