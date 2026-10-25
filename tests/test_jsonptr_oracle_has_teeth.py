"""The `jsonptr` oracle must accept the answer key and reject every plausible-wrong implementation.

`tasks/jsonptr` exists to be a task where care shows up in acceptance. That is only evidence if the
oracle can tell care from haste, so the claim is a test rather than a hope: the oracle is run against
`tasks/jsonptr/fixed` (it must pass) and against the same tree with each `sabotage/*.js` in place of
`src/pointer.js` (each must fail, and the failure must be attributable to the rule that is wrong).

The last test is the one that makes the task worth running at all. `wrong_unescape_order.js` has the
unescaping order backwards -- the error RFC 6901 section 3 names, because `~01` then becomes `~1` and
then `/` -- and it must still pass EVERY pointer in the RFC's own section 5 example set. If it ever
fails one of those, the task stops discriminating: a hasty implementation would be caught by the
specification's own examples, which is a much weaker thing to have built.
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
TASK = ROOT / "tasks" / "jsonptr"
FIXED = TASK / "fixed"
SABOTAGE = sorted((TASK / "sabotage").glob("*.js"))
TRAP = TASK / "sabotage" / "wrong_unescape_order.js"

RFC = "resolve: RFC 6901 section 5"


def run_oracle(tree: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, NINNY_TREE=str(tree))
    return subprocess.run(
        ["bash", str(TASK / "oracle" / "accept.sh")],
        cwd=str(TASK), env=env, capture_output=True, text=True, timeout=600,
    )


def output(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


def failing(proc: subprocess.CompletedProcess) -> list[str]:
    return [line.strip()[len("FAILED "):] for line in output(proc).splitlines()
            if line.strip().startswith("FAILED ")]


def tree_with(fixture: Path, tmp: str) -> Path:
    tree = Path(tmp) / "tree"
    shutil.copytree(FIXED, tree)
    shutil.copy(fixture, tree / "src" / "pointer.js")
    return tree


class TheJsonptrOracleHasTeeth(unittest.TestCase):
    def test_the_answer_key_passes_the_oracle(self):
        proc = run_oracle(FIXED)
        self.assertIn("GATE PASSED", output(proc), output(proc)[-2000:])
        self.assertEqual(proc.returncode, 0, output(proc)[-2000:])
        counts = re.search(r"ACCEPTANCE: (\d+) tests, (\d+) failed", output(proc))
        if counts is None:
            self.fail(output(proc)[-2000:])
        self.assertGreater(int(counts.group(1)), 0, "an oracle that runs nothing is not a pass")

    def test_every_sabotage_file_is_a_drop_in_replacement(self):
        # A fixture that requires a sibling, or that does not load, is not a drop-in: it would
        # crash the oracle and the failure would prove nothing about the contract.
        for fixture in SABOTAGE:
            with self.subTest(fixture=fixture.name):
                self.assertNotIn("require('./", fixture.read_text(),
                                 f"{fixture.name} requires a sibling, so it is not self-contained")

    def test_each_plausible_wrong_implementation_fails_the_oracle(self):
        self.assertTrue(SABOTAGE, "no sabotage files, so nothing is being proven")
        for fixture in SABOTAGE:
            with self.subTest(fixture=fixture.name):
                with tempfile.TemporaryDirectory() as tmp:
                    proc = run_oracle(tree_with(fixture, tmp))
                self.assertNotEqual(proc.returncode, 0,
                                    f"the oracle accepted {fixture.name}, so this task cannot "
                                    f"separate careful reading from coding to the happy path")
                self.assertTrue(failing(proc),
                                f"{fixture.name} failed without a named check:\n{output(proc)[-2000:]}")

    def test_the_trap_passes_the_rfcs_own_examples_and_is_still_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_oracle(tree_with(TRAP, tmp))
        lines = failing(proc)
        named = "\n".join(lines)
        self.assertNotIn(RFC, named,
                         f"the trap is visible to the RFC's own example set, so the task no longer "
                         f"needs care -- only the examples:\n{named}")
        traps = [line for line in lines if "trap" in line]
        self.assertTrue(traps, f"the trap was not caught by a trap case:\n{named}")


    def test_a_suite_written_from_the_examples_does_not_kill_the_trap(self):
        # The other half of the claim. The oracle can tell careful from hasty -- and a suite built
        # from the specification's own examples CANNOT, which is why a task whose examples cover
        # the rule measures nothing. This one passes against the answer key and against the trap.
        with tempfile.TemporaryDirectory() as tmp:
            tree = tree_with(TRAP, tmp)
            (tree / "tests" / "own").mkdir(parents=True, exist_ok=True)
            shutil.copy(TASK / "oracle" / "example_suite.test.js",
                        tree / "tests" / "own" / "example.test.js")
            proc = subprocess.run(["bash", "tools/run_own_tests.sh"], cwd=str(tree),
                                  capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0,
                         f"an example-driven suite caught the trap, so the examples do cover the "
                         f"rule and this task measures typing, not care:\n{output(proc)[-2000:]}")


if __name__ == "__main__":
    unittest.main()
