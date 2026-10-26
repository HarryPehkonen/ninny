"""The reported test count: the number that makes a shrinking suite visible.

The count appears in observation text today, so a reader can only see it by reading prose.
Every trap this closes is about a suite that got SMALLER without anyone noticing: a CMake
test list that stops compiling an unbuilt file, a Node test file that loads but asserts
nothing, a runner whose discovery silently matches one file instead of six.

The convention is one line a task's own runner prints:

    NINNY_TESTS: 12

It is optional -- a runner that prints nothing loses the number, not the run -- and it is
never compared against anything. It is recorded, and the model is told it, because a
number the model can see is a number it can act on.
"""

import unittest

from ninny.env import Observation, describe_test_exit, reported_test_count


class ReportedTestCountTests(unittest.TestCase):
    def test_a_runner_that_prints_the_count_is_read(self):
        output = "ok 1 - a\nok 2 - b\n# tests 2\nNINNY_TESTS: 2\n"
        self.assertEqual(2, reported_test_count(output))

    def test_a_runner_that_does_not_print_it_reports_nothing(self):
        self.assertIsNone(reported_test_count("ok 1 - a\n# tests 1\n"))
        self.assertIsNone(reported_test_count(""))

    def test_the_last_line_wins_when_a_suite_prints_more_than_once(self):
        self.assertEqual(7, reported_test_count("NINNY_TESTS: 3\nnoise\nNINNY_TESTS: 7\n"))

    def test_a_malformed_line_is_not_a_number(self):
        # A count has to be a count. Prose next to the prefix is not evidence.
        for text in (
            "NINNY_TESTS: many\n",
            "NINNY_TESTS:\n",
            "NINNY_TESTS: -1\n",
            "NINNY_TESTS=12\n",
            "see NINNY_TESTS: 12 above\n",
        ):
            self.assertIsNone(reported_test_count(text), text)

    def test_zero_is_a_number_and_it_is_the_interesting_one(self):
        self.assertEqual(0, reported_test_count("NINNY_TESTS: 0\n"))

    def test_the_sentence_the_model_reads_names_the_count(self):
        said = describe_test_exit(0, "bash tools/run_own_tests.sh", tests=12)
        self.assertIn("tests PASSED", said)
        self.assertIn("12", said)

    def test_the_sentence_says_nothing_about_a_count_it_does_not_have(self):
        self.assertNotIn("cases", describe_test_exit(1, "bash tools/run_own_tests.sh"))

    def test_an_observation_carries_the_count_apart_from_its_exit_code(self):
        self.assertIsNone(Observation(ok=True, exit_code=0, output="no count here").tests)


if __name__ == "__main__":
    unittest.main()
