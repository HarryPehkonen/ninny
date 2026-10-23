#!/usr/bin/env bash
#
# tree - is the working tree source, and only source?
#
# Three failures this repo has actually had, all cheap to re-detect:
#
#   * staged checks copied INTO a task tree and never cleaned up (tasks/*/checks silently
#     grew to 69 MB per verification, and 1.28 GB of runs/ plus checks/ in total);
#   * bytecode committed by accident (__pycache__, *.pyc) - an artifact is not source;
#   * work that exists only in the working tree, which every other stage happily tests
#     because the gates run on the WORKING TREE, not on the commit. Export
#     CI_REQUIRE_CLEAN=1 (that is what .githooks/pre-push does) to make that a failure.
#
# "No residue" is asserted rather than assumed because this repo's residue is invisible:
# runs/ and tasks/*/checks/ are gitignored, so a clean `git status` never mentioned them.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
fail=0

say_fail() { printf 'tree: %s\n' "$1" >&2; fail=1; }

# 1. Artifacts that must never be tracked. Counted, so "none" is a measured statement.
tracked_bytecode=$(git ls-files | grep -cE '__pycache__|\.py[cod]$' || true)
if [ "${tracked_bytecode:-0}" -ne 0 ]; then
    git ls-files | grep -E '__pycache__|\.py[cod]$' >&2
    say_fail "$tracked_bytecode tracked bytecode file(s)"
fi

# 2. Residue from a check staged inside a task. The fix (check artifacts go to $TMPDIR) is
#    covered by a test; this is the belt for the tree that is already dirty.
residue=$(find tasks examples -maxdepth 2 -type d -name checks 2>/dev/null | wc -l)
if [ "$residue" -ne 0 ]; then
    find tasks examples -maxdepth 2 -type d -name checks >&2
    say_fail "$residue staged-check director(ies) inside a task; they belong in \$TMPDIR"
fi

# 3. Untracked files are not source either - and they are what a push would leave behind.
untracked=$(git status --porcelain | grep -c '^??' || true)
if [ "${untracked:-0}" -ne 0 ]; then
    git status --porcelain | grep '^??' >&2
    say_fail "$untracked untracked file(s); commit them or add them to .gitignore"
fi

# 4. The clean-tree rule, only when the caller asks for it: a hand run is never required to
#    be clean, a push to a public remote is.
if [ "${CI_REQUIRE_CLEAN:-0}" = "1" ]; then
    dirty=$(git status --porcelain | grep -v '^??' | wc -l)
    if [ "$dirty" -ne 0 ]; then
        git status --porcelain | grep -v '^??' >&2
        say_fail "$dirty uncommitted edit(s) to tracked files, with CI_REQUIRE_CLEAN=1"
    fi
fi

# 5. Every task's adapter is the one its config renders. A hand-edited runner and a config
#    nobody re-rendered look identical until one of them lies to the harness, and the failure
#    would be blamed on the task. The claim is "the file on disk is what task.toml says".
drift=$(python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from ninny.config import load_task
from ninny.runner import drift
bad = []
for task_dir in sorted(p for p in Path("tasks").iterdir() if p.is_dir()):
    try:
        task = load_task(task_dir)
        ok, note = drift(task.root, task.meta)
    except Exception as exc:
        bad.append(f"{task_dir.name}: {exc}")
        continue
    if not ok:
        bad.append(f"{task_dir.name}: {note}")
print("\n".join(bad))
PY
)
if [ -n "$drift" ]; then
    printf '%s\n' "$drift" >&2
    say_fail "task adapter(s) differ from their [runner] config; run: ninny runner --task <dir> --write"
fi

[ "$fail" -eq 0 ] || exit 1
echo "tree ok: no tracked bytecode, no check residue, no untracked files$([ "${CI_REQUIRE_CLEAN:-0}" = "1" ] && printf ', tree clean')"
