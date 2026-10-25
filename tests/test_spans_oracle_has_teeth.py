"""The `spans` oracle must accept the answer key and reject a hasty implementation.

The whole reason `tasks/spans` exists is to be a task where careful reading of the contract
shows up in acceptance. That is only evidence if the oracle can tell careful from hasty, so
the claim is a test rather than a hope: the oracle is run against `tasks/spans/fixed` (it must
pass) and against the same tree with `sabotage/hasty_spans.py` in place of `src/spans.py` (it
must fail, and it must fail in the set semantics rather than in the text form).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK = ROOT / "tasks" / "spans"
FIXED = TASK / "fixed"
HASTY = TASK / "sabotage" / "hasty_spans.py"

FAILING = re.compile(r"^FAIL: \S+ \(__main__\.(\w+)\.")


def run_oracle(tree: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, NINNY_TREE=str(tree))
    return subprocess.run(
        ["bash", str(TASK / "oracle" / "gate.sh")],
        cwd=str(TASK), env=env, capture_output=True, text=True, timeout=600,
    )


def output(proc: subprocess.CompletedProcess) -> str:
    """unittest writes its FAIL lines to stderr; only the verdict is printed to stdout."""
    return proc.stdout + proc.stderr


def hasty_tree(tmp: str) -> Path:
    tree = Path(tmp) / "tree"
    shutil.copytree(FIXED, tree)
    shutil.copy(HASTY, tree / "src" / "spans.py")
    return tree


class TheSpansOracleHasTeeth(unittest.TestCase):
    def test_the_answer_key_passes_the_oracle(self):
        proc = run_oracle(FIXED)
        self.assertIn("GATE PASSED", output(proc), output(proc)[-2000:])
        self.assertEqual(proc.returncode, 0, output(proc)[-2000:])
        checks = re.search(r"ACCEPTANCE: (\d+) tests, (\d+) failed", output(proc))
        if checks is None:
            self.fail(output(proc)[-2000:])
        self.assertGreater(int(checks.group(1)), 0, "an oracle that runs nothing is not a pass")

    def test_a_hasty_implementation_fails_the_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_oracle(hasty_tree(tmp))
        self.assertNotEqual(proc.returncode, 0,
                            "the oracle accepted a hasty implementation, so this task cannot "
                            "separate careful reading from coding to the happy path")
        self.assertIn("GATE FAILED", output(proc), output(proc)[-2000:])

    def test_the_teeth_are_in_the_set_semantics_not_the_text_form(self):
        # The sabotage file parses correctly on purpose. If the oracle failed it inside Parse,
        # the test above would pass for a reason that has nothing to do with the contract.
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_oracle(hasty_tree(tmp))
        classes = {m.group(1) for m in (FAILING.match(line) for line in output(proc).splitlines()) if m}
        self.assertTrue(classes, f"no failing case was attributed to a class:\n{output(proc)[-2000:]}")
        self.assertNotIn("Parse", classes,
                         f"the hasty implementation's text form is correct, so Parse must not "
                         f"fail it; failing classes were {sorted(classes)}")


if __name__ == "__main__":
    unittest.main()
