#!/usr/bin/env python3
"""The acceptance suite for the `ninny-gate` task.

It lives OUTSIDE the task tree, and `ninny check` stages a copy of the submission
beside it rather than running inside it.

It drives the submission's own gate through its public API, and it checks **both
directions**: a gate that refuses everything is as broken as a gate that refuses
nothing, so the "still allowed" and "allowed again after RED" checks are load
bearing, not decoration.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TREE = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NINNY_TREE", ".")).resolve()

LOAD_ERROR = ""
ninny = None
if not (TREE / "ninny" / "tdd.py").is_file():
    LOAD_ERROR = f"there is no ninny/tdd.py under {TREE}"
else:
    sys.path.insert(0, str(TREE))
    try:
        for module in [name for name in sys.modules if name == "ninny" or name.startswith("ninny.")]:
            del sys.modules[module]
        ninny = importlib.import_module("ninny")
        importlib.import_module("ninny.actions")
        importlib.import_module("ninny.config")
        importlib.import_module("ninny.env")
        importlib.import_module("ninny.tdd")
    except Exception as exc:  # noqa: BLE001 - any import failure is an acceptance failure
        ninny = None
        LOAD_ERROR = f"{type(exc).__name__}: {exc}"

MUST_BE_REFUSED = [
    "ninny/tdd.py",
    "tests/../ninny/tdd.py",
    "tests/own/../../ninny/tdd.py",
    "../outside.py",
    "../../etc/passwd",
]
MUST_BE_ALLOWED = ["tests/own/test_gate.py", "tests/test_gate.py"]


class GateBypass(unittest.TestCase):
    def setUp(self):
        if ninny is None:
            self.fail(f"could not import the submitted ninny package: {LOAD_ERROR}")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        (self.work / "ninny").mkdir()
        (self.work / "ninny" / "tdd.py").write_text("# placeholder\n")
        (self.work / "tests" / "own").mkdir(parents=True)
        self.task = self._task()
        self.policy = ninny.tdd.TDDPolicy("enforce", self.task, self.work)
        self.state = self.policy.new_state()

    def _task(self):
        task_dir = self.work / "_task"
        (task_dir / "tree").mkdir(parents=True)
        (task_dir / "SPEC.md").write_text("probe\n")
        (task_dir / "task.toml").write_text(
            'name = "probe"\n'
            'tree = "tree"\n'
            'test_cmd = "true"\n'
            'test_globs = ["tests/**"]\n'
            'src_globs = ["ninny/**"]\n'
            'protected_globs = ["tools/**"]\n'
        )
        return ninny.config.load_task(task_dir)

    @staticmethod
    def write(path):
        return ninny.actions.Action(name="write_file", args={"path": path, "content": "x = 1\n"})

    def refused(self, path):
        return bool(self.policy.gate(self.write(path), self.state, 1))

    def make_red(self):
        """Write a test and observe it fail, exactly as a run does."""
        self.policy.observe(
            self.write("tests/own/test_gate.py"),
            ninny.env.Observation(ok=True, exit_code=0, output="", note=""),
            self.state,
            1,
        )
        self.policy.observe(
            ninny.actions.Action(name="run_tests", args={}),
            ninny.env.Observation(ok=False, exit_code=1, output="", note=""),
            self.state,
            2,
        )

    def test_paths_into_the_source_are_refused_before_red(self):
        for path in MUST_BE_REFUSED:
            with self.subTest(path=path):
                self.assertTrue(self.refused(path), f"{path} got past the gate")

    def test_ordinary_test_paths_are_still_allowed_before_red(self):
        for path in MUST_BE_ALLOWED:
            with self.subTest(path=path):
                self.assertFalse(self.refused(path), f"{path} was refused")

    def test_source_writes_are_allowed_again_after_red(self):
        self.make_red()
        for path in ("ninny/tdd.py", "tests/../ninny/tdd.py", "tests/own/../../ninny/tdd.py"):
            with self.subTest(path=path):
                self.assertFalse(self.refused(path), f"{path} was still refused after a RED was seen")

    def test_classification_still_works_for_ordinary_paths(self):
        self.assertTrue(self.task.is_src_path("ninny/tdd.py"))
        self.assertFalse(self.task.is_src_path("tests/own/test_gate.py"))
        self.assertTrue(self.task.is_test_path("tests/own/test_gate.py"))
        self.assertTrue(self.task.is_test_path("tests/test_gate.py"))

    def test_the_submitted_suite_still_passes(self):
        done = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=str(TREE),
            capture_output=True,
            text=True,
            timeout=600,
        )
        tail = "\n".join(((done.stdout or "") + (done.stderr or "")).strip().splitlines()[-5:])
        self.assertEqual(done.returncode, 0, "ninny's own suite no longer passes:\n" + tail)


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromTestCase(GateBypass)
    )
    checks = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nACCEPTANCE: {checks} tests, {failed} failed")
    verdict = "GATE PASSED" if failed == 0 and checks > 0 else "GATE FAILED"
    print(verdict)
    return 0 if verdict == "GATE PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
