"""A task is not trusted until it has been shown to fail, and to pass.

The discipline this automates is the one that caught the most expensive bug of the
project: an oracle handed a relative path graded the wrong directory and reported a
confident pass that meant nothing. Running the oracle by hand was not enough -- what
made it trustworthy was running it against a tree that MUST fail and against a
known-good tree that MUST pass.

`verify-task` refuses to call a task trustworthy until both directions are observed.
"""

import tempfile
import unittest
from pathlib import Path

from ninny import cli

TASK_TOML = """name = "probe"
spec_file = "SPEC.md"
tree = "tree"
test_cmd = "{test_cmd}"
oracle = "oracle"
oracle_cmd = "bash oracle/gate.sh"
{fixed}
"""

# Fails on `value = 0`, passes once the value is 1. The grep is LAST on purpose: an
# `echo` after it would make the script's exit status the echo's, so the oracle would
# always report success. `verify-task` caught exactly that in an earlier version.
ORACLE = """#!/usr/bin/env bash
echo "checking x.py"
grep -q 'value = 1' "$NINNY_TREE/src/x.py"
"""

ALWAYS_PASS = """#!/usr/bin/env bash
echo "5 tests, 0 failed"
exit 0
"""


def build(root: Path, *, oracle=ORACLE, test_cmd="sh -c 'exit 0'", fixed: int | None = 1) -> Path:
    (root / "tree" / "src").mkdir(parents=True)
    (root / "tree" / "src" / "x.py").write_text("value = 0\n")
    (root / "SPEC.md").write_text("make x.py hold 1\n")
    (root / "oracle").mkdir()
    (root / "oracle" / "gate.sh").write_text(oracle)
    if fixed is not None:
        (root / "fixed" / "src").mkdir(parents=True)
        (root / "fixed" / "src" / "x.py").write_text(f"value = {fixed}\n")
    (root / "task.toml").write_text(
        TASK_TOML.format(
            test_cmd=test_cmd,
            fixed='fixed_tree = "fixed"' if fixed is not None else "",
        )
    )
    return root


class VerifyTaskTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "task"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def run_verify(self, *extra: str) -> tuple[int, str]:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["verify-task", "--task", str(self.root), "--out", str(self.root / "checks"), *extra])
        return code, buf.getvalue()

    def test_a_task_with_both_controls_is_verified(self):
        build(self.root)
        code, output = self.run_verify()
        self.assertIn("RED on the given tree", output)
        self.assertIn("GREEN on the fixed tree", output)
        self.assertIn("VERIFIED", output)
        self.assertEqual(code, 0)

    def test_an_oracle_that_passes_on_the_given_tree_is_a_broken_task(self):
        build(self.root, oracle=ALWAYS_PASS)
        code, output = self.run_verify()
        self.assertIn("BROKEN TASK", output)
        self.assertIn("passes on the tree the agent starts from", output)
        self.assertNotEqual(code, 0)

    def test_an_oracle_that_fails_on_the_fixed_tree_is_a_broken_task(self):
        build(self.root, fixed=99)
        code, output = self.run_verify()
        self.assertIn("BROKEN TASK", output)
        self.assertIn("does not pass on the known-good tree", output)
        self.assertNotEqual(code, 0)

    def test_a_red_start_is_reported_but_does_not_condemn_the_task(self):
        # This test used to assert the opposite. It encoded a rule that is not true:
        # a runner that fails on an empty suite is a GOOD runner -- that is what stops
        # a vacuous suite from counting as a pass -- so a red start is expected for a
        # task whose suite begins empty. The real roman task exposed the false alarm.
        build(self.root, test_cmd="sh -c 'exit 1'")
        code, output = self.run_verify()
        self.assertIn("INFO", output)
        self.assertIn("own test command fails on the tree the agent starts from", output)
        self.assertNotIn("BROKEN TASK", output)
        self.assertEqual(code, 0)

    def test_no_fixed_tree_means_unverified_not_verified(self):
        build(self.root, fixed=None)
        code, output = self.run_verify()
        self.assertIn("UNVERIFIED", output)
        self.assertNotEqual(code, 0)

    def test_a_fixed_tree_can_be_given_on_the_command_line(self):
        build(self.root, fixed=None)
        good = Path(self._tmp.name) / "good"
        (good / "src").mkdir(parents=True)
        (good / "src" / "x.py").write_text("value = 1\n")
        code, output = self.run_verify("--fixed", str(good))
        self.assertIn("GREEN on the fixed tree", output)
        self.assertIn("VERIFIED", output)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
