"""Two labels that claim more than the harness knows, when no test globs were declared.

harrisbook post 35, finding 2, asked for the verdict word, and `unmeasured` was the answer to that. This is
the label sitting beside it, found in a live repository run (`NameGenerator`, arm `ng-utf8-1`): the run's
step-12 write was `tests/test_char_length.py`, and the record called it `first_src_step: 12`.

The cause is not a wrong classification, it is the absence of a definition. `is_test_path` returns False for
every path when the task declares no test globs, while a repository task sets `src_globs = ["**"]` -- every
path is the work -- so every write falls through to the source branch and the FIRST write becomes the first
source step, whatever it happened to be. With no way to tell a test from a source, the honest record has
neither label, and it already says why in `globs_declared`.

`last_src_step` is deliberately NOT gated: it is a timing fact ("the last write"), it drives the staleness
rule, and it is true whatever the write was.

The fixture is the REAL `Task` rather than a double, because the defect lives in the interaction between two
real globs lists -- and the constructor that produces them is asserted directly.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.config import Task, repo_task
from ninny.tdd import TDDPolicy, snapshot


def make_task(globs: list[str], tmp: str) -> Task:
    return Task(
        root=Path(tmp), name="fixture", spec="", tree_src=Path(tmp), oracle_dir=None,
        test_cmd="true", oracle_cmd=None, test_globs=globs, src_globs=["**"],
        preflight=[], step_limit=10, timeout_s=1, test_timeout_s=1,
        require_test_file=False,
    )


class Write:
    name = "write_file"

    def __init__(self, path):
        self.path = path


class Ok:
    ok = True
    exit_code = 0


def policy(test_globs: list[str], workdir: str) -> TDDPolicy:
    return TDDPolicy("request", make_task(test_globs, workdir), workdir)


class TheRepositoryDoorDeclaresNoTestGlobs(unittest.TestCase):
    """The premise of every test below, asserted against the constructor that produces it."""

    def test_repo_task_declares_no_test_globs_and_every_path_as_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
            (Path(tmp) / "a.txt").write_text("x\n")
            subprocess.run(["git", "-C", tmp, "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", tmp, "-c", "user.email=h@localhost", "-c", "user.name=h",
                            "commit", "-qm", "init"], check=True, capture_output=True)
            task = repo_task(tmp, "a spec", "true")
            self.assertEqual(task.test_globs, [])
            self.assertEqual(task.src_globs, ["**"])
            self.assertFalse(task.require_test_file)


class NoGlobsMeansNoClassification(unittest.TestCase):
    def test_the_tree_snapshot_can_see_a_repository(self):
        """`src_globs=["**"]` must resolve to the whole tree, or the reconciliation is dead.

        `snapshot` strips a trailing "/**" to find its root; a bare "**" is left as the base, so it
        looked inside a directory literally named "**" and saw nothing. A repository run's tree
        reconciliation therefore never noticed a write it exists to notice.
        """
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            (Path(tmp) / "src" / "a.cpp").write_text("one\n")
            self.assertIn("src/a.cpp", snapshot(Path(tmp), ["**"]))

    def test_a_repository_write_is_not_called_a_source_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol = policy([], tmp)
            state = pol.new_state()
            pol.observe(Write("tests/test_char_length.py"), Ok(), state, 12)
            self.assertIsNone(state.first_src_step,
                              "no globs were declared, so nothing may be called a source")
            self.assertIsNone(state.first_test_step)

    def test_the_write_is_still_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol = policy([], tmp)
            state = pol.new_state()
            pol.observe(Write("tests/test_char_length.py"), Ok(), state, 12)
            self.assertEqual(state.write_steps, [[12, "tests/test_char_length.py"]],
                             "the write itself is a fact and must survive")

    def test_a_benchmark_still_labels_its_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol = policy(["tests/own/**"], tmp)
            state = pol.new_state()
            pol.observe(Write("src/roman.cpp"), Ok(), state, 4)
            self.assertEqual(state.first_src_step, 4)

    def test_a_benchmark_still_separates_a_test_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol = policy(["tests/own/**"], tmp)
            state = pol.new_state()
            pol.observe(Write("tests/own/test_x.py"), Ok(), state, 3)
            self.assertEqual(state.first_test_step, 3)
            self.assertIsNone(state.first_src_step)

    def test_the_tree_reconciliation_does_not_label_either(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            (Path(tmp) / "src" / "a.cpp").write_text("one\n")
            pol = policy([], tmp)
            state = pol.new_state()
            (Path(tmp) / "src" / "a.cpp").write_text("two\n")
            pol.observe_tree(state, 9)
            self.assertIsNone(state.first_src_step,
                              "a changed file is not a source file when nothing defined sources")
            self.assertEqual(state.last_src_step, 9, "the last write is still a timing fact")

    def test_the_tree_reconciliation_still_labels_a_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            (Path(tmp) / "src" / "a.cpp").write_text("one\n")
            task = make_task(["tests/own/**"], tmp)
            task.src_globs = ["src/**"]
            pol = TDDPolicy("request", task, tmp)
            state = pol.new_state()
            (Path(tmp) / "src" / "a.cpp").write_text("two\n")
            pol.observe_tree(state, 9)
            self.assertEqual(state.first_src_step, 9)

    def test_the_record_says_the_classification_was_never_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = policy([], tmp).new_state()
            self.assertFalse(state.as_dict()["globs_declared"])


if __name__ == "__main__":
    unittest.main()
