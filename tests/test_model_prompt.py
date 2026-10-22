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


if __name__ == "__main__":
    unittest.main()
