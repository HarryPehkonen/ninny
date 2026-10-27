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

