# The delegate whose handback is evidence — plan

**Repo:** `~/hermes-workspace/ninny` at `55df2ed` (main == origin/main, clean).
**Written:** 2026-10-26 14:11. **Executed:** 2026-10-26, same day.
**Status: EXECUTED through step 2; step 3 is in flight.** Commits: `9a5fb49` (this plan),
`f8c2670` (0 — the seal's mount, the manual), `0162bfc` (`ninny verdict`), `a205935`
(`run --repo`), `81ea9c0` (the README opening), `66fce59` (**Ninny's own patch, applied**),
`194b7b1` (the three defects the first repository run found), `55df2ed` (LESSONS).

**Two decisions in this plan that did not survive contact, both recorded in their commits:**
- **`--repo` defaults to `request`, not `enforce`.** `enforce` refuses a source write until a red
  has been seen; on a repository whose suite is *green*, every way to make a red is itself a write.
  A deadlock is not strictness. `enforce` is one flag away (`--test-glob`).
- **The patch is `git diff` in the worktree against its staged commit**, not against the live tree:
  the live tree moves (my own commit landing mid-run read as the delegate deleting it) and is full
  of gitignored residue. Measured on the first run: 30.8 MB, 2,224 file headers, 482,462 removed
  lines, for a change of ten.

**What step 3 has produced so far:** `66fce59` — a 17-step, $0.0045 run fixed
`build_sandbox(binds=None)`'s `TypeError` in `ninny/sandbox.py` and added its own test; applied by
hand with 366 tests green. Its verdict was **exit 1, unproven** — good patch, no evidence, because
it never ran the suite. That distinction is the product.

**Goal:** make this sentence true for a developer who is not us: *a generic agent delegates a
small, specified change to Ninny with one command, and gets back a diff plus a record it can
accept or reject mechanically — without reading prose and without trusting the delegate.*

**Architecture (three things, in payoff order):**
1. `ninny verdict` — one JSON line and an exit code read off `result.json`. The exit code is
   the API an orchestrator consumes. Pure read; defines the contract the other two serve.
2. `ninny run --repo` — a second *constructor* for `Task`, not a second code path: `cmd_run`
   runs unchanged. Staged on a `git worktree`, diff via `git diff HEAD`.
3. A README that opens with a real transcript of an orchestrator **rejecting** a handback,
   produced by running (2) on Ninny itself and (1) on the result.

**Tech:** Python 3.11+ stdlib only (the standing rule), `git` as a subprocess, bwrap optional.

---

## 0. Where the evidence stands (so the plan rests on numbers, not on Gemini's prose)

| condition (dogfood-stamp, `enforce`, deepseek-v4.1-flash) | n | accepted | red-first | bypass events | green-after-last-write |
|---|---|---|---|---|---|
| cap 30, four actions | 3 | 2 | **0** | 11 total | n/a |
| cap 60, four actions | 3 | 3 | **0** | yes, all 3 | 3 |
| cap 60, **+ `edit_file`** (`ab-editfile` + `ab-editfile2`) | **9** | 9 | **9** | **0** | 9 |
| cap 60, + `edit_file`, **seal unbound in `enforce`** (`ab-unsealed`) | 3 | 3 | **3** | **0** | 3 |

Red lands one step before the first source write in every one of the twelve. Same model, same
task, same mode; the only change is the tool. This is the first outcome-adjacent number that has
moved in the whole campaign. It is also **one task**: the corpus-wide claim is still open.

The unsealed row is the confirmation run this plan asked for, and it held the pre-registered
prediction: bypasses stayed 0, red-first stayed 3/3, and `suite_frozen_since_red` stayed true in
all three — the drop I allowed for did not happen. It cost **42.0** mean steps against the sealed
batch's 32.3, so the seal was not only a theorem about the artifact; it was also a shortcut.

What is already pushed since the review: `d5e1b33` (edit_file + gate), `487670f` (README five
actions), `6620ea6` (describe(), README table, text-wire note). What is **written and red, not
shipped**: `tests/test_prompt_names_every_action.py` (3 F), `tests/test_seal_mount_is_split_only.py`
(5 F). Both are held until the running batch finishes, because both change the model's input.

---

## Phase 0 — close the open condition (precondition, ~1 h, ~$0.10)

Not new work; the plan is void without it.

0.1 Wait for `ab-editfile2-5..6`. Score. Record the n=9 row in `docs/LESSONS.md`.
0.2 Ship the two held changes **in one commit** (they are one condition change):
   - `ninny/prompt.py:32-37` — add `edit_file` to `## How to act` (5 items); `:175` — the
     no-tool-call message names all five; `:118` — the seal notice names `edit_file` among the
     write routes. (Guard: `tests/test_prompt_names_every_action.py`, 3 tests go green.)
   - `ninny/agent.py:286-314` `_enforce_seal` — bind read-only **only when `self.policy.mode ==
     "split"`**; every other mode logs `[seal] recorded, not enforced in mode X` and keeps
     `close_seal` telemetry. (Guard: `tests/test_seal_mount_is_split_only.py`, 3 tests, 5
     subtests go green; `split` still binds — that subtest is the safety.)
   - `README.md:296` already says this is the design; add one sentence under "## The seal"
     that the mount is `split`-only and `suite_frozen_since_red` is reported in every mode.
   - `docs/LESSONS.md`: the split-brain entry (bash blocked, file tools not; cost = the `bits`
     unrepairable-assertion arms).
0.3 Re-run 3 arms (`AB_LABEL=unsealed`). **Pre-registered prediction:** bypass stays 0, red-first
   stays 3/3, and `suite_frozen_since_red` may come back `false` in one arm (an assertion fixed
   after the red). That number is the price of unfreezing, and it is the honest one.
   **Kill:** if bypass or red-first regress, revert 0.2 (`git revert <sha>`) and stop.

Undo for the phase: one `git revert`.

---

## Phase A — `ninny verdict` (payoff: highest per line; cost: ~2 h; risk: none)

**Why first:** it is the contract. Phases B and C exist to produce something this reads.
Today an orchestrator must know to AND five of the 25 `tdd` fields; `cli.py:173` prints prose.

**Contract (exit code mirrors the test contract the repo already teaches):**

| exit | meaning | condition |
|---|---|---|
| 0 | **artifact present** — accept | `exit_status == "Submitted"` ∧ `red_before_code` ∧ `suite_frozen_since_red` ∧ `green_after_last_write` ∧ no `bypass_detected` |
| 1 | **handed back, unproven** — reject or read | submitted, but at least one of the above is false; `reasons[]` names each |
| 2 | **did not hand back** | `exit_status` ≠ Submitted (StepLimit, error, cost cap) — nothing to grade |

One JSON line on stdout, always, e.g.
`{"verdict":"artifact","exit":0,"run":"runs/x/arm-1","red_step":14,"first_src_step":15,"green_after_last_write":true,"suite_frozen_since_red":true,"bypass_detected":[],"reasons":[],"patch":"runs/x/arm-1/diff.patch","cost_usd":0.0444}`

**Tasks (TDD, one commit each or one for the phase):**
- A.1 `tests/test_verdict.py`: nine cases — the three exits, each `reasons` entry, a missing
  field = exit 2 with `reasons:["record incomplete: <field>"]` (never a silent pass), and
  **determinism** (same file → same line). Run → red.
- A.2 `ninny/verdict.py` (~60 lines): `verdict_of(result: dict) -> tuple[int, dict]` +
  `cmd_verdict(args)` taking a run dir **or** a `result.json` path. Pure; no I/O beyond reading.
- A.3 `ninny/cli.py`: subcommand `verdict <run_dir>`; `run` prints the same JSON line **after**
  the summary and returns its exit code (today `run` returns 0 on StepLimit — check
  `cmd_run`'s return; an orchestrator must not read "the process finished" as "accepted").
- A.4 `scripts/ab-score.sh`: add a `verdict` column so the campaign table and the orchestrator
  read the same bit.
- A.5 `docs/VERDICT.md` (short) + README section "Consuming the handback" with the three lines
  an orchestrator writes. Mention: **a verdict is read off the record, never off the prose.**

**Kill:** none — if the field set turns out wrong the contract moves, the shape stays.
**Undo:** `git revert <sha>`; nothing else depends on it until Phase C.

---

## Phase B — `ninny run --repo` (payoff: the door; cost: ~½ day; risk: medium, all measurable)

**Design decision (recommended, measured):** no new noun. `ninny run` gains `--repo PATH`, and
when it is present `load_task` is bypassed for `task_from_repo(...)`. Reason: `cmd_run` reads
~15 `Task` fields, every one of which has a sane repo-derived value; `oracle_dir`/`oracle_cmd`
are already `Optional`. A second subcommand would duplicate the loop. (Also: do not squat on a
generic verb like `work`.)

```
ninny run --repo . --spec SPEC.md|"text" --test-cmd "scripts/gate.sh --tier fast" \
          [--runner NAME] [--tests GLOB=tests/**] [--name NAME] [--tdd enforce] [--steps 40]
```

- `--spec` — a path **or** a literal; required.
- `--test-cmd` — **required, no auto-detection in v1.** Harri's repos alone split between
  `scripts/gate.sh` (KitCI) and `tools/ci.sh` (AI-DEV-STARTER); a guess that is wrong 50% of the
  time is worse than one flag. YAGNI until a second user asks.
- `--runner` — optional; reuses the existing `[runner]` conventions (`docs/RUNNERS.md`) so
  `NINNY_TESTS` is counted and exit 2 ("nothing ran") is real. Without it the exit-code contract
  is whatever the command returns, and the record says `test_counts: null` honestly.
- `--tests` — `test_globs`; `src_globs` = everything else except `protected_globs`. **B.0 must
  verify** how `tdd.py` matches `src_globs` today (one field, one read) before this default is
  trusted.

**Staging — `git worktree`, not `copytree`:** `git worktree add --detach runs/<name>/tree HEAD`.
Reasons: (a) KitCI's `tree` stage and most gates shell out to git, so a bare copy cannot run the
test command; (b) committed state only — uncommitted edits in the developer's checkout are **not**
staged, which is a feature: the handback is against a commit, and the diff applies to it;
(c) `diff.patch` = `git -C tree diff HEAD` (binary-safe, `git apply`-able), replacing
`write_diff(tree_src, workdir)` for this path only. Cleanup: `git worktree remove --force` after
the patch is written, unless `--keep`.

**bwrap consequence (measure, do not assume):** a worktree's `.git` is a *file* pointing at
`<repo>/.git/worktrees/<name>`. Inside bwrap that path must be bound (read-write: git writes the
index) or every `git` call fails with "not a git repository". B.2 adds that bind when `--repo` is
used and proves it with a sandboxed run that executes `git status`.

**Tasks:**
- B.0 Read `tdd.py`'s glob matching for `src_globs`/`protected_globs` (read-only, 10 min).
  Decide the default; write it down in the docstring of `task_from_repo`.
- B.1 `tests/test_task_from_repo.py`: builds a throwaway git repo in tmp, asserts a `Task` with
  `name`, `spec` (literal and file), `test_cmd`, `tree_src` = a worktree at HEAD, `oracle_cmd is
  None`, `test_globs`, and that **uncommitted files are absent** from the worktree. Red first.
- B.2 `ninny/config.py`: `task_from_repo(repo, spec, test_cmd, runner, tests, name) -> Task`
  (~50 lines) + `ninny/stage.py` or inline: `add_worktree()`, `remove_worktree()`, `git_diff()`.
  `ninny/sandbox.py`: the `.git/worktrees/<name>` bind when the tree's `.git` is a file.
- B.3 `ninny/cli.py`: the flags; `--repo` makes `--task` an error (one source of truth). The
  summary and the Phase A verdict line print as before.
- B.4 Offline end-to-end (`tests/test_run_end_to_end.py` already stubs `ModelClient`/`Pricing`):
  `run --repo <tmp repo> --spec "..." --test-cmd "python3 -m unittest"` → `diff.patch`,
  `result.json`, verdict line, worktree removed.
- B.5 **Live measurement, 3 arms, on `ninny` itself**, spec = a real small change (candidate:
  "`ninny doctor` lists `target/`, `.ninny-build/`, `build/` as residue" — an open item), test-cmd
  `scripts/gate.sh --tier fast`, model deepseek-v4.1-flash, bwrap. This *is* Phase C's raw
  material.
- B.6 `docs/TASKLESS.md`: one page — the command, what is and is not staged, the bwrap bind,
  the exit code. Written so a reader could adapt it (Harri's bar).

**Kill criteria:** (i) if a worktree inside bwrap cannot be made to run `git status` in a day,
fall back to `git archive HEAD | tar -x` staging and declare "test commands that need git are
unsupported in bwrap" in `TASKLESS.md` — honest and still useful; (ii) if B.5's three arms all
StepLimit, the problem is the spec or the cap, not the door — report, don't widen scope.
**Undo:** `git revert` of the phase commits; no task, no mode, no existing CLI flag changes.

---

## Phase C — the proof and the README (payoff: the reason anyone looks; cost: ~3 h + ~$0.20)

- C.1 From B.5's arms, pick the **rejection**: a handback where `verdict` is 1 (stale tree,
  suite changed after red, or never green) — if none occurs in 3 arms, run 3 more with
  `--tdd off` (the control arm exists precisely to produce unproven handbacks: 13% red-first).
  If `off` also yields nothing rejectable in six arms, that is itself reportable: say so.
- C.2 README rewrite of the **top 40 lines only**: open with the one-line command, the JSON
  verdict line of the rejection, the three-line orchestrator rule (`exit 0 → apply the patch;
  1 → read reasons; 2 → nothing was handed back`), then the accept case. Everything below the
  fold stays; "It is also not a worker" (README:48) is rewritten to: an instrument *and* a
  delegate, and the record is the same in both.
- C.3 `docs/LESSONS.md`: "a missing tool reads as a discipline failure" (shipped), "the mount
  froze every mode", and "the orchestrator's API is an exit code".
- C.4 Tag nothing. **No v1.0.0 in this plan** — that stays Harri's explicit call, per standing
  instruction.

**What C does NOT claim:** better code. Every task is at acceptance ceiling; the claim made is
*"a test seen to fail, the same test seen to pass, green observed after the last edit — and the
record says so."* Any sentence stronger than that gets cut.

---

## What this plan will NOT touch

- The ten benchmark tasks, their oracles, `verify-task`, `oracle_gate` — unchanged.
- `--tdd split` semantics and its seal (the artifact mode keeps its mount).
- Model choice; no new providers; no OpenRouter.
- The text (completions) wire stays at four actions, documented as such.
- No auto-detected test command, no `.ninny/` convention, no PyPI, no plugin/MCP/multi-agent.
- No `edit_file` for the fixture-less `check`/`verify-task` paths — they grade trees, not runs.

## Honest costs and risks, ranked

1. **bwrap + worktree** is the only unknown that could eat a day. Measured in B.2 first;
   fallback named.
2. **Unfreezing `enforce`** (0.2) may lower `suite_frozen_since_red`. That is a true number
   replacing a flattering one; the record keeps reporting it.
3. **One task** carries the 7/7. B.5 is the second task, on a real repo, with a real gate.
   If it does not replicate, the README cannot lead with it and C.2 shrinks to the verdict API.
4. Scope creep pressure from the Gemini list (auto-detect, `work`, retiring the seal entirely).
   Each is declined above with a reason; revisit only on a second user's ask.

## Open calls for Harri (the plan recommends; you decide)

1. **Name:** `ninny run --repo` (recommended) vs a new `ninny work`.
2. **Default `--tdd` for `--repo`:** `enforce` (recommended, after 0.2) vs `off`.
3. **B.5's spec:** the `doctor` residue list (recommended: small, real, open) vs something else
   you'd rather see land first.
4. **Go on Phase 0 now** while the batch finishes, or wait for n=9 first.

## Verification at every step
- `python3 -m unittest discover -s tests` green (314 today); the fast gate on every commit; the
  full gate (all 11 tasks `verify-task`) on every push via the hook — that is how a change to
  `Task` or the sandbox is proven not to break the corpus.
- Every behavioural change: pre-registered prediction, 3 arms, number reported whichever way
  it goes, undo line in the commit.
