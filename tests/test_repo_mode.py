"""`ninny run --repo`: the same run loop pointed at a working copy.

A benchmark task is a fixture with an oracle. A repository is neither, and four fields carry the
difference: no oracle directory, no test globs until they are declared, every path is the work,
and the red does not have to come from a test file the model wrote. The gate, the exit-code
contract, the record and `ninny verdict` are the same code the benchmarks run on.

Two traps live here, both of the shape this repository has a lesson about -- a rule that can
never be satisfied is indistinguishable from a broken harness:

- With `src_globs = ["**"]`, a write is refused until a red is seen. On a repository whose suite
  is GREEN, that is a deadlock: every way to make a red is itself a write. Hence `request` as the
  default for a repository, and `enforce` once `--test-glob` says which paths are the tests.
- With `require_test_file = True`, `first_test_step` can only be set by a write under a test
  glob. With none declared, `red_ok` would be false forever and every record would say
  `no-tests`. Hence `require_test_file = False` here, `True` for a benchmark.
"""

import subprocess
import tempfile
import unittest
from dataclasses import fields, replace
from pathlib import Path

from ninny.actions import Action
from ninny.cli import (build_parser, cmd_run, default_tdd_for, stage_worktree,
                       write_worktree_diff)
from ninny.config import ConfigError, Task, repo_task
from ninny.tdd import TDDPolicy
from ninny.verdict import EXIT_ARTIFACT, EXIT_UNPROVEN, verdict_of


def a_repo(directory: Path) -> Path:
    """A real repository with one commit, because staging is a worktree of it."""
    directory.mkdir(parents=True, exist_ok=True)

    def git(*argv):
        return subprocess.run(argv, cwd=directory, check=True, capture_output=True)

    def commit(message):
        git("git", "-c", "user.email=p@x", "-c", "user.name=probe", "commit", "-q",
            "--allow-empty", "-m", message)

    git("git", "init", "-q", "-b", "main", ".")
    commit("one")
    (directory / "app.py").write_text("print('hello')\n")
    (directory / "tests").mkdir(exist_ok=True)
    (directory / "tests" / "test_app.py").write_text("def test_one():\n    assert False\n")
    git("git", "add", "-A")
    commit("two")
    return directory


def write(policy: TDDPolicy, state, path: str, suspect: str = "") -> bool:
    """Whether the gate lets this write through: '' means allowed."""
    return policy.gate(Action(name="write_file", args={"path": path, "content": "x"}),
                       state, 1, suspect) == ""


