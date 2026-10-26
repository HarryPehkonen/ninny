"""The read-only bind belongs to the mode that makes the claim it enforces.

`state.sealed` is snapshotted at the red in every mode (tdd.py), and `_enforce_seal` bound those
files read-only in every mode too -- so in `enforce` bash was physically blocked while the file
tools, which run in this process and not inside the sandbox, walked straight past the bind. Two
layers disagreeing about one path is the split-brain this repo already has a lesson for, and the
cost was real: a run that got an assertion wrong could not fix it, which is the `bits` failure.

Outside `split` the seal is telemetry, and that is still a claim: `close_seal` compares the suite at
handback and `suite_frozen_since_red` reports it either way.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from ninny.agent import Agent
from ninny.tdd import TDDPolicy
from tests.test_tdd import build_task

SEALED_FILE = "tests/own/test_a.py"


class StubAgent(Agent):
    """Just enough Agent to call `_enforce_seal`: no loop, no client, no sandbox."""

    def __init__(self, mode: str):
        self.policy = SimpleNamespace(mode=mode)
        self.calls: list[list[str]] = []
        self.env = SimpleNamespace(sandbox=SimpleNamespace(
            name="stub", sealed_ancestors=[], seal_readonly=self.record_seal))
        self.workdir = Path("/nonexistent")
        self._sealed_applied = False
        self.lines: list[str] = []

    def record_seal(self, paths, ancestors=None):
        self.calls.append([str(path) for path in paths])
        return False

    def _sealed_ancestors(self, sealed):
        return []

    def log(self, line: str) -> None:
        self.lines.append(line)


class TheMountBelongsToSplit(unittest.TestCase):
    def setUp(self):
        self.task = build_task(Path("/nonexistent"))

    def a_state_with_a_sealed_suite(self, mode: str):
        state = TDDPolicy(mode, self.task, Path("/nonexistent")).new_state()
        state.sealed = {SEALED_FILE: "hash"}
        state.seal_step = 4
        return state

    def test_split_still_binds_the_sealed_files(self):
        """The change must not unfreeze the mode whose claim depends on being frozen."""
        agent = StubAgent("split")
        agent._enforce_seal(self.a_state_with_a_sealed_suite("split"))
        self.assertEqual(len(agent.calls), 1, agent.lines)
        self.assertEqual(agent.calls[0], [f"/nonexistent/{SEALED_FILE}"])

    def test_no_other_mode_binds_anything(self):
        for mode in ("off", "request", "enforce", "reverse"):
            with self.subTest(mode=mode):
                agent = StubAgent(mode)
                agent._enforce_seal(self.a_state_with_a_sealed_suite(mode))
                self.assertEqual(agent.calls, [], f"{mode} must not bind a path: {agent.lines}")

    def test_the_skip_says_why_in_the_log(self):
        agent = StubAgent("enforce")
        agent._enforce_seal(self.a_state_with_a_sealed_suite("enforce"))
        self.assertTrue(any("not enforced" in line for line in agent.lines), agent.lines)


if __name__ == "__main__":
    unittest.main()
