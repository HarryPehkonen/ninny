# Make the preflight state the suite's duration

`ninny run --repo` prints a preflight before the first model call (`ninny/cli.py::preflight_lines`). One
line currently says only what timeout the suite *gets*:

    preflight: suite `bash scripts/run-tests.sh` gets 600s; a single bash action gets 600s

What a caller cannot see is how long that suite *takes*. That number is the difference between reading "40
steps" as a budget and as a trap: the two repository runs this preflight was written for spent their whole
budget reading, against a suite that took 121 s per run.

## What to change

1. **First file to touch: `ninny/cli.py`.** In `preflight_lines`, time the task's `test_cmd` once and put the
   measurement on that line:

       preflight: suite `bash scripts/run-tests.sh` took 6.1s; it gets 600s, a single bash action 600s

2. **First test to write: `tests/test_preflight.py`.** Add a case asserting the measured duration appears on
   the line, and that an ordinary `--repo` invocation still returns no refusal.

## Rules

- Measure in the run's working tree, through the same shell the run uses.
- If the suite cannot run at all, say so on that line instead of raising. A preflight must never be the
  reason a run dies. `tests/test_preflight_seam.py` parses a real command line and runs the preflight
  against it; keep it passing.
- No new flags and no config file: everything rides on what the caller already passes.
- Acceptance: `bash scripts/run-tests.sh` -- the repository's own suite. It exits 0 on success, and it fails
  when no tests run.
- Out of scope: the rest of `preflight_lines`, and every other subcommand.
