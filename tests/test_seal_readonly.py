"""The seal is enforced by the filesystem, not by a rule.

The gate refuses a `write_file` into a sealed test file, and the first live `split` run showed
exactly how much that is worth: the arm rewrote its failing test through `python3 - <<'PY'` in a
bash action, the gate never saw it, and only the seal could tell. A rule constrains a tool; a
read-only bind constrains the capability. These tests pin the bind, its order, and the honesty
of the record when the backend cannot provide one.
"""

import unittest
from pathlib import Path

from ninny.sandbox import BwrapSandbox, Sandbox, build_sandbox


class TheBindIsBuilt(unittest.TestCase):
    def bwrap(self) -> BwrapSandbox:
        return BwrapSandbox("/usr/bin/bwrap")

    def test_a_plain_sandbox_binds_nothing_read_only_from_the_tree(self):
        # bwrap always ro-binds /usr and /etc. What must NOT be there is a read-only bind of a
        # path inside the working tree: that is the seal, and it only exists once one is set.
        box = self.bwrap()
        argv = box.wrap("true", Path("/tmp/tree"))
        pairs = [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv) if a == "--ro-bind"]
        self.assertFalse([pair for pair in pairs if pair[0].startswith("/tmp/tree")])
        self.assertEqual(box.sealed_readonly, ())

    def test_a_sealed_file_is_bound_read_only_at_its_own_path(self):
        box = self.bwrap()
        box.seal_readonly(["/tmp/tree/tests/own/test_x.py"])
        argv = box.wrap("true", Path("/tmp/tree"))
        pairs = [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv) if a == "--ro-bind"]
        self.assertIn(("/tmp/tree/tests/own/test_x.py", "/tmp/tree/tests/own/test_x.py"), pairs)

    def test_the_seal_bind_comes_after_the_writable_tree_bind(self):
        # bwrap applies mounts left to right and the later one wins. A read-only bind placed
        # before `--bind tree tree` would be quietly undone by it, and the seal would look
        # enforced while writing still worked -- the worst of both.
        box = self.bwrap()
        box.seal_readonly(["/tmp/tree/tests/own/test_x.py"])
        argv = box.wrap("true", Path("/tmp/tree"))
        tree_at = argv.index("/tmp/tree")
        seal_at = argv.index("/tmp/tree/tests/own/test_x.py")
        self.assertGreater(seal_at, tree_at)

    def test_bwrap_says_it_can_enforce_and_none_says_it_cannot(self):
        self.assertTrue(BwrapSandbox("/usr/bin/bwrap").seal_readonly(["/x"]))
        box = build_sandbox("none")
        self.assertFalse(box.seal_readonly(["/x"]))
        self.assertEqual(box.sealed_readonly, ("/x",))

    def test_the_sandbox_base_class_cannot_enforce(self):
        # Every backend that cannot must say so rather than pretend. The record prints which
        # of the two happened, so a report-only seal can never read as an enforced one.
        self.assertFalse(Sandbox.can_seal_readonly)


if __name__ == "__main__":
    unittest.main()
