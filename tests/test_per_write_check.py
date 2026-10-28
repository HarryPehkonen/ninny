"""The declared check, run after a write, without being asked.

The model pays a step to learn what a compiler says. The harness pays seconds and none. What makes
this language-agnostic is what it does NOT do: it reads the exit code and nothing else. Ninny never
parses a toolchain's output -- parsing compiler text is where "any language" dies.
"""
import unittest
from pathlib import Path

from ninny.config import load_task
from ninny.runner import task_check_cmd
from ninny.tdd import CHEAP_CHECK_TIMEOUT, TDDState, cheap_check_line, run_one

TASKS = Path(__file__).resolve().parent.parent / "tasks"


class RunOneTests(unittest.TestCase):
    def test_a_passing_command_reports_zero(self):
        code, seconds = run_one("true", Path("."), 30)
        self.assertEqual(code, 0)
        self.assertGreaterEqual(seconds, 0.0)

    def test_a_failing_command_reports_its_own_exit_code(self):
        self.assertEqual(run_one("exit 3", Path("."), 30)[0], 3)

    def test_a_command_that_never_started_is_127_not_a_failure(self):
        self.assertEqual(run_one("definitely-not-a-real-command-xyz", Path("."), 30)[0], 127)

    def test_a_command_that_was_cut_off_is_124(self):
        self.assertEqual(run_one("sleep 5", Path("."), 1)[0], 124)

    def test_the_cap_is_small_because_the_point_is_that_it_is_cheap(self):
        self.assertLessEqual(CHEAP_CHECK_TIMEOUT, 60)


class TheLineTests(unittest.TestCase):
    def test_the_line_carries_the_exit_code_and_the_time(self):
        line = cheap_check_line(1, 4.2)
        self.assertIn("exit 1", line)
        self.assertIn("4.2s", line)

    def test_the_line_is_one_line_and_short(self):
        line = cheap_check_line(0, 0.4)
        self.assertNotIn("\n", line)
        self.assertLess(len(line), 80)


class DeclarationTests(unittest.TestCase):
    def test_a_task_without_a_declared_check_declares_nothing(self):
        # Honest absence: a toolchain with no build step says so by saying nothing.
        self.assertIsNone(task_check_cmd(load_task(TASKS / "roman")))

    def test_a_task_that_declares_one_reports_it(self):
        self.assertTrue(task_check_cmd(load_task(TASKS / "nasm-sum")))


class TheRecordTests(unittest.TestCase):
    def test_the_record_has_a_place_for_what_was_observed(self):
        state = TDDState(mode="request")
        self.assertEqual(state.as_dict()["checks"], [])
        state.checks.append([7, 0, 4.1])
        self.assertEqual(state.as_dict()["checks"], [[7, 0, 4.1]])
