"""Parsing a reply into actions, and refusing to act on nonsense."""

import unittest

from ninny import SUBMIT_SENTINEL
from ninny.actions import (
    ACTION_NAMES,
    Action,
    actions_from_text,
    actions_from_tool_calls,
    parse_reply,
    validate,
)


class FakeResponse:
    def __init__(self, text="", tool_calls=(), finish_reason=""):
        self.text = text
        self.tool_calls = list(tool_calls)
        self.finish_reason = finish_reason


class FakeToolCall:
    def __init__(self, name, arguments, id=""):
        self.name = name
        self.arguments = arguments
        self.id = id


class TextActionTests(unittest.TestCase):
    def test_bash_fence(self):
        actions = actions_from_text("Let me look around.\n\n```bash\nls -la\n```\n")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].name, "bash")
        self.assertEqual(actions[0].command, "ls -la")
        self.assertEqual(actions[0].source, "text")

    def test_write_file_takes_the_path_from_the_fence_line(self):
        text = "```write_file src/thing.py\nvalue = 1\n```"
        actions = actions_from_text(text)
        self.assertEqual(actions[0].name, "write_file")
        self.assertEqual(actions[0].path, "src/thing.py")
        self.assertEqual(actions[0].content, "value = 1\n")

    def test_write_file_without_a_path_is_malformed_not_silent(self):
        actions = actions_from_text("```write_file\nvalue = 1\n```")
        self.assertEqual(actions[0].name, "write_file")
        self.assertTrue(actions[0].malformed)
        self.assertIn("path", validate(actions[0]))

    def test_run_tests_fence(self):
        actions = actions_from_text("```run_tests\n```")
        self.assertEqual(actions[0].name, "run_tests")

    def test_several_actions_keep_their_order(self):
        text = "```bash\nfirst\n```\nthen\n```run_tests\n```\n```bash\nthird\n```"
        names = [a.name for a in actions_from_text(text)]
        self.assertEqual(names, ["bash", "run_tests", "bash"])

    def test_json_action_is_a_fallback(self):
        actions = actions_from_text('I will act: {"name": "bash", "arguments": {"command": "ls"}}')
        self.assertEqual(actions[0].name, "bash")
        self.assertEqual(actions[0].command, "ls")

    def test_prose_alone_yields_nothing(self):
        self.assertEqual(actions_from_text("I have finished. Please run the gate."), [])

    def test_a_fenced_block_with_an_unknown_language_is_ignored(self):
        self.assertEqual(actions_from_text("```python\nprint(1)\n```"), [])


class ParseReplyTests(unittest.TestCase):
    def test_tool_calls_win(self):
        response = FakeResponse(text="ignored", tool_calls=[FakeToolCall("bash", {"command": "ls"}, "c1")])
        actions, note = parse_reply(response)
        self.assertEqual(actions[0].source, "tool_call")
        self.assertEqual(note, "")

    def test_text_actions_are_used_with_a_note(self):
        actions, note = parse_reply(FakeResponse(text="```bash\nls\n```"))
        self.assertEqual(actions[0].name, "bash")
        self.assertIn("fenced blocks", note)

    def test_unparseable_tool_arguments_are_flagged(self):
        call = FakeToolCall("bash", {"__unparsed__": "{not json"})
        actions = actions_from_tool_calls([call])
        self.assertTrue(actions[0].malformed)
        self.assertIn("JSON", validate(actions[0]))


class ValidateTests(unittest.TestCase):
    def test_every_declared_action_is_known(self):
        for name in ACTION_NAMES:
            args = {"command": "ls"} if name == "bash" else {"path": "a", "content": ""} if name == "write_file" else \
                   {"path": "a"} if name == "read_file" else {}
            self.assertEqual(validate(Action(name=name, args=args)), "", name)

    def test_unknown_action_names_are_rejected(self):
        message = validate(Action(name="deploy_to_production", args={}))
        self.assertIn("unknown action", message)
        self.assertIn("bash", message)

    def test_empty_bash_is_rejected(self):
        self.assertIn("non-empty", validate(Action(name="bash", args={"command": "   "})))

    def test_write_file_needs_content(self):
        self.assertIn("content", validate(Action(name="write_file", args={"path": "a.py"})))

    def test_read_file_needs_a_path(self):
        self.assertIn("path", validate(Action(name="read_file", args={})))


class SubmitTests(unittest.TestCase):
    def test_the_sentinel_is_a_submit(self):
        self.assertTrue(Action(name="bash", args={"command": f"echo {SUBMIT_SENTINEL}"}).is_submit())

    def test_an_unrelated_echo_is_not(self):
        self.assertFalse(Action(name="bash", args={"command": "echo hello"}).is_submit())

    def test_describe_never_crashes_on_odd_arguments(self):
        for name in ACTION_NAMES:
            Action(name=name, args={}).describe()


if __name__ == "__main__":
    unittest.main()
