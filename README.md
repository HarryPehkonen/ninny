# Ninny

A tiny coding-agent harness that **enforces and measures process, not just outcomes**.

Ninny is a fork of [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) (MIT),
re-implemented on the standard library. It exists because of one measurement:

> Across 27 clean runs with 12 models, in two different harnesses, at every price
> point, **not one run ever wrote a test and watched it fail before writing the code
> it was testing.** Every harness asks for test-first in prose. None of them can
> tell you whether it happened.

Ninny can, and it will refuse to let a run proceed until it does.

## What it is not

No MCP. No multi-agent. No plugin system. No daemon, no server, no browser. Four
actions, one loop, and a record. It measures a *process property* — did a failing
test exist before the implementation — and it treats that as a first-class result
alongside whether the code works.

## Zero dependencies

```
pip install ninny     # installs nothing else
```

Ninny imports only the standard library. That is a deliberate reversal of the
upstream design, for a measured reason: mini-swe-agent declares 15 runtime
dependencies, and **litellm — one of them — pulls in `mcp`**. It is the transitive
source of a plugin protocol in what should be a 400-line loop, which is why
installing mini needs `--with "mcp>=2.2.0,<3"` to stop a `ModuleNotFoundError` on
the call path. `import litellm` also costs 2.7 s before any work happens. Dropping
it dropped all of that.

## Quickstart

```bash
git clone https://github.com/HarryPehkonen/ninny
cd ninny

# 1. see what this machine can do
python3 -m ninny doctor

# 2. run a model against a task, with test-first enforced
python3 -m ninny run \
    --task tasks/roman \
    --model deepseek/deepseek-v4.1-flash \
    --provider local \
    --tdd enforce

# 3. judge it YOURSELF. The harness never grades its own subject.
python3 -m ninny check --task tasks/roman --tree runs/roman/<arm>/tree
```

Step 2 prints a record; step 3 is the verdict, and it is run by hand, per run.

A real first run of the shipped example task, `deepseek/deepseek-v4.1-flash`,
sandboxed with bubblewrap, `--tdd enforce`:

```
=== Submitted ===
exit=Submitted  steps=9  api_calls=9  cost=$0.0021
tokens: in=29582 out=2796
test-first: red-first  (mode=enforce, red_step=4, first_src_step=7, refusals=0, bypasses=0)
```

`red_step=4` is the failing test it ran and read; `first_src_step=7` is when it
first wrote the implementation. And `ninny check` on that submission:

```
ACCEPTANCE: 9 tests, 0 failed
GATE PASSED
```

## The four actions

| action | what it does |
|---|---|
| `bash` | run a shell command in the working tree |
| `write_file` | write a file, creating parent directories |
| `read_file` | read a file, optionally a line range |
| `run_tests` | run the task's own test command and report the exit status |

`write_file` exists because quoting a whole file through a shell is where models
most often corrupt their own work — measured: one model had the right code and
stripped the quotes out of its character literals on the way through the shell,
turning `if (c == ',')` into `if (c == ,)`.

`run_tests` exists because it makes a RED observation a **harness event** instead of
a guess at the model's shell history. Its exit status is unambiguous, and the
test-first record is built on exactly that.

A new action is allowed when a measured failure justifies one. Extensible, never
speculative.

## Test-first, as a state machine

```bash
--tdd request    # never refuse; record what happened  (the control condition)
--tdd enforce    # refuse source writes until a test has been seen to fail
--tdd reverse    # allow the code first; require tests before submitting
--tdd off
```

Every run ends with a verdict:

- **`red-first`** — wrote a test, ran it, saw it fail, then implemented.
- **`red-after-code`** — implemented, and only later produced a failing test.
- **`no-red`** — wrote tests but never saw one fail.
- **`no-tests`** — never wrote a test at all.

`reverse` is the control that makes a comparison about **order** rather than about
how many tests happened to get written.

Enforcement is not trusted on its own. After every action the source tree is
hashed, and any change while the run is still in the test phase is recorded as a
bypass. A model that finds a route around the gate shows up in the trajectory
instead of quietly winning. (That detector originally compared mtimes, which missed
two writes inside one filesystem timestamp tick; its own test caught it, and it
hashes content now.)

