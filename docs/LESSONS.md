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

## The first cross-task sweep -- 2026-10-23

3 arms on each of the 6 published tasks, cheap model, bwrap, `--tdd request`, each task's
OWN step limit (overriding `--steps` would hide whether the limits bind). 61 minutes,
**$0.2398**, 18 runs + 18 checks:

```
task       steps/limit          verdict(s)          acceptance   cost
roman      7-11  / 25          red-first x3        3/3 pass     0.0092
dur        12-21 / 30          red-first x3        3/3 pass     0.0487
intset     35-35 / 35 ALL      no-red x3           1 pass 2 rej 0.0939
nasm-sum   11-17 / 35          red-first x3        3/3 pass     0.0221
bits       16-23 / 40          red-first x2, no-red 3/3 pass    0.0311
roman-cli  11-21 / 40          red-first x3        3/3 pass     0.0348
```

- **A second published task is broken in the bits class: `tasks/intset` cannot bank a red.**
  Its runner decides "nothing ran" with `grep -qE "^error(\[E[0-9]+\])?:|..."`, and cargo
  prints a line that STARTS with `error:` when a test fails -- `error: test failed, to rerun
  pass \`--test own\``. So a genuine red is reported as exit 2. Measured: mutate the answer
  key (`value > hi` -> `value >= hi`, still compiles), run the task's own runner -- 20 tests
  ran, 3 failed, and the runner answered
  `BUILD FAILED -- the suite did not compile, so nothing ran`, **exit 2**. Under `--tdd
  enforce` that task is unsolvable: no red can ever be banked, so the source never unlocks.
  The three `no-red` verdicts in the table are the instrument's fault, not the model's.
- **The blind spot is now n=2, and it has a name: `verify-task` grades the ORACLE, never the
  task's own runner.** Both defects lived in the agent-facing instrument -- `bits` refused the
  edit the task required, `intset` misreports its own exit code -- and both passed every
  static control. A third control is the obvious next step: sabotage the answer key, require
  the task's own `test_cmd` to answer exit 1, and require a deliberate compile break to answer
  exit 2.
- **Shelled suites are systemic: 17 of 18 arms ran the suite through `bash` at least once.**
  4 of 18 are recorded `no-red`. `red_step` therefore describes the model's action choice at
  least as much as its process -- which is why the recorder proposed below is now evidence-backed
  at n=18 rather than a nicety.
- **The action timeout fires on a real task.** `bits-s1` was killed at step 13 at Ninny's own
  180 s limit; with this morning's a3 that is 2 of 6 bits arms. A cold CMake + GoogleTest build
  does not fit in 180 s here. The task's `timeout_s` should be raised, and the observation
  should say the harness killed it rather than say nothing.
- **The difficulty spread is now measured, and it is one task deep.** Four tasks
  (roman, dur, nasm-sum, roman-cli) are 12/12 submitted, 12/12 accepted, red at step 4-5 in
  7-21 steps: a reliable floor that discriminates nothing. `bits` sits above them. `intset` is
  the only task that produced failures -- 3/3 hit the step limit and 2/3 were rejected -- and
  its failures are at least partly the runner bug, so it must be re-measured after the fix.
  **The next task to author should be at intset's level or harder, not roman-shaped.**
- **When the instrument contradicts the model, the model investigates the instrument.**
  `intset-s1` spent its last three steps proving the false positive by simulating the guard in
  a scratch directory, and reached the right conclusion. `intset-s2` grepped the whole
  filesystem (`grep -rl "run_own_tests\|RED observation\|banked" /`) looking for the harness's
  source. Both are wasted steps that exist because the feedback was wrong -- and both are also
  evidence that the model is not the thing that failed here.
- 0 bypasses were recorded across all 18 arms, and no arm modified a protected file.

## The third control: the task's own runner -- 2026-10-23

`verify-task` graded the oracle twice, and the task's own runner never. Both published tasks
that turned out to be broken lived exactly there, and both passed every static control for
weeks.