class TheRepoConstructor(unittest.TestCase):
    def test_it_is_a_task_with_no_fixture_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            task = repo_task(repo, "add a flag", "python3 -m unittest")
            self.assertEqual(task.name, "myapp")
            self.assertEqual(task.tree_src, repo)
            self.assertIsNone(task.oracle_dir)          # nothing to stage, nothing to hide
            self.assertIsNone(task.oracle_cmd)
            self.assertEqual(task.test_cmd, "python3 -m unittest")
            self.assertEqual(task.test_globs, [])       # not guessed
            self.assertEqual(task.src_globs, ["**"])    # the whole working copy is the work
            self.assertEqual(task.protected_globs, [])
            self.assertEqual(task.preflight, [])

    def test_the_main_repo_is_bound_into_the_sandbox(self):
        """Measured, not assumed: a worktree's .git is a FILE pointing at the main repository,
        so `git rev-parse HEAD` inside bwrap fails without this bind. Read-only is enough for
        status, diff and log; add/commit fail cleanly, which is the delegate's business."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            self.assertEqual(repo_task(repo, "s", "t").sandbox_binds, [str(repo)])

    def test_the_red_does_not_have_to_come_from_the_models_own_test_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            self.assertFalse(repo_task(repo, "s", "t").require_test_file)
            # And a benchmark still says True, by default, so nothing about the measured
            # benchmark numbers changes.
            benchmark = next(field for field in fields(Task) if field.name == "require_test_file")
            self.assertIs(benchmark.default, True)

    def test_it_refuses_a_directory_that_is_not_a_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                repo_task(Path(tmp) / "absent", "s", "t")
            (Path(tmp) / "plain").mkdir()
            with self.assertRaises(ConfigError):
                repo_task(Path(tmp) / "plain", "s", "t")

    def test_it_refuses_an_empty_test_command_rather_than_guessing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            with self.assertRaises(ConfigError):
                repo_task(repo, "s", "")


class WhatCountsAsARed(unittest.TestCase):
    def policy(self, repo: Path, **kwargs) -> TDDPolicy:
        return TDDPolicy(kwargs.pop("mode", "enforce"), repo_task(repo, "s", "t", **kwargs), repo)

    def test_a_failing_run_is_enough_in_a_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            state = self.policy(repo).new_state()
            state.red_step, state.red_exit = 7, 1
            self.assertTrue(state.red_ok)          # the suite that was already there
            self.assertTrue(state.red_before_code)

    def test_the_same_run_is_not_enough_in_a_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            task = replace(repo_task(repo, "s", "t"), require_test_file=True)
            state = TDDPolicy("enforce", task, repo).new_state()
            state.red_step, state.red_exit = 7, 1
            self.assertFalse(state.red_ok)         # no test file of the model's own
            state.first_test_step = 6
            self.assertTrue(state.red_ok)          # now there is something to fail

    def test_the_rule_travels_in_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            self.assertIs(self.policy(repo).new_state().as_dict()["require_test_file"], False)


class TheGateOnARealRepository(unittest.TestCase):
    def test_a_declared_test_path_is_writable_before_the_red(self):
        """`src_globs` is ["**"], so the only thing keeping a repository's own tests editable
        before the red is that a test path is never counted as a source path."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            policy = self.policy(repo, test_globs=["tests/**"])
            state = policy.new_state()
            self.assertTrue(write(policy, state, "tests/test_app.py"))
            self.assertTrue(write(policy, state, "tests/test_new.py"))
            self.assertFalse(write(policy, state, "app.py"))

    def test_the_red_opens_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            policy = self.policy(repo, test_globs=["tests/**"])
            state = policy.new_state()
            state.red_step, state.red_exit = 1, 1
            self.assertTrue(write(policy, state, "app.py"))

    def test_a_write_outside_the_worktree_is_refused_even_after_a_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            policy = self.policy(repo, test_globs=["tests/**"])
            state = policy.new_state()
            state.red_step, state.red_exit = 1, 1
            self.assertFalse(write(policy, state, "../outside.py"))

    def policy(self, repo: Path, **kwargs) -> TDDPolicy:
        return TDDPolicy("enforce", repo_task(repo, "s", "t", **kwargs), repo)


class TheRepoDoorOnTheCommandLine(unittest.TestCase):
    """The flags, and the one rule that keeps `enforce` from deadlocking a green repository."""

    def args_for(self, *extra: str):
        return build_parser().parse_args(["run", "--model", "some/model", *extra])

    def test_the_flags_exist_and_carry_what_they_say(self):
        args = self.args_for("--repo", "/tmp/r", "--prompt", "do a thing", "--test-cmd", "ctest",
                             "--test-glob", "tests/**", "--test-glob", "**/*_test.py")
        self.assertEqual(args.repo, "/tmp/r")
        self.assertEqual(args.prompt, "do a thing")
        self.assertEqual(args.test_cmd, "ctest")
        self.assertEqual(args.test_glob, ["tests/**", "**/*_test.py"])
        self.assertIsNone(args.tdd)  # nothing was said, so the mode is a decision, not a default

    def test_a_task_still_defaults_to_request(self):
        self.assertEqual(default_tdd_for(False, None), "request")

    def test_a_repository_without_declared_tests_defaults_to_request(self):
        """Not a fallback: `enforce` here refuses every write until a red is seen, and on a
        green suite the only way to make a red is a write. A deadlock, not strictness."""
        self.assertEqual(default_tdd_for(True, None), "request")
        self.assertEqual(default_tdd_for(True, []), "request")

    def test_a_repository_with_declared_tests_defaults_to_enforce(self):
        self.assertEqual(default_tdd_for(True, ["tests/**"]), "enforce")

    def test_the_two_doors_are_refused_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            args = self.args_for("--repo", str(repo), "--task", str(repo),
                                 "--prompt", "p", "--test-cmd", "t")
            with self.assertRaises(ConfigError):
                cmd_run(args)

    def test_a_repository_without_a_prompt_is_refused_before_anything_is_spent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            with self.assertRaises(ConfigError):
                cmd_run(self.args_for("--repo", str(repo), "--test-cmd", "t"))

    def test_a_repository_without_a_test_command_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            with self.assertRaises(ConfigError):
                cmd_run(self.args_for("--repo", str(repo), "--prompt", "p"))

    def test_both_prompt_spellings_at_once_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            args = self.args_for("--repo", str(repo), "--prompt", "p", "--prompt-file", "f",
                                 "--test-cmd", "t")
            with self.assertRaises(ConfigError):
                cmd_run(args)

    def test_staging_is_a_worktree_at_head_and_the_repo_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            workdir = Path(tmp) / "run" / "tree"
            stage_worktree(repo, workdir)
            self.assertTrue((workdir / "app.py").is_file())
            self.assertTrue((workdir / ".git").is_file())  # a FILE; the main repo holds the rest

            def head(where):
                return subprocess.run(["git", "-C", str(where), "rev-parse", "HEAD"],
                                      capture_output=True, text=True).stdout.strip()

            self.assertEqual(head(workdir), head(repo))
            (workdir / "app.py").write_text("print('changed')\n")
            self.assertIn("hello", (repo / "app.py").read_text())

    def test_a_staging_failure_is_a_clean_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plain").mkdir()
            with self.assertRaises(ConfigError):
                stage_worktree(Path(tmp) / "plain", Path(tmp) / "run" / "tree")


