# Ninny

A tiny coding-agent harness that **turns process into a measurement**, not a request.

Ninny answers two questions about a model writing code, and keeps the evidence for both:

1. **What did it do?** Every run leaves a record, a diff, and an oracle log — plus a
   transcript in your state directory and a one-line index over every invocation.
2. **Was there a failing test before the implementation?** That is a first-class result,
   named in the record, not a claim in a prompt.

It exists because of one measurement: across **27 clean runs with 12 models**, in two
different harnesses, at every price point, **not one run wrote a test and watched it fail
before writing the code it was testing.** Every harness asks for test-first in prose. None
of them could tell you whether it happened.

Ninny is small on purpose: four actions, one loop, no dependencies, and a record you can
check by hand.

---

## Built on mini-swe-agent

Ninny is a **fork of [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) 2.4.6**
by Kilian A. Lieret and Carlos E. Jimenez, released under the MIT licence. The upstream
project describes itself as *"The 100 line AI agent that solves GitHub issues or helps you
in your command line"* — and that minimalism is the root of this one. Its loop shape, its
single `bash`-plus-submit interface, its submit sentinel, its format-error repair and its
trajectory format are all upstream's design, and they are the reason a harness like this
could be written at all.

What Ninny changes is one thesis: mini asks *did the work get done*; Ninny asks *did the
work get done, and is there any evidence about how*. That required a re-implementation on
the standard library (see [Zero dependencies](#zero-dependencies)) and the additions
described below. Where this project is wrong, the fault is Ninny's, not upstream's.

- [NOTICE](NOTICE) — exactly what came from upstream, version and URL included.
- [LICENSE.md](LICENSE.md) — the upstream MIT notice preserved verbatim, plus Ninny's.
- Ninny is **not** mini-swe-agent and must never be described as such. The MIT licence
  grants no trademark rights, and mislabelling a fork is how credit gets lost.

## What it is not

No MCP. No multi-agent. No plugin system. No daemon, no server, no browser. Four actions,
one loop, and a record. The additions are allowed only when a *measured* failure justifies
one — there is a note in the source for every one of them.

It is also not a worker. Ninny is an **instrument**: it measures what a model-and-task
does. The shape it can handle is one module, well specified, decided by the repo's own gate
or an oracle, on a disposable tree. Four actions cannot do a multi-file refactor, and
pretending otherwise is how a harness grows a plugin registry.

## Install

Ninny has no dependencies, so there is nothing to resolve and no virtualenv to prepare.

```bash
# nothing to install at all
git clone https://github.com/HarryPehkonen/ninny && cd ninny
python3 -m ninny doctor

# as a command, ephemeral, no install and no state left behind
uvx --from . ninny doctor
uvx --from git+https://github.com/HarryPehkonen/ninny ninny doctor   # same code path

# as a command, persistent
uv tool install git+https://github.com/HarryPehkonen/ninny          # or pipx, or pip
uv tool uninstall ninny                                            # undoes it
```

Once Ninny is published to PyPI those shorten to `uv tool install ninny` / `pip install ninny`.

**For an agent, the ephemeral route is the one to reach for.** An agent cannot be handed a
venv-activation step or a dependency resolution in the middle of a task; `uvx --from … ninny
run …` is one line, no install, no state, nothing to clean up, and it runs on whatever Python
uv picks — it chose **3.14** for me on a project whose classifiers then stopped at 3.13. That
is what zero dependencies buys.

Verified in this order: `python3 -m ninny doctor` with nothing installed; `uvx --from .
ninny doctor` ephemeral from a clone; and, once this repository was public,
`uvx --from git+https://github.com/HarryPehkonen/ninny ninny doctor`, which builds the
package out of GitHub and runs it with no third-party import.

### Zero dependencies

Ninny imports only the standard library, and that is not a slogan — the whole suite passes
with site-packages switched off:

```
python3 -S -m unittest discover -s tests -t .    # 154 tests, OK
```

Run on **Python 3.11, 3.12, 3.13 and 3.14**, 154 tests green on each, with no code changes
between them. `requires-python = ">=3.11"` because `tomllib` is the one modern thing it uses.

This is a deliberate reversal of the upstream design, for a measured reason: mini-swe-agent
declares **14 runtime requirements** (35 `Requires-Dist` lines in total; the other 21 sit
behind the `dev`/`modal`/`contree` extras, which are not what an install pulls), and
**litellm — one of the 14 — pulls in `mcp`**. That is the transitive source of a plugin
protocol inside what should be a 400-line loop; it is why installing mini needs
`--with "mcp>=2.2.0,<3"` to avoid a `ModuleNotFoundError` on the call path. `import
litellm` also costs 2.7 s before any work happens. Dropping it dropped all of that.

## Quickstart

```bash
# 0. prove the task grades the way it must, before spending anything on it
python3 -m ninny verify-task --task tasks/roman

# the same, from a project whose fixtures live in ./.ninny -- no flag at all
cd myproject && python3 -m ninny verify-task

# 1. see what this machine can do
python3 -m ninny doctor

# 2. run a model against a task
python3 -m ninny run --task tasks/roman --model <model-id> --provider local

# 3. judge it YOURSELF. The harness never grades its own subject.
python3 -m ninny check --task tasks/roman --tree runs/roman/<arm>/tree
```

Step 2 prints a record; step 3 is the verdict, and it is run by hand, per run. A real run of
the shipped example task, `deepseek/deepseek-v4.1-flash`, sandboxed with bubblewrap, defaults
throughout (paths shortened; the record holds absolute ones):

```
=== Submitted ===
exit=Submitted  steps=9  api_calls=9  cost=$0.0027
tokens: in=36960 out=3740
test-first: red-first  (mode=request, red_step=4 (exit 1), first_src_step=5, refusals=0, bypasses=0)
  diff:       1 added, 1 changed, 0 deleted (+182 -5)
  log:        ~/.local/state/ninny/logs/20261022-164648-run-redkind-r1.log
```

```
$ python3 -m ninny check --task tasks/roman --tree runs/roman/redkind-r1/tree
ACCEPTANCE: 9 tests, 0 failed
GATE PASSED
exit 0
```

## What every run leaves behind

A number you cannot re-derive is a rumour. Each invocation writes four things:

- `trajectory.json` / `trajectory.md` — the record: every step, every refusal, the verdict,
  the cost, and the hashes of the spec and the starting tree it came from
- `diff.patch` — what the run actually changed, against the tree it started from
- `oracle.log` — written by `check`: the verdict, and the output it came from
- a **transcript in the state directory**, and one line in an index over every invocation

When a result is reported, all four paths are named.

`diff.patch` is not decoration. "What did it change?" used to be answered by diffing two
directories by hand, and that is how the last real bug in this project was found: a model
edited a source file through a shell heredoc, and the record — which watched `write_file`
and nothing else — said no source file had ever been touched. A second opinion on the same
question is what caught it.

### The log, and the index

The run directory answers *what happened in this run*. It does not answer *what has Ninny
been doing, and where is the log of it* — and by the time an agent asks that, the terminal
output is gone.

```
$XDG_STATE_HOME/ninny/logs/            (default: ~/.local/state/ninny/logs/, mode 0700)
    20261022-160831-check-cron.log     the full transcript of one invocation, mode 0600
    history.tsv                        one line per invocation, appended, never rewritten
```

Both streams are teed, not just stdout: the interesting line in a run that failed is the
one on stderr, and an audit that stops at stdout is an audit of the happy path. The log
wraps the failure paths too, so a run that dies still leaves both — otherwise the index
would be a list of the runs that went right, which is exactly backwards.

`history.tsv` names its columns on the first line and writes every column on every line,
empty when a field does not apply, so column five is column five:

```
# timestamp	subcommand	task	model	exit_status	steps	cost_usd	verdict	run_dir	log_file
2026-10-22T16:14:50	run	roman	deepseek/deepseek-v4.1-flash	Submitted	10	0.003846	red-first	.../runs/roman/default-told-r2	.../20261022-161343-run-default-told-r2.log
2026-10-22T16:15:52	check	roman		0			OK		.../20261022-161552-check-roman.log
```

Two lines, two invocations: the run, and the judgement of it. The `check` line has no model
and no steps because a `check` uses neither.

A **registered API key is scrubbed on the way to disk**: the process writing the log is the
process holding the key, and its reader may paste the file into a context window. A log
directory that cannot be written is a warning, never a dead run — a harness that refuses to
work because it cannot keep a diary is worse than one that keeps no diary. `--no-log` turns
the whole thing off, on every subcommand.

## `verify-task`: a task is not trusted until it has been proved

An oracle that passes on the tree the agent starts from grades nothing. An oracle that
fails on a solved tree makes the task unsolvable. Both directions, or neither:

```
$ python3 -m ninny verify-task --task tasks/roman
  INFO  own test command fails on the tree the agent starts from   (exit 1 -- expected ...)
  PASS  oracle is RED on the given tree   (exit 1)
  PASS  oracle is GREEN on the fixed tree   (exit 0)
  PASS  own test command reports a planted failing test as a red   (exit 1 -- it ran, and failed)

VERIFIED: the oracle fails where it must, and passes where it must.  (3 controls ran)
```

The third control is the one that grades the *task's own runner* rather than the oracle. It
plants a test that cannot pass (`oracle/probe.sh`, declared as `probe_cmd`), runs the task's
own test command, and requires `1` — ran, and failed. A `2` there means the runner misreports
a red as a build error; a `0` means its suite cannot see a red at all. The dataset has to be a
*planted test*, not a broken answer key: the answer key carries no suite (the agent writes
that), so `test_cmd` on it correctly answers `2` and the control would ask the runner nothing.

A task with no `probe_cmd` is still verified, and says which control did not run — it is not a
task whose runner lies, it is a task whose runner nobody has asked yet.

Exit `0` verified, `1` broken task, `2` unverified — a control that has never been run.
`INFO` never condemns a task: a runner that fails on an empty suite is a *good* runner,
because that is what stops a vacuous suite from counting as a pass. The keeper knows which
case it is; the tool refuses to guess.

This check earns its keep. It caught its own author: an early fixture ran `grep` and then
`echo`, so the script's exit status was `echo`'s and the oracle passed on everything.
`verify-task` said *"it passes on the tree the agent starts from, so it grades nothing."*

So did the third control, within an hour of existing. Both controls above grade the oracle;
neither ever ran the task's own runner against a case it could see failing, and that blind spot
is n=2: `tasks/bits` shipped refusing the edit it required, and `tasks/intset` shipped a
genuine red reported as `exit 2` "nothing ran" because its build-error grep matched Cargo's own
`error: test failed, to rerun pass ...` line. Both passed every static control for weeks; both
were found by spending money on a model. The same task's `tests/own/README.md` also told the
agent to write `tests/own/*.rs`, which Cargo never compiles — that README now says
`tests/own/main.rs`, and its example is code that is run.

## Told, and blocked, are two different things

`enforce` ships two changes at once: the model is **told** that test-first is enforced, and
source writes are **blocked** until a failing test has been seen. Comparing it against a run
that neither tells nor blocks cannot say which of the two did the work — and in the first
eighteen-arm batch the gate never fired once, while the behaviour changed anyway.

So the two axes were separated: `--tdd` decides what the gate blocks, `--tdd-prompt`
decides what the model reads. Six arms a cell, two tasks, oracle judged by hand:

| cell | red-first | steps | $/arm | refusals | bypasses |
|---|---|---|---|---|---|
| neither (not told, no gate) | 2/6 | 19.5 | 0.0245 | 0 | 0 |
| **told only** | **6/6** | **16.7** | **0.0140** | 0 | 0 |
| **both** (shipped default) | **6/6** | 18.2 | 0.0140 | 1 | 0 |
| blocked only | 4/6 | 19.0 | 0.0189 | 5 | **2** |

**The instruction did the work; blocking without telling is strictly worse.** Blocking
alone cost more, produced fewer red-first runs, and is the only cell where a model evaded
the rule.

*That conclusion was drawn while the exit-code bug described in
[Known limits](#known-limits) was still in the harness: most of the example task's banked
reds were not observations of a failing test, and every cell above that includes them is
inflated. The arms are being re-run before any of these rates is quoted again. Treat the
table as what was believed at the time, not as a current result.*

The consequence is now the default: a run that asks for nothing is **told**. It carries the
enforced wording with the gate left loose, and `--tdd enforce` is what adds refusal on top.
`off` still means silent; `reverse` keeps its own block, because the enforced text describes
the opposite sequence and telling a reverse run that would be a lie.

The honest cost of that change: it changes the conditions of every future arm, so the
"neither" row above is historical. It was the right default for the artifact's users — an
agent does not read your documentation, it reads your defaults.

To set the axes apart by hand, when you are measuring rather than working:

```bash
python3 -m ninny run --task tasks/roman --tdd request --tdd-prompt enforce   # told, not blocked
python3 -m ninny run --task tasks/roman --tdd enforce --tdd-prompt request   # blocked, not told
```

Both are recorded (`run.tdd_mode`, `run.tdd_prompt_mode`), so an arm can be identified from
its own trajectory instead of from a note somebody wrote down.

## Test-first, as a state machine

```bash
--tdd request    # never refuse; record what happened  (the loose gate, the default)
--tdd enforce    # also refuse source writes until a test has been seen to fail
--tdd reverse    # allow the code first; require tests before submitting
--tdd off
```

### The phases, named

An `enforce` or `reverse` run moves through three phases, and the model is told which one it
is in -- in the prompt, in a refusal, and in the observation that comes back after an action.
The note goes on the observation because a note in the harness's own log is a note the model
never reads:

```
1  RED-FIRST   write a test that RUNS and fails
2  GREEN       implement until the suite passes
3  HAND BACK   submit; the record must show the red before the source
```

The plan line prints the sequence before the first model call, and each step line carries the
phase the step started in. The names live in one place -- `PHASE_ORDER`, `PHASE_LABELS`,
`PHASE_JOBS` in `ninny/tdd.py` -- and the prompt, the refusal text and the observations are
readers of it. Two moments earn an interruption: the phase moving, and a suite that reported
nothing at all. The second one is the one that matters on a compiled task, where a build error
is the commonest way to think you have gone red when nothing ran.

Every run ends with a verdict:

- **`red-first`** — wrote a test, ran it, saw it fail, then implemented.
- **`red-after-code`** — implemented, and only later produced a failing test.
- **`no-red`** — wrote tests but never saw one fail.
- **`no-tests`** — never wrote a test at all.

`run_tests` is a **first-class action**, which is what makes a RED observation a harness
event rather than a guess at the model's shell history.

That event is a **contract on the exit code**, because the harness will not read compiler
output to decide whether a test really failed:

```
0  the tests ran and passed
1  the tests ran and failed          -> a RED observation
2  the suite could not run at all    -> nothing was observed, so not a RED
```

Exit 2 is the load-bearing one. A build error, an import error, a suite with nothing to
collect -- all of them end non-zero, none of them observed anything, and all of them used to
be banked as a RED. Such a run still appears in the record, with its code; it is simply not
an observation, and `enforce` will not unlock the source on one either. On a compiled task
the shortest path to a legitimate red is therefore the stub that the C++ runner recommends
in its own failure message. The shipped tasks implement this contract; `ninny/env.py` states
it once, and `ninny/tdd.py` reads the same constants.

`reverse` is the control that makes a comparison about **order** rather than about how many
tests happened to get written.

Enforcement is not trusted on its own. After every action the source tree is hashed, and
any change while the run is still in the test phase is recorded as a bypass — so a model
that finds a route around the gate shows up in the trajectory instead of quietly winning.
The tree is the arbiter, not the action log: it caught both live bypasses in the dataset
after the gate had missed them.

## A run cannot hand back a red tree

Test-first asks whether a test was seen to fail before the code was written. This asks a
different question: is the thing green? If the last `run_tests` the arm ran exited
non-zero, the submit is refused once, with the reason, in **every** mode. It is not a
test-first rule, so it is not conditional on the test-first mode. `--allow-red-submit`
turns it off — the switch between *get the best code out of this model* and *measure what
this model does when nobody stops it*.

## The four actions

| action | what it does |
|---|---|
| `bash` | run a shell command in the working tree |
| `write_file` | write a file, creating parent directories |
| `read_file` | read a file, optionally a line range |
| `run_tests` | run the task's own test command and report the exit status |

`write_file` exists because quoting a whole file through a shell is where models most often
corrupt their own work — measured: one model had the right code and stripped the quotes out
of its character literals on the way through the shell, turning `if (c == ',')` into
`if (c == ,)`.

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

# verify-task's third control: a command that plants a test which cannot pass, so the task's
# own runner can be required to report it as a red (exit 1) rather than as "nothing ran"
# (exit 2). Runs with cwd = the staging directory, like oracle_cmd. Optional: without it the
# control says it did not run, and the task is still verified by the two oracle controls.
probe_cmd = "bash oracle/probe.sh"

# What run_tests runs. Its exit code is the contract: 1 is a failing test (a RED), 2
# means the suite could not run, which is not an observation. The script fails when no
# tests exist, so a vacuous suite cannot be mistaken for a pass.
test_cmd = "bash tools/run_own_tests.sh"

test_globs = ["tests/own/**"]
src_globs = ["src/**"]
protected_globs = ["tools/**"]     # the agent may not edit the instrument
preflight = ["python3 -V"]         # must work INSIDE the sandbox, or we don't score
step_limit = 25
```

**The oracle must live outside `tree/`, and Ninny refuses to load a task that gets this
wrong.** If the agent can read the acceptance suite it can write its own tests from the
answer key, and both "did it write tests" and "did it write them first" stop meaning
anything. To adapt this for your own project, copy the layout above and point
`oracle/gate.sh` at your real test suite: `ninny check` copies the submission into a scratch
directory, runs the oracle beside it, and hands it the tree in `$NINNY_TREE`. The next
section has the two full recipes — a new project, and an existing one that must not gain
any files at all.

### The format is not Python-shaped

The only task shipped here is `tasks/roman`, because **a benchmark whose answer key is
public is not a benchmark**: the two harder tasks used for the measurements in this README
(and the C++ arenas behind them) are deliberately not published, answer keys least of all.
`tasks/roman` does ship with its answer key (`fixed/`), because it is an example rather than
a benchmark — nobody should score a model on it and expect to learn anything.

The same format does run other languages and other test runners. A C++ task — a cron
expression parser with bitmask semantics, frozen headers, graded by 122 acceptance checks
compiled with `-Wall -Wextra -Wpedantic -Werror` — was ported to this layout, passed
`verify-task` on the first try, and was then solved by `deepseek/deepseek-v4.1-flash` at a
40-step limit for **$0.0614** with a clean `ACCEPTANCE: 122 checked, 0 failed`. Nothing in
the harness needed to know it was C++: the task brought its own test command, its own
preflight and its own oracle.

That run also produced the example that forced the change now in the harness (see
[Known limits](#known-limits)): of its three observed reds, one was `cc1plus: fatal error:
src/*.cpp: No such file or directory` — a build error, where nothing ran at all — and two
were real assertion failures. Ninny banked the build error as the RED and reported the run
`red-first` off it. Under the exit-code contract it is `red-after-code`: the build error is
no longer an observation, and the first test that really ran came after the first source
write.

A re-run under the contract is the cleaner example, and it exposes the next limit above:
`Submitted` in 28 steps for $0.0394, oracle **`ACCEPTANCE: 122 checked, 0 failed`** by hand,
and a recorded `test_runs` of `[[5,2],[7,1],[9,1],[11,0],[15,0]]`. It wrote its suite, then a
**482-byte stub** into `src/`, could not compile (2), fixed that, ran the suite and watched it
fail (1), then wrote the real implementation and went green. Test-first in substance, and the
verdict still reads `red-after-code`, because the stub is a file under `src/` and it landed one
step before the red.

## Starting a new project, or adopting an existing one

Two rules decide the layout, and neither is negotiable:

- **The oracle never lives inside the tree.** If the agent can read the acceptance suite it
  can write its tests from the answer key, and *did it write tests* and *did it write them
  first* both stop meaning anything. `ninny` refuses to load a task that gets this wrong.
- **The starting tree is copied for every run.** Your project is never written to, so a
  fixture can point at a real checkout without risking it.

Everything else is a convention you can move.

### A new project: write the spec before the code

| path | why it exists |
|---|---|
| `SPEC.md` | the contract the model is given — the interface, the error behaviour, the exit codes, what counts as canonical. Written before any code, and frozen: it is the only thing standing between "the model solved it" and "the model solved something" |
| `task.toml` | the declaration: which directories, what the agent's test loop is, what it may not touch |
| `tree/` | the agent's whole world — the interface, unimplemented, plus the instrument that measures it |
| `oracle/` | the hidden grader, and `frozen.sha256` for the instrument |
| `fixed/` | the answer key. It is not documentation for the model; it is the control that proves the oracle can pass at all |

Day one, in this order:

1. **`SPEC.md`, before the code.** Then the interface it describes, unimplemented, under
   `tree/`.
2. **The stub must build.** Not a file that throws — a stub that runs and returns nothing.
   That is what makes the agent's first RED *a test that ran and failed* rather than
   `exit 2` from a compiler. In a compiled language it is not optional: a C++ task without a
   stub produced `cc1plus: fatal error` as its "first red", where nothing ran at all.
3. **The instrument**: what `run_tests` runs (`test_cmd`), and a `tests/own/README.md`
   telling the agent how its suite is executed and what the exit codes mean. Add it to
   `protected_globs`, and hash it in `oracle/frozen.sha256` — the manifest key refuses the
   edit, the hash proves whether it happened anyway.
4. **`oracle/`**, outside the tree, with `oracle_cmd`. This is your real test suite plus
   anything the agent must not see.
5. **`fixed/`** — a copy of `tree/` with the reference implementation dropped in. Then
   `ninny verify-task --task tasks/<name>`: **RED on the stub, GREEN on `fixed/`**. A task
   that cannot fail on the stub grades nothing; an oracle that only ever fails proves
   nothing. This control caught nine of the ten oracle bugs found while building these
   fixtures.
6. Only then spend money on arms, and judge each one by hand with `ninny check`.

### An existing project that must not gain files

The fixtures do not have to live in the project, and `test_cmd` is a **command, not a
file** — so nothing has to be added to the repository at all. Keep the fixture directory
somewhere else and point it at a snapshot:

```bash
# a snapshot, not the live checkout: every arm must start from the same tree
git -C ~/work/myproject archive HEAD | tar -x -C fixtures/myproject/snapshot
```

```toml
# fixtures/myproject/task.toml -- outside the project, nothing added to it
name = "myproject"
spec_file = "SPEC.md"
tree = "snapshot"                 # gets copied per run; the live checkout is never touched
oracle = "oracle"                 # stays here, outside the project
oracle_cmd = "bash oracle/accept.sh"

# The project's own harness, with both guards inlined: nothing-ran, and the count.
# test_cmd runs with cwd set to the run's copy of the tree, through a shell.
test_cmd = """
ctest --test-dir build --output-on-failure; rc=$?
n=$(ctest --test-dir build -N 2>/dev/null | grep -c 'Test #')
echo "NINNY_TESTS: $n"
[ "$n" -gt 0 ] || exit 2
exit $rc
"""

protected_globs = ["tests/**", "CMakeLists.txt"]   # the project's suite and its build
src_globs = ["src/**"]
preflight = ["cmake --version"]                    # must work inside the sandbox
sandbox_binds = []                                 # toolchains outside /usr, e.g. ["$HOME/.hermes/node"]
```

The same shape works for any runner — run it, keep the exit code, count what it collected,
print `NINNY_TESTS: <n>`, and `exit 2` when the count is zero. Two details, both of them
things that bit while writing this: `grep -c` prints `0` rather than nothing, so that count
is never empty, but a runner that prints no count line at all — pytest collecting nothing —
needs `n=${n:-0}` first, or the guard ends up comparing an empty string. And the count only
means something if the runner prints it on **every** run, including the failing ones.
Without a count, "my suite quietly got smaller" has no failing signal at all.

What this costs you, honestly:

- **No frozen hash.** A file under `tree/` can be hashed; an inline command cannot. The
  substitute is `protected_globs`, which *refuses* the write instead of detecting it
  afterwards — prevention for edits made through Ninny's own action, while an edit smuggled
  through a shell heredoc is caught later by the tree diff and recorded as `bypass_detected`.
- **The count is only as good as your harness.** If the project's suite cannot say how many
  tests it has, the one signal that catches a shrinking suite is gone.
- **Test-first ordering is the weakest metric here** and is recorded, never gated. Expect
  `red-after-code` in compiled projects where the first real test run lands after a stub.
- Runs and logs stay outside the repo (`runs/`, `~/.local/state/ninny/logs`), so adopting
  Ninny adds nothing to your checkout — not even a `.gitignore` line, unless you keep the
  fixtures in the same repository.

**Where the fixtures live is a real choice, and `--task` defaults to the first one:**

- `./.ninny/` — the convention. `ninny run` and `ninny verify-task` need no flag from
  inside the project. They are then inside your repository, so commit them or add a
  `.gitignore` line.
- anywhere else — `--task ../ninnyspec`, or `--task fixtures/myproject`. Nothing is added
  to the checkout and the fixtures stay out of its history.

Either way, whether the answer key is genuinely out of the agent's reach is a property of
the **sandbox**, not of the path. Measured with `Sandbox.hides(oracle, workdir)`, the value
the guard reads:

| `--sandbox` | `hides(oracle)` | what happens |
|---|---|---|
| `bwrap` | `True` | the oracle is not in the sandbox at all |
| `none` | `None` — "cannot tell" | the run proceeds under the `NO SANDBOX` banner |

So `--sandbox none` does not refuse: `None` is not `False`, and the guard only refuses a
sandbox that positively reports the oracle as readable (that is when you need
`--allow-oracle-visible`). If you want the answer key to be unreachable rather than merely
unattributed, sandbox the run.

A runnable instance of exactly this layout ships in
[`examples/existing-project/`](examples/existing-project/): an inline `test_cmd`, a
snapshot instead of the live checkout, and an oracle outside the project.
`ninny verify-task --task examples/existing-project` proves it in about a second.

## Sandboxing

```bash
--sandbox none     # default: bash runs as you
--sandbox bwrap    # every bash action runs in a namespace where only the tree exists
--bwrap-path PATH  # a bwrap binary that is not on PATH
```

With `bwrap`, the agent cannot see your home directory, and cannot see the oracle you keep
beside the task — which is what makes the test-first record attributable. In a live run the
model went looking (`ls -la ..`, `find … -iname '*cron*'`) and found exactly one directory
chain: its own tree. bubblewrap is Linux-only, so it is never a hard requirement; `none` is
the fallback and the run says so out loud.

**You do not need root or a package manager to try it** (verified on Debian 13: bubblewrap
0.12.0, a 56 KB `.deb` holding one binary and four system libraries, 3 ms of overhead per
action, running as your own uid):

```bash
apt-get download bubblewrap && dpkg -x bubblewrap_*.deb root
python3 -m ninny run ... --sandbox bwrap --bwrap-path ./root/usr/bin/bwrap
```

A sandbox that hides the compiler would score every model as unable to build, so each task
declares `preflight` commands that must work **inside** the sandbox. If they fail, Ninny
refuses to score the run rather than blame the model. Ninny also refuses to score a run in
which the agent can read the oracle, unless you pass `--allow-oracle-visible` and accept an
unattributable result.

## Honest cost

Cost is computed from token usage against **the endpoint's own published prices** (`/models`),
or a file you supply with `--price-file`. If the price is unknown, Ninny reports the cost as
unknown rather than guessing. A bundled price table that silently disagrees with your
provider is how an evaluation publishes numbers that are wrong by 2–5×.

## Pointing it at any endpoint

```bash
--provider local|openai|openrouter|ollama|llamacpp
--base-url http://host:port/v1          # anything OpenAI-compatible
--wire chat|completions                 # protocol shape
```

Two wires are implemented and tested: `chat` (`/chat/completions` with tool calls) and
`completions` (plain text, for models that cannot emit a tool call at all — a real and
measured failure mode; live-verified against a model that speaks it). Adding a third is a
path, a body builder and a parser. See [docs/PROVIDERS.md](docs/PROVIDERS.md).

## Known limits

Written down because a harness that hides its own seams is lying to you.

- **A "RED" is an exit code, and it means only what the task's runner says it means.** The
  contract above separates "the tests ran and failed" (1) from "nothing ran" (2), and the
  distinction was measured before it was trusted: of the **36 stored runs that banked a RED,
  the 25 that banked one where nothing executed were not observations** — in the example
  task, 24 of its 26, every one of them `Start directory is not importable`, from a package
  marker that did not exist yet; in the C++ task, its one red, the build error. The harder
  task was unaffected: **0 of its 9 reds** were fake. A task whose runner exits 1 for both
  kinds of failure keeps the old weakness, and the harness cannot see that from the outside —
  a red is worth exactly as much as the task it came from. **What a red still does not mean
  is that the test had teeth**: see the next limit.
- **Order is a Python-shaped question.** `red_step < first_src_step` asks whether a test failed
  before the first source write, and on a compiled task nothing can fail until the sources
  compile, so the model must put *something* in `src/` first -- exactly what the C++ task's own
  failure message recommends ("the fix is a stub"). Both C++ arms recorded here wrote a stub
  and were reported `red-after-code` for it. The answer is not a stub detector; it is to read
  `test_runs` and the diff, of which the verdict is only a summary. That arm's sequence --
  `[[5,2],[7,1],[9,1],[11,0],[15,0]]` -- reads as textbook test-first, and no one-word verdict
  could carry it. **A verdict is a summary for Python-shaped tasks; the record is the evidence
  everywhere.**
- **The write gate classifies intent from a shell command**, so a source write through an
  intermediary can slip past it (a heredoc, or a script written into the tree and then run).
  Both live instances were caught by hashing the tree afterwards — which is why the tree,
  not the action log, is the arbiter.
- **Teeth are measured but not built in.** Sabotaging 20 stored solutions of the example
  task took 19 seconds and every one of them caught at least five of the six seeded defects —
  so on that task an automatic check would print "all clear" every time. It is deferred until
  a task's own tests *are* the deliverable.
- **Four actions cannot do a multi-file refactor.** Deliberate.
- **`bwrap` is Linux-only.** Deliberate, and always optional.

## Testing, and the gate

The suite is stdlib `unittest`, and needs no site-packages to run:

```bash
python3 -m unittest discover -s tests       # the whole suite
python3 -S -m unittest discover -s tests    # and with no site-packages at all
```

`./scripts/gate.sh` is **the gate**: [kit-ci](https://github.com/HarryPehkonen/KitCI) reading
`gate.toml`, four stages, offline, no service and no account. Arm it once per clone —
`git config core.hooksPath .githooks` — and `git commit` runs the fast tier while `git push`
runs the full one. Deliberate bypass: `--no-verify`.

| stage | ~cost | the claim it keeps honest |
|---|---|---|
| `tree` | 0.0 s | the tree is source: no tracked bytecode, no staged-check residue inside a task (this repo lost 1.28 GB to that), no untracked files. `CI_REQUIRE_CLEAN=1`, which `pre-push` exports, also refuses uncommitted edits to tracked files. |
| `tests` | 0.5 s | the suite passes — and Ninny's **own** exit-code contract is applied to Ninny: `0` ran and passed, `1` ran and failed, `2` nothing ran. `python3 -m unittest` prints `NO TESTS RAN` and **exits 0**, so a suite that quietly stopped being collected would otherwise read as green. |
| `stdlib` | 0.6 s | every module under `ninny/` imports with no site-packages, and the suite runs under `python3 -S` too. This is the stage that fails if a third-party import ever appears. |
| `tasks` | 20 s | every task and example still **verifies**: the oracle RED on the stub tree, GREEN on the answer key. `bits` (CMake + GoogleTest) and `roman-cli` dominate, and a first run on a cold build cache costs ~55 s — that first number is a measurement of the cache, not of the gate. |

Costs are warm; a cold first run roughly triples the cheap stages and the `tasks` one. Tiers:
`fast` = `tree tests stdlib` (~1 s, for the commit hook); `full` = all four (~21 s warm, ~57 s
cold, for `push`, a hand run, and the publish path). `kit-ci --list` prints the stage list from
the same parse the run uses.

Two things worth knowing before you trust a green:

- **A fresh clone has no hooks armed.** `core.hooksPath` lives in `.git/config`, not in the
  tree, so a clone commits and pushes unguarded while looking armed. That is why this repo's
  publish path — a *filtered* clone, since the history holds two private tasks — runs
  `./scripts/gate.sh` by hand before pushing rather than relying on the hook.
- **A missing engine fails loudly**, not green: with no `kit-ci` on `PATH`, `scripts/gate.sh`
  exits 1 and says so.

The suites that matter most are `tests/test_tdd.py`, which includes the ways the state machine
could be fooled (a passing test is not a RED observation, a test file alone does not unlock
the source, the instrument cannot be edited, a source change that sneaks past the gate is
still detected) — and `tests/test_logs.py`, which pins the properties a log has to have to be
worth reading.

## Why it works this way

The design is not taste. Each of these is a measured or published claim, and where a
reference says something better than this README can, it is quoted.

**On enforcing process rather than asking for it.** Kent Beck, in *Augmented Coding:
Beyond the Vibes* (25 June 2025), draws the line this project sits on:

> In vibe coding you don't care about the code, just the behavior of the system. In
> augmented coding you care about the code, its complexity, the tests, & their coverage.

And he lists what to watch for when the model drifts, which is precisely what this harness
records rather than trusts:

> 1. Loops. 2. Functionality I hadn't asked for (even if it was a reasonable next step).
> 3. Any indication that the genie was cheating, for example by disabling or deleting tests.

Ninny's bypass detector and red-tree rule exist because that third one happened here, live:
one arm manufactured a throwaway failing test to satisfy the letter of the rule, and two
wrote around a write-gate that was watching the wrong thing.

**On what a good test is.** Beck's *Test Desiderata* names the property the teeth probe
measures, in his words:

> **Behavioral** — tests should be sensitive to changes in the behavior of the code under
> test. If the behavior changes, the test result should change.

A suite where `to_roman(4)` returns `"IIII"` and nothing complains is not behavioral, and
no amount of "did you write it first" makes it so. That is why the two questions are kept
separate: the order is one measurement, the artifact is another.

**On not optimising the wrong number.** Inozemtseva & Holmes, *Coverage Is Not Strongly
Correlated with Test Suite Effectiveness* (ICSE 2014), across 31,000 test suites on five
systems up to 724,000 lines, found a *low to moderate* correlation between coverage and
effectiveness once suite size is controlled for, concluding that coverage **"should not be
used as a quality target"**, and that the number of test *methods* correlates with
effectiveness rather better. So Ninny counts what it can observe (a red was seen, at which
step, by which action) and refuses to score a percentage.

**On invented sabotage.** Mutating a program to see whether its tests notice is not a trick
invented here: it goes back to DeMillo, Lipton & Sayward, *Hints on Test Data Selection:
Help for the Practicing Programmer* (*Computer*, April 1978), and the state of the art is
summarised in Jia & Harman's survey (*IEEE TSE*, 2011). At industrial scale, Google
reports **400,000 mutants evaluated per month, about 80% of them productive** (Petrović et
al., *An Industrial Application of Mutation Testing*, ICST 2018), and describes running the
technique incrementally on changed code in review across **two billion lines of code and
over 500 million tests executed daily**, evaluated with 24,000+ developers on 1,000+
projects (Petrović et al., *Practical Mutation Testing at Scale*, arXiv:2102.11378).

The lesson taken from that literature is about *tooling*, not principle. Mutation is a
language-agnostic idea and a language-specific tool (mutmut, cosmic-ray, PIT, Stryker,
cargo-mutants, mull) — and a mutant must still compile, which in C++ means a generic
operator generates mostly build errors. Hand-picked sabotage per task beats an automatic
operator, which is why the probe here was 20 seconds of work rather than a subsystem.

**On measuring your own instruments.** Seven bugs were found in this project, and **all
seven were in the measurement code** — the part that decides what the numbers mean. Three
would have published false numbers. Not one was found by the harness. They were found by
running both-direction controls on every oracle, running the oracle by hand, reading the
diffs, comparing arms against each other, and replaying every stored run after every rule
change. If you take one thing from this repository, take that ratio.

## References

- mini-swe-agent 2.4.6 — <https://github.com/SWE-agent/mini-swe-agent> (MIT, Kilian A.
  Lieret and Carlos E. Jimenez); the root of this project.
- Kent Beck, *Augmented Coding: Beyond the Vibes*, Tidy First?, 25 June 2025 —
  <https://tidyfirst.substack.com/p/augmented-coding-beyond-the-vibes>
- Kent Beck, *Test Desiderata* — <https://kentbeck.github.io/TestDesiderata/>
- R. A. DeMillo, R. J. Lipton, F. G. Sayward, *Hints on Test Data Selection: Help for the
  Practicing Programmer*, Computer 11(4):34–41, April 1978 — doi:10.1109/C-M.1978.218136
- Y. Jia, M. Harman, *An Analysis and Survey of the Development of Mutation Testing*,
  IEEE TSE 37(5):649–678, 2011 — doi:10.1109/TSE.2010.62
- G. Petrović et al., *An Industrial Application of Mutation Testing: Lessons, Challenges,
  and Research Directions*, ICST 2018
- G. Petrović, M. Ivanković et al., *Practical Mutation Testing at Scale: A View from
  Google*, arXiv:2102.11378
- L. Inozemtseva, R. Holmes, *Coverage Is Not Strongly Correlated with Test Suite
  Effectiveness*, ICSE 2014

## Licence

MIT. Ninny's own notice and the upstream notice it inherits are both in
[LICENSE.md](LICENSE.md); [NOTICE](NOTICE) records the provenance. Ninny is not
mini-swe-agent, and must never be described as such.