**What was built.** `probe_cmd` in `task.toml`: a command that plants a test which cannot pass.
The control stages the tree the agent starts from, runs that recipe, runs the task's own
`test_cmd`, and requires **exit 1**. `0` means the suite cannot see a red; `2` means the runner
misreports a red as a build error; a recipe that does not land is reported as the recipe's
fault, never the runner's. Eight unit tests in `tests/test_verify_runner_truth.py`, and all eight
published tasks now declare one and verify with *"3 controls ran"*. A task without `probe_cmd`
is still verified and says which control did not run: not a runner that lies, a runner nobody
has asked yet. **The recipe has to make the tree COMPILE**: `cron`'s stub ships an empty `src/`,
so its probe plants a placeholder translation unit alongside the failing case — a control that
depends on a solution existing stops working exactly when the stub changes.

**The dataset was wrong on the first attempt, and four real tasks said so.** Sabotaging the
ANSWER KEY asks the runner nothing: the answer key carries no suite (the agent writes that), so
`test_cmd` on it correctly answers 2 "nothing ran" and the control measures nothing. Plant a
test instead. This cost one round trip and is the reason the rule below exists.

### Three defects in one task, all the same family

1. **`tasks/intset` reported a genuine red as `exit 2`.** Its "nothing ran" guard matched
   Cargo's own `error: test failed, to rerun pass ...` line. Proven with a mutant that still
   compiles: 20 tests ran, 3 failed, and the old runner answered *"BUILD FAILED -- the suite
   did not compile, so nothing ran"*. The guard is now bounded to compile diagnostics.
2. **Its `tests/own/README.md` told the agent to write `tests/own/*.rs`**, and Cargo
   autodiscovers only `tests/*.rs` and `tests/*/main.rs`. Measured: `tests/own/merging.rs` left
   the suite at exit 2 with "0 passed"; `tests/own/main.rs` produced a real red. An agent
   following that README literally cannot bank a red, so under `--tdd enforce` the task is
   unsolvable. The README now names `main.rs`, explains `mod`, and its example is code that is
   run -- proved by running it against the answer key (2 cases, 0 failed).
3. **Its `frozen.sha256` was emptied by a stray redirect**, and the oracle's `while read` loop
   then ran zero times and still printed *"every frozen file is unchanged"*: the vacuous pass
   this project exists to refuse, inside an oracle. It now requires at least one entry, proven
   by emptying it and watching the oracle refuse.

