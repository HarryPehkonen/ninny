"""sandbox_binds must be portable, not a hard-coded path into one machine's home.

A task whose interpreter lives under a home directory needs that path bound into the
sandbox. Writing `/home/someone/.hermes/node` into a published task.toml makes the task
work on exactly one machine. `$HOME` and `~` are expanded when the manifest is read, so a
task can say `$HOME/.hermes/node` and mean the right directory wherever it runs.

Expansion happens at load time on the host, not inside the sandbox: the sandbox sets HOME
to /tmp, so expanding later would point at the wrong place.
"""

import os
import tempfile
import unittest
from pathlib import Path

from ninny.config import load_task


def _task_dir(tmp: Path) -> Path:
    root = tmp / "task"
    (root / "tree" / "src").mkdir(parents=True)
    (root / "oracle").mkdir()
    (root / "SPEC.md").write_text("a spec\n")
    return root


class SandboxBindExpansionTests(unittest.TestCase):
    def _load(self, binds: str):
        with tempfile.TemporaryDirectory() as tmp:
            root = _task_dir(Path(tmp))
            (root / "task.toml").write_text(
                'name = "t"\nspec_file = "SPEC.md"\ntree = "tree"\noracle = "oracle"\n'
                'test_cmd = "true"\n' + binds
            )
            return load_task(root)

    def test_home_variable_is_expanded(self):
        task = self._load('sandbox_binds = ["$HOME/.hermes/node"]\n')
        self.assertEqual(task.sandbox_binds, [os.path.join(os.path.expanduser("~"), ".hermes/node")])

    def test_tilde_is_expanded(self):
        task = self._load('sandbox_binds = ["~/.local/share/mise"]\n')
        self.assertEqual(task.sandbox_binds, [os.path.join(os.path.expanduser("~"), ".local/share/mise")])

    def test_an_absolute_path_is_left_alone(self):
        task = self._load('sandbox_binds = ["/usr/lib/node"]\n')
        self.assertEqual(task.sandbox_binds, ["/usr/lib/node"])

    def test_no_binds_is_still_empty(self):
        task = self._load("")
        self.assertEqual(task.sandbox_binds, [])


if __name__ == "__main__":
    unittest.main()
