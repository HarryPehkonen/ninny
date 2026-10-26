"""`--task` defaults to ./.ninny, and says so when that directory is not there.

The default is a convention, not magic, and three things have to hold for it to be one:
it is used when the flag is omitted, it loses to an explicit `--task`, and when the
directory it expects is missing it *names* that directory. A default that fails
somewhere deeper costs more than the flag it saved.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ninny import cli

DEFAULT = ".ninny"

TASK_TOML = """name = "probe"
spec_file = "SPEC.md"
tree = "tree"
test_cmd = "sh -c 'exit 0'"
oracle = "oracle"
oracle_cmd = "bash oracle/gate.sh"
fixed_tree = "fixed"
"""

# RED on the tree the agent starts from, GREEN on the fixed tree. The grep is last on
# purpose: an `echo` after it would make the script's exit status the echo's.
ORACLE = """#!/usr/bin/env bash
grep -q 'value = 1' "$NINNY_TREE/src/x.py"
"""

ALWAYS_PASS = """#!/usr/bin/env bash
echo "5 tests, 0 failed"
exit 0
"""


def build(root: Path, *, oracle: str = ORACLE) -> Path:
    """The smallest task `verify-task` will accept."""
    (root / "tree" / "src").mkdir(parents=True)
    (root / "tree" / "src" / "x.py").write_text("value = 0\n")
    (root / "fixed" / "src").mkdir(parents=True)
    (root / "fixed" / "src" / "x.py").write_text("value = 1\n")
    (root / "oracle").mkdir()
    (root / "oracle" / "gate.sh").write_text(oracle)
    (root / "SPEC.md").write_text("make x.py hold 1\n")
    (root / "task.toml").write_text(TASK_TOML)
    return root


class TaskDefaultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(os.chdir, os.getcwd())
        self._env = mock.patch.dict(
            os.environ, {"NINNY_LOG_DIR": str(self.dir / "logs")}
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                return cli.main(argv), buf.getvalue()
            except SystemExit as exc:  # argparse still refusing the omitted flag
                return (exc.code if isinstance(exc.code, int) else 1), buf.getvalue()

    def test_the_convention_directory_is_dot_ninny(self):
        self.assertEqual(cli.DEFAULT_TASK_DIR, DEFAULT)

    def test_task_defaults_to_the_convention_directory(self):
        build(self.dir / DEFAULT)
        os.chdir(self.dir)
        code, out = self.run_cli(["verify-task", "--out", str(self.dir / "checks")])
        self.assertIn("VERIFIED", out)
        self.assertEqual(code, 0)

    def test_an_explicit_task_still_wins(self):
        build(self.dir / DEFAULT)  # a good task
        other = self.dir / "other"
        other.mkdir()
        build(other, oracle=ALWAYS_PASS)  # a broken one
        os.chdir(self.dir)
        code, out = self.run_cli(
            ["verify-task", "--task", str(other), "--out", str(self.dir / "checks")]
        )
        self.assertIn("BROKEN TASK", out)
        self.assertNotEqual(code, 0)

    def test_a_missing_default_names_the_directory_it_looked_in(self):
        os.chdir(self.dir)  # nothing here at all
        code, out = self.run_cli(["verify-task"])
        self.assertNotEqual(code, 0)
        self.assertIn(DEFAULT, out)
        self.assertIn("--task", out)


if __name__ == "__main__":
    unittest.main()
