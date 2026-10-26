"""The refusal tells the model how to get a RED, so it has to fit the task it is in.

The sentence used to be one string with `', '.join(test_globs)` dropped into it. That is
right for a benchmark task, where the globs say which files are the tests -- and it renders
as "write a test under  with write_file" in repo mode, where `--test-glob` was not passed
and `test_globs` is empty. An empty list dropped into the middle of an instruction is the
kind of thing that makes a model guess, so the wording adapts: it names the globs when there
are any, and when there are none it says plainly that the repository's own suite is what has
to fail first.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.actions import Action
from ninny.config import Task
from ninny.tdd import TDDPolicy


def a_task(root: Path, test_globs) -> Task:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "own").mkdir(parents=True, exist_ok=True)
    (root / "src" / "thing.py").write_text("value = 0\n")
    return Task(
        root=root,
        name="tiny",
        spec="",
        tree_src=root,
        oracle_dir=None,
        test_cmd="true",
        oracle_cmd=None,
        test_globs=list(test_globs),
        src_globs=["**"],
        protected_globs=[],
        preflight=[],
        step_limit=5,
        timeout_s=5,
        test_timeout_s=5,
        require_test_file=False,
    )


def a_refusal(test_globs) -> str:
    """The refusal the model reads when it writes source before any test has gone red."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        task = a_task(root, test_globs)
        policy = TDDPolicy("enforce", task, root)
        state = policy.new_state()
        message = policy.gate(
            Action(name="write_file", args={"path": "src/thing.py", "content": "x"}), state, 1
        )
        assert message, "the gate was expected to refuse a source write before the red"
        return message


class TheRefusalNamesWhereTheTestGoes(unittest.TestCase):
    def test_with_globs_it_names_them(self):
        message = a_refusal(["tests/own/**"])
        self.assertIn("write a test under tests/own/** with write_file", message)
        self.assertNotIn("the repository's own suite", message)

    def test_without_globs_it_says_the_repositorys_own_suite_is_what_fails_first(self):
        message = a_refusal([])
        self.assertIn("the repository's own suite", message)
        self.assertIn("fail first", message)
        # And it does not drop an empty list into the middle of the instruction.
        self.assertNotIn("write a test under  with write_file", message)
        self.assertNotIn("write a test under", message)

    def test_both_wordings_still_say_how_to_run_it_and_what_a_red_is_not(self):
        for globs in (["tests/own/**"], []):
            message = a_refusal(globs)
            self.assertIn("run_tests", message)
            self.assertIn("exit 2", message)


if __name__ == "__main__":
    unittest.main()
