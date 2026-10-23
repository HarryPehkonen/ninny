"""Check artifacts must not land inside the task tree.

`check` and `verify-task` copy the task, run its own suite and the oracle, and leave the
build output behind. Staging that inside the task directory grew the repository past 1 GB
of gitignored debris -- `tasks/intset/checks` alone reached 69 MB per verification, and a
Rust task's `target/` reached 956 MB. The task tree is source; a check is disposable.
"""

import tempfile
import unittest
from pathlib import Path

from ninny import cli
from ninny.config import load_task


class CheckBaseLocationTests(unittest.TestCase):
    def test_the_default_is_not_inside_the_task(self):
        task = load_task("tasks/roman")
        base = cli._default_check_base(task).resolve()
        task_root = Path(task.root).resolve()
        self.assertNotEqual(base, task_root / "checks")
        self.assertNotIn(task_root, base.parents, "check scratch must not live under the task")

    def test_the_default_is_scratch_space(self):
        task = load_task("tasks/roman")
        base = cli._default_check_base(task)
        self.assertTrue(
            str(base).startswith(tempfile.gettempdir()),
            f"expected scratch under {tempfile.gettempdir()}, got {base}",
        )
        self.assertEqual(base.name, task.name)


if __name__ == "__main__":
    unittest.main()
