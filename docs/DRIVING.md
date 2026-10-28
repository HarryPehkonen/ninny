# Driving Ninny

This is the manual for the tool, written so that a clone of this repository and a Python
interpreter are the whole requirement. If you are an agent being pointed at this file: the
short version is `doctor`, `verify-task`, `run`, `verdict`, and the exit codes are the API.

Nothing here needs installing. Ninny imports only the standard library.

```bash
git clone https://github.com/HarryPehkonen/ninny && cd ninny
python3 -m ninny doctor
```

## What you need

- **Python 3.11 or newer.** `python3 -m ninny` from the checkout. If that works, you are done;
  there is no second step. If you prefer a command on your PATH, `uvx --from . ninny …` or
  `uv tool install git+https://github.com/HarryPehkonen/ninny` both work against the same code.
- **A model.** Any OpenAI-compatible endpoint. `--provider` defaults to `local`, which means
  `http://127.0.0.1:8645/v1` and the API key in `NINNY_API_KEY`; `--base-url` and `--api-key`
  override both, and `--provider openai|openrouter|ollama|llamacpp` pick a preset whose key
  comes from that provider's own environment variable. `python3 -m ninny doctor` prints the
  endpoint actually in use. **The model ids are whatever that endpoint serves** -- `curl -s
  "$BASE/models"` lists them with their pricing, and `doctor` reports how many there are. There is
  no `ninny models` command; a reader with only this clone would have to guess one without this
  line, which is why it is a line.
- **Bubblewrap, optional but recommended.** Scored runs should be sandboxed, so that the model
  cannot read the oracle that grades it. On most distributions `bwrap` is a package
  (`apt install bubblewrap`); without root, `apt-get download bubblewrap && dpkg -x bubblewrap_*.deb root`
  gives you `./root/usr/bin/bwrap`. Pass wherever it landed:

  ```bash
  BWRAP=$(command -v bwrap || echo ./root/usr/bin/bwrap)
  ```

  With the distribution package the binary is usually `/usr/bin/bwrap`; `command -v bwrap`
  answers it either way. A run without a sandbox is still a run, but the number it produces is not attributable,
  because the answer was inside the tree the whole time. Ninny says so when it starts.

## The five commands

```bash
python3 -m ninny doctor                        # what this machine can do, and where the model is
python3 -m ninny verify-task --task tasks/roman   # prove a task grades correctly before spending money
python3 -m ninny run --task tasks/roman --model <model-id> \
    --sandbox bwrap --bwrap-path "$BWRAP" --steps 40 --name arm1
python3 -m ninny verdict runs/roman/arm1       # grade the HANDBACK: 0 artifact | 1 unproven | 2 nothing
python3 -m ninny check --task tasks/roman --tree runs/roman/arm1/tree   # grade the ARTIFACT against the oracle
```

`verdict` and `check` are different questions and both work on either door. `verdict` reads the
run's own record and asks whether the delegate handed back something that can be applied and
believed. `check` runs the task's oracle against the tree the arm produced. A patch can be
real -- `verdict` 0 -- and still fail the oracle, or pass the oracle having never run the
suite it was supposed to test. Run both, and read them together:

| `verdict` | `check` | what it means |
| --- | --- | --- |
| 0 `artifact` | 0 `GATE PASSED` | a real patch that the oracle accepts -- the strongest reading available |
| 0 `artifact` | non-zero | a patch that is evidence of a process, applied to a tree the oracle rejects |
| 1 `unproven` | 0 | the right artifact from a process the record cannot vouch for (no red, no suite run) |
| 2 `nothing` | any | nothing was handed back |

## Two doors

**A task** (`--task`, a fixture with a frozen spec and an oracle) is a benchmark: the order of
the work and the artifact are both graded, and `verify-task` has already proved the task
discriminates.

**Your repository** (`--repo`) is the same loop pointed at a working copy:

```bash
python3 -m ninny run --repo ~/src/myrepo \
    --prompt-file brief.md \
    --test-cmd "bash scripts/gate.sh --tier fast" \
    --sandbox bwrap --bwrap-path "$BWRAP" --name myrepo-1
```

`--check-cmd` declares a cheap check for a repository run -- a build, a compile -- which the harness
runs, along with `--test-cmd`, if the run ends at the step limit. On a C++ project an incremental build
costs seconds against minutes for a full gate, which is what makes it worth declaring. A task declares
the same thing as `[runner] build`.

