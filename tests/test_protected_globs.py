"""Protection is declared, never defaulted -- and it holds in every mode.

`repo_task` starts with `protected_globs = []`, which is the right default: a built-in guess about
someone else's repository is a guess. But the hole it leaves is real -- in one live repository run the
delegate could have edited the acceptance command that was grading it. Detection exists afterwards
(`suite_frozen_since_red` records that the suite did not move after the red); prevention is one glob
away, and this is the test that it works where a caller would actually use it.

The check sits ABOVE the mode branch in `TDDPolicy.gate` (`tdd.py:493` against the mode test at `:507`),
which is why this holds under `--tdd request` -- the configuration repository runs default to. A caller
should not have to turn on test-first enforcement to stop a delegate editing its own acceptance command.
"""

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.cli import build_parser
from ninny.config import repo_task
from ninny.tdd import TDDPolicy, TDDState


class FakeWrite:
    def __init__(self, path):
        self.name = "write_file"
        self.path = path

    def is_submit(self):
        return False


class ProtectionIsDeclaredNotDefaulted(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "src").mkdir()
        (self.dir / "src" / "sim.cpp").write_text("int main(){return 0;}\n")
        (self.dir / "tools").mkdir()
        (self.dir / "tools" / "run_acceptance.sh").write_text("#!/bin/sh\nexit 1\n")
        for cmd in (["git", "init", "-q", str(self.dir)],):
            subprocess.run(cmd, check=True, capture_output=True)
        for cmd in (["git", "-C", str(self.dir), "add", "-A"],):
            subprocess.run(cmd, check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.dir), "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "fixture"], check=True, capture_output=True)

    def task(self, **kw):
        return repo_task(self.dir, "do a thing", test_cmd="bash tools/run_acceptance.sh", **kw)

    def test_nothing_is_protected_unless_the_caller_names_it(self):
        task = self.task()
        self.assertEqual(task.protected_globs, [])
        self.assertFalse(task.is_protected("tools/run_acceptance.sh"))

    def test_a_named_glob_protects_the_acceptance_command(self):
        task = self.task(protected_globs=["tools/**"])
        self.assertTrue(task.is_protected("tools/run_acceptance.sh"))
        self.assertFalse(task.is_protected("src/sim.cpp"), "protection must not swallow the work")

    def test_the_gate_refuses_even_under_tdd_request(self):
        # The point of the whole feature: no --test-glob, no enforcement, protection still holds.
        task = self.task(protected_globs=["tools/**"])
        policy = TDDPolicy("request", task, self.dir, require_green=True)
        state = TDDState("request")
        refusal = policy.gate(FakeWrite("tools/run_acceptance.sh"), state, 3)
        self.assertTrue(refusal.startswith("Refused:"), f"the write was not refused: {refusal!r}")
        self.assertIn("tools/run_acceptance.sh", refusal, "the refusal must name the path")
        self.assertTrue([r for r in state.refusals if "protected" in r[1]])

    def test_an_ordinary_source_write_still_goes_through(self):
        task = self.task(protected_globs=["tools/**"])
        policy = TDDPolicy("request", task, self.dir, require_green=True)
        state = TDDState("request")
        self.assertEqual(policy.gate(FakeWrite("src/sim.cpp"), state, 3), "")

    def test_the_command_line_takes_the_glob(self):
        args = build_parser().parse_args(["run", "--repo", str(self.dir), "--model", "m",
                                          "--prompt", "x", "--test-cmd", "bash tools/run_acceptance.sh",
                                          "--protected-glob", "tools/**", "--protected-glob", "ci/**"])
        self.assertEqual(args.protected_glob, ["tools/**", "ci/**"])


if __name__ == "__main__":
    unittest.main()
