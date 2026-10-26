"""The prose and the schemas have to agree about what the model can do.

`edit_file` went into `TOOLS`, into the gate and into the step log, and three other places were
missed: the `## How to act` list, the no-tool-call error message, and the parenthetical in the seal
notice that enumerates the ways a red file can change. The schema is what makes a call legal; this
prose is the manual the model actually reads, so a tool missing from it is a tool the model has
been told does not exist.

These walk the action lists rather than naming the actions, so the next one cannot be added to the
schemas and left out of the prose.
"""

import unittest
from types import SimpleNamespace

from ninny.actions import ACTION_NAMES, WRITE_ACTIONS
from ninny.prompt import INSTANCE_TEMPLATE, SEAL_NOTICE, format_error_message


class TheManualNamesEveryAction(unittest.TestCase):
    def test_every_action_is_in_the_how_to_act_list(self):
        for name in ACTION_NAMES:
            self.assertIn(f"`{name}`", INSTANCE_TEMPLATE,
                          f"{name} is offered as a tool but missing from the manual")

    def test_every_action_is_named_when_a_reply_had_none(self):
        message = format_error_message(SimpleNamespace(finish_reason="stop"), "", "chat")
        for name in ACTION_NAMES:
            self.assertIn(name, message, f"{name} is missing from the no-tool-call message")

    def test_the_seal_notice_names_every_write_route(self):
        """It enumerates the ways a file that was red can change. A write route missing from that
        list is a route the model has been told does not exist."""
        for name in WRITE_ACTIONS:
            self.assertIn(f"`{name}`", SEAL_NOTICE, f"{name} is a write route the notice omits")


if __name__ == "__main__":
    unittest.main()
