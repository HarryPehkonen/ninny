"""The task's own runner has to report a test it can see failing as a red.

`verify-task` shipped with two controls, and both grade the ORACLE: RED on the stub tree,
GREEN on the answer key. Neither one ever runs the task's own `test_cmd` against a case it can
see failing, and that blind spot is n=2:

  * `tasks/bits` refused the edit the task required (protected_globs), and
  * `tasks/intset` reported a genuine red as exit 2 "nothing ran", because its build-error
    grep matched cargo's `error: test failed, to rerun pass ...`.

Both passed every static control for weeks. Both were found by spending money on a model.

The third control closes it: plant a test that cannot pass, run the task's own test command,
and require **1** -- ran and failed. A 2 there means the runner misreports a red as a build
error; a 0 means the suite cannot see a red at all.

The dataset matters, and the first attempt got it wrong: sabotaging the ANSWER KEY does not
work, because the answer key carries no suite (the agent writes that), so `test_cmd` on it
correctly answers 2 and the control asks the runner nothing. Measured on four real tasks.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ninny import cli

# The contract, honoured: a planted failing case comes back as 1.
HONEST_RUNNER = """#!/usr/bin/env bash
if [ -f tests_planted.txt ]; then
  echo "FAIL the instrument reports a red"
  exit 1
fi
echo "nothing planted yet"
exit 0
"""

# The intset shape: a real red, reported as "nothing ran".
LYING_RUNNER = """#!/usr/bin/env bash
if [ -f tests_planted.txt ]; then
  echo "BUILD FAILED -- the suite did not compile, so nothing ran."
  exit 2
fi
echo "nothing planted yet"
exit 0
"""

# Green no matter what is planted.
DEAF_RUNNER = """#!/usr/bin/env bash
echo "all good"
exit 0
"""

# cwd = the staging directory, like oracle_cmd, so a recipe can reach into tree/.
PROBE = """#!/usr/bin/env bash
set -eu
printf 'FAIL the instrument reports a red\\n' > tree/tests_planted.txt
"""

NO_OP_PROBE = """#!/usr/bin/env bash
true
"""

FAILED_PROBE = """#!/usr/bin/env bash
exit 3
"""

TASK_TOML = """name = "probe"
spec_file = "SPEC.md"
tree = "tree"
test_cmd = "bash run_own.sh"
oracle = "oracle"
oracle_cmd = "bash oracle/gate.sh"
fixed_tree = "fixed"
{probe}
"""

ORACLE = """#!/usr/bin/env bash
echo "checking x.py"
grep -q 'value = 1' "$NINNY_TREE/src/x.py"
"""


def build(root: Path, *, runner=HONEST_RUNNER, probe=PROBE, probe_cmd=True) -> Path:
    (root / "tree" / "src").mkdir(parents=True)
    (root / "tree" / "src" / "x.py").write_text("value = 0\n")
    (root / "tree" / "run_own.sh").write_text(runner)
    (root / "SPEC.md").write_text("make x.py hold 1\n")
    (root / "oracle").mkdir()
    (root / "oracle" / "gate.sh").write_text(ORACLE)
    (root / "oracle" / "probe.sh").write_text(probe)
    (root / "fixed" / "src").mkdir(parents=True)
    (root / "fixed" / "src" / "x.py").write_text("value = 1\n")
    (root / "task.toml").write_text(
        TASK_TOML.format(probe='probe_cmd = "bash oracle/probe.sh"' if probe_cmd else "")
    )
    return root


class RunnerTruthTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "task"
        self.root.mkdir()
        self._env = mock.patch.dict(
            os.environ, {"NINNY_LOG_DIR": str(Path(self._tmp.name) / "logs")}
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def verify(self) -> tuple[int, str]:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["verify-task", "--task", str(self.root),
                             "--out", str(Path(self._tmp.name) / "checks")])
        return code, buf.getvalue()

    def test_an_honest_runner_passes_the_third_control(self):
        build(self.root)
        code, out = self.verify()
        self.assertEqual(code, 0, out)
        self.assertIn("VERIFIED", out)
        self.assertIn("planted failing test", out)

    def test_a_runner_that_calls_a_red_nothing_ran_is_a_broken_task(self):
        build(self.root, runner=LYING_RUNNER)
        code, out = self.verify()
        self.assertEqual(code, 1, out)
        self.assertIn("BROKEN TASK", out)
        self.assertIn("misreports a red", out)

    def test_a_runner_that_cannot_see_a_red_is_a_broken_task(self):
        build(self.root, runner=DEAF_RUNNER)
        code, out = self.verify()
        self.assertEqual(code, 1, out)
        self.assertIn("BROKEN TASK", out)
        self.assertIn("cannot see a red", out)

    def test_a_probe_recipe_that_plants_nothing_is_caught(self):
        build(self.root, probe=NO_OP_PROBE)
        code, out = self.verify()
        # A no-op recipe plants nothing and the honest runner is then green: that is a finding
        # about the recipe, and the message must not blame the runner for it.
        self.assertIn("cannot see a red", out)
        self.assertIn("planted failing test", out)

    def test_a_probe_recipe_that_fails_loudly_is_caught(self):
        build(self.root, probe=FAILED_PROBE)
        code, out = self.verify()
        self.assertEqual(code, 1, out)
        self.assertIn("did not land", out)

    def test_without_a_recipe_the_task_still_verifies_and_says_so(self):
        build(self.root, probe_cmd=False)
        code, out = self.verify()
        self.assertEqual(code, 0, out)
        self.assertIn("VERIFIED", out)
        self.assertIn("no probe_cmd", out)
        self.assertIn("did not run", out)

    def test_the_probe_never_touches_the_task_on_disk(self):
        build(self.root)
        self.verify()
        self.assertFalse((self.root / "tree" / "tests_planted.txt").exists())


if __name__ == "__main__":
    unittest.main()