Staging is a `git worktree` at HEAD, so your checkout is untouched and the run is isolated; the
main repository is bound into the sandbox read-only so that git works inside. `--test-cmd` is
required and never guessed, and `--prompt`, `--prompt-file` (or `--prompt "one line"`) supplies
the brief. `--test-glob` (repeatable) turns on the red-first gate: without it a run only
*records* the order of writes, with it the gate refuses a source write until a test has been
seen to fail. On a repository whose suite is already green, `--test-glob` is a deadlock --
every way to produce a red is itself a write -- which is why it is not the default.

## The exit-code contract

This is the whole reason a record is worth reading. A suite's exit code says which of three
things happened, and Ninny never parses output to guess:

```
0  the tests ran and passed
1  the tests ran and failed        -> a RED observation
2  the suite could not run at all  -> nothing was observed, so it is not a red
```

`126`/`127` (the shell's "not executable" / "not found") mean the same as 2: nothing ran. A
task whose runner cannot tell a build error from a failing test cannot produce a trustworthy
red, and the report says so rather than counting it. This is also why `verify-task` exists and
has three controls, not two: the oracle must be RED on the tree an agent starts from, GREEN on
the answer key, and the task's own runner must report a planted failing test as exit 1.

## The seven limits, all adjustable

| flag | what it caps | default |
| --- | --- | --- |
| `--steps N` | model turns | the task's, or 60 in repo mode |
| `--wall-time N` | total elapsed seconds | **0, i.e. no limit** |
| `--timeout N` | one bash action | `max(120, the declared suite timeout)` |
| `--test-timeout N` | the repo's own suite | 600 |
| `--request-timeout N` | one model call | 600 |
| `--cost-limit` | not enforced, recorded only | -- |
| `--tdd off\|request\|enforce\|reverse` | what the gate does, not what the model reads | `request` |

An explicit `--timeout` always wins over the floor. A run that ends at `StepLimit` ended
because it ran out of turns, not because anything crashed -- `--steps` is usually the dial to
reach for.

## The brief is the primary lever

Measured, two arms per condition, one model, same flags:

```
brief naming ~10 files, ordering the reading     0 writes, 13-byte patch, no handback   $0.100 / $0.212
brief naming ~10 files + budget notes            4 writes, red-first, no handback      $0.097 / $0.114
brief naming its first file and first test       8 and 6 writes, BOTH SUBMITTED        $0.057 / $0.044
    (the same, on a repository we own)
```

The last row's arms came back graded `artifact` at half the cost of the runs that failed, and
one of them never received a budget note, because it had already written a failing test before
the note fires. **The brief, not the advice, is what makes a repository run produce a
handback.** A brief that orders reconnaissance instead of naming an entry point spends the
whole budget reading -- in the first row above, on a 123-translation-unit repository, that was
forty steps and nothing written.

A brief that works names four things: **the first file to touch, the first test to write, the
acceptance command, and what is out of scope.** The template is in the README under
"The brief you hand it". Before a run spends anything, the preflight counts the paths the brief
names and reports the ones that are not in the tree -- the cheapest way to learn that a brief
has stopped matching the repository.

## What a finished run leaves behind

Everything is under `runs/<subject>/<arm>/`:

- `trajectory.json`, `trajectory.md` -- the record: every step, the verdict word, `red_step`,
  `first_src_step`, `writes`, `told`, `test_runs`, `harness_runs`, `suite_frozen_since_red`,
  `bypass_detected`, the diff stat, the cost, and the spec/tree hashes the run started from.
- `diff.patch` -- what changed, against the commit the run was staged at. This is the
  deliverable.
- `result.json` -- the record's machine-readable front matter, written INCREMENTALLY while the
  run is still going.
- `oracle.log` -- written by `check`, beside the tree it graded.
- `checks` in the record -- the declared cheap check, run on the harness's own initiative after every
  write that landed: `[step, exit, seconds]`. The same line the delegate was shown, so the record and
  the model can never disagree about what the tree was doing.
- `limit_runs` in the record -- what the harness ran *after* a run died at the step limit:
  `[step, kind, exit, seconds]`, with `kind` either `check` (the declared cheap check) or `suite`
  (the acceptance command). A run that ends at the limit produced a patch nobody can judge, so the
  record says whether the tree builds and what the suite answered, in the same exit-code contract as
  everything else. Nothing about the run changes; it is already over.
- `tree/` -- the arm's working copy, left in place so the patch can be applied and the work
  inspected.
- plus a durable transcript and one appended line in the index at
  `$XDG_STATE_HOME/ninny/logs/history.tsv` (default `~/.local/state/ninny/logs`, `--no-log` to
  turn both off, in which case nothing is created at all).

**Read `result.json` only after the process has exited.** Because it is written as the run goes,
a snapshot taken mid-run reports empty `test_runs` and `red_step` -- which reads exactly like a
run that never tested anything. That mistake has produced a wrong verdict twice. Mid-run, read
the console line or the durable log; when the run is over, read the record.

## Three things that look like failures and are not

- **`the suite was stale at handback; harness ran it -> exit 0`** -- the handback rule working.
  The model wrote after its last suite run, so the harness ran the suite itself and allowed the
  submit on the strength of that green, rather than refusing on a stale result.
- **`refused: write_file: tests/test_thing.py`** under `--tdd enforce` -- the gate doing its job.
  Source writes are refused until a red has been observed; write the failing test first and the
  path opens. The refusal text says which rule fired.
- **`at the limit, check: 0` / `at the limit, suite: 1`** -- not failures, an observation: the run
  ended at the step limit, so the harness ran the declared cheap check and the acceptance command in
  the tree the arm left behind and recorded both exit codes. `check` 0 with `suite` 1 means the tree
  builds and its tests fail, which is a different and much more useful fact than "nothing back".
- **`no-write`** in a record -- the run produced nothing at all. That is a weaker and more
  specific fact than "the tests were not run", and the record keeps the two apart:
  `writes=0` is the number to look at.

## What this assumes

Written down because a reader deserves to know where the edges are, and because three of these have
already produced surprises.

**A task run assumes nothing but a shell and Python.** The fixture is in the repository, the commands
come from `task.toml`, and nothing touches git.

**A repository run assumes git.** Staging is a `git worktree` at HEAD, so the path must be a git working
tree with at least one commit and `git` must be on PATH. Nothing is ever committed and your branch is
never moved, but your `.git` does gain a worktree registration, the patch is `git diff --cached` inside
that disposable worktree, and `git add -A` runs there -- which respects `.gitignore`, so build residue
stays out of the patch.

Which means **worktrees accumulate**: every `--repo` run leaves one and nothing prunes them. `git -C
<repo> worktree list` shows them, and `git -C <repo> worktree prune` is the cleanup once the arm's
directory is gone. An arm's `tree/` is where its patch came from, so prune only what you have finished
judging.

**The live repository is bound read-only into the sandbox.** A worktree's `.git` is a FILE pointing at
the main repository, so without that bind git inside the sandbox reports "not a git repository". The
consequence is worth knowing: a sandboxed delegate can READ the live checkout. One arm used that to find
its brief already implemented, in a commit its worktree did not have.

**Both doors assume a POSIX shell.** Every declared command -- the acceptance command, the cheap check,
the probe, the oracle -- is run through the shell (`shell=True`), with the working directory set to the
tree. It must be a shell string.

**A run assumes its tree is still there at the end.** If it has been pruned away the observation records
exit 126 rather than failing, or quietly succeeding.

**The cheap check runs after every write, and reports nothing but an exit code.** A delegate pays a
step and its tokens to learn what a compiler says; the harness pays seconds and none, which measured on
a 126-translation-unit repository is 4 s against the 120 s an acceptance command costs. Four of the
tasks shipped here declare a `build`, so they get the signal for free. There is no output parsing, no
error-message matching and no language in it: the meaning of the number is the exit-code table, the same
table for every toolchain.

**Nothing assumes a language.** The commands are declared, the exit-code contract is the only thing
Ninny reads, and a toolchain with no cheap check declares none.

## Reproducing a number

`spec_sha256` and `tree_sha256` in the record pin the exact inputs, and the oracle is
deterministic, so a graded arm can be re-checked at any time -- `check` will write the same
`oracle.log` again. A number without its hashes is not a result.

## Where to look next

- `README.md` -- what Ninny is, why it works this way, and the measured tables behind it.
- `docs/AUTHORING-TASKS.md` -- writing a task: `task.toml`, the oracle, the runner, the rules
  that are enforced rather than advised.
- `docs/RUNNERS.md` -- the runner conventions for each language, and the failure that made each
  rule.
- `docs/PROVIDERS.md` -- the endpoint seam.
- `docs/LESSONS.md` -- every lesson the project paid for, including the ones that were bugs in
  the harness rather than in a model.
