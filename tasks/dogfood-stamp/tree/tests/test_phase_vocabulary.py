"""The phases, named for the agent: what to do next, and what a red is NOT.

Ninny has carried a phase on its state since the beginning (`test`, `impl`, `done`) and has
never said so to the model. These tests pin the vocabulary where the model can see it --
the prompt, the refusal text, and the observation that comes back after an action.

Two moments are worth interrupting for, and they are the two ways a run goes wrong in
silence:

  * a suite that reported nothing at all. Exit 2 is "nothing ran", and a model that has just
    seen a compiler error reads it as "it failed, good". Measured 2026-10-23: a C++ task
    with no compiling stub produced `cc1plus: fatal error` as its claimed first red, which
    the contract refuses. The task author absorbed that in the stub; the agent was told
    nothing.
  * a phase that changed without the model being told, so it keeps writing tests after the
    red is already banked.

The third place is the plan line, which is for the operator rather than the model.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ninny import SUBMIT_SENTINEL
from ninny.config import Task
from ninny.prompt import render_instance
from ninny.tdd import (
    MODES, PHASE_JOBS, PHASE_LABELS, PHASE_ORDER, TDDPolicy, phase_line, phases_line)


class FakeTask:
    spec = "Implement it.\n"
    test_globs = ["tests/own/**"]
    src_globs = ["src/**"]


def an_action(name, path="", command=""):
    return SimpleNamespace(
        name=name, path=path, command=command, content="x",
        is_submit=lambda: name == "bash" and SUBMIT_SENTINEL in command,
    )


def an_observation(exit_code=None, ok=True, tests=None):
    return SimpleNamespace(exit_code=exit_code, ok=ok, tests=tests, render=lambda: "the output")


class VocabularyTests(unittest.TestCase):
    def test_the_three_phases_are_in_order_and_say_what_to_do(self):
        self.assertEqual(list(PHASE_ORDER), ["test", "impl", "done"])
        self.assertEqual(
            [PHASE_LABELS[p] for p in PHASE_ORDER], ["RED-FIRST", "GREEN", "HAND BACK"]
        )
        first = phase_line("test")
        self.assertTrue(first.startswith("1/3 RED-FIRST"))
        self.assertIn("RUNS", first)  # the rule: a red is a test that ran and failed
        self.assertIn("3/3", phase_line("done"))
        self.assertEqual(len(PHASE_JOBS), 3)

    def test_an_unknown_phase_falls_back_to_the_first_one(self):
        self.assertEqual(phase_line("nonsense"), phase_line("test"))

    def test_the_plan_line_names_all_three(self):
        line = phases_line()
        for label in PHASE_LABELS.values():
            self.assertIn(label, line)

    def test_the_enforced_prompt_names_the_phases_and_what_a_red_is_not(self):
        text = render_instance(FakeTask(), "/work", "enforce", "note")
        for label in PHASE_LABELS.values():
            self.assertIn(label, text)
        self.assertIn("exit 2", text)
        self.assertIn("not a red", text)

    def test_off_still_says_nothing_about_testing(self):
        text = render_instance(FakeTask(), "/work", "off", "note")
        self.assertNotIn("RED-FIRST", text)
        self.assertNotIn("GREEN", text)
        # `off` is the control arm: it is not told about the seal either. The seal still runs and
        # is still recorded there, so this silence is what keeps its number a measurement of what
        # the model does unprompted rather than one of what it was asked for.
        self.assertNotIn("compared at handback", text)

    def test_every_mode_that_tells_the_model_anything_explains_the_seal(self):
        # The seal runs in every mode that banks a red, so a mode that says nothing about it is
        # promising one thing and measuring another -- which is exactly how `enforce` arms came to
        # rewrite their own red suite in five of eight runs while the prompt said nothing.
        for mode in MODES:
            text = render_instance(FakeTask(), "/work", mode, "note")
            self.assertNotIn("{seal}", text, f"mode {mode} left the placeholder unrendered")
            if mode == "off":
                # The control arm stays silent -- see the note on SEAL_NOTICE.
                self.assertNotIn("compared at handback", text)
                self.assertNotIn("sealed", text)
                continue
            # `split` spells the same promise out at greater length, so accept its own wording:
            # it is enforced as well as told, and its paragraph names the read-only binds.
            self.assertTrue(
                "compared at handback" in text or "sealed" in text,
                f"mode {mode} does not tell the model the suite is compared at handback",
            )

    def test_the_seal_notice_says_the_two_things_that_make_it_fair(self):
        text = render_instance(FakeTask(), "/work", "enforce", "note")
        self.assertIn("ADD", text)              # adding test files is still allowed
        self.assertIn("final message", text)    # and that is where a wrong test should be reported

    def test_reverse_gets_the_definition_without_the_opposite_order(self):
        text = render_instance(FakeTask(), "/work", "reverse", "note")
        self.assertNotIn("RED-FIRST", text)
        self.assertIn("not a red", text)

    def test_a_refusal_states_the_phase_the_run_is_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "tree"
            (work / "src").mkdir(parents=True)
            (work / "tests" / "own").mkdir(parents=True)
            task = Task(
                root=Path(tmp), name="tiny", spec="s\n", tree_src=work, oracle_dir=None,
                test_cmd="true", oracle_cmd=None, test_globs=["tests/own/**"],
                src_globs=["src/**"], protected_globs=[], preflight=[],
                step_limit=5, timeout_s=5, test_timeout_s=5,
            )
            policy = TDDPolicy("enforce", task, work)
            state = policy.new_state()
            message = policy.gate(an_action("write_file", path="src/thing.py"), state, 1)
            self.assertIn("1/3 RED-FIRST", message)
            self.assertIn("exit 2", message)  # the not-a-red rule, in the commonest refusal


class NoteTests(unittest.TestCase):
    """The one line the model is told after an action ran."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.work = root / "tree"
        (self.work / "src").mkdir(parents=True)
        (self.work / "tests" / "own").mkdir(parents=True)
        self.task = Task(
            root=root, name="tiny", spec="Make thing.py hold 1.\n", tree_src=self.work,
            oracle_dir=None, test_cmd="true", oracle_cmd=None, test_globs=["tests/own/**"],
            src_globs=["src/**"], protected_globs=[], preflight=[],
            step_limit=5, timeout_s=5, test_timeout_s=5,
        )
        self.policy = TDDPolicy("enforce", self.task, self.work)
        self.state = self.policy.new_state()

    def test_a_run_that_reported_nothing_is_told_it_was_not_a_red(self):
        note = self.policy.note_for(an_action("run_tests"), an_observation(exit_code=2), self.state)
        self.assertIn("not a red", note)
        self.assertIn("exit 2", note)

    def test_the_red_is_announced_with_the_next_phase(self):
        self.policy.observe(an_action("write_file", path="tests/own/t.py"),
                            an_observation(), self.state, 1)
        self.policy.observe(an_action("run_tests"), an_observation(exit_code=1), self.state, 2)
        self.assertEqual(self.state.phase, "impl")
        note = self.policy.note_for(an_action("run_tests"), an_observation(exit_code=1), self.state)
        self.assertIn("GREEN", note)
        self.assertIn("step 2", note)

    def test_the_news_is_one_shot(self):
        self.policy.observe(an_action("write_file", path="tests/own/t.py"),
                            an_observation(), self.state, 1)
        self.policy.observe(an_action("run_tests"), an_observation(exit_code=1), self.state, 2)
        self.assertIn("GREEN", self.policy.note_for(an_action("run_tests"),
                                                   an_observation(exit_code=1), self.state))
        self.assertEqual(self.policy.note_for(an_action("read_file"),
                                              an_observation(), self.state), "")

    def test_an_ordinary_action_is_not_interrupted(self):
        self.assertEqual(self.policy.note_for(an_action("read_file"), an_observation(), self.state), "")

    def test_a_passing_run_after_a_red_is_not_told_it_was_a_red(self):
        self.policy.observe(an_action("write_file", path="tests/own/t.py"),
                            an_observation(), self.state, 1)
        self.policy.observe(an_action("run_tests"), an_observation(exit_code=1), self.state, 2)
        self.policy.note_for(an_action("run_tests"), an_observation(exit_code=1), self.state)
        note = self.policy.note_for(an_action("run_tests"), an_observation(exit_code=0), self.state)
        self.assertEqual(note, "")


