# Does telling the model about its budget reduce wasted runs? — PRE-REGISTERED 2026-10-27

**Why.** Two repository runs on this machine ended without a handback and without a single write:
`protekt-shotgun-1` (40 of 40 steps, 706 s, zero writes, `diff.patch` 13 bytes) and `repo-refusal-wording`
(30 of 30 steps, zero writes of source, no submit). In both, the model spent its whole budget reading.
The brief for the first one *ordered* that reading: *"Read these before writing anything … re-check every
name"*, then named about ten files in a 123-TU C++ repository, against a 40-step budget. Nothing in the
loop ever told the model how much budget was left, or that it had written nothing.

**The change under test.** Two notes, each said ONCE, appended as a user message before the step's model
call — the same "told, not blocked" axis as the phase news:

1. **Silence note** — at 50 % of the budget with `write_steps == []`: *you have spent N of M steps and
   written nothing; the deliverable is a patch.*
2. **Budget note** — in the last ~15 % of the budget: *N steps remain of M; hand back what you have.*

Each is recorded in the state (`told: [[step, kind], …]`) so the record shows whether the model was told,
which is what makes the arms comparable.

**Arms.** The real failing case, unchanged: `--repo ~/hermes-workspace/protekt`, the same
`shotgun-brief.md`, `--test-cmd "bash tools/ci.sh fast" --test-glob tests/* --tdd enforce --steps 40`,
model `deepseek/deepseek-v4.1-flash`. Two arms per condition, same name stem.

- **baseline** — the code as it stands at `d537c3b`, launched first.
- **told** — after the notes land.

**Pre-registered prediction (before either arm ran).**
- `writes` in the baseline: 0 and 0. In `told`: **> 0 in both arms** — that is the prediction the change
  is betting on.
- At least one `told` arm reaches `Submitted`; if it submits with a stale suite, the harness runs the
  suite itself (shipped `194b7b1`) and the verdict grades that honestly — a rushed handback is a *graded*
  handback, which is already a strict improvement on a run that dies with nothing.
- The record shows the notes in `told`, and each kind appears exactly once (a repeated note is noise).

**Cost ceiling.** ≤ $0.12 per arm (baseline measured $0.0603 for 40 steps).

**Metrics, in order.** (1) `write_steps` non-empty; (2) `exit_status == Submitted`; (3) `ninny verdict`
exit code; (4) steps; (5) cost. Recorded per arm from `result.json`, not from the log.

**Known confounds, shared by both conditions (so the comparison holds, but read it with this in mind).**
- The brief's addendum describes files that are *uncommitted* in the PROTEKT working tree, and repo mode
  stages a worktree **at HEAD** — so those files are absent in every arm, and the model may spend steps
  looking for `pellets.hpp` before concluding it is not there. This is a property of the brief, not of
  Ninny, and it is identical in both conditions.
- `tools/ci.sh fast` is a 121 s C++ build; whether the suite can be observed at all inside the run's test
  timeout is checked before launching, because a timeout would make "no suite observed" look like
  "the model chose not to look".
- Two arms per condition is enough to see "nothing at all" versus "something" and is not enough to
  estimate a rate. If both `told` arms write, the honest claim is *it stopped the total loss*, not
  *it raises success by X*.

---

## RESULT — 2026-10-27, 13:43–14:30

Scored from `result.json` **after each process exited**. (That matters: `result.json` is written
incrementally, and a first read at 14:20 against a still-running arm showed `test_runs=[]` for an arm
that had in fact run the suite at step 34. Read the record when the run is over, or read a snapshot.)

| arm | exit_status | steps | writes | `told` | `test_runs` | verdict | cost | patch |
|---|---|---|---|---|---|---|---|---|
| `budget-base-1` | StepLimit | 40 | **0** | — (field absent) | `[]` | `no-write` | $0.1006 | **13 B, 0 files** |
| `budget-base-2` | pending | | | | | | | |
| `budget-told-1` | StepLimit | 40 | **4** | `[[21,'silence'],[35,'budget']]` | `[[34,1]]` | `red-first` | $0.0974 | **11,644 B, 3 files** |
| `budget-told-2` | StepLimit | 40 | **4** | `[[21,'silence'],[35,'budget']]` | `[[33,1]]` | `red-first` | $0.1136 | **4,720 B, 3 files** |

**Prediction, clause by clause.**
1. *`writes` 0 and 0 in the baseline, > 0 in both `told` arms* — **HELD.** 0 vs 4 and 4.
2. *At least one `told` arm reaches `Submitted`* — **FAILED.** Every arm in both conditions hit
   `StepLimit`. The total loss stopped; the handback did not start.
