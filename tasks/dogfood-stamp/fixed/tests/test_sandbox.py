"""The sandbox seam: what a task may declare about the world its toolchain needs.

A task whose toolchain lives outside /usr cannot be scored at all. The Node task hit this
first: its interpreter is a per-user install under the home directory, which the sandbox
hides on purpose, and the run was refused with `node: command not found`. Refusing was the
right call -- scoring a model on a toolchain the sandbox removed would be a harness-caused
failure -- but the task had no way to say what it needed.

So a task may declare extra paths to expose read-only. They are listed in the sandbox plan,
so the record says what the run could see instead of leaving it to be inferred.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.config import load_task
from ninny.sandbox import BwrapSandbox


def _task(tmp: str, extra: str = "") -> object:
    root = Path(tmp)
    (root / "tree").mkdir()
    (root / "SPEC.md").write_text("a spec\n")
    (root / "task.toml").write_text(
        'test_cmd = "bash tools/run_own_tests.sh"\n' + extra
    )
    return load_task(root)


class SandboxBindTests(unittest.TestCase):
    def test_a_task_may_declare_extra_read_only_binds(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _task(tmp, 'sandbox_binds = ["/opt/node/bin", "/opt/node/lib"]\n')
            self.assertEqual(["/opt/node/bin", "/opt/node/lib"], task.sandbox_binds)

    def test_a_task_that_declares_none_gets_an_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], _task(tmp).sandbox_binds)

    def test_declared_binds_become_read_only_binds_at_the_same_path(self):
        box = BwrapSandbox("/bin/true", False, ["/opt/node/bin"])
        joined = " ".join(box.wrap("echo hi", Path("/tmp/tree")))
        self.assertIn("--ro-bind /opt/node/bin /opt/node/bin", joined)

    def test_the_standard_binds_are_untouched(self):
        box = BwrapSandbox("/bin/true", False, ["/opt/node/bin"])
        joined = " ".join(box.wrap("echo hi", Path("/tmp/tree")))
        self.assertIn("--ro-bind /usr /usr", joined)
        self.assertIn("--ro-bind /etc /etc", joined)

    def test_a_task_with_no_binds_produces_no_extra_flags(self):
        box = BwrapSandbox("/bin/true", False, [])
        joined = " ".join(box.wrap("echo hi", Path("/tmp/tree")))
        self.assertNotIn("/opt/node", joined)
        self.assertEqual(2, joined.count("--ro-bind"))

    def test_the_sandbox_plan_names_what_was_exposed(self):
        # The plan line is printed at the start of every run, so it is where a reader
        # finds out what the run could see. Silence about an exposed path is the thing
        # being prevented here.
        box = BwrapSandbox("/bin/true", False, ["/opt/node/bin"])
        self.assertIn("/opt/node/bin", box.describe())

    def test_a_plan_with_no_extra_binds_says_nothing_about_binds(self):
        box = BwrapSandbox("/bin/true", False, [])
        self.assertNotIn("bind", box.describe())
        self.assertIn("SANDBOXED", box.describe())


if __name__ == "__main__":
    unittest.main()
