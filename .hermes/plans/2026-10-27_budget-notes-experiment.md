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
