"""A repository run stages a worktree at HEAD, so uncommitted work is invisible to it.

Measured cost of not saying this: `ng-utf8-2` (NameGenerator, 45 steps) spent its last five steps on
`git log --all`, `git fsck --lost-found` and `git log -- src/NameGenerator.cpp`, hunting in history for
a path its brief had named, because the brief had been written against a working tree the run could not
see. A brief is written by a caller who has the working tree in front of them; the run gets HEAD.

This is a line, never a refusal. A dirty tree is a legitimate state -- the caller may be deliberately
measuring against a commit -- but it is a state the caller should be told about before the model spends
a token, and the honest way to tell them is the count, the paths, and the consequence.
"""

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.cli import preflight_lines
from ninny.config import repo_task


def args_for(**over) -> argparse.Namespace:
    base = dict(steps=40, timeout=None, tdd="request", test_glob=[], repo="/tmp/repo")
    base.update(over)
    return argparse.Namespace(**base)


def git(*cmd, cwd):
    return subprocess.run(["git", "-C", str(cwd), *cmd], check=True, capture_output=True, text=True)


class ARepositoryRunIsToldWhatItCannotSee(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        (self.dir / "tests").mkdir()
        (self.dir / "tests" / "test_sim.cpp").write_text("// a test\n")
        subprocess.run(["git", "init", "-q", str(self.dir)], check=True, capture_output=True)
        git("add", "-A", cwd=self.dir)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fixture", cwd=self.dir)
        self.head = git("rev-parse", "--short", "HEAD", cwd=self.dir).stdout.strip()
        self.task = repo_task(self.dir, "do a thing", test_cmd="bash tools/ci.sh fast",
                              check_cmd="make -j2", test_globs=[])

    def preflight(self, prompt="edit src/sim.cpp"):
        return preflight_lines(self.task, self.dir, prompt, args_for(repo=str(self.dir)))

    def test_a_clean_tree_says_nothing_about_it(self):
        lines, _ = self.preflight()
        self.assertFalse([l for l in lines if "uncommitted" in l],
                         f"a clean tree must not raise an alarm: {lines}")

    def test_an_uncommitted_change_is_named_with_its_consequence(self):
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 1;}\n")
        lines, _ = self.preflight()
        warning = [l for l in lines if "uncommitted" in l]
        self.assertTrue(warning, f"the dirty tree was not mentioned: {lines}")
        joined = " ".join(warning)
        self.assertIn("src/sim.cpp", joined, "the caller needs the path, not just a count")
        self.assertIn("HEAD", joined, "and the reason it matters: the run stages HEAD")

    def test_a_new_untracked_file_is_named_too(self):
        # The case that actually bit: a brief naming a file that exists only in the working tree.
        (self.dir / "src" / "helper.cpp").write_text("// uncommitted\n")
        lines, _ = self.preflight("edit src/helper.cpp")
        self.assertTrue([l for l in lines if "uncommitted" in l], f"untracked file missed: {lines}")

    def test_it_is_a_line_and_not_a_refusal(self):
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 1;}\n")
        _, refusal = self.preflight()
        self.assertEqual(refusal, "", "a dirty tree is a state to report, never a reason to refuse")

    def test_an_ignored_build_directory_is_not_reported(self):
        # Build output is uncommitted by design. Reporting it would make the line useless in exactly
        # the repositories it matters most for (`build/` was 25 of 27 changed files in one live run).
        (self.dir / ".gitignore").write_text("build/\n")
        (self.dir / "build").mkdir()
        (self.dir / "build" / "cache.bin").write_text("noise\n")
        git("add", "-A", cwd=self.dir)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ignore build", cwd=self.dir)
        (self.dir / "build" / "more.bin").write_text("more noise\n")
        lines, _ = self.preflight()
        self.assertFalse([l for l in lines if "uncommitted" in l],
                         f"ignored build output must not be reported: {lines}")


if __name__ == "__main__":
    unittest.main()
