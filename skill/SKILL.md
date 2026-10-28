---
name: ninny-harness
description: Use when running or extending Ninny, the test-first harness.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [harness, tdd, evaluation, coding-agent, ninny]
    related_skills: [coding-model-evaluation, coding-agent-orchestration, self-hosted-quality-gates]
---

# Ninny: the test-first coding harness

## When to Use

- Running Ninny on a task, or adding a task/oracle to the repo.
- Any work on a clone of this repository.
- Comparing coding harnesses by *process* rather than by outcome.
- Sandboxing a coding agent on Linux without root.

Ninny is Harri's fork of mini-swe-agent 2.4.6 (MIT), stdlib-only. It exists to *enforce and measure* test-first, not to ask
for it in prose. Repo is public: `HarryPehkonen/ninny`.

Support files, load on demand: `references/task-layout.md` (authoring a task, editing
`task.toml`, or asking why a write was refused), `references/traps-found-the-hard-way.md`
(a record that surprises you -- a refusal, a `no-red`, a missing verdict -- or before
blaming a model for a bad process), `references/publishing.md` (pushing to the public
repo, and proving the publish landed).

**The same material, generified, now ships with the tool as `docs/DRIVING.md`.** Someone who clones
Ninny gets the manual without this skill, and a fresh agent that had never seen the repository drove a
full arm from it on the first try. Add caller-facing lessons THERE first and point here, so the two
cannot drift: the repository document is the definition, and this file is the agent-facing one. An
operator's copy may sit outside the repository with this machine's paths in it; nothing here depends on
those.

## Run it

```bash
cd <the clone>            # BWRAP=$(command -v bwrap || echo ./root/usr/bin/bwrap)
python3 -m ninny verify-task --task tasks/roman   # prove the task grades correctly
    # THREE controls now, not two: the oracle is RED on the tree the agent starts from, GREEN
    # on the answer key, and the task's OWN runner must report a planted failing test as exit 1
    # (`probe_cmd` in task.toml, a recipe that plants a test which cannot pass). A task without
    # probe_cmd still verifies, and the verdict names the control that did not run.
python3 -m ninny doctor                     # what this machine can do
python3 -m ninny run --task tasks/roman --model deepseek/deepseek-v4.1-flash \
    --sandbox bwrap --bwrap-path "$BWRAP" --steps 40 --name arm1
    # told by default; add --tdd enforce to also gate writes.
    # A SCORED run uses bwrap: --sandbox none leaves the oracle readable and the number
    # unattributable (Sandbox.hides -> None when there is no sandbox to ask).
python3 -m ninny check --task tasks/roman --tree runs/roman/arm1/tree
```

Every run leaves FOUR things, and a reported result names them: `trajectory.json/.md`
(the record), `diff.patch` (what changed, against the starting tree), `oracle.log`
(written by `check`), and the durable log below. The record also carries
`spec_sha256`/`tree_sha256` so a number traces back to its exact inputs.

The record carries two more fields the harness fills in on its own initiative, holding the same numbers
the delegate was shown, so the two can never disagree: **`checks`** (`[step, exit, seconds]` for the
declared cheap check after every write that landed) and **`limit_runs`** (`[step, kind, exit, seconds]`
for what was run after a run ended with no handback at all). Both are in `docs/DRIVING.md` too.

**Read `result.json` only after the process has exited.** It is written incrementally, so a snapshot taken
mid-run reports empty `test_runs`/`red_step` and reads exactly like a run that never ran the suite. This has
produced a wrong verdict twice; the durable log line and the printed summary are the mid-run sources.

### The log: what has Ninny been doing?

`$XDG_STATE_HOME/ninny/logs` (default `~/.local/state/ninny/logs`, directory 0700,
files 0600): a transcript per invocation plus `history.tsv` — one appended line per
invocation, header-named, fixed column positions:

```
timestamp  subcommand  task  model  exit_status  steps  cost_usd  verdict  run_dir  log_file
```

Both streams are teed and the failure paths are wrapped, so a run that dies still leaves
the log and the line; a registered API key is scrubbed on the way to disk; a log
directory that cannot be written is a warning, never a dead run. `--no-log` on every
subcommand turns it off and must then create nothing at all.

Modes: `--tdd` chooses what the GATE does — `enforce` (refuses source writes until a RED
test is seen), `request` (record only, the default), `reverse` (code first, tests
required before submit), `off`. `--tdd-prompt` chooses which Testing block the model
READS, and the two are separate axes, both recorded (`run.tdd_mode`,
`run.tdd_prompt_mode`). A run that asks for neither is TOLD: the enforced wording ships
by default. Verdicts: `red-first`, `red-after-code`, `no-red`, `no-tests`.