3. *Each note appears exactly once in `told`* — **HELD**, identically in both arms (`[[21,'silence'],
   [35,'budget']]`), so the notes fire at the same point regardless of what the model does in between.
4. *≤ $0.12 per arm* — **HELD** ($0.0974, $0.1136, $0.1006). But the estimate the ceiling was set from
   ($0.0603 for 40 steps, from the October run) was wrong for this tree and model: ~$0.10 is the going
   rate.

**What the logs show, in order.**
- `told-1`: note at 21 → a 5,487-byte test at **step 23** → ran the suite at 34 (`exit 1`, a real RED)
  → `GREEN` at 35 → tried to hand back and was refused: *"your own tests are failing — the last
  `run_tests` run exited non-zero… A handover on a red tree is not a result."* → kept working, wrote
  source at 37 and edited the test at 38 → step limit.
- `told-2`: note at 21 → test at **step 26** → suite at 33 (`exit 1`) → wrote source at 36, 40, and a
  header at 37 → step limit. Never attempted a submit.
- `base-1`: 40 steps of reading, no write, no test run, no submit, 13-byte empty patch.

**Protections that fired, unprompted, in both `told` arms:** `told-1` had a write to `tools/probe3.cpp`
refused by the protected-glob rule plus the test-first message; `told-2` had a write outside the tree
(`/tmp/probe.cpp`) refused. `bypass_detected` is empty in all three.

**What this supports.** One note — said once, at the halfway point, only because nothing had been
written — converted a run that produced 13 bytes into runs that produced a failing test, a suite run,
and 4.7 KB / 11.6 KB of patch, at the same step limit and the same cost. Both told arms wrote the test
*first* and ran it, unprompted, which is the behaviour the whole harness exists to encourage.

**What this does NOT support.**
- Not a success rate: n=2 per condition, one brief, one repo, one model, one budget.
- Not a handback: both told arms died at 40 steps, and `green_after_last_write` is `None` in both — they
  went green *before* their last write, so their code is unproven. `red-first` is a claim about order,
  not about being finished.
- Not a correctness claim: a repository task has no oracle. Nobody has said those tests are right.
- Not sufficiency. 40 steps is still too few for this brief; the honest reading is that the notes
  stopped the total loss and the caller's dial (a budget sized to the brief) is the other half.

**Confound, as pre-registered, and how it played out.** PROTEKT committed `acdeff4` after the original
failing run, so these arms are not the original tree — and it did not weaken the comparison in the
direction that matters: the baseline still produced 13 bytes and zero writes, and `budget-base-1`
(steps 34–37) was observed running `git show <sha>:tests/test_shotgun.cpp` in git history to find a
brief-named file absent from its staged tree. That is the pre-registered confound, seen directly — and
it is the exact fact the new preflight now prints as `names N paths; … missing: …`.

**Two corrections and one addition, from the run's own summary line (`told-1`).**
- The patch is not merely "3 files": it is `3 files changed, 217 insertions(+), 2 deletions(-)`.
- At steps 39–40 it ran a scratch check and then `clang-format -i` over its own files. It was *polishing*
  when the budget ended, not stuck — which is what "the budget cut it off" actually means here.
- `suite_frozen=yes (sealed at step 34, reported only)` — reported, not enforced, which is the seal
  behaving as designed outside `--tdd split`.

## FOLLOW-UP, pre-registered (2026-10-27, written before launch)

**Question.** The notes stopped the total loss; the runs still died at 40 steps with a patch in hand. Was
the *budget* the remaining blocker?

**Change under test.** None — no new code. This runs the shipped code at a budget sized to the brief rather
than the default: `--steps 80`, everything else identical to `budget-told-*`.

**Arms.** Two: `budget-room-1`, `budget-room-2` — same brief, same repo, same model, same flags.

**Prediction.** At least one arm reaches `Submitted` **with `green_after_last_write` set** — a handback
whose last write was followed by a green suite. That is precisely the claim the notes alone could not make.
A second, weaker expectation: both arms still write, because the notes are still in the code.

**What would falsify it.** Both arms hitting `StepLimit` again at 80 steps, or submitting with
`green_after_last_write` still `None`. Either one means the blocker is not the budget, and the next suspect
is the brief itself — its reading list, and the files it names that are absent from the staged tree.

**Cost ceiling.** ≤ $0.30 per arm (40 steps measured ~$0.10; cost tracks steps, not notes).

## FOLLOW-UP ABANDONED — same day, before either arm did any work

The two `budget-room-*` arms were killed within about a minute of launch, for **two** reasons — and the
first one is mine:

