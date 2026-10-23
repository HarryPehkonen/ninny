"""What a tree's own build output is, per ecosystem.

One definition, because the digest, the diff and the gate must agree. A missing entry is
not cosmetic: a Rust arm added 61 files to its `diff.patch` for a 17-line change, because
cargo's `target/` was not in the skip list, and a reader looking at "61 added" would have
drawn the wrong conclusion about what the model did.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.artifacts import SKIP_PARTS, is_ignored, tree_diff


class BuildOutputIsNotSourceTests(unittest.TestCase):
    def test_each_ecosystems_build_directory_is_ignored(self):
        for part in ("build", "target", "node_modules", "dist", ".venv", "venv"):
            self.assertIn(part, SKIP_PARTS)
            self.assertTrue(is_ignored(Path(part) / "artifact.bin"), part)

    def test_a_file_inside_a_build_directory_is_ignored_at_any_depth(self):
        self.assertTrue(is_ignored(Path("a/b/target/debug/deps/thing.rlib")))
        self.assertTrue(is_ignored(Path("x/node_modules/left-pad/index.js")))

    def test_the_sources_are_not_ignored(self):
        for path in ("src/lib.rs", "Cargo.toml", "tests/own/set.rs", "tools/run_own_tests.sh"):
            self.assertFalse(is_ignored(Path(path)), path)

    def test_a_rust_build_directory_does_not_land_in_the_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before", Path(tmp) / "after"
            (before / "src").mkdir(parents=True)
            (after / "src").mkdir(parents=True)
            (before / "src" / "lib.rs").write_text("pub fn a() -> u32 { 1 }\n")
            (after / "src" / "lib.rs").write_text("pub fn a() -> u32 { 2 }\n")
            (after / "target" / "debug").mkdir(parents=True)
            (after / "target" / "debug" / "libintset.rlib").write_bytes(b"\x7fELF and so on")
            patch, stat = tree_diff(before, after)
            self.assertNotIn("target", patch)
            # One source file changed and nothing was added that a human would call a file:
            # the 61-file diff this covers was entirely cargo's own build output.
            self.assertIn("0 added", stat)
            self.assertIn("1 changed", stat)


if __name__ == "__main__":
    unittest.main()
