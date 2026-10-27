"""The duration line, reached the way a caller reaches it: a real command line.

`tests/test_preflight.py` measures the fragment in isolation. This file repeats the one claim
that has to survive the seam -- the measured duration is on the suite line and an ordinary
`--repo` invocation is still not refused -- through the real parser, so a preflight that reads
an argument name argparse never sets fails here rather than at launch.
"""

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.cli import build_parser, preflight_lines
from ninny.config import repo_task


class TheSuiteDurationSurvivesTheRealCommandLine(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        for cmd in (["git", "init", "-q", str(self.dir)],
                    ["git", "-C", str(self.dir), "add", "-A"],
                    ["git", "-C", str(self.dir), "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "fixture"]):
            subprocess.run(cmd, check=True, capture_output=True)
        self.test_cmd = "sleep 0.3; echo measured >> marker.txt"
        self.task = repo_task(self.dir, "do a thing", test_cmd=self.test_cmd, test_timeout_s=600)

    def parse(self, *extra: str) -> argparse.Namespace:
        argv = ["run", "--repo", str(self.dir), "--prompt-file", "/dev/null",
                "--test-cmd", self.test_cmd, "--model", "test/model"]
        return build_parser().parse_args(argv + list(extra))

    def test_the_measured_duration_is_on_the_line_and_the_run_is_not_refused(self):
        args = self.parse("--test-glob", "tests/*")
        lines, refusal = preflight_lines(self.task, self.dir, "edit src/sim.cpp", args)
        self.assertEqual(refusal, "")
        joined = "\n".join(lines)
        self.assertIn(f"suite `{self.test_cmd}` took ", joined)
        self.assertIn("single bash action", joined)


if __name__ == "__main__":
    unittest.main()
