"""The adapter as a config, tested against what the toolchains actually said.

`tests/fixtures/runners/*.txt` are real transcripts, captured by `capture.sh` from the
hand-written adapters in four states: nothing to run, one planted failing test, one planted
passing test, and a suite that does not compile. Each fixture names the exit code its adapter
returned.

This test renders each task's `[runner]` table into a script, replays every fixture through the
RENDERED script, and requires it to answer exactly what the hand-written one answered. That is
the whole equivalence argument: same transcripts, same verdicts, no compiler in the loop.

The replay seam belongs to the rendered script (`NINNY_RUNNER_REPLAY`), so what is tested here
is the artifact that runs in a sandbox -- not a Python mirror of it that could drift.
"""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from ninny.config import load_task
from ninny.runner import config_for, drift, render

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "runners"

# What each state means. A state may not disagree with itself: this is the contract, not a
# preference, and a hand-written adapter that answered otherwise would be a finding.
EXPECTED = {"empty": 2, "emptyish": 2, "red": 1, "green": 0, "broken": 2}
COUNTED = ("red", "green")


def load_fixture(path: Path) -> tuple[str, str, int]:
    text = path.read_text()
    task = re.search(r"^# task:\s*(\S+)$", text, re.M)
    state = re.search(r"^# state:\s*(\S+)$", text, re.M)
    rc = re.search(r"^# rc:\s*(\d+)$", text, re.M)
    assert task and state and rc, f"{path} is not a capture"
    return task.group(1), state.group(1), int(rc.group(1))


def fixtures() -> list[tuple[Path, str, str, int]]:
    if not FIXTURES.is_dir():
        return []
    out = []
    for path in sorted(FIXTURES.glob("*.txt")):
        task, state, rc = load_fixture(path)
        out.append((path, task, state, rc))
    return out


class RunnerConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def rendered(self, task: str) -> Path:
        config = config_for(load_task(REPO / "tasks" / task).meta)
        self.assertIsNotNone(config, f"{task} declares no [runner]")
        script = self.tmp / f"{task}.sh"
        script.write_text(render(config))
        return script

    def replay(self, script: Path, fixture: Path, rc: int) -> tuple[int, str]:
        env = dict(os.environ, NINNY_RUNNER_REPLAY=str(fixture), NINNY_RUNNER_REPLAY_RC=str(rc))
        done = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
        return done.returncode, done.stdout + done.stderr

    # The hand-written adapters this change replaces. A disagreement here is a FINDING, not a
    # failure of the fixtures: it is the defect the config exists to stop repeating. Exactly one
    # is known, and it is the reason the layer was rebuilt.
    KNOWN_DEFECTS = {
        ("roman", "broken"): "unittest's synthetic _FailedTest counts as one test, so an "
                             "unimportable suite answers 1 (a red) instead of 2 (nothing ran)",
    }

    def test_the_hand_written_adapters_are_wrong_in_exactly_the_known_way(self):
        """A state that disagrees with the contract is a finding; an unlisted one is a surprise."""
        seen = 0
        found = {}
        for path, task, state, rc in fixtures():
            self.assertIn(state, EXPECTED, f"{path}: unknown state")
            seen += 1
            if rc != EXPECTED[state]:
                found[(task, state)] = rc
        self.assertGreater(seen, 0, "no fixtures: run tests/fixtures/runners/capture.sh")
        self.assertEqual(
            set(found), set(self.KNOWN_DEFECTS),
            f"the hand-written adapters disagree with the contract in an unrecorded way: {found}",
        )
        for key, rc in found.items():
            self.assertEqual(rc, 1, f"{key}: only a red-as-not-a-red is expected, got {rc}")

    def test_the_rendered_adapter_answers_the_contract(self):
        """Same transcript in, the contract's exit code out, for every task and state."""
        for path, task, state, rc in fixtures():
            with self.subTest(task=task, state=state):
                code, out = self.replay(self.rendered(task), path, rc)
                self.assertEqual(
                    code, EXPECTED[state],
                    f"{task}/{state}: rendered answered {code}, the contract says "
                    f"{EXPECTED[state]}\n{out}",
                )

    def test_the_count_is_reported_when_cases_ran_and_is_zero_when_they_did_not(self):
        for path, task, state, rc in fixtures():
            with self.subTest(task=task, state=state):
                _, out = self.replay(self.rendered(task), path, rc)
                found = re.search(r"^NINNY_TESTS: (\d+)$", out, re.M)
                self.assertIsNotNone(found, f"{task}/{state}: no count line\n{out}")
                count = int(found.group(1))
                if state in COUNTED:
                    self.assertGreaterEqual(count, 1, f"{task}/{state}: {count} cases ran")
                else:
                    self.assertEqual(count, 0, f"{task}/{state}: nothing ran, so no cases")

    def test_every_task_that_declares_a_config_can_be_rendered_twice_the_same(self):
        for task in sorted(p.name for p in (REPO / "tasks").iterdir() if p.is_dir()):
            config = config_for(load_task(REPO / "tasks" / task).meta)
            if config is None:
                continue
            with self.subTest(task=task):
                self.assertEqual(render(config), render(config))

    def test_the_rendered_script_carries_the_contract_and_the_tasks_own_words(self):
        """The prose is the onboarding: it was measured to teach the arms, so it must survive."""
        for task in ("roman", "intset", "bits"):
            text = render(config_for(load_task(REPO / "tasks" / task).meta))
            self.assertIn("a RED observation", text)
            self.assertIn("nothing ran", text)
            self.assertIn(load_task(REPO / "tasks" / task).meta["runner"]["note"].splitlines()[0], text)

    def test_a_require_glob_still_globs(self):
        """The bug the third control caught on four tasks at once: quoting kills the glob."""
        script = render({"run": "true", "require": "tests/own/*.cpp", "count": "^ok "})
        self.assertIn("tests/own/*.cpp", script)
        self.assertNotIn("'tests/own/*.cpp'", script)
        self.assertIn("if ! ls tests/own/*.cpp", script)

    def test_drift_notices_an_edited_adapter_in_either_copy(self):
        """tree/ and fixed/ both carry the instrument, so either one drifting is a failure."""
        task_dir = self.tmp / "task"
        for sub in ("tree", "fixed"):
            (task_dir / sub / "tools").mkdir(parents=True)
            (task_dir / sub / "tools" / "run_own_tests.sh").write_text("old")
        meta = {"tree": "tree", "fixed_tree": "fixed",
                "runner": {"run": "true", "count": "^ok "}}
        self.assertFalse(drift(task_dir, meta)[0])
        script = render(meta["runner"])
        for sub in ("tree", "fixed"):
            (task_dir / sub / "tools" / "run_own_tests.sh").write_text(script)
        self.assertTrue(drift(task_dir, meta)[0])
        (task_dir / "fixed" / "tools" / "run_own_tests.sh").write_text(script + "# edited\n")
        ok, note = drift(task_dir, meta)
        self.assertFalse(ok)
        self.assertIn("fixed", note)


if __name__ == "__main__":
    unittest.main()
