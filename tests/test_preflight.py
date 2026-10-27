"""What the caller is shown before the model spends anything.

Two repository runs died reading a brief that named ten files against a 40-step budget, and the question
afterwards was "why did it read for forty steps". The preflight is that answer, printed before the first
model call: counts and comparisons, never a judgement about whether the task is well-posed.
"""

import argparse
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from ninny.cli import preflight_lines
from ninny.config import repo_task


def args_for(**over) -> argparse.Namespace:
    base = dict(steps=40, timeout=None, tdd="request", test_glob=["tests/*"], repo="/tmp/repo")
    base.update(over)
    return argparse.Namespace(**base)


class ThePreflightStatesWhatIsAboutToBeSpent(unittest.TestCase):
    def setUp(self):
        # repo_task refuses a path that is not a git repository (--repo stages a worktree of it), so
        # the fixture is one, with one commit.
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        (self.dir / "tests").mkdir()
        (self.dir / "tests" / "test_sim.cpp").write_text("// a test\n")
        for cmd in (["git", "init", "-q", str(self.dir)],
                    ["git", "-C", str(self.dir), "add", "-A"],
                    ["git", "-C", str(self.dir), "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "fixture"]):
            subprocess.run(cmd, check=True, capture_output=True)
        self.task = repo_task(self.dir, "do a thing", test_cmd="bash tools/ci.sh fast",
                              test_timeout_s=600)

    def test_it_counts_the_tree_and_the_shell_budget(self):
        lines, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp", args_for())
        joined = "\n".join(lines)
        self.assertEqual(refusal, "")
        # Two translation units, because the test source is one too -- the count is of the tree, not
        # of the shipping code.
        self.assertIn("2 translation units", joined)
        self.assertIn("1 test sources", joined)
        self.assertIn("budget 40 steps", joined)
        self.assertIn("600s", joined)

    def test_it_says_which_of_the_named_paths_exist(self):
        lines, _ = preflight_lines(self.task, self.dir, "edit src/sim.cpp and src/gone.cpp", args_for())
        joined = "\n".join(lines)
        self.assertIn("names 2 paths; 1 exist", joined)
        self.assertIn("gone.cpp", joined)

    def test_a_brief_with_no_reachable_entry_point_is_called_out(self):
        lines, _ = preflight_lines(self.task, self.dir, "edit src/absent.cpp", args_for())
        self.assertTrue(any("no entry point" in line for line in lines))

    def test_a_brief_naming_no_path_at_all_is_called_out(self):
        lines, _ = preflight_lines(self.task, self.dir, "make the tanks shoot better", args_for())
        self.assertTrue(any("names no file path at all" in line for line in lines))

    def test_enforce_without_a_test_glob_is_refused(self):
        _, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp",
                                     args_for(tdd="enforce", test_glob=[]))
        self.assertIn("REFUSING", refusal)
        self.assertIn("--test-glob", refusal)

    def test_enforce_with_a_glob_is_allowed(self):
        _, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp",
                                     args_for(tdd="enforce", test_glob=["tests/*"]))
        self.assertEqual(refusal, "")


class ThePreflightStatesHowLongTheSuiteTakes(unittest.TestCase):
    """The timeout says what the suite may spend; only a measurement says what it spends.

    Two repository runs read for their whole budget against a 121 s suite, and no line ever said
    "121 s". The duration belongs on the same line as the timeout, measured in the run's own
    working tree, through the same shell a bash action uses -- and a suite that cannot run at all
    must be reported there rather than raising, because a preflight is never the reason a run dies.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        for cmd in (["git", "init", "-q", str(self.dir)],
                    ["git", "-C", str(self.dir), "add", "-A"],
                    ["git", "-C", str(self.dir), "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "fixture"]):
            subprocess.run(cmd, check=True, capture_output=True)

    def test_the_measured_duration_appears_on_the_suite_line(self):
        # A real command in a real tree: it sleeps long enough to be timed and leaves a file
        # behind, so a measurement of the WRONG tree is visible too.
        task = repo_task(self.dir, "do a thing",
                         test_cmd='sleep 0.3; echo measured >> marker.txt', test_timeout_s=600)
        started = time.monotonic()
        lines, refusal = preflight_lines(task, self.dir, "edit src/sim.cpp", args_for())
        elapsed = time.monotonic() - started
        self.assertEqual(refusal, "")
        suite_lines = [line for line in lines if "single bash action" in line]
        self.assertTrue(suite_lines, f"no suite line in {lines!r}")
        line = suite_lines[0]
        measured = re.search(r"took (\d+(?:\.\d+)?)s", line)
        self.assertIsNotNone(measured, f"no measured duration on {line!r}")
        self.assertGreaterEqual(float(measured.group(1)), 0.3, line)
        self.assertGreaterEqual(elapsed, 0.3, "the preflight did not actually run the suite")
        self.assertIn("600s", line)
        self.assertTrue((self.dir / "marker.txt").exists(),
                        "the suite did not run in the working tree it was measured for")

    def test_a_suite_that_cannot_run_is_reported_not_raised(self):
        task = repo_task(self.dir, "do a thing", test_cmd="bash tools/absent.sh",
                         test_timeout_s=600)
        lines, refusal = preflight_lines(task, self.dir, "edit src/sim.cpp", args_for())
        self.assertEqual(refusal, "")
        suite_lines = [line for line in lines if "single bash action" in line]
        self.assertTrue(suite_lines, f"no suite line in {lines!r}")
        line = suite_lines[0]
        self.assertNotIn("took", line)
        self.assertIn("could not run", line.lower())


if __name__ == "__main__":
    unittest.main()
