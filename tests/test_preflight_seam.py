"""The seam between the CLI's argument names and the code that reads them.

`preflight_lines` was tested in isolation and passed while `ninny run --repo` was broken: it read
`args.test_globs`, and the flag is `--test-glob`, so argparse sets `test_glob`. The helper was right and
the wiring was wrong -- the failure mode a unit test on the helper cannot see. These tests parse a real
command line with the real parser, then run the preflight against it.
"""

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.cli import build_parser, preflight_lines
from ninny.config import repo_task


class ThePreflightReadsTheArgumentsThatActuallyExist(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        for cmd in (["git", "init", "-q", str(self.dir)],
                    ["git", "-C", str(self.dir), "add", "-A"],
                    ["git", "-C", str(self.dir), "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "fixture"]):
            subprocess.run(cmd, check=True, capture_output=True)
        self.task = repo_task(self.dir, "do a thing", test_cmd="true", test_timeout_s=600)

    def parse(self, *extra: str) -> argparse.Namespace:
        argv = ["run", "--repo", str(self.dir), "--prompt-file", "/dev/null", "--test-cmd", "true",
                "--model", "test/model"]  # --model is required by the parser and never called here
        return build_parser().parse_args(argv + list(extra))

    def test_the_shape_that_crashed_now_runs(self):
        """--repo with --tdd enforce and a glob: the exact command line that raised AttributeError."""
        args = self.parse("--test-glob", "tests/*", "--tdd", "enforce")
        lines, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp", args)
        self.assertEqual(refusal, "")
        self.assertTrue(lines)

    def test_every_argument_the_preflight_reads_exists(self):
        """Names, not values: the bug was an attribute argparse never set."""
        args = self.parse("--steps", "80")
        for name in ("steps", "timeout", "tdd", "test_glob", "repo"):
            self.assertTrue(hasattr(args, name), f"the preflight reads args.{name}")

    def test_enforce_without_a_glob_is_still_refused_through_the_real_parser(self):
        args = self.parse("--tdd", "enforce")
        _, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp", args)
        self.assertIn("REFUSING", refusal)

    def test_the_repository_suite_timeout_is_a_dial(self):
        """--test-timeout reaches repo_task; a repository has no task.toml to declare one in."""
        self.assertEqual(self.parse("--test-timeout", "900").test_timeout, 900)
        self.assertIsNone(self.parse().test_timeout)


if __name__ == "__main__":
    unittest.main()