**The phases are named, and the model is told which one it is in.** An `enforce`/`reverse`
run moves through `RED-FIRST -> GREEN -> HAND BACK` (`PHASE_ORDER`/`PHASE_LABELS`/`PHASE_JOBS`
in `ninny/tdd.py`; the internal state names stay `test`/`impl`/`done`, so no record shape
moved, and the plan line prints the sequence before the first model call). The vocabulary has
three readers and one definition: the prompt, the refusal text, and the observation that comes
back after an action. **The note rides on the observation, never on the harness log** -- the log
is operator-facing and the model does not read it, while the observation is the same string the
record stores, so what the model was told and what the record claims cannot drift apart. An interruption is earned by the phase moving, by a suite that reported nothing at all
(exit 2, the C++ build-error case, where a model that has just read `cc1plus: fatal error` reads
it as a failure it earned) -- and by the budget, twice at most: a run that has written nothing at
half its steps is told once, and the end of the budget gets ONE note, the specific "run the acceptance
command, a patch that does not build cannot be believed" when nothing has gone green yet and the
generic hand-back warning when it has, never both. The kind lands in `told`, so a run that was told
to verify can never read like one that was not. See "What the model is told about its own budget"
in the README. It is guidance, not enforcement: the order of writes stays a
recorded number and never becomes a gate.

**A red is only an observation if the suite actually ran, and the exit code is the
contract** (stated once in `ninny/env.py`, read by `ninny/tdd.py`):

```
0  the tests ran and passed
1  the tests ran and failed          -> a RED observation
2  the suite could not run at all    -> nothing was observed, so not a RED
```

Ninny never parses compiler output. A build error, an import error and an empty suite are
all non-zero and none of them observed anything, so a task whose runner cannot tell them
apart cannot produce a trustworthy red — the task declares it in the only channel a shell
command has. `enforce` will not unlock the source on a 2 either, and exit 2 shows up in the
run summary as the code next to `red_step`.

**The harness never runs the gate.** `ninny check` is run by hand, per submission;
that rule comes from the C++ eval rig and it is deliberate — a harness that grades
its own subject is not evidence.

## What to enforce, and what to only record (measured)

Six arms a cell, two tasks, one model, oracle hand-judged:

```
cell                          red-first  steps  $/arm   refusals  bypasses
told only  (nudge)               6/6      16.7  0.0140      0         0
told + gated  (shipped enforce)  6/6      18.2  0.0140      1         0
gated only  (silent)             4/6      19.0  0.0189      5         2
neither  (the old default)       2/6      19.5  0.0245      0         0
```

- **Tell the model about the process; enforce properties of the ARTIFACT at handback.**
  On the order of writes, telling alone matched the fully gated cell at the same cost and
  two fewer steps — the gate never fired in either. Gating without telling was worse on
  every axis and is the only cell with bypasses against it.
- **Submit-time refusals are the ones that work.** Across every stored run they produced
  compliance on the retry, without exception: a submission is judged on the artifact,
  while a write gate has to infer intent from a shell command.
- **Record the order; never gate on it.** A real arm satisfied the letter of the RED rule
  with a throwaway failing test, deleted it and submitted — the verdict still said
  `red-after-code`. That is exactly why the order is the metric and existence is not.
- **Know when the writing is over.** Ninny's leverage is in the task and its oracle, not
  in more rules on the model: on both shipped tasks acceptance is 18/18 across every cell,
  so the process record is the only thing that varies.
- **Grade the instrument the agent USES, not only the one that grades the agent.** The oracle
  controls say nothing about the `test_cmd` the model actually calls. Two published tasks were
  broken exactly there -- one refused the edit it required, one reported a genuine red as
  exit 2 -- and both passed every static control for weeks until models were run against them.
  `probe_cmd` closes it; the failing case that justifies a fix has to come from an arm or a
  control, never from a design conversation.

## Task layout (the rules are enforced, not advisory)

Moved to `references/task-layout.md` -- read it when you are adding a task, editing
`task.toml`, or asking why a write was refused.

## Working on a real repository (`ninny run --repo`)

The second door: same loop, same gate, same exit-code contract, same record, same `ninny verdict`,
pointed at a working copy instead of a fixture.

```bash
ninny run --repo ~/src/myrepo \
    --prompt "add a --json flag to the report command" \
    --test-cmd "bash scripts/gate.sh --tier fast" \
    --sandbox bwrap --bwrap-path "$BWRAP" --name myrepo-1
ninny verdict runs/myrepo/myrepo-1      # 0 artifact | 1 unproven, with reasons | 2 nothing back
```

- `--test-cmd` is required and never guessed; `--prompt` or `--prompt-file` is required (there is
  no SPEC.md to stand in for it). `--repo` and `--task` are different doors and are refused
  together.
