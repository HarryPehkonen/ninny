"""A bypass is a SOURCE write, and a repository's source glob matches everything.

Found in a live repository run (`NameGenerator`, arm `ng-utf8-2`): the record carried

    bypass_detected: [[11, "tests/test_length_counts_characters.py"]]

and step 11's write was the delegate's OWN TEST FILE. It did not bypass anything -- it wrote a test,
which is the behaviour the mode asks for. `repo_task` sets `src_globs = ["**"]` ("every path is the
work"), so the tree reconciliation's changed-file list contains every file, and the only thing that can
turn that list into a source/test distinction is `is_test_path`. Without it, the detector accused honest
work of cheating, which is worse than recording nothing: a false bypass makes the whole record suspect.

This is the same root cause as `first_src_step` in `test_no_globs_no_classification.py` -- two labels fed
by one list. The label was fixed there; the accusation is fixed here.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.config import Task
from ninny.tdd import TDDPolicy


def make_task(test_globs: list[str], tmp: str) -> Task:
    return Task(
        root=Path(tmp), name="fixture", spec="", tree_src=Path(tmp), oracle_dir=None,
        test_cmd="true", oracle_cmd=None, test_globs=test_globs, src_globs=["**"],
        preflight=[], step_limit=10, timeout_s=1, test_timeout_s=1,
        require_test_file=False,
    )


def policy(test_globs: list[str], tmp: str) -> TDDPolicy:
    # enforce: this is the mode in which a bypass is even possible.
    return TDDPolicy("enforce", make_task(test_globs, tmp), tmp)


class ATestWriteIsNotABypass(unittest.TestCase):
    def test_writing_a_test_file_while_in_the_test_phase_is_not_recorded_as_a_bypass(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tests").mkdir()
            (Path(tmp) / "tests" / "t.py").write_text("one\n")
            pol = policy(["tests/**"], tmp)
            state = pol.new_state()
            state.phase = "test"
            (Path(tmp) / "tests" / "t.py").write_text("two\n")
            pol.observe_tree(state, 11)
            self.assertEqual(state.bypass_detected, [],
                             "a test file written in the test phase is the mode working, not a bypass")

    def test_a_real_source_write_in_the_test_phase_is_still_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            (Path(tmp) / "src" / "a.cpp").write_text("one\n")
            pol = policy(["tests/**"], tmp)
            state = pol.new_state()
            state.phase = "test"
            (Path(tmp) / "src" / "a.cpp").write_text("two\n")
            pol.observe_tree(state, 11)
            self.assertEqual(state.bypass_detected, [[11, "src/a.cpp"]],
                             "refusing source in the test phase is what this detector is for")

    def test_with_no_test_globs_every_write_is_a_source_write(self):
        """The honest limit: with nothing declared, `enforce` can only be chosen deliberately, and then
        every path really is source -- so a write in the test phase really is a bypass. This test exists
        so that behaviour cannot drift into silence unnoticed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tests").mkdir()
            (Path(tmp) / "tests" / "t.py").write_text("one\n")
            pol = policy([], tmp)
            state = pol.new_state()
            state.phase = "test"
            (Path(tmp) / "tests" / "t.py").write_text("two\n")
            pol.observe_tree(state, 11)
            self.assertEqual(state.bypass_detected, [[11, "tests/t.py"]])


if __name__ == "__main__":
    unittest.main()
