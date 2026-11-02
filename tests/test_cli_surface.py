"""Every door `main()` walks through has to be open on every command.

`main()` writes the transcript and the index line for every invocation -- there is no switch, and a
subparser that quietly gained one would put back the ability to silence the record. This walks every
command instead: `--no-log` used to be spelled once in a loop, and `verdict` shipped without joining it
once, so every unit test passed while the real command died in `main()` with
over the subparsers, so a harness that writes into your home directory always has an off switch.
`verdict` was registered after that loop, so `ninny verdict <run>` parsed fine, passed every unit
test that called `cmd_verdict` directly, and then died inside `main()` with
`AttributeError: 'Namespace' object has no attribute 'no_log'`.

That is the shape of the bug this test exists for: the function can be perfect and the command
still unusable, because the tests called the function and the user calls the door.
"""

import unittest

from ninny.cli import build_parser

#: Every command `main()` can dispatch. Adding one means adding it here and joining the
#: shared-flag loop in `build_parser`; the second is what this checks.
COMMANDS = ("run", "check", "verify-task", "runner", "doctor", "verdict")


def argv_for(command: str) -> list[str]:
    """The least a command needs in order to parse. Nothing else is exercised here."""
    if command == "check":
        return [command, "--tree", "somewhere"]
    if command == "verdict":
        return [command, "somewhere"]
    if command == "run":
        return [command, "--model", "some/model"]  # --model is the one required argument
    return [command]


class EveryCommandAcceptsTheSharedFlags(unittest.TestCase):
    def test_no_command_can_silence_the_record(self):
        """A record you can switch off is not a record.

        The flag used to be spelled once, in a loop over every subparser, and the failure mode it
        guarded was real: `verdict` shipped outside that loop, every unit test passed, and the real
        command died in `main()` with `AttributeError: 'Namespace' object has no attribute 'no_log'`.
        There is no flag now, and this walks every command so one cannot come back unnoticed.
        """
        parser = build_parser()
        for command in COMMANDS:
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    parser.parse_args(argv_for(command) + ["--no-log"])

    def test_every_command_has_a_function_to_dispatch_to(self):
        parser = build_parser()
        for command in COMMANDS:
            with self.subTest(command=command):
                args = parser.parse_args(argv_for(command))
                self.assertTrue(callable(getattr(args, "func", None)),
                                f"`ninny {command}` sets no func, so main() would crash")

    def test_the_command_name_is_what_main_logs(self):
        parser = build_parser()
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(parser.parse_args(argv_for(command)).command, command)


if __name__ == "__main__":
    unittest.main()
