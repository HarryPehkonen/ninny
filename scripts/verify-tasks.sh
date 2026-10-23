#!/usr/bin/env bash
#
# tasks - the stage no other repo can have: every task still verifies.
#
# `verify-task` is Ninny's own two-way control - the oracle must be RED on the tree the agent
# starts from and GREEN on the answer key. A task that fails it is worse than a broken test:
# every run it grades is meaningless, and nothing else in this repo would notice. The
# examples are graded by the same control, because they ship as documented recipes.
#
# Anti-vacuous: the count of tasks checked is asserted. A glob that matched nothing must not
# be able to report a pass - the same rule the models are held to.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

checked=0
bad=0
for dir in tasks/*/ examples/*/; do
    [ -f "$dir/task.toml" ] || continue
    name=${dir%/}
    checked=$((checked + 1))
    out=$(python3 -m ninny verify-task --task "$dir" 2>&1); rc=$?
    if [ "$rc" -eq 0 ] && printf '%s\n' "$out" | grep -q '^VERIFIED'; then
        echo "ok: $name"
    else
        bad=$((bad + 1))
        printf 'FAILED: %s (exit %s)\n' "$name" "$rc" >&2
        printf '%s\n' "$out" | tail -10 >&2
    fi
done

if [ "$checked" -eq 0 ]; then
    echo "tasks: no task with a task.toml was found - the stage is vacuous" >&2
    exit 2
fi

echo "tasks: $checked verified, $bad failed"
[ "$bad" -eq 0 ] || exit 1