class PhaseReachesTheModelTests(unittest.TestCase):
    """The plumbing: a note the model never receives is a comment."""

    class FakeClient:
        model = "fake/model"
        wire = "chat"

        def __init__(self, replies):
            self.replies = list(replies)

        def complete(self, messages, tools=None):
            return self.replies.pop(0)

    def setUp(self):
        from ninny.model import Response, ToolCall

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.work = root / "tree"
        (self.work / "src").mkdir(parents=True)
        (self.work / "tests" / "own").mkdir(parents=True)
        # A suite that runs and fails while src/thing.py is missing, and passes once it is
        # there: the whole point is to earn a red and then live to see green.
        self.test_cmd = "test -f src/thing.py"
        self.task = Task(
            root=root, name="tiny", spec="Make thing.py hold 1.\n", tree_src=self.work,
            oracle_dir=None, test_cmd=self.test_cmd, oracle_cmd=None,
            test_globs=["tests/own/**"], src_globs=["src/**"], protected_globs=[],
            preflight=[], step_limit=6, timeout_s=5, test_timeout_s=5,
        )
        self.run_dir = root / "run"
        self.replies = [
            Response(tool_calls=[ToolCall(name="write_file",
                                          arguments={"path": "tests/own/t.py", "content": "x"},
                                          id="1")]),
            Response(tool_calls=[ToolCall(name="run_tests", arguments={}, id="2")]),
            Response(tool_calls=[ToolCall(name="write_file",
                                          arguments={"path": "src/thing.py", "content": "value = 1\n"},
                                          id="3")]),
            Response(tool_calls=[ToolCall(name="run_tests", arguments={}, id="4")]),
            Response(tool_calls=[ToolCall(name="bash",
                                          arguments={"command": f"echo {SUBMIT_SENTINEL}"}, id="5")]),
        ]

    def drive(self):
        from ninny.agent import Agent
        from ninny.env import Environment
        from ninny.sandbox import build_sandbox

        agent = Agent(
            client=self.FakeClient(self.replies),
            environment=Environment(self.work, build_sandbox("none"), timeout=5,
                                    test_cmd=self.test_cmd, test_timeout=5),
            policy=TDDPolicy("enforce", self.task, self.work),
            task=self.task, workdir=self.work, run_dir=self.run_dir,
            pricing=None, step_limit=5, log=lambda _line: None, prompt_mode="enforce",
        )
        agent.run()
        return agent

    def test_the_observation_the_model_reads_announces_the_next_phase(self):
        agent = self.drive()
        contents = [m.get("content") or "" for m in agent.messages]
        self.assertTrue(
            any("GREEN" in text and "step 2" in text for text in contents),
            "the model was never told the red was banked and the phase moved on",
        )

    def test_the_transcript_and_the_record_agree(self):
        agent = self.drive()
        # result.json is the run's own record of itself, which is where a reader looks.
        tdd = json.loads((self.run_dir / "result.json").read_text())["tdd"]
        self.assertEqual(tdd["phase"], "done")
        self.assertEqual(tdd["red_step"], 2)
        self.assertEqual(tdd["first_src_step"], 3)
        self.assertEqual(tdd["verdict"], "red-first")
        self.assertEqual(tdd["test_runs"], [[2, 1], [4, 0]])


if __name__ == "__main__":
    unittest.main()
