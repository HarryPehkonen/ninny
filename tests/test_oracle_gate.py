"""One oracle standard, and the loader refuses anything else.

An oracle may grade the implementation with an external corpus. It may not gate acceptance on
the submission's own test files passing: once a suite has gone red the seal forbids repairing
it, so the model cannot always meet that gate -- and three live `bits` arms failed acceptance
with an implementation the corpus passed. Two tasks answering the same question differently is
how that stayed invisible for sixty arms.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.config import ConfigError, load_task


class OracleGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "tiny"
        (self.root / "tree").mkdir(parents=True)
        (self.root / "SPEC.md").write_text("do a thing\n")

    def write(self, extra: str) -> None:
        (self.root / "task.toml").write_text(
            'name = "tiny"\ntree = "tree"\ntest_cmd = "true"\n' + extra
        )

    def test_the_default_is_the_implementation(self):
        self.write("")
        self.assertEqual(load_task(self.root).oracle_gate, "implementation")

    def test_the_standard_may_be_stated(self):
        self.write('oracle_gate = "implementation"\n')
        self.assertEqual(load_task(self.root).oracle_gate, "implementation")

    def test_gating_on_the_submissions_own_suite_is_refused(self):
        self.write('oracle_gate = "implementation+suite"\n')
        with self.assertRaises(ConfigError) as caught:
            load_task(self.root)
        self.assertIn("seal forbids", str(caught.exception))

    def test_every_task_in_this_repo_declares_the_same_standard(self):
        repo = Path(__file__).resolve().parent.parent / "tasks"
        tasks = sorted(repo.glob("*/task.toml"))
        self.assertGreaterEqual(len(tasks), 10, "the corpus shrank; is the glob right?")
        for toml in tasks:
            with self.subTest(task=toml.parent.name):
                self.assertEqual(load_task(toml.parent).oracle_gate, "implementation")


if __name__ == "__main__":
    unittest.main()
