"""The prompts: one system message, one instance message.

The structure follows mini-swe-agent: a terse system message, then an instance
message carrying the task, the rules, the submit sentinel and the system
information block.
"""

from __future__ import annotations

import platform

from ninny import SUBMIT_SENTINEL, __version__

SYSTEM_TEMPLATE = "You are a helpful assistant that can interact with a computer."

INSTANCE_TEMPLATE = """Please complete this task:

<task>
{spec}
</task>

You are working in {workdir}. Everything you need is there.

## How to act

Each reply must contain at least one tool call.

1. `bash` -- run a shell command. Every action runs in a fresh shell, so `cd` and
   exported variables do NOT persist between actions; combine them in one command
   instead (`cd build && make`). {sandbox_note}
2. `write_file` -- write a file, creating parent directories. Prefer this over a
   heredoc: quoting a whole file through a shell is where models most often
   corrupt their own work.
3. `read_file` -- read a file, optionally with a line range.
4. `run_tests` -- run your own tests and see the result. A non-zero exit means they
   failed.

Finish by calling `bash` with exactly this command and nothing else:
`echo {sentinel}`
After that you cannot continue working on the task.

{tdd_block}
## Working rules

- File changes persist between actions; shell state does not.
- Work in small steps: change something, then run something that shows whether it
  worked.
- Do not ask questions. Nobody is watching until you submit.

<system_information>
{ninny} on {system} {release} {machine}
</system_information>
"""

TDD_BLOCKS = {
    "off": "",
    "request": """## Testing

Write tests for the behaviour you implement. There is no rule about the order in
which you write them.

""",
    "enforce": """## Testing (ENFORCED in this run)

You must write a test and **see it fail** before any implementation is accepted.
Writes into the source tree are refused until then. The sequence is:

1. `write_file` a test under {test_globs}
2. `run_tests` and read the failure it reports
3. `write_file` the implementation

The harness records whether a failing test was observed before the implementation.
It cannot record what did not happen, and it watches the source tree to confirm
the refusal was not routed around.

""",
    "reverse": """## Testing

Implement first if you like. Before you may submit, you must write tests for what
you implemented and run them.

""",
}


def render_instance(task, workdir: str, tdd_mode: str, sandbox_note: str) -> str:
    tdd_block = TDD_BLOCKS.get(tdd_mode, "")
    if "{test_globs}" in tdd_block:
        tdd_block = tdd_block.format(test_globs=", ".join(task.test_globs))
    return INSTANCE_TEMPLATE.format(
        spec=task.spec.strip(),
        workdir=workdir,
        sandbox_note=sandbox_note,
        sentinel=SUBMIT_SENTINEL,
        tdd_block=tdd_block,
        ninny=f"ninny {__version__}",
        system=platform.system(),
        release=platform.release(),
        machine=platform.machine(),
    )


def format_error_message(response, note: str, wire: str) -> str:
    """What the model is told when its reply contained no usable action."""
    if response.finish_reason == "length":
        return (
            "Your previous reply was cut off at the output token limit before it contained a "
            "tool call. Be more concise and finish with exactly one tool call."
        )
    if wire == "completions":
        return (
            "Your previous reply contained no action. Reply with a fenced block, for example:\n"
            "```bash\nls -la\n```\n"
            "or\n```write_file src/thing.cpp\n<the whole file>\n```\n"
            "For the test loop use:\n```run_tests\n```"
        )
    return (
        "Your previous reply contained no tool call, so nothing happened. "
        "Every reply must contain at least one tool call: bash, write_file, read_file or run_tests."
        + (f"\n({note})" if note else "")
    )