- `--test-glob` (repeatable) is what turns ON the red-first gate. Without it the run is `request`:
  the handback rule (green after the last source write, enforced by the harness itself if the model
  skipped it) still holds, and the order is recorded. With it, the gate refuses source writes until
  a red is seen -- and on a repository whose suite is GREEN that is a deadlock, because every way to
  make a red is itself a write. That is why it is not the default.
- Staging is a `git worktree` at HEAD, so the repository is untouched and the run is isolated. **The
  main repo is bound into the sandbox read-only** -- measured: a worktree's `.git` is a FILE
  pointing at it, so without the bind git inside bwrap reports "not a git repository"; with it
  status/diff/log work and add/commit fail cleanly, which is the delegate's business anyway.
- The patch is `git diff --cached` in the worktree against the commit it was staged at, with
  `git add -A` first so a new file is included -- NEVER a comparison against the live tree.
- **Every limit is a dial, and each has its own.** `--steps` (60 by default in repo mode), `--wall-time`
  (default **0, which is no limit at all**), `--timeout` (one bash action; floors at the declared suite
  timeout, so a slow gate is not killed while it is producing evidence), `--request-timeout` (one model call,
  600 s), `--test-timeout` (the repository's own suite, 600 s).
- **The declared cheap check is a THIRD job for `[runner] build`** -- and for a repository run's
  `--check-cmd`. The harness runs it after every write that lands and puts ONE line in the delegate's own
  observation (`the harness ran the declared check: exit 0 (0.0s)`), spending no step and no token, blocking
  nothing and never counting as a red. Exit code only, output never parsed: that is what keeps it
  language-agnostic, and it is DECLARED, never inferred, so a toolchain with no build step says nothing and
  gets nothing. Prove such a harness-side feature with the same run twice, wiring on and off -- 3 writes gave
  3 checks with it and 0 without (`b4518eb`).
- **A run that ends with no handback is observed too** -- the step limit, a wall-clock kill, a repeated
  format error: `limit_runs` records the check and the suite with their exit codes. `check: 0` with
  `suite: 2` reads "it builds, and the suite could not run", which is nothing like `no-handback`.
- **Worktrees accumulate.** Every `--repo` run leaves one and nothing prunes it: `git -C <repo> worktree
  list` to see them, `worktree prune` once the arm's directory is gone. Nothing is ever committed and your
  branch never moves, but your `.git` does gain the registration.
- A log line reading **`the suite was stale at handback; harness ran it -> exit 0`** is the handback rule
  working, not a failure: the model wrote after its last suite run, so the harness ran the suite itself and
  allowed the submit on the strength of that green.
- A repository run is graded on the handback; a benchmark is graded on its order AND its artifact.

Ninny wrote its own source this way first (`66fce59`): a run fixed a `binds=None` crash in
`sandbox.py` and added its own test, applied by hand with the suite green -- and the run's verdict
was `unproven` (exit 1) because it never ran the suite. Good patch, missing evidence: the two are
graded separately, and that is the point.

### The brief is the primary lever (measured 2026-10-27)

A repo brief IS the task description, and how it is written decides whether a run produces anything. Six arms,
one model (`deepseek/deepseek-v4.1-flash`), two per condition:

```
brief naming ~10 files, ordering the reading     0 writes, 13-byte patch, no handback   $0.100 / $0.212
brief naming ~10 files + budget notes            4 writes, red-first, no handback      $0.097 / $0.114
brief naming its first file and first test       8 and 6 writes, BOTH SUBMITTED        $0.057 / $0.044
    (the same, on a repository we own)
```

Both of the last pair came back graded `artifact` by `ninny verdict`, at half the cost of the runs that
failed -- and one of them never received a budget note, because it had already written a failing test before
the note fires. **The brief, not the notes, is what makes a repository run produce a handback.** A brief that
orders reconnaissance ("read these before writing anything") instead of naming an entry point spends the whole
budget reading.

A brief that works names four things: **the first file to touch, the first test to write, the acceptance
command, and what is out of scope.** The template, with the reasoning, is in the README under "The brief you
hand it". The preflight counts the paths a brief names and reports the ones absent from the tree, which is the
cheapest way to learn that a brief has stopped matching the repository -- before the run spends anything.

**Two rules about the subject.** Measure on a repository this project owns end to end: a repo under
simultaneous development by someone else moves mid-run (one arm read the live checkout through its read-only
bind and found its brief already implemented; another lost its tree twice), and no number from it is
attributable. And a repository has no oracle -- `ninny verdict` grades the *handback*, and nothing has said
the patch is correct, so read the patch before adopting it. One was adopted that way and was better than the
plan it replaced.

## Sandbox without root

```bash
apt-get download bubblewrap && dpkg -x bubblewrap_*.deb root
ninny run ... --sandbox bwrap --bwrap-path ./root/usr/bin/bwrap
```

bwrap starts fully sandboxed as uid 1000, no runtime root, ~3 ms/action overhead,
and the tree is bound at its real path so absolute paths in the agent's shell still
work. Linux-only, so it is a preferred backend with a documented fallback, never a
requirement.

## Traps found the hard way

Moved to `references/traps-found-the-hard-way.md` -- read it when a record surprises you
(a refusal, a `no-red`, a missing verdict, a timeout) or before blaming a model for a bad
process.

## Publishing an update (plain `git push`)

Moved to `references/publishing.md` -- read it when pushing an update and when proving the
publish landed (verify at the URL, never through a remote name). It also records why publishing
used to need a filtered force-push, since that was a symptom of tracking what must not ship.

## Grading an arm's own suite (teeth)

When the deliverable of a task IS the test suite, its quality is the result, and the only
measurement that means anything is sabotage:

1. **Control first.** Run the arm's suite on the pristine tree and require exit 0. A suite
   that is not green before any mutation makes every number below meaningless.
2. **Hand-pick the mutants, and require each to still compile.** A mutant that fails to
   build is not a mutant; discard it and say so, never count it as caught. Keep them
   gross: a dropped subtractive pair, an off-by-one at the range edge, one digit's value
   wrong, the canonical-form comparison removed.
3. **Point both suites at every mutant** -- the arm's own suite AND the acceptance corpus.
   The corpus is the reference; if it misses one, the corpus has a hole and that is the
   finding. Measured on the roman-cli arms: own suite 5/5, corpus 5/5, both arms.
4. **Say what it does not prove.** Five gross mutants answer "does this suite notice a
   wrong implementation at all". They say nothing about a subtle one; that is mutation
   testing, which needs generated mutants and is not this.
5. **Copy the tree without its `build/`.** An arm's tree carries the CMake cache from its
   own run, full of absolute paths pointing at the original -- copy it as-is and every
   mutant reports `configure failed`, which looks exactly like "the mutant did not
   compile" and is a lie about the suite. Delete `build/` after copying, before mutating.

To judge whether a suite is dense, read the count the harness prints at RUNTIME, not the
number of `CHECK(` call sites in the file: the same line inside a loop over 1..3999 or a
recursive sweep executes thousands of times (one arm reported 186,637 checks from 65 call
sites). A grep of the source is not a measurement of anything.

- **A RED must be a test that RAN.** The task's own runner is the whole contract: exit
  `0` ran and passed, `1` ran and failed, `2` could not run -- and a build or configure
  failure is 2, never 1. On a COMPILED task, ship a stub that compiles, or the order
  metric is unmeasurable: a first run that fails to build is 2, so the model writes the
  implementation first and every arm reads `red-after-code`. With a compiling stub the
  same task measured `red-first` on both arms, red before the first source write.
- **A suite that asserts nothing is not a pass.** The C++ harness prints
  "<label>: 0 checked, 0 failed" and the Python one prints "Ran 0 tests"; both exit 0, so
  the runner must catch the count itself (`[ -z "$n" ] || [ "$n" -eq 0 ]`, and
  `^Ran [1-9][0-9]* tests?` -- a leading-zero-allowing regex matches zero). gtest does the
  same thing: `0 tests from 0 test suites` then `PASSED`, exit 0.
- **`--tdd` values are `off|request|enforce|reverse`.** `none` is not one of them, and
  `tools/batch.py --modes none` fails every arm at argument parsing with exit 2 and an
  empty row. Rows that record `HARNESS-ERROR` are the honest outcome -- read one log
  before re-running.
- **`oracle = "oracle"` must be in task.toml**, not just `oracle_cmd`. Without it
  `_stage` copies nothing beside the tree and every oracle call exits **127**, which reads
  like a missing binary rather than a missing manifest key.
- **`fixed_tree` is a complete tree, not just the answer file.** `_stage(task, fixed, ...)`
  copies that directory AS the tree, so a `fixed/` holding only `src/<answer>.cpp` stages a
  tree with no headers and no build file, and verify-task reports BROKEN TASK on a task
  that is fine. Copy `tree/` to `fixed/`, then drop the reference in.

## Fork provenance (mechanical, not optional)

`LICENSE.md` carries mini's MIT notice verbatim ("Copyright (c) 2025 Kilian A.
Lieret and Carlos E. Jimenez") plus Harri's; `NOTICE` names upstream version, URL,
and what changed. **MIT grants no trademark rights: never describe Ninny as
mini-swe-agent.** Upstream is 2.4.6 and the fork surface measured 352 touchable
lines (loop 190, executor 92, parser 70) out of 5,349 LOC.
