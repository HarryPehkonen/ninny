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

11. **A task can be unsolvable and still pass both controls.** `tasks/bits` shipped with
    `CMakeLists.txt` in `protected_globs` -- the same file its README, the file's own header
    and the oracle's own comment all tell the agent to edit. The gate refuses that write in
    every mode, so a registered test could never exist, so the suite could never run, so no
    run could ever see a red. Unsolvable. `verify-task` passed anyway, because the oracle
    grades the *answer key*, whose CMakeLists was already correct: both controls grade the
    ends of a task and neither one runs the middle. What would have caught it is one arm --
    `history.tsv` has 20 rows for `bits` and every one of them is `verify-task`, zero agent
    runs. Run every task at least once before trusting it; the answer-key control proves an
    oracle, not a task.

12. **A file's own promise is a specification, and it can be unmet.** That header said the
    acceptance corpus "checks that everything else is unchanged"; the corpus hashed two other
    files and skipped this one deliberately. The fix was to implement the promise -- hash the
    region above the marker, which is the region the file says is frozen -- and then to stop
    protecting the file, so the gate no longer refuses the edit the task requires. Teeth
    measured: a compile flag edited above the marker gives
    `FAIL CMakeLists.txt above the marker was edited`, and the submission is rejected, while
    the clean answer key still verifies.
    Known limit, recorded rather than fixed: appending *below* the marker is allowed by design
    (the corpus appends its own target there), so a submission could silence warnings by
    appending rather than editing. The acceptance corpus still decides the verdict.

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

## The gate — 2026-10-23

Ninny had none. Ten of Harri's other repos carry a `gate.toml` for KitCI, and this was the
eleventh: `tree tests stdlib tasks`, fast tier ~1 s on commit, full ~21 s on push. The
`tasks` stage is the one no other repo can have — `verify-task` on every task, which is the
repo's own two-way control run on the repo.

Three lessons, all measured while wiring it:

- **`python3 -m unittest discover` prints `Ran 0 tests` and `NO TESTS RAN`, and exits 0.** So
  a suite that quietly stopped being collected reads as green — the same class as pytest's
  exit 5 (which docsum guards with `fail_on = "exit:5"`). The stage therefore applies Ninny's
  own contract to Ninny: 0 ran and passed, 1 ran and failed, 2 nothing ran. Both branches have
  their own sabotage: `mv tests` aside reaches "no count line", an empty importable `tests/`
  reaches "0 tests ran".
- **A hook inherits the environment of whatever fired it, so it must state its own tier's
  rule.** With `CI_REQUIRE_CLEAN=1` left exported in a shell from a publish run, the next
  `git commit` had its tree stage refuse the very file it was committing — a commit is *made*
  from a staged tree. `pre-commit` now unsets it. The failure was also masked by a
  `git commit ... | tail -4`, which returns the pipe's status: capture `rc=$?` on the next
  line.
- **A cost quoted without its cache state is not a measurement.** The full tier measured
  54.6 s, then 20.0 s: no ccache here, and `bits` (CMake + GoogleTest) builds cold in its
  staging directory on the first run. The README carries both numbers, labelled.

## The phases, named -- 2026-10-23

- **The state carried a phase from the first day and nothing said so to the model.** `test`,
  `impl`, `done` were in the record and invisible in the run. The fix is a vocabulary, not a
  mechanism: one table (`PHASE_ORDER` / `PHASE_LABELS` / `PHASE_JOBS`) and three readers -- the
  prompt, the refusal text, the observation after an action. ~40 lines, no new concepts, and
  the internal names did not change, so no record shape moved.
- **A note the model never reads is a comment.** The step line is operator-facing; the phase
  had to ride on the observation itself, which is also the string the record stores -- so what
  the record says the model was told and what it was told cannot drift apart.
- **The interruption earns its place at exit 2.** A model that has just read `cc1plus: fatal
  error` reads it as a failure it earned; the vocabulary names the phase, and the note says
  what a red is not, at the moment it happens. Before this, that sentence lived only in a
  task author's stub comment, so every task that forgot one taught the lesson badly.
