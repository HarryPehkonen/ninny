"""The provider seam, and the prompt that explains it to the model."""

import json
import unittest

from ninny import SUBMIT_SENTINEL
from ninny.model import ModelClient, ModelError, flatten_messages
from ninny.prompt import format_error_message, render_instance


class FakeTask:
    spec = "Implement it.\n"
    test_globs = ["tests/own/**"]


class WireTests(unittest.TestCase):
    def client(self, wire="chat"):
        return ModelClient(model="m", base_url="http://example.invalid/v1", wire=wire)

    def test_an_unknown_wire_is_refused_with_a_pointer_to_the_docs(self):
        with self.assertRaises(ModelError) as caught:
            self.client("grpc")
        self.assertIn("PROVIDERS.md", str(caught.exception))

    def test_each_wire_has_its_own_path(self):
        self.assertEqual(self.client("chat").path, "/chat/completions")
        self.assertEqual(self.client("completions").path, "/completions")

    def test_chat_carries_messages_and_the_tools(self):
        body = self.client().build_body([{"role": "user", "content": "hi"}], [
            {"type": "function", "function": {"name": "bash"}}
        ])
        self.assertEqual(body["messages"][0]["content"], "hi")
        self.assertIn("tools", body)
        self.assertEqual(body["tool_choice"], "auto")

    def test_completions_flattens_the_conversation_and_sends_no_tools(self):
        body = self.client("completions").build_body(
            [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
            [{"type": "function", "function": {"name": "bash"}}],
        )
        self.assertIn("System", body["prompt"])
        self.assertIn("User", body["prompt"])
        self.assertNotIn("tools", body)

    def test_temperature_and_max_tokens_are_only_sent_when_set(self):
        self.assertNotIn("temperature", self.client().build_body([], None))
        client = ModelClient("m", "http://x/v1", temperature=0.2, max_tokens=99)
        body = client.build_body([], None)
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["max_tokens"], 99)


