"""The declared check's duration, said before the run spends anything.

Measured 2026-11-02 on `xiao-ac-dimmer` (harrisbook post 37): a repository run declared its cheap check
as the delegate's own unit tests (0.3 s) while the acceptance command was `check_board.py` (1.1 s). The
check went red for eight consecutive writes for a reason the delegate had invented, then green while the
board regressed -- and the acceptance criterion was never run by anyone until the harness ran it at the
limit. Both numbers existed all along, one line apart; the caller had been shown only the suite's.

This supports a rule rather than enforcing one: declare as the cheap check the fastest command that can
FAIL for the reason the run is graded on. The preflight's job is to make the two visible together.
"""

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.cli import build_parser, preflight_lines
from ninny.config import repo_task


class ThePreflightShowsWhatTheCheckCosts(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        for cmd in (["git", "init", "-q", str(self.dir)],
                    ["git", "-C", str(self.dir), "add", "-A"],
                    ["git", "-C", str(self.dir), "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "fixture"]):
            subprocess.run(cmd, check=True, capture_output=True)
        self.accept = "echo acceptance >> marker.txt"
        self.task = repo_task(self.dir, "do a thing", test_cmd=self.accept, test_timeout_s=600)

    def parse(self, *extra: str) -> argparse.Namespace:
        argv = ["run", "--repo", str(self.dir), "--prompt-file", "/dev/null",
                "--test-cmd", self.accept, "--model", "test/model"]
        return build_parser().parse_args(argv + list(extra))

    def with_check(self, cmd: str) -> None:
        # The same field `cmd_run` sets from --check-cmd.
        self.task.check_cmd = cmd

    def lines(self, *extra: str) -> str:
        got, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp", self.parse(*extra))
        self.assertEqual(refusal, "")
        return "\n".join(got)

    def test_the_check_and_its_duration_are_on_the_line(self):
        self.with_check("python3 -m unittest discover -s tools/tests -q")
        joined = self.lines()
        self.assertIn("unittest discover", joined)
        self.assertIn("the declared check", joined)

    def test_nothing_is_said_when_no_check_is_declared(self):
        joined = self.lines()
        self.assertNotIn("the declared check", joined)

    def test_a_check_that_is_the_acceptance_command_is_not_called_different(self):
        self.with_check(self.accept)
        self.assertNotIn("different command", self.lines())

    def test_a_check_that_cannot_see_the_acceptance_criterion_is_called_different(self):
        self.with_check("python3 -m unittest discover -s tools/tests -q")
        self.assertIn("different command", self.lines())


class TheFlagReachesTheCaller(unittest.TestCase):
    def test_check_cmd_parses(self):
        argv = ["run", "--repo", "/tmp/x", "--prompt-file", "/dev/null", "--test-cmd", "true",
                "--model", "test/model", "--check-cmd", "make"]
        self.assertEqual(build_parser().parse_args(argv).check_cmd, "make")


if __name__ == "__main__":
    unittest.main()