- **Vocabulary is guidance and stays unenforced.** The order of the writes is still a recorded
  number, never a gate; the RED rule is unchanged and still lives at handback. Nothing here
  can refuse a run that a refusal did not already refuse.
- **Honest limit: rendered and unit-tested, not yet measured on arms.** The next C++ arms are
  the test of whether the exit-2 note shortens the path to a legitimate red, or is just noise
  in every observation.

## The bits arms -- 2026-10-23 (the first time that task was ever run)

Three arms, cheap model, `--sandbox bwrap`, `--tdd request` (record only), $0.0433 total:

```
arm  steps  cost     recorded verdict  red_step  first test  first src  tests  acceptance
a1      10  $0.0139  no-red            --                3          5     12   PASSED 5/5
a2      33  $0.0180  red-first         7                 4          8     24   PASSED 5/5
a3      24  $0.0114  no-red            --                3          9     13   PASSED 5/5
```

- **The task is solvable, and the protected-globs fix is what made it so.** 3/3 passed the
  acceptance corpus, each after editing `CMakeLists.txt` -- the edit the manifest used to
  refuse. This is the whole argument for fixing a manifest you have not run: the same task,
  one line different, goes from impossible to a 1.4-cent solve.
- **The frozen region survived all three, including a wholesale rewrite.** One arm wrote a
  brand-new `CMakeLists.txt` (1516 bytes against the original 1615) and still reproduced the
  region above the marker byte for byte. The file's own header instruction was sufficient --
  and the new frozen-region check passed on all three (5 checked, 0 failed, which includes it).
  Self-description inside the tree works; that is the accessibility finding, and it is positive.
- **The record lost a genuine red in two of the three arms.** a1 and a3 both ran the suite
  through `bash`, saw the runner print `EXIT=1` before their first source write, and are
  recorded `no-red`, because `red_step` comes only from the `run_tests` action. Both also wrote
  `; echo "EXIT=$?"` -- they were reading the exit code, just not through the action. So a
  verdict describes the observations the harness could see: quote these as "recorded no-red",
  never as "did not test first", and never as evidence about the model's process.
- **Ninny's own 180 s action timeout looked like nothing at all.** a3's first suite run died at
  the timeout (exit 124, the runner never printed a verdict), and the model retried with
  `timeout 170 bash tools/run_own_tests.sh` -- a cold CMake + GoogleTest build of 13 targets
  does not fit in 180 s on this machine. A weaker arm would read that observation as "my tests
  failed", or as a broken task. The model adapted; the harness said nothing about what had
  happened.
- **Entry cost measured:** 10-33 steps and 1.1-1.8 cents to a passing submission, and one arm
  opened by reading `tests/own/README.md` and `tools/run_own_tests.sh` -- the two files the
  task ships for exactly that. Looking for a documentation gap, the arms did not show one. The
  gaps they showed are signal gaps.

## Open, deliberately not done

- **Version stamp for frozen files** — distinguish "task updated" from "submission edited".
- **Make the two silent events visible, using the mechanism the phases already use.** Both
  were measured on the bits arms, and both are the same class of thing: an event whose meaning
  to the harness is never said back to the model. (a) The task's own test command appearing
  inside a `bash` action -- record it (`shelled_test_run`, with steps) and say so in the
  observation, because the harness cannot see that red and the model cannot tell that its
  process record just went blank. (b) An action killed by Ninny's own timeout -- say so, since
  the observation is otherwise indistinguishable from a suite that reported nothing. Neither is
  a gate; both are ~15 lines on the path the phase note already travels. Honest limit on (a):
  string matching the `test_cmd` will sometimes miss a wrapped command or fire on a listing --
  it is a recorder, so a miss costs fidelity, not correctness.
- **One shared runner convention** — four hand-rolled runners each re-implemented count
  parsing and the anti-vacuous guard, and each copy had its own bug. A single helper would
  remove the duplication and the bug class.
