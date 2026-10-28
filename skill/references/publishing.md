# Publishing an update (plain `git push`)

> Extracted from `ninny-harness/SKILL.md` (split by scripts/split_skill.py).
> The body keeps a pointer; this file keeps the detail.

GitHub (`HarryPehkonen/ninny`) and this clone are **one lineage**: local `main` tracks
`origin/main`, and publishing is one command.

```bash
cd <the clone>
git add <explicit paths>          # never -A: it sweeps up work in progress
git commit -F <msg>
git push                          # the pre-push hook runs the full gate, ~25 s warm
```

`core.hooksPath=.githooks` lives in `.git/config`, not in the tree, so a **fresh clone is
unguarded** while looking armed: arm it with `git config core.hooksPath .githooks`. The push
hook exports `CI_REQUIRE_CLEAN=1` and refuses a dirty tree; `pre-commit` runs the fast tier and
does not.

## Why it used to need a ritual, and why that was the bug

Publishing was a **filtered force-push clone**: the history held two tasks that must not be
public (`tasks/cron`, `tasks/ninny-gate` — they carry answer keys), so the public repo was
rebuilt each time by rewriting every commit to strip them. Rewriting changes hashes, so the
published `main` shared **no ancestry** with local `master`: a plain push could never
fast-forward, `git pull` could never bring anything back, and the two histories drifted by
whatever a publish run happened to include. Measured before the fix: `git remote -v` empty in
the working clone, 149 files published against 238 tracked, and the published `main` an object
the local repo did not even have.

The fix was to stop **tracking** what must not ship: one `filter-branch` removed those two paths
from all 37 commits, `master` became `main`, and publishing became `git push`. They were untracked
for a few hours, then **published as well** (2026-10-23) once the trade was weighed by scan rather
than assumption: no keys, tokens, private keys, `.env`/auth/credential files, absolute paths or
addresses — the only `sk-` strings are `sk-whatever` in a sample provider config. **Nothing in this
repo is secret, so nothing in it is hidden.**

**Removal is not unpublishing.** A pushed commit survives in GitHub's history, in forks and in
whatever scraped it; deleting the files at the tip fixes nothing. Publish only what you would be
content to have permanently public, and if you need an uncontaminated benchmark later, build tasks
that were never public. That is a decision made once — not a switch you can flip back.

**If publishing needs a ritual, the repo is tracking something it should not.** Force,
filtering, and "remember to run the gate by hand" were all consequences of one directory tree
being in the wrong place. The tell is a publish path that is not `git push`.

Full pre-rewrite history, as undo:
a local bundle kept outside the repository (`git clone <bundle>` restores
every commit as it stood).

## Proving a publish landed

Verify against GitHub itself, never through a remote name — a clone's `origin` can point at a
local path, in which case `git ls-remote origin main` answers from the local repo and reports a
false MATCH while GitHub stays empty.

```bash
git ls-remote https://github.com/HarryPehkonen/ninny main   # == git rev-parse HEAD
gh api 'repos/HarryPehkonen/ninny/git/trees/main?recursive=1' \
  --jq '[.tree[]|select(.type=="blob")]|length'             # == git ls-files | wc -l
gh api 'repos/HarryPehkonen/ninny/git/trees/main?recursive=1' \
  --jq '[.tree[].path|select(startswith("tasks/cron") or startswith("tasks/ninny-gate"))]|length'   # 0
```

## Lessons that travelled with this file

- **A rate computed before a rule changed must be re-derived, and with ONE rule.** When the
  exit-code contract landed, the retrospective over stored runs was computed three times and
  gave three answers, because each pass mixed sources of truth (the stored verdict, the
  re-derived source step, a text-sniffed red). Settle on one objective rule, then EYEBALL
  the raw evidence for a handful of cases before quoting any number: three of five sampled
  runs changed the answer. The defensible form is "of the N runs that banked a RED, M banked
  one where nothing executed", with the marker in the run's own output as the evidence.
- **The example task's first `run_tests` fails for a reason that has nothing to do with
  tests.** Its runner used `discover -t .`, which is unimportable until `tests/own/__init__.py`
  exists, so 24 of its 26 banked reds were that discovery error. Fixed with `-t tests/own`.
  Before blaming a model for a bad process, check whether the task's own harness makes the
  good process reachable: a harness that mismeasures its own housekeeping is measuring the
  wrong thing.