1. **They crashed on a bug in the preflight I had committed an hour earlier.** `preflight_lines` read
   `args.test_globs`, and the flag is `--test-glob`, so argparse sets `test_glob`. Every `ninny run --repo`
   on `main` was dying at launch with an `AttributeError`. My own suite stayed green because the helper was
   tested in isolation and the *seam* — a real parsed `Namespace` — was tested nowhere. Fixed, with the
   seam test that should have existed. The experiment found this in a minute, which is what it was for.
2. **And even fixed, the tree had moved.** **PROTEKT `96a5318` landed `feat(sim): make the shotgun a real
   weapon, and let every bolt hit its own side` at 13:49**, which is the feature the brief asks for. The
   arms would have measured a model against work already done in the tree they stage.

So the follow-up was abandoned twice over: once because it could not run, and once because the question it
was written to answer no longer had a subject.

That commit is also the answer to a question the first batch left open: `budget-base-1` spent steps 34–37
running `git show 96a5318:tests/test_shotgun.cpp` because **the commit that satisfies the brief was
created while that arm was running**. The brief was not stale when it was written and was stale by the time
the arms read it — and the only place that fact is visible before spending money is the preflight's
missing-paths line, which would have printed `missing: tests/test_shotgun.cpp` for every one of the four
arms.

**What that changes.** The follow-up question ("was the budget the remaining blocker?") needs a brief that
is *actually pending* at launch, so it is now the PROTEKT side's to re-issue against a fresh task, not
something this repo can re-run against the old one. Recorded rather than replaced with a substitute brief,
because a substitute would have answered a different question.

**New open item, from the same evidence.** `--repo` stages HEAD at launch, which is right, but nothing
checks that the brief still describes that tree. A run whose brief names a file the staged tree does not
have is already detected by the preflight; a run whose brief is *satisfied* by the staged tree is not
detected at all, and cannot be, by any check that does not understand the task. Stated as a limit, not as a
feature request.

## THE SUBJECT WAS THE WRONG CHOICE — corrected 2026-10-27, at Harri's word

**Harri: "Protekt is a completely different project under active development. You can't rely on anything
there."** He is right, and the evidence was already in this file before he said it: the tree moved twice
during the first batch (`acdeff4` at 11:41, `96a5318` at 13:49), the brief belongs to another conversation,
and neither fact is controllable from this repo. Most of the confounds here are consequences of choosing a
subject someone else was editing.

**The rule this leaves behind.** A measurement subject has to be one this project controls end to end:
frozen or owned, with a brief that is still pending at launch and a tree that cannot move mid-run. For
repository mode that means **Ninny itself** — the same reason the benchmark arms use `tasks/`, where the
fixture is frozen by construction. Repository mode is the thing under test, so it needs a repository whose
state is part of the experiment rather than a coincidence in someone else's day.

**What survives, and what does not.**
- Survives: the comparison inside the first batch (all four arms launched within minutes of each other, and
  the baseline reproduced the failure on the newer tree anyway), and every conclusion about the *notes* —
  those are about the record the run writes, not about PROTEKT.
- Does not survive: any claim about PROTEKT, its brief, its feature, or the correctness of those patches.
  Nothing here says anything about that project, and nothing should be read as if it did.
- `budget-base-2`, still running when he said this, is the last PROTEKT datum and is reported as exactly
  that: one arm against a moving tree. No further arms run there.

## NEXT EXPERIMENT, pre-registered — repository mode on a subject this project owns

**Why this subject.** PROTEKT is out (see above). Repository mode needs a repository whose state is part of
the experiment, so this runs against **Ninny itself**, whose only editor is this conversation. The brief is a
real pending item from the caller-guidance design — item 3: state the suite's *measured* duration in the
preflight, because a duration is what tells a caller whether 40 steps is a budget or a trap.

**Arms.** `ninny-duration-1`, `ninny-duration-2`: `--repo ~/hermes-workspace/ninny`,
`--prompt-file .hermes/plans/2026-10-27_suite-duration-brief.md`, `--test-cmd "bash scripts/run-tests.sh"`,
`--test-glob 'tests/*.py'`, `--tdd enforce`, `--steps 60`, model `deepseek/deepseek-v4.1-flash`.

**Prediction.** At least one arm reaches `Submitted` **with `green_after_last_write` set**, and its patch is
small enough to read in a minute. The brief names the first file and the first test, so the reading that ate
the PROTEKT runs has nothing to feed on — which is the prediction's real content: *a brief with an entry
point spends its budget solving instead of orienting.*

**What would falsify it.** Both arms at `StepLimit` with no submit, or a patch touching files the brief did
not name. Either one means the entry point was not the problem, and the next suspect is step efficiency on a
400-test repository.

**Cost ceiling.** ≤ $0.20 per arm (60 steps on a small tree, with a 6 s suite).

