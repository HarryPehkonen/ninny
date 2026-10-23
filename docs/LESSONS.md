# Ninny — lessons and decisions

Written 2026-10-22, at the end of the mixed-project campaign. The campaign is closed.
This file is the record: what was measured, what was learned, what was kept, what was cut,
and what is still open. It is the reference for anyone (including a future me) tempted to
re-run the experiments or re-add the scaffolding.

## What Ninny is

A stdlib-only fork of mini-swe-agent whose differentiator is **test-first enforced as a
state machine**. It runs a model against a frozen task tree and records, mechanically,
whether a failing test was observed before the implementation was written. The unit of
truth is the **exit code**, not the model's narration:

    0  the suite ran and passed
    1  the suite ran and failed      <- a RED observation
    2  the suite could not run       <- nothing was observed

Everything else in the record (steps, cost, verdict, refusals, bypasses, counts) is built
on top of those three numbers.

## What was measured

8 tasks, 94 scored runs, **$1.47** total. Languages and harnesses: C++ (Make, CMake +
GoogleTest), Python (unittest, pytest), JavaScript (`node --test`), Rust (cargo), x86-64
assembly (nasm + ld + make).

| outcome | count |
|---|---|
| Submitted | 78 |
| StepLimit | 16 |
| verdict `red-first` | 68 |
| verdict `red-after-code` | 11 |
| verdict `no-red` | 15 |

Every arm that got past preflight and produced a tree passed its oracle — including the
StepLimit arms. **Correctness and test-first are different measurements**: an arm can be
right and never have observed a red.

## Lessons — the instrument (all of these were bugs in the harness, not the model)

1. **The exit-code contract is the load-bearing idea.** Every runner bug found was a
   violation of it: a build error reported as RED, a zero-case suite reported as PASS, a
   "no tests found" reported as PASS. Fix the contract, and the measurements become
   trustworthy.

2. **"Nothing ran" must never count as a result.** Zero `CHECK`s exited 0 in C++; an empty
   TAP file counted as one passing test in Node; ctest's exit 8 covers both "some tests
   failed" and "no tests were found"; a suite with no `#[test]` ran nothing in Rust. Each
   runner now refuses to call a vacuous run a pass.

3. **A 127 is not a RED.** `verify-task` counted *any* non-zero oracle exit as "the oracle
   rejects the stub". A typo'd script name would have "verified" a task whose oracle never
   executed a line. Fixed: 2/126/127 are "did not run", and the verdict says so.

4. **Frozen hashes without versioning produce false alarms.** When the task itself changes
   (a runner fix), every old arm looks like "the submission edited the instrument". This
   burned real time twice. A version stamp per task would separate "instrument changed"
   from "submission cheated".

5. **A dead feature is worse than a missing one.** `sandbox_binds` existed in code and in
   the config's known keys, but **no manifest declared it**. Three Node arms refused at
   preflight with `node: command not found` before anyone noticed the feature was unused.
   It now works (with `$HOME` expansion at load time) and is exercised by the `dur` task.

6. **Vocabulary drift costs real money.** `tools/batch.py` translated its `none` mode
   straight into `--tdd none`, but the CLI accepts `off|request|enforce|reverse`. Twelve
   arms died at exit 2 with $0 spent — silent except for the exit code. One vocabulary:
   accept the CLI's words and let argparse reject the rest.

7. **Paths are where correctness leaks.** `oracle_cmd` runs with cwd set to the staging
   directory, so it must be `bash oracle/accept.sh`, not `bash accept.sh`. bwrap needs an
   absolute source path. Each cost a debugging cycle.

   The worst case was `ninny check` staging *inside* the task directory: every
   verification copied the task, built it, and left the output behind. `tasks/intset/checks`
   reached 69 MB per verification (956 MB with a Rust `target/`), and the repo passed 1 GB
   of gitignored debris. Fixed: the default staging root is now
   `$TMPDIR/ninny-checks/<task>`, and `--out` still puts it wherever you ask. A check is
   disposable, so its scratch does not belong in the source tree.

8. **Analysis scripts break on real data.** A sort key of `None` crashed the tally twice.
   Guard the fields; do not assume every JSON has every key.

9. **Build output belongs in the skip list.** A Rust arm's diff listed 61 added files that
   were entirely `cargo target/`. `target/`, `node_modules/`, `dist/`, `.venv/` are now
   excluded from the digest, the diff and the gate.

10. **The answer-key control is the highest-value control.** Nine of ten oracle bugs in one
    stretch were mine, and every one was caught by running the corpus against the reference
    implementation. An oracle that only ever fails proves nothing. `verify-task` requires
    both directions: RED on the stub, GREEN on the answer key.

## Lessons — about TDD enforcement and the model

- **Telling the model about TDD barely changed whether it went red-first.** With the gate
  off and the prompt on, 6/6 arms still went red-first; with the prompt off and the gate
  on, the arms also went red-first. The prompt is cheap; the gate is for enforcement, not
  for discovery.

- **Judge, don't gate.** Every process gate tried had a legitimate exception. Gate
  properties of the *artifact* (frozen instrument unchanged, oracle outside the tree,
  acceptance passes); measure how the work happened (red before code, refusals, bypasses)
  and let the reader decide. Submit-time refusals produced compliance; the two write-time
  bypasses were missed by the gate and caught only by the tree.

- **Step limits are the binding constraint for some tasks.** `dur` submitted 3/5 arms
  within 30 steps; the other 2 hit the limit and still produced correct trees. `intset`
  produced `no-red` verdicts at 33–35 steps. A StepLimit is a budget outcome, not a
  correctness verdict.

- **A cheap model is good enough for the instrument's purpose.** deepseek-v4.1-flash:
  68/94 red-first, all produced trees passing their oracles. The failures were budget and
  instrument, not capability.

## Decisions — keep

- Exit codes 0/1/2 and the "nothing ran" guards in every runner.
- The oracle lives **outside** the tree; the frozen instrument is hashed.
- `verify-task` runs both controls (RED on stub, GREEN on key).
- Test counts recorded as a number (`NINNY_TESTS: N`) so a shrinking suite leaves a trace.
- `sandbox_binds`, expanded on the host at load time; build-output skip list.
- The eight task fixtures stay: they are the regression suite and worked examples.

## Decisions — cut

- **`tools/batch.py` deleted.** It was experiment scaffolding with a duplicated vocabulary.
  A batch is a `for` loop over `ninny run`; the CLI already prints the judge command.
- **`runs/` and `tasks/*/checks/` deleted.** 1.3 GB of gitignored residue. The numbers they
  contained are in this file; the trees they held were graded and recorded.
- **The told/untold 2×2 design is closed.** The question is answered; re-running it would
  spend money to re-learn "the prompt barely matters".
- **No new tasks this cycle.** The marginal information per arm had fallen below the cost
  of authoring and grading one.

## Open, deliberately not done

- **Version stamp for frozen files** — distinguish "task updated" from "submission edited".
- **One shared runner convention** — four hand-rolled runners each re-implemented count
  parsing and the anti-vacuous guard, and each copy had its own bug. A single helper would
  remove the duplication and the bug class.
