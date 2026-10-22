"""What a run leaves behind, so somebody who was not here can audit it.

A run used to leave a record and a whole tree, and answering "what did it actually
change?" meant diffing two directories by hand. That is the first thing anyone asks,
and it is the artifact that catches a model which rewrote a file it meant to edit.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.artifacts import tree_diff, tree_digest, write_diff


class DiffTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.before = self.root / "before"
        self.after = self.root / "after"
        for base in (self.before, self.after):
            (base / "src").mkdir(parents=True)
            (base / "src" / "keep.py").write_text("value = 0\n")
            (base / "src" / "gone.py").write_text("obsolete = True\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_an_added_file_is_in_the_patch(self):
        (self.after / "src" / "new.py").write_text("fresh = 1\n")
        patch, stat = tree_diff(self.before, self.after)
        self.assertIn("+++ b/src/new.py", patch)
        self.assertIn("+fresh = 1", patch)
        self.assertIn("1 added", stat)

    def test_a_changed_file_shows_both_sides(self):
        (self.after / "src" / "keep.py").write_text("value = 1\n")
        patch, stat = tree_diff(self.before, self.after)
        self.assertIn("-value = 0", patch)
        self.assertIn("+value = 1", patch)
        self.assertIn("1 changed", stat)
        self.assertIn("+1 -1", stat)

    def test_a_deleted_file_is_in_the_patch(self):
        (self.after / "src" / "gone.py").unlink()
        patch, stat = tree_diff(self.before, self.after)
        self.assertIn("+++ /dev/null", patch)
        self.assertIn("-obsolete = True", patch)
        self.assertIn("1 deleted", stat)

    def test_an_unchanged_tree_produces_no_patch(self):
        patch, stat = tree_diff(self.before, self.after)
        self.assertEqual(patch.strip(), "")
        self.assertIn("0 added, 0 changed, 0 deleted", stat)

    def test_bytecode_cache_is_ignored(self):
        (self.after / "src" / "__pycache__").mkdir()
        (self.after / "src" / "__pycache__" / "keep.cpython-313.pyc").write_bytes(b"\x00\x01")
        patch, stat = tree_diff(self.before, self.after)
        self.assertEqual(patch.strip(), "")
        self.assertIn("0 added", stat)

    def test_build_output_is_not_part_of_the_diff(self):
        """A compiled loop writes build/own and object files. Not something an arm did.

        The C++ task's own test command compiles the suite into build/ before running
        it, so without this rule every C++ arm's diff.patch is a megabyte of compiler
        output with the actual change buried inside it.
        """
        (self.after / "build").mkdir()
        (self.after / "build" / "own").write_bytes(b"\x7fELF\x02\x01\x01")
        (self.after / "src" / "thing.o").write_bytes(b"\x7fELF\x02\x01\x01")
        patch, stat = tree_diff(self.before, self.after)
        self.assertEqual(patch.strip(), "")
        self.assertIn("0 added", stat)

    def test_a_binary_file_is_named_not_crashed(self):
        (self.before / "blob.bin").write_bytes(b"\xff\xfe\x00")
        (self.after / "blob.bin").write_bytes(b"\xff\xfe\x01")
        patch, stat = tree_diff(self.before, self.after)
        self.assertIn("blob.bin", patch)
        self.assertIn("binary", patch.lower())

    def test_write_diff_puts_the_patch_on_disk(self):
        (self.after / "src" / "keep.py").write_text("value = 2\n")
        out = self.root / "diff.patch"
        stat = write_diff(self.before, self.after, out)
        self.assertTrue(out.is_file())
        self.assertIn("+value = 2", out.read_text())
        self.assertIn("1 changed", stat)


class DigestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tree = self.root / "tree"
        (self.tree / "src").mkdir(parents=True)
        (self.tree / "src" / "thing.py").write_text("value = 0\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_digest_is_stable(self):
        self.assertEqual(tree_digest(self.tree), tree_digest(self.tree))

    def test_the_digest_changes_when_a_file_changes(self):
        before = tree_digest(self.tree)
        (self.tree / "src" / "thing.py").write_text("value = 1\n")
        self.assertNotEqual(before, tree_digest(self.tree))

    def test_the_digest_does_not_depend_on_where_the_tree_lives(self):
        other = self.root / "elsewhere"
        (other / "src").mkdir(parents=True)
        (other / "src" / "thing.py").write_text("value = 0\n")
        self.assertEqual(tree_digest(self.tree), tree_digest(other))

    def test_bytecode_cache_does_not_move_the_digest(self):
        before = tree_digest(self.tree)
        (self.tree / "src" / "__pycache__").mkdir()
        (self.tree / "src" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
        self.assertEqual(before, tree_digest(self.tree))


    def test_build_output_does_not_move_the_digest(self):
        before = tree_digest(self.tree)
        (self.tree / "build").mkdir()
        (self.tree / "build" / "own").write_bytes(b"\x7fELF")
        self.assertEqual(before, tree_digest(self.tree))


if __name__ == "__main__":
    unittest.main()