class HowARepositoryRecordIsGraded(unittest.TestCase):
    """The same verdict, on a record whose suite was the model's to extend."""

    def record(self, **overrides):
        tdd = {
            "verdict": "red-first",
            "test_files": ["tests/test_app.py"],
            "first_test_step": 1,
            "first_src_step": 4,
            "red_step": 3,
            "red_exit": 1,
            "red_before_code": True,
            "green_after_last_write": True,
            "suite_frozen_since_red": True,
            "bypass_detected": [],
            "harness_runs": [],
        }
        tdd.update(overrides)
        return {"exit_status": "Submitted", "steps": 9, "cost_usd": 0.01, "tdd": tdd}

    def test_a_repository_that_extended_its_suite_after_the_red_is_still_the_artifact(self):
        code, line = verdict_of(self.record(require_test_file=False,
                                            suite_frozen_since_red=False))
        self.assertEqual(code, EXIT_ARTIFACT)
        self.assertEqual(line["verdict"], "artifact")
        self.assertIs(line["suite_frozen_since_red"], False)  # reported, not required
        self.assertIs(line["require_test_file"], False)

    def test_a_benchmark_that_did_the_same_is_unproven(self):
        code, line = verdict_of(self.record(suite_frozen_since_red=False))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertIn("not the suite that went red", "; ".join(line["reasons"]))

    def test_every_applicable_reason_shows_up_together(self):
        """Two here, not three: a repository record is not refused for its order, so the red
        clause does not fire. The other two do, and both are named."""
        code, line = verdict_of(self.record(require_test_file=False, red_before_code=False,
                                            green_after_last_write=False,
                                            bypass_detected=[[7, "src/a.py"]]))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertEqual(len(line["reasons"]), 2)
        self.assertIn("no green observed", "; ".join(line["reasons"]))
        self.assertIn("went round the tools", "; ".join(line["reasons"]))

    def test_a_benchmark_gets_all_three(self):
        code, line = verdict_of(self.record(require_test_file=True, red_before_code=False,
                                            green_after_last_write=False,
                                            bypass_detected=[[7, "src/a.py"]]))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertEqual(len(line["reasons"]), 3)


