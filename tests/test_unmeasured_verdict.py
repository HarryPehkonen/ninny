"""`unmeasured`, not `no-tests`, when nothing declared which paths are tests.

harrisbook post 35, finding 2: a repository run without `--test-glob` had its step-12 write -- the test
file, `tools/tests/test_route.py` -- shown labelled as its FIRST SOURCE WRITE, and the run was graded
`no-tests`. The behaviour was defensible; the label was not. `no-tests` reads as "the model wrote no
test", which was false here.

The distinction is the declaration, not the door. A benchmark task declares `test_globs`, so "you wrote
no test file" is a measurement. A repository run declares none unless the caller passes `--test-glob`,
so no write can be classified at all -- and then the honest word is `unmeasured`.
"""

import unittest

from ninny.tdd import TDDPolicy, TDDState


class FakeTask:
    def __init__(self, test_globs, require_test_file=False):
        self.test_globs = test_globs
        self.require_test_file = require_test_file
        self.src_globs = ["**"]


class TheWordWhenNothingWasDeclared(unittest.TestCase):
    def state(self, globs: bool) -> TDDState:
        return TDDState(mode="request", globs_declared=globs)

    def test_a_run_that_declared_no_globs_is_unmeasured(self):
        st = self.state(False)
        st.write_steps.append([12, "tools/tests/test_route.py"])
        self.assertEqual(st.verdict(), "unmeasured")

    def test_a_benchmark_that_wrote_no_test_file_still_says_no_tests(self):
        st = self.state(True)
        st.write_steps.append([4, "src/roman.cpp"])
        self.assertEqual(st.verdict(), "no-tests")

    def test_nothing_written_is_still_no_write(self):
        self.assertEqual(self.state(False).verdict(), "no-write")

    def test_the_state_learns_the_declaration_from_the_task(self):
        self.assertFalse(TDDPolicy("request", FakeTask([]), ".").new_state().globs_declared)
        self.assertTrue(
            TDDPolicy("request", FakeTask(["tests/own/**"]), ".").new_state().globs_declared)

    def test_a_double_that_says_nothing_keeps_the_benchmark_default(self):
        class Bare(FakeTask):
            pass

        task = Bare(["tests/*"])
        del task.test_globs
        self.assertTrue(TDDPolicy("request", task, ".").new_state().globs_declared)

    def test_the_word_reaches_the_record(self):
        st = self.state(False)
        st.write_steps.append([12, "a.py"])
        self.assertEqual(st.as_dict()["verdict"], "unmeasured")


if __name__ == "__main__":
    unittest.main()