class ParseTests(unittest.TestCase):
    def test_chat_text_and_tool_calls(self):
        client = ModelClient("m", "http://x/v1")
        response = client.parse_body({
            "choices": [{
                "message": {
                    "content": "thinking",
                    "tool_calls": [{
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": json.dumps({"command": "ls"})},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        })
        self.assertEqual(response.text, "thinking")
        self.assertEqual(response.tool_calls[0].name, "bash")
        self.assertEqual(response.tool_calls[0].arguments, {"command": "ls"})
        self.assertEqual(response.tool_calls[0].id, "c1")
        self.assertEqual(response.usage["prompt_tokens"], 5)
        self.assertEqual(response.finish_reason, "tool_calls")

    def test_unparseable_arguments_are_kept_for_the_error_message(self):
        client = ModelClient("m", "http://x/v1")
        response = client.parse_body({
            "choices": [{"message": {"tool_calls": [
                {"function": {"name": "bash", "arguments": "{oops"}}
            ]}}]
        })
        self.assertIn("__unparsed__", response.tool_calls[0].arguments)

    def test_the_legacy_function_call_shape_is_understood(self):
        client = ModelClient("m", "http://x/v1")
        response = client.parse_body({
            "choices": [{"message": {"function_call": {"name": "bash", "arguments": '{"command": "ls"}'}}}]
        })
        self.assertEqual(response.tool_calls[0].arguments, {"command": "ls"})

    def test_completions_reads_text(self):
        client = ModelClient("m", "http://x/v1", wire="completions")
        response = client.parse_body({"choices": [{"text": "```bash\nls\n```"}]})
        self.assertIn("ls", response.text)
        self.assertEqual(response.tool_calls, [])

    def test_missing_usage_is_empty_not_an_error(self):
        client = ModelClient("m", "http://x/v1")
        self.assertEqual(client.parse_body({"choices": [{"message": {}}]}).usage, {})


class FlattenTests(unittest.TestCase):
    def test_the_transcript_keeps_the_roles_and_ends_open(self):
        text = flatten_messages([
            {"role": "system", "content": "S"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "content": "output"},
        ])
        self.assertIn("### System", text)
        self.assertIn("### Result", text)
        self.assertIn("[bash]", text)
        self.assertTrue(text.rstrip().endswith("### Assistant"))


class PromptTests(unittest.TestCase):
    def test_the_enforced_block_appears_only_when_enforcing(self):
        enforced = render_instance(FakeTask(), "/work", "enforce", "sandbox note")
        requested = render_instance(FakeTask(), "/work", "request", "sandbox note")
        self.assertIn("ENFORCED", enforced)
        self.assertIn("tests/own/**", enforced)
        self.assertNotIn("ENFORCED", requested)

    def test_the_prompt_carries_the_task_the_workdir_and_the_sentinel(self):
        text = render_instance(FakeTask(), "/somewhere", "request", "NO SANDBOX")
        self.assertIn("Implement it.", text)
        self.assertIn("/somewhere", text)
        self.assertIn(SUBMIT_SENTINEL, text)
        self.assertIn("NO SANDBOX", text)

    def test_a_truncated_reply_gets_a_truncation_message(self):
        class Response:
            finish_reason = "length"
            text = ""

        self.assertIn("cut off", format_error_message(Response(), "", "chat"))

    def test_a_reply_with_no_action_is_told_what_tool_calls_are(self):
        class Response:
            finish_reason = "stop"
            text = "I would suggest writing a test."

        self.assertIn("tool call", format_error_message(Response(), "", "chat"))
        self.assertIn("fenced block", format_error_message(Response(), "", "completions"))


class PromptModeTests(unittest.TestCase):
    """What the model is TOLD and what the harness BLOCKS are two axes.

    `enforce` ships both at once -- a stronger instruction AND a gate that refuses
    source writes -- so comparing it against `request` cannot say which one produced
    the behaviour. The eighteen-arm batch came out enforce 6/6 red-first against
    request 2/6, with ZERO test-first refusals in the enforce arms: the instruction is
    the suspect, and this is the seam that can test it. `--tdd-prompt` sets the two
    axes apart, and both are recorded so an arm can be identified afterwards.
    """

    class FakeClient:
        """Enough of ModelClient to drive one step to a submit, with no network."""

        model = "fake/model"
        wire = "chat"

        def __init__(self, replies):
            self.replies = list(replies)

        def complete(self, messages, tools=None):
            return self.replies.pop(0)

    def setUp(self):
        import tempfile
        from pathlib import Path

        from ninny.config import Task

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.work = root / "tree"
        (self.work / "src").mkdir(parents=True)
        (self.work / "src" / "thing.py").write_text("value = 0\n")
        (self.work / "tests" / "own").mkdir(parents=True)
        self.task = Task(
            root=root, name="tiny", spec="Make thing.py hold 1.\n", tree_src=self.work,
            oracle_dir=None, test_cmd="true", oracle_cmd=None,
            test_globs=["tests/own/**"], src_globs=["src/**"], protected_globs=["tools/**"],
            preflight=[], step_limit=5, timeout_s=5, test_timeout_s=5,
        )
        self.run_dir = root / "run"

    def tearDown(self):
        self._tmp.cleanup()

    def drive(self, gate_mode: str, prompt_mode: str):
        """One step that submits, so the whole loop runs offline and ends cleanly."""
        from ninny.agent import Agent
        from ninny.env import Environment
        from ninny.model import Response, ToolCall
        from ninny.sandbox import build_sandbox
        from ninny.tdd import TDDPolicy

        submit = Response(
            tool_calls=[ToolCall(name="bash", arguments={"command": f"echo {SUBMIT_SENTINEL}"}, id="1")]
        )
        agent = Agent(
            client=self.FakeClient([submit]),
            environment=Environment(self.work, build_sandbox("none"), timeout=5,
                                    test_cmd="true", test_timeout=5),
            policy=TDDPolicy(gate_mode, self.task, self.work),
            task=self.task, workdir=self.work, run_dir=self.run_dir,
            pricing=None, step_limit=1, log=lambda _line: None,
            prompt_mode=prompt_mode,
        )
        agent.run()
        return agent

    def test_a_run_can_be_told_to_enforce_without_being_blocked(self):
        agent = self.drive(gate_mode="request", prompt_mode="enforce")
        self.assertIn("ENFORCED", agent.messages[1]["content"])
        self.assertEqual(agent.policy.mode, "request")

    def test_a_run_can_be_blocked_without_being_told(self):
        agent = self.drive(gate_mode="enforce", prompt_mode="request")
        self.assertNotIn("ENFORCED", agent.messages[1]["content"])
        self.assertEqual(agent.policy.mode, "enforce")

    def test_the_prompt_mode_falls_back_to_the_gate_mode(self):
        agent = self.drive(gate_mode="enforce", prompt_mode="")
        self.assertIn("ENFORCED", agent.messages[1]["content"])

    def test_both_axes_are_recorded_so_the_arm_can_be_identified_later(self):
        self.drive(gate_mode="request", prompt_mode="enforce")
        run = json.loads((self.run_dir / "trajectory.json").read_text())["run"]
        self.assertEqual(run["tdd_mode"], "request")
        self.assertEqual(run["tdd_prompt_mode"], "enforce")


if __name__ == "__main__":
    unittest.main()