class ThePatchIsTheDelegatesWork(unittest.TestCase):
    """The defect the first repository run found, in its own numbers: 30.8 MB, 2,224 file headers,
    482,462 removed lines, for a change of ten lines. `write_diff` compared the live tree against
    the worktree, so anything the live tree had and a fresh checkout did not -- my own README
    commit landing mid-run, every gitignored file on disk -- read as the delegate deleting it."""

    def test_it_names_the_edits_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            workdir = Path(tmp) / "run" / "tree"
            base = stage_worktree(repo, workdir)

            # A commit lands in the live repo while the run is going: not the delegate's work.
            (repo / "moved_on.py").write_text("committed elsewhere\n")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=p@x", "-c", "user.name=p",
                            "commit", "-q", "-m", "mid-run"], check=True, capture_output=True)
            # And the live tree has gitignored residue a fresh worktree does not.
            (repo / "residue.bin").write_text("x" * 5000)
            (repo / ".gitignore").write_text("residue.bin\n")

            (workdir / "app.py").write_text("print('changed')\n")   # an edit
            (workdir / "tests" / "test_new.py").write_text("def test_new():\n    assert True\n")

            patch_path = Path(tmp) / "diff.patch"
            write_worktree_diff(workdir, base, patch_path)
            patch = patch_path.read_text()

            self.assertIn("app.py", patch)                 # the edit
            self.assertIn("test_new.py", patch)            # the new file, staged first
            self.assertNotIn("moved_on.py", patch)         # the live tree's commit, not its work
            self.assertNotIn("residue.bin", patch)         # gitignored residue
            self.assertLess(len(patch), 4000, "a ten-line change is not a 30 MB patch")

    def test_the_stat_line_describes_the_same_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = a_repo(Path(tmp) / "myapp")
            workdir = Path(tmp) / "run" / "tree"
            base = stage_worktree(repo, workdir)
            (workdir / "app.py").write_text("print('changed')\n")
            stat = write_worktree_diff(workdir, base, Path(tmp) / "d.patch")
            self.assertIn("1 file changed", stat)
            self.assertIn("1 insertion(+)", stat)


class HowARepositoryRecordIsGradedOnTheHandback(unittest.TestCase):
    """A repository run keeps its order in the record; it is not refused for it."""

    def record(self, **overrides):
        tdd = {
            "verdict": "red-after-code",
            "test_files": [],
            "first_test_step": None,
            "first_src_step": 9,
            "red_step": 12,
            "red_exit": 1,
            "red_before_code": False,
            "green_after_last_write": True,
            "suite_frozen_since_red": None,
            "bypass_detected": [],
            "harness_runs": [[13, 0]],
            "require_test_file": False,
        }
        tdd.update(overrides)
        return {"exit_status": "Submitted", "steps": 14, "cost_usd": 0.004, "tdd": tdd}

    def test_a_repository_run_that_never_saw_a_red_can_still_be_the_artifact(self):
        code, line = verdict_of(self.record())
        self.assertEqual(code, EXIT_ARTIFACT)
        self.assertEqual(line["verdict"], "artifact")
        self.assertEqual(line["order"], "red-after-code")   # reported, not a refusal
        self.assertEqual(line["reasons"], [])

    def test_but_not_when_nothing_observed_the_tree_being_handed_back(self):
        """The first repository run, exactly: submitted, never ran the suite."""
        code, line = verdict_of(self.record(green_after_last_write=None, harness_runs=[],
                                            red_step=None, red_before_code=False))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertEqual(len(line["reasons"]), 1)
        self.assertIn("no green observed after the last source write", line["reasons"][0])

    def test_a_benchmark_is_still_held_to_its_order(self):
        code, line = verdict_of(self.record(require_test_file=True))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertIn("no red before the first source write", "; ".join(line["reasons"]))

    def test_a_bypass_is_still_a_refusal_for_a_repository(self):
        code, line = verdict_of(self.record(bypass_detected=[[11, "app.py"]]))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertIn("went round the tools", "; ".join(line["reasons"]))


if __name__ == "__main__":
    unittest.main()