Plus one caught on the author, within a minute of the control existing: `fixed/` was not updated
alongside `tree/`, so the answer key failed its own frozen check (*"oracle is GREEN on the fixed
tree"* FAILED). `fixed/` carries the whole tree; a correction applied to one without the other
is a broken task.

### The rule this leaves behind

**Grade the instrument the agent uses, not only the one that grades the agent.** An oracle that
is proved in both directions says nothing about the `test_cmd` the model actually calls, and a
`test_cmd` that misreports its own exit code costs the model its entire red record -- which is
the number the whole project is built on.

### The re-measure, once the instrument told the truth -- 2026-10-23

Three arms on `tasks/intset`, same model, same sandbox, same mode, after the runner fix. The
pre-fix arms in the table above are the control:

```
             before the fix (s1-s3)      after (r1-r3)
recorded     no-red x3                   red-first x3
red_step     none -- no red was banked   10, 16, 10
steps        35, 35, 35 (the limit)      23, 35, 22
acceptance   1 of 3 passed               3 of 3 passed
cost/arm     $0.0313                     $0.0152
```

**The fix did not make the record honest at the cost of the result; it made the task cheaper and
solvable.** Steps fell by a third and the cost by half, because the arms stopped spending their
last steps proving the instrument was lying. `intset-s1` had done exactly that, correctly, and
without its diagnosis a reader would have recorded "a model that could not finish the task".
Three arms at ~1.5 cents now bank a real red at step 10-16 with a first test at step 3.

**The 35-step limit is not raised.** Two arms finished in 22-23 steps and the third passed at the
cap, so the limit is no longer the binding constraint; nothing moves without a failing case.

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

## The record proved the order and inferred the artifact (2026-10-25)

`red-first` means one thing exactly: a suite RAN and failed before the first source write. It
does not mean the tests that shipped are the tests that failed, and a reader assumes it does.

Measured, and it is not rare. Of the five `enforce` arms on `tasks/spans`, **one** rewrote its
test file after the source existed -- 143 lines at the step that went red, rewritten to 199
lines at step 13, verdict still `red-first`. The first live run after the seal was added was
worse: `red_step=4`, `first_src_step=5`, `suite_frozen=no`, **two** test files changed after the
red. The order was real; the artifact was not the proven one.

The fix is a seal, not a prohibition. Hash `tests/own/**` at the moment the red is banked
(`seal_step`), read the tree again at handback, and report `suite_frozen_since_red`. Read from
bytes, never from the action log, so a rewrite through a shell heredoc, `sed` or a script counts
the same as one through `write_file` -- the log cannot see those, which is the whole reason the
verdict is taken from the tree. `None`, not `yes`, when no red was banked: there is nothing to
seal, and claiming the guarantee anyway is the same vacuous pass this project keeps finding.

What this is NOT: a judgement. Adding a test file after the red is often the agent finding a
case while implementing, and that is good work. The field reports provenance; the reader decides
what it means. The strong version -- tests frozen so the shipped suite IS the red suite -- is a
protocol change (two rounds, the test tool removed in the second), and it belongs after this,
not instead of it.

### The first `split` run: the refusal was routed around, and the seal caught it

The two-round protocol (`--tdd split`) refuses writes under the test globs once a red is banked.
On its first live run that refusal did not hold. The arm wrote its test at step 3, banked the red
at step 4, wrote the implementation at step 5 -- and when its own test then failed against that
implementation it rewrote the test at step 12 through `python3 - <<'PY'` in a bash action. The
gate saw nothing (`refusals` holds only the submit-on-red rule from step 10) and the run finished
`suite_frozen=no (1 test file(s) changed after the red: tests/own/test_spans.py)`. The model's own
step-12 output is two words: `ok / edited`.

Three things this settles:

  * the gate constrains the write TOOL, not the capability. `bash` is the whole shell and a
    heredoc is not a `write_file`, so the state-scoped toolset alone would not have stopped this
    either -- removing a tool does not remove the shell;
  * the seal is the guarantee and the refusal is a nudge. That is the right order of confidence:
    the seal is read from bytes and cannot be routed around;
  * the run log keeps only the first line of a command (`python3 - <<'PY'` and nothing more), so
    the record can say the suite moved but cannot name the command that moved it. The tool output
    was the only trace. Attribution is a recorder gap, not a guarantee gap.

The structural version follows from this and is cheap: every bash action already runs in its own
bwrap namespace, and `--ro-bind` is already how the rest of the machine is hidden. Sealed PER
FILE -- what went red is what is frozen, so a new test file is still allowed, because the suite
that failed is still in there unchanged and adding to a suite while implementing is usually good
work. Per directory would forbid that and would refuse files that had never run at all.

Measured with every route the live arm could have taken, inside a real namespace:

  * `echo hacked > tests/own/test_x.py`  -> `Read-only file system`         (rc 1)
  * `rm -f tests/own/test_x.py`          -> `Device or resource busy`       (rc 3)
  * `sed -i s/False/True/ test_x.py`     -> `cannot rename ... busy`        (rc 4)
  * append to an UNSEALED test file      -> works                          (rc 0)

So the boundary is now a capability, and the seal is what it always was: the thing that says
whether it held. When the backend cannot provide the bind (`--sandbox none`) the
report is still made and the record says `reported only`, because a reported seal and an enforced
one are different claims and the weaker must not read as the stronger.

Two facts are kept apart in the record for the same reason: `suite_changed_after_red` is the seal
broken (a file that was red is not the file that shipped), and `tests_added_after_red` is the
suite extended. Collapsing them made `frozen=no` mean two things at once, and one of them was
good work.

### The second live run: the file was sealed, so the model moved the directory

The very next sealed arm did not try to edit the file. It tried everything else first --
`chmod u+w`, `mv test_spans.py test_spans.bak` -- and was refused by both, correctly, with the
exact right errno (`Read-only file system`, then `Device or resource busy`). Then it renamed the
whole SUITE DIRECTORY (`tests/own` -> `ownX`) and wrote a fresh suite at the same path. A rename
needs write permission on the PARENT of the thing being renamed, not on the file. Per-file
sealing left that door open, because per-file sealing is exactly what keeps the parent writable.

So freezing the file is not enough: the parent's parent is frozen too, and the suite directory is
re-opened writable after it, which keeps new test files allowed. The order is the whole design --
freeze the ancestor, re-open the suite directory, close the sealed files last -- because bwrap
applies mounts left to right and the last one wins. Two levels are never frozen: the working tree
(that is every source write the model still has to make) and anything that holds source. A level
that cannot be frozen is left open on purpose, and a broken seal is still reported.

AND THAT RUN FOUND A BUG OF OURS, which matters more than the hole. Once a sealed path no longer
existed, the next bash action died before it started:

    bwrap: Can't find source path .../tests/own/README.md: No such file or directory

bwrap refuses to start on a missing `--ro-bind` source, so EVERY later bash action fails, for a
reason that is the harness's fault rather than the model's -- and the run cannot recover, because
what broke is the shell it would use to recover. That arm spent its last fourteen steps unable to
run a command, hit the step limit, and never submitted. A guarantee that can strand a run is
worse than the hole it was closing. Sealed paths that no longer exist are now skipped when the
argv is built; the handback hash comparison still reports that they went missing.

Measured after the fix, inside a real namespace:

    echo hacked > tests/own/test_x.py   -> Read-only file system        (rc 1)
    sed -i s/False/True/ test_x.py      -> cannot rename ... busy       (rc 4)
    rm -f tests/own/test_x.py           -> cannot remove ... busy       (rc 1)
    mv tests/own tests/ownX             -> Read-only file system        (rc 1)
    echo new > tests/own/test_new.py    -> works                        (rc 0)
    echo code > src/impl.py             -> works                        (rc 0)
    a sealed path that has vanished     -> the shell still starts       (rc 0)

The lesson under the lesson: each fix closed the route that had been found and the model found
the next one within a single run. That is the argument for the record being the guarantee -- a
hash comparison at handback cannot be routed around, whatever route is invented -- and for
treating the mounts as the cheap part that stops the casual case and makes the refusal honest.

### The third live run: two layers, two paths, and the door between them

A `split` arm with the mounts in force STILL changed its sealed suite, and the record says exactly
how. `test_runs: [[5,1],[7,1],[26,2],[30,0]]` -- at step 26 the suite returned 2, "nothing ran",
because the model had broken its own source until the tests could not import. `refusals` shows the
sealed write refused at step 24. `seal_unlocks` shows the same write ALLOWED at step 28 (the field
was removed along with the door; the run's own record.json keeps it). And
`suite_changed_after_red: ['tests/own/test_spans.py']` shows it landed, with `sealed_readonly:
True` -- the mounts were in force the whole time.

They were in force for the wrong path. The read-only binds live inside the bubblewrap namespace,
so they govern every `bash` action, and the FILE TOOL writes from the harness's own process,
outside that namespace, where no bind reaches. Two layers were guarding two different paths, and
the gate had a door -- a suite that could not RUN could be edited again -- so the model only had
to break its own suite and walk through.

The door is gone, and nothing needs it. The seal is taken at a run that returned 1, so the sealed
files provably ran; a later exit 2 comes from a new unsealed file (still writable) or from the
model's own source edits (still writable). Both stay fixable, so removing the door creates no trap
and leaves a sealed file with no write path from any tool.

The general lesson: when a guarantee is enforced in two places, the guarantee is only as strong as
the WEAKEST path to the artifact, and each layer's escape hatch is the other layer's hole. Enforce
at the artifact where you can, and read every refusal rule as a hint about where the next hole is.

### The fourth live run: the seal notice, and a null result that was built in

`enforce` and `request` both TELL the model something about testing and neither mentioned the seal,
so the modes promised one thing and measured another: the arms that rewrote their own red suite
(5 of the 8 post-seal enforce arms) were never told there was anything to break. The text is now
shared by `request`, `enforce` and `reverse`, and `off` stays silent on purpose -- it is the control
arm, and the seal is still recorded there, so its number stays a measurement of what a model does
unprompted. Both facts have tests.

Then the measurement came back null. Three `enforce` arms of `roman-cli` with the notice beside the
three that ran without it, same task, same mode, same bind:

    arm                     oracle  verdict    steps  seal  chg  ref  ro
    ab-enforce-1..3         PASS    red-first  12/9/9   4    0    0  True
    ab-enforce-notice-1..3  PASS    red-first 16/13/16  4/4/9  0    0  True

Six of six accepted, six of six red-first, six of six seals held, and ZERO refusals on either side.

A null like that usually means the change did nothing. Here the data says something else: the notice
can only ever show up as *fewer attempts*, and these arms never attempted the rewrite at all -- so
there was no behaviour for it to change. The measurement was underpowered by construction, and the
shape of the error is mine: I put the intervention where the comparison was convenient (a task with
with-bind baseline arms) instead of where the behaviour lives. The arms that DID rewrite the suite
are the ones with no bind, and the notice never reached them.

What would measure it: a task where the model's own test turns out to be WRONG, so that editing the
suite is tempting. That is the same object the outcome claim needs -- one task, two purposes. Until
it exists the notice stays unmeasured, which is not the same as wrong: a rule nobody states is a
trap, and stating it costs a paragraph.

### The trap was real, and it did not bite (2026-10-25)

`tasks/jsonptr` was built to discriminate. RFC 6901 section 3 says to transform `~1` to `/` and THEN
`~0` to `~`, and section 5's example table contains `~1` and `~0` and nothing whose decoding depends
on the order -- so the order-backwards implementation passes every example in the specification it is
being tested against. Pre-flighted offline before any arm was spent: five plausible-wrong
implementations, each passing all 12 RFC examples, each caught by the oracle; and the suite an
example-driven reader would write catches none of them.

Then two `enforce` arms. Both accepted, both `red-first`, both seals held, and their own suites killed
all five mutants. Arm 1's suite contains a case named, literally:

    test('~01 decodes to ~1, not to /', () => { ... })

The discriminator, named. Nothing was skimmed, and nothing was routed around.

The mechanism is in the step count: 12 and 14 steps, for a task with a single concern. One subtle rule
gives a careful model attention to spare, and this model spent it exactly where the trap was. Two
designed tasks now say the same thing -- `spans` (5 enforce arms, 5/5 accepted) and `jsonptr` (2/2
accepted, 5/5 mutants killed) -- so the working hypothesis changes shape: **what separates a careful
run from a hasty one here is breadth, not depth.** Many requirements competing for the same attention
is a different problem from one rule that is easy to get wrong, and only the first has been shown to
matter.

The standing finding is unchanged and now harder to argue with: **the corpus has never produced a
submitted-and-wrong arm.** Test-first cannot show up as a better OUTCOME where the first attempt is
already right, and on small, single-concern tasks the first attempt is right. The harness's measurable
effects are elsewhere, and they are real: the order of the writes (13% -> 100% red-first), the artifact
at handback (the seal, and the routes around it that the record caught), and now the teeth of the suite
an arm ships (5 of 5 mutants killed, measured per arm -- a property that could have failed and did not).

### The first non-acceptance, and it was procedural (2026-10-25)

Fifty-eight arms in, one failed acceptance: `bits/ab-enforce-notice-1`. The implementation is FINE --
the acceptance corpus builds and passes. What fails is that **the submission's own suite does not
pass**, and the record says why:

    test_runs      [[6,1],[8,1]]      red at 6, red at 8, and then 21 steps with NO test run
    refusals       [[12,'outside: /tmp/verify.cpp'], [24,'submit on a red tree']]
    exit_status    Submitted (step 29)
    final_output   11 characters: "---dirs---"

The two failing cases are the model's OWN test bugs -- boundary guards that should have been
`p > 2u` and `n >= 1` -- and the model diagnosed exactly that, in a comment, inside a NEW test file it
added (which the seal allows) rather than the sealed file (which it does not). So it knew the suite was
red, and handed it back anyway.

**The corpus requires a RED before the code and requires nothing at all before the handback.** A run
can ship a suite it has never once seen pass, and nothing in the record objects. That is the mirror of
the rule the project is built on, and it stayed invisible for 58 arms because arms usually re-run their
suite on the way to green.

My own contribution to it: the seal notice said "an honest red is worth more than an edited green",
written with a sealed, genuinely-wrong test in mind and readable as a general licence to hand back red.
Reworded to separate the two cases -- the implementation is wrong (keep going until green) from a sealed
test being wrong (report it, do not edit it) -- and it now states the missing invariant outright: never
hand back a suite you have not run since your last change.

Enforcing it would be the same shape as `submit on a red tree`, which DID fire on this arm at step 24
and was recorded: carry `last_run_step` and `last_src_step`, and nudge the first submit when the suite
has not run since the last source write. Stated but not yet enforced -- one rule, one arm of evidence.

**Three arms, not one (same task).** When the rest of the `bits` arms landed: 0 of 3 accepted, all three
for the identical reason -- `ok the acceptance corpus builds and passes` together with `FAIL the
submission's own tests do not pass`. bits-1: last run step 8, then 21 steps of work, submitted. bits-2:
last run step 29, then StepLimit, never submitted. bits-3: last run step 15, submitted. Three
independent arms wrote correct code and handed back a suite they had never once seen pass. The
implementation was never the problem.

**And the oracles do not agree on what a finished job is.** bits fails a handback whose suite is red;
spans accepts one -- 3 of 3, with the last observed run red for every arm. Same protocol, two standards,
so the accepted column is not comparable across tasks and any "acceptance rate" is partly a statement
about which oracle the arm happened to draw. The seal makes it worse than merely inconsistent: a sealed
test that is wrong cannot be repaired, so bits' gate is one the model is forbidden to meet. Arm 1
diagnosed its boundary guard in a comment, in a new file, because the sealed one had no write path. A
gate the harness itself blocks is a trap, not a standard.

**And the check that said so graded nothing.** When check 2 stopped failing first, the answer-key
control caught what it had been hiding: bits' check 3 ran `ctest -R ninny_acceptance`, which finds no
tests under this project, prints "No tests were found!!!" and exits 0 -- read as a pass. In every tree,
including the answer key, for the whole campaign. So "the acceptance corpus passes" was a sentence
about a corpus that never ran, and the three arms' acceptance verdicts rested on it. The corpus was
honest all along -- run directly it passes 9/9 on arm 1's implementation and fails 9/9 on the stub --
but the plumbing was not. Check 3 now runs the binary itself and asserts the count against the corpus
source, so it can neither be vacuous nor shrink in silence.

The lesson is the one this repo keeps teaching from a new angle: **a check that cannot fail is not a
check, and one loud check can hide a broken one.** Check 2 failing loudly was why nobody looked at
check 3 -- exactly as a RED at step 8 made the missing GREEN unobservable. Both times the hiding was
done by a *correct* signal that happened to speak first.

**And the discipline applies to the commit messages, not only to the arms.** Phase 2's message said the
split block went "29 -> 9 lines" and the prompt "100 -> 92". The measurement says 13 and 84. The numbers
were written before the measurement ran -- the exact failure the GREEN rule now catches in an arm: a
claim written where an observation was available and cheaper. In the arms the fix is "run it rather than
ask"; here it is "measure it before writing it down". It mattered because a reader auditing the commit
would have found two numbers that no tool in this repo produces.

**And a missing tool looks exactly like a discipline failure from the record's side.** All three
`dogfood-stamp` arms wrote `ninny/**` through a shell heredoc and never banked a red: the record
said `bypass_detected` eleven times over, `red_step: None` every time, which reads as three models
walking around the gate. It was one missing tool. `write_file` takes the complete file, and the file
was four thousand lines of somebody else's code, so the shell was the only way to change part of it.
The fix was `edit_file`, not a wall -- and the general rule is that a spike in bypasses is a
question about the toolset before it is a verdict on the model.

**And two enforcement layers over one path will disagree.** The read-only bind that seals the
suite was applied in *every* mode while the gate that refuses a write into a sealed test fired in
`split` alone (tdd.py's sealed branch is mode-guarded). So in `enforce` bash was physically blocked
-- the bind is a mount, and bash runs inside it -- while `write_file` and `edit_file` walked
straight past it, because the file tools run in the harness's own process and not in the sandbox.
Neither layer was wrong on its own; together they meant the record and the physics told different
stories about the same file. The fix was to give the bind to the mode whose claim it enforces
(`split`) and leave the seal as telemetry everywhere else. A layer should be able to say which
claim it is enforcing; if it cannot, it is guarding something nobody promised.

**And the command is not the function.** `ninny verdict`'s unit tests all passed -- they called
`cmd_verdict` directly -- and `ninny verdict <run>` died inside `main()` with
`AttributeError: 'Namespace' object has no attribute 'no_log'`, because the flag is spelled once in
a loop over the subparsers and the new parser was registered after it. Every test called the
function; the user calls the door. `tests/test_cli_surface.py` now walks the commands and refuses
one that cannot take the shared flags. Run the command, not the thing you wrote a test for.

**A pipeline inside a preflight reports the wrong exit code.** Probing a worktree inside bwrap:
`git rev-parse HEAD` failed with "not a git repository" while `git status --porcelain | head -2`
came back ok, because a shell pipeline exits with the status of its last command. The probe was
mine, but the lesson is the harness's: an oracle, a preflight or a gate that pipes has an exit code
that means something other than what it is read as. Only the first command's status is evidence.

**A rule that cannot be satisfied is indistinguishable from a broken harness.** `ninny run --repo`
defaults to `request`, and takes `enforce` only once `--test-glob` says which files are the tests.
The plan for this door recommended `enforce` by default, and on a repository whose suite is green
that is a deadlock: every way to make a red is itself a write, and the gate refuses writes until a
red. Two more of the same shape sat beside it -- an empty `test_globs` would leave `red_ok` false
forever and report every repository run as `no-tests`, and `src_globs = ["**"]` would make the
model's own test file a source file that the gate then refuses. Before adding a gate, ask what a
run could DO to satisfy it; if the answer needs a step the gate also blocks, it is not strictness.

**A patch against a moving tree is not a patch.** Ninny's first repository run produced a 30.8 MB
diff with 2,224 file headers and 482,462 removed lines for a change of ten, because the patch
compared the LIVE tree against the worktree: a commit landing mid-run read as the delegate deleting
it, and every gitignored file on disk read as another deletion. Diff the worktree against the
commit it was staged at -- and stage first, or a file the delegate created is missing from a diff
that otherwise claims to be its work.

**A claim in a commit message is still a claim.** One commit here said `ninny run` "still returns 0
when the process finished". The line returns 0 only for `Submitted`; the real gap is narrower and
worse -- a submitted run returns 0 whatever the artifact says, which is how an arm with four shell
bypasses read as accepted. It took a correction commit, which is the cheap version of the problem.
Read the line before describing it.

## The adapter layer: six copies of one bug class (2026-10-23)

**Resolved:** the six hand-written adapters are now configs (`[runner]` in each `task.toml`)
rendered into the tree by `ninny/runner.py`, checked against the config by the gate. The four
lessons below are what the conversion itself measured.

**The layer nobody checked was the adapter.** Six scripts, 41-72 lines, 3-5 hand-rolled guards
each, no two alike -- and every defect of the campaign lived there, not in the harness: a task
that refused its own required edit, a red reported as "nothing ran" because a guard matched
Cargo's `error: test failed`, a README telling agents to write files Cargo never compiles, an
empty frozen manifest that still printed "every frozen file is unchanged". The loop was
language-blind; the layer beneath it was six copies of the same guessing game. Replacing the
guesses with four declared answers (build, run, count, failure) removed the class.

**The answer key carries the instrument too.** Rendering the adapter into `tree/` and not into
`fixed/` turns a hash-manifested runner into "the oracle is GREEN fails" -- the task looks
unsolvable when the answer key is merely stale. Render both, always; `ninny runner --write` now
does, and the drift check inspects both.

**Quote the directory, not the glob.** `shlex.quote("tests/own/*.cpp")` produces a literal path,
so the `require` guard fails on every run and every task reports "nothing to run yet" as exit 2.
The third control caught it on four tasks at once -- which is what it is for. Quote the head of
the path and leave the pattern to expand.

**A tool's "Ran 1 test" can be its own fiction.** `unittest` reports an unimportable module as
one synthetic `_FailedTest`, so a suite that never compiled answers 1 (a red) without a guard --
exactly the false red the contract exists to prevent. The hand-written `roman` adapter had this
bug; the rendered one declares `build_fail` and answers 2. The transcript that proves it is in
`tests/fixtures/runners/roman.broken.txt`.

## The publish ritual was the design talking (2026-10-23)

**Every publish was a filtered force-push clone, and that was a symptom, not a policy.** The
history held two tasks that must not be public (`tasks/cron`, `tasks/ninny-gate`), so the public
repo was built by cloning this one and rewriting every commit to strip them. Rewriting changes
hashes, so the published `main` shared no ancestry with local `master`: a plain `git push` could
never fast-forward, `git pull` could never bring anything back, and the two drifted by whatever a
publish run happened to include. Measured on the day it was fixed: `git remote -v` empty in the
working clone, published tree 149 files against 238 tracked, and the published `main` an object
this repo did not even have.

**The fix is to stop tracking what must not ship, not to keep rewriting it out.** The two tasks
were ignored for a few hours — on disk, invisible to a fresh clone — and then published as well,
once the trade was actually weighed: nothing in them is a secret (a scan found no keys, no tokens,
no absolute paths, no addresses; the only `sk-` strings in them are `sk-whatever` in a sample
config), and contamination risk is proportional to what gaming the benchmark is worth. One
`filter-branch` removed them from all 37 commits, `master` became `main`, and publishing became
`git push`. A bundle of the pre-rewrite history sits outside the repo (`_backups/`), because a
history rewrite with no undo is not a decision, it is a trap.

**Removal is not unpublishing.** A pushed commit lives on in GitHub's history, in forks, and in
whatever scraped it; deleting the files at the tip fixes nothing. So the honest rule is: publish
only what you would be content to have permanently public, and if you need an uncontaminated
benchmark later, build tasks that were never public. That is a decision made once, about the
future — not a switch you can flip back.

**The generalisation: if publishing needs a ritual, the repo is tracking something it should not.**
Force, filtering, and "remember to run the gate by hand" were all consequences of one directory
tree being in the wrong place. The tell is a publish path that is not `git push`.

## A record is written while the run is still going

`result.json` is not written once, at the end. Scoring an arm that is still running reads a snapshot, and
a snapshot can be empty where the finished record is not: a first pass over a run that had already called
`run_tests` at step 34 showed `test_runs=[]`, and looked like the harness failing to observe a suite run it
had in fact observed. Read the record after the process exits -- or read it twice and believe the second.
Applies to any number taken from a run in flight, including `write_steps` and `told`.
