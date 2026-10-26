"""`binds=None` means "no extra binds", the same as `binds=[]`.

A caller with no extra paths to expose has nothing to pass and writes `binds=None`,
which used to crash on `for path in binds`. An empty list already means "no extra
binds", so the two spellings must be interchangeable rather than one of them being a
TypeError waiting for the first caller who had nothing to add.
"""

import unittest
from pathlib import Path

from ninny.sandbox import BwrapSandbox, build_sandbox


class SandboxNullBindsTests(unittest.TestCase):
    def test_a_sandbox_can_be_constructed_with_binds_none(self):
        box = BwrapSandbox("/bin/true", False, None)
        self.assertEqual([], box.binds)

    def test_binds_none_and_binds_empty_produce_the_same_sandbox(self):
        workdir = Path("/tmp/tree")
        with_none = BwrapSandbox("/bin/true", False, None)
        with_empty = BwrapSandbox("/bin/true", False, [])
        self.assertEqual(with_empty.binds, with_none.binds)
        self.assertEqual(
            with_empty.wrap("echo hi", workdir),
            with_none.wrap("echo hi", workdir),
        )

    def test_build_sandbox_accepts_binds_none(self):
        box = build_sandbox("bwrap", bwrap_path="/bin/true", binds=None)
        self.assertEqual([], box.binds)

    def test_no_extra_binds_means_no_extra_ro_bind_flags(self):
        box = BwrapSandbox("/bin/true", False, None)
        joined = " ".join(box.wrap("echo hi", Path("/tmp/tree")))
        self.assertEqual(2, joined.count("--ro-bind"))


if __name__ == "__main__":
    unittest.main()