## A task is a directory

```
tasks/roman/
├── task.toml      the declaration
├── SPEC.md        what the model is given
├── tree/          the starting tree, copied per run
│   ├── src/roman.py
│   ├── tests/own/
│   └── tools/run_own_tests.sh
└── oracle/        the acceptance suite -- NEVER copied into the run
    ├── gate.sh
    └── test_roman.py
```

```toml
name = "roman"
spec_file = "SPEC.md"
tree = "tree"
oracle = "oracle"
oracle_cmd = "bash oracle/gate.sh"

# What run_tests runs. A non-zero exit is what counts as RED. The script fails
# when no tests exist, so a vacuous suite cannot be mistaken for a pass.
test_cmd = "bash tools/run_own_tests.sh"

test_globs = ["tests/own/**"]
src_globs = ["src/**"]
protected_globs = ["tools/**"]     # the agent may not edit the instrument
preflight = ["python3 -V"]         # must work INSIDE the sandbox, or we don't score
step_limit = 25
```

**The oracle must live outside `tree/`, and Ninny refuses to load a task that gets
this wrong.** If the agent can read the acceptance suite it can write its own tests
from the answer key, and both "did it write tests" and "did it write them first"
stop meaning anything. To adapt this for your own project, copy the layout above and
point `oracle/gate.sh` at your real test suite: `ninny check` copies the submission
into a scratch directory and runs the oracle beside it, handing you the tree in
`$NINNY_TREE`.

## Sandboxing

```bash
--sandbox none     # default: bash runs as you
--sandbox bwrap    # every bash action runs in a namespace where only the tree exists
--bwrap-path PATH  # a bwrap binary that is not on PATH
```

With `bwrap`, the agent cannot see your home directory, and cannot see the oracle
you keep beside the task — which is what makes the test-first record attributable.
bubblewrap is Linux-only, so it is never a hard requirement; `none` is the fallback
and the run says so out loud.

**You do not need root or a package manager to try it** (verified on Debian 13):

```bash
apt-get download bubblewrap && dpkg -x bubblewrap_*.deb root
ninny run ... --sandbox bwrap --bwrap-path ./root/usr/bin/bwrap
```

A sandbox that hides the compiler would score every model as unable to build, so
each task declares `preflight` commands that must work **inside** the sandbox. If
they fail, Ninny refuses to score the run rather than blame the model.

Ninny also refuses to score a run in which the agent can read the oracle, unless you
pass `--allow-oracle-visible` and accept an unattributable result.

## Honest cost

Cost is computed from token usage against **the endpoint's own published prices**
(`/models`), or a file you supply with `--price-file`. If the price is unknown,
Ninny reports the cost as unknown rather than guessing. A bundled price table that
silently disagrees with your provider is how an evaluation publishes numbers that
are wrong by 2–5×.

## Pointing it at any endpoint

```bash
--provider local|openai|openrouter|ollama|llamacpp
--base-url http://host:port/v1          # anything OpenAI-compatible
--wire chat|completions                 # protocol shape
```

Two wires are implemented and tested: `chat` (`/chat/completions` with tool calls)
and `completions` (plain text, for models that cannot emit a tool call at all —
a real and measured failure mode). Adding a third is a path, a body builder and a
parser. See [docs/PROVIDERS.md](docs/PROVIDERS.md).

## Testing

```bash
python3 -m unittest discover -s tests -t .
```

78 tests. The suite that matters most is `tests/test_tdd.py`, which includes the
ways the state machine could be fooled: tests that pass are not a RED observation, a
test file alone does not unlock the source, the instrument cannot be edited, and a
source change that sneaks past the gate is detected.

## Credit

Ninny is a fork of **mini-swe-agent 2.4.6** by Kilian A. Lieret and Carlos E.
Jimenez, and it takes from it the shape of the loop, the submit sentinel, the
format-error repair and the trajectory format. See [NOTICE](NOTICE) for exactly
what came from upstream and what changed. The upstream MIT notice is preserved
verbatim in [LICENSE.md](LICENSE.md).

Ninny is not mini-swe-agent, and must never be described as such — the MIT licence
grants no trademark rights.
