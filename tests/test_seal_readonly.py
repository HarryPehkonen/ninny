"""The seal is enforced by the filesystem, not by a rule.

The gate refuses a `write_file` into a sealed test file, and the first live `split` run showed
exactly how much that is worth: the arm rewrote its failing test through `python3 - <<'PY'` in a
bash action, the gate never saw it, and only the seal could tell. A rule constrains a tool; a
read-only bind constrains the capability.

The SECOND live run showed the bind alone was not enough either -- see
TheSuiteDirectoryCannotBeRenamedAside. These tests pin the mounts, their order, and the honesty
of the record when a backend cannot provide them at all.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from ninny.sandbox import BwrapSandbox, Sandbox, build_sandbox


class SealFixture(unittest.TestCase):
    """A real working tree, because a bind of a path that does not exist is skipped on purpose."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ninny-seal-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tree = self.tmp / "tree"
        (self.tree / "tests" / "own").mkdir(parents=True)
        (self.tree / "src").mkdir()
        self.sealed = self.tree / "tests" / "own" / "test_x.py"
        self.sealed.write_text("assert False\n")

    def bwrap(self) -> BwrapSandbox:
        return BwrapSandbox("/usr/bin/bwrap")

    def argv(self, sealed=None, ancestors=()) -> list[str]:
        box = self.bwrap()
        box.seal_readonly([str(sealed or self.sealed)], ancestors=ancestors)
        return box.wrap("true", self.tree)

    @staticmethod
    def ro_pairs(argv) -> list[tuple[str, str]]:
        return [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv) if a == "--ro-bind"]


class TheBindIsBuilt(SealFixture):
    def test_a_plain_sandbox_binds_nothing_read_only_from_the_tree(self):
        # bwrap always ro-binds /usr and /etc. What must NOT be there is a read-only bind of a
        # path inside the working tree: that is the seal, and it only exists once one is set.
        box = self.bwrap()
        argv = box.wrap("true", self.tree)
        self.assertFalse([p for p in self.ro_pairs(argv) if p[0].startswith(str(self.tree))])
        self.assertEqual(box.sealed_readonly, ())

    def test_a_sealed_file_is_bound_read_only_at_its_own_path(self):
        self.assertIn((str(self.sealed), str(self.sealed)), self.ro_pairs(self.argv()))

    def test_the_seal_bind_comes_after_the_writable_tree_bind(self):
        # bwrap applies mounts left to right and the later one wins. A read-only bind placed
        # before `--bind tree tree` would be quietly undone by it, and the seal would look
        # enforced while writing still worked -- the worst of both.
        argv = self.argv()
        self.assertLess(argv.index(str(self.tree)), argv.index(str(self.sealed)))

    def test_bwrap_says_it_can_enforce_and_none_says_it_cannot(self):
        self.assertTrue(self.bwrap().seal_readonly([str(self.sealed)]))
        box = build_sandbox("none")
        self.assertFalse(box.seal_readonly([str(self.sealed)]))
        self.assertEqual(box.sealed_readonly, (str(self.sealed),))

    def test_both_seals_are_kept_for_the_backend(self):
        parent = str(self.sealed.parent)
        box = self.bwrap()
        box.seal_readonly([str(self.sealed)], ancestors=[parent])
        self.assertEqual(box.sealed_readonly, (str(self.sealed),))
        self.assertEqual(box.sealed_ancestors, (parent,))


class TheSuiteDirectoryCannotBeRenamedAside(SealFixture):
    """Freezing the file is not enough: the parent directory has to be frozen too.

    The first live sealed run found this. The file itself refused every route -- chmod, `mv`,
    `sed -i`, a heredoc -- so the model renamed the whole suite directory (`tests/own` -> `ownX`)
    and wrote a fresh suite at the same path. A rename needs write permission on the PARENT of
    the thing being renamed, which is not the file, so per-file sealing left that door open.
    """

    def ancestor(self) -> str:
        return str(self.tree / "tests")

    def test_the_ancestor_is_frozen(self):
        pairs = self.ro_pairs(self.argv(ancestors=[self.ancestor()]))
        self.assertIn((self.ancestor(), self.ancestor()), pairs)
        self.assertIn((str(self.sealed), str(self.sealed)), pairs)

    def test_the_suite_directory_is_reopened_for_new_tests(self):
        # Freezing an ancestor freezes everything under it. The suite directory has to come back
        # writable or new test files would be refused -- and per-file sealing exists to allow them.
        argv = self.argv(ancestors=[self.ancestor()])
        frozen_at = argv.index(self.ancestor())
        reopened_at = argv.index(str(self.sealed.parent))
        self.assertLess(frozen_at, reopened_at)                      # later mounts win
        self.assertLess(reopened_at, argv.index(str(self.sealed)))    # then close the file last
        self.assertEqual(argv[reopened_at - 1], "--bind")

    def test_a_missing_sealed_file_is_skipped_rather_than_breaking_the_sandbox(self):
        # bwrap refuses to start on a missing `--ro-bind` source, and then EVERY later bash action
        # fails for a reason that is the harness's fault, and the shell is what broke so the run
        # cannot recover. A model action made a live run unwinnable this way. The seal still
        # reports it: the handback hash comparison notices the file is gone.
        gone = self.tree / "tests" / "own" / "gone.py"
        argv = self.argv(sealed=gone)
        self.assertNotIn(str(gone), argv)
        self.assertIn("bash", argv)

    def test_no_stray_empty_bind_is_emitted(self):
        # A sealed file at the tree root has no parent directory to re-open, and `--bind '' ''`
        # would be a broken argument rather than a no-op.
        top = self.tree / "test_top.py"
        top.write_text("assert False\n")
        self.assertNotIn("", self.argv(sealed=top))

    def test_the_base_class_cannot_enforce(self):
        # Every backend that cannot must say so rather than pretend. The record prints which of
        # the two happened, so a report-only seal can never read as an enforced one.
        self.assertFalse(Sandbox.can_seal_readonly)


if __name__ == "__main__":
    unittest.main()
