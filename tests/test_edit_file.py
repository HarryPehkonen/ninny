"""The fifth action, and every place where a write is special.

`write_file` takes the complete file, which is the wrong tool for changing one function inside a
four-hundred-line one: on `tasks/dogfood-stamp` all three arms reached for a bash heredoc instead,
and the bypass detector caught every one of those writes afterwards. The answer to that is a tool,
not a wall -- `edit_file` replaces an exact single occurrence, and refuses zero or several, because
a wrong guess about *which* occurrence to change corrupts a file silently.

Half of these tests are here for the other reason a new write tool is dangerous: the gate, the seal
and the write bookkeeping all keyed on the literal name `write_file`. A write tool that is not on
that list is a new way around all three.
"""

import tempfile
import unittest
from pathlib import Path

from ninny.actions import ACTION_NAMES, TOOLS, WRITE_ACTIONS, Action, validate
from ninny.env import Environment
from ninny.sandbox import build_sandbox
from tests.test_tdd import TDDBase

TEST_FILE = "tests/own/test_thing.py"


def an_edit(path: str, old: str = "beta", new: str = "BETA") -> Action:
    return Action(name="edit_file", args={"path": path, "old_string": old, "new_string": new})


class EditFileAction(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        (self.work / "src").mkdir()
        self.target = self.work / "src" / "thing.py"
        self.target.write_text("alpha\nbeta\ngamma\n")
        self.env = Environment(self.work, build_sandbox("none"), timeout=5,
                               test_cmd="true", test_timeout=5)

    def edit(self, old="beta", new="BETA"):
        return self.env.execute(an_edit("src/thing.py", old, new))

    # ---------------------------------------------------------------- the tool
    def test_it_is_offered_and_named(self):
        names = [tool["function"]["name"] for tool in TOOLS]
        self.assertIn("edit_file", names)
        self.assertIn("edit_file", ACTION_NAMES)

    def test_it_is_declared_a_write(self):
        self.assertIn("edit_file", WRITE_ACTIONS)
        self.assertIn("write_file", WRITE_ACTIONS)

    def test_a_missing_argument_is_explained(self):
        self.assertIn("old_string", validate(an_edit("src/thing.py", old="", new="x")))
        self.assertIn("new_string", validate(Action(name="edit_file",
                                                    args={"path": "src/thing.py", "old_string": "a"})))
        bad = Action(name="edit_file", args={"old_string": "a", "new_string": "b"})
        self.assertIn("path", validate(bad))

    # ---------------------------------------------------------------- exact once
    def test_it_replaces_the_one_occurrence(self):
        observation = self.edit()
        self.assertTrue(observation.ok, observation.output)
        self.assertEqual(self.target.read_text(), "alpha\nBETA\ngamma\n")

    def test_zero_matches_is_refused_and_the_file_is_untouched(self):
        before = self.target.read_text()
        observation = self.edit(old="not in this file")
        self.assertFalse(observation.ok)
        self.assertEqual(observation.note, "refused")
        self.assertIn("does not appear", observation.output)
        self.assertEqual(self.target.read_text(), before)

    def test_two_matches_is_refused_and_the_file_is_untouched(self):
        self.target.write_text("beta\nmiddle\nbeta\n")
        before = self.target.read_text()
        observation = self.edit()
        self.assertFalse(observation.ok)
        self.assertIn("appears 2 times", observation.output)
        self.assertEqual(self.target.read_text(), before)

    def test_a_file_that_is_not_there_is_a_refusal_that_points_at_write_file(self):
        observation = self.env.execute(an_edit("src/absent.py"))
        self.assertFalse(observation.ok)
        self.assertIn("write_file", observation.output)

    def test_an_empty_old_string_is_a_refusal(self):
        observation = self.edit(old="")
        self.assertFalse(observation.ok)
        self.assertIn("old_string", observation.output)

    def test_a_single_replacement_only(self):
        self.target.write_text("beta\nbeta\n")
        observation = self.env.execute(an_edit("src/thing.py", "beta\nbeta", "BETA"))
        self.assertTrue(observation.ok, observation.output)
        self.assertEqual(self.target.read_text(), "BETA\n")


class TheGateSeesAnEditAsAWrite(TDDBase):
    """The whole point: a new way to write must not be a new way past the gate or the seal."""

    def test_a_source_edit_before_a_red_is_refused_in_enforce(self):
        policy = self.policy_for("enforce")
        state = policy.new_state()
        self.assertFalse(self.allow(policy, state, an_edit("src/thing.py")),
                         "an edit into the source before a red must be refused")
        self.assertIn("src/thing.py", str(state.refusals))

    def test_a_sealed_test_cannot_be_edited_after_the_seal_is_taken(self):
        """Mid-run the mount stops a rewrite; the gate is the second line, once a seal exists.

        What matters here is symmetry: `write_file` was already refused by this branch, and a new
        write tool that the branch does not know about would be a way around it.
        """
        policy = self.policy_for("split")
        state = policy.new_state()
        (self.work / TEST_FILE).parent.mkdir(parents=True, exist_ok=True)
        (self.work / TEST_FILE).write_text("assert False\n")
        self.apply(policy, state, self.write(TEST_FILE, "assert False\n"), step=3)
        self.apply(policy, state, self.run_tests(), exit_code=1, step=4)
        policy.close_seal(state)
        self.assertTrue(state.sealed, "the red should have sealed the suite")
        self.assertIn(TEST_FILE, state.sealed)
        self.assertFalse(self.allow(policy, state, an_edit(TEST_FILE)),
                         "the seal must refuse an edit_file into a sealed test")
        self.assertFalse(self.allow(policy, state, self.write(TEST_FILE, "assert True\n")),
                         "and the same for write_file: the new tool must not be a way round it")

    def test_an_allowed_edit_counts_as_a_source_write(self):
        """Otherwise green_after_last_write would call a handback fresh when it is not."""
        policy = self.policy_for("off")
        state = policy.new_state()
        self.apply(policy, state, an_edit("src/thing.py"), step=4)
        self.assertEqual(state.first_src_step, 4)
        self.assertEqual(state.last_src_step, 4)

    def test_a_protected_path_cannot_be_edited(self):
        policy = self.policy_for("off")
        state = policy.new_state()
        self.assertFalse(self.allow(policy, state, an_edit("tools/run.sh")),
                         "tools/ is not the agent's to edit")


if __name__ == "__main__":
    unittest.main()
