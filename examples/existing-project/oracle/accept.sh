#!/usr/bin/env bash
# The hidden acceptance suite for the demo-project fixture. Lives outside the project and
# outside the snapshot, so the agent never sees it.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tree="${NINNY_TREE:?NINNY_TREE must point at the staged submission}"

rc=0
out=$(cd "$tree" && python3 -m pytest -q 2>&1) || rc=$?
echo "--- the project's own suite ---"
echo "$out" | tail -3

# The part the agent must not see: properties, not just the project's examples.
NINNY_TREE="$tree" python3 - <<'PY' || rc=1
import os, sys
sys.path.insert(0, os.environ["NINNY_TREE"])
from calc.core import add
cases = [(1, 2, 3), (7, -3, 4), (0, 5, 5), (1000, 234, 1234), (-5, -6, -11)]
for a, b, want in cases:
    got = add(a, b)
    if got != want:
        print(f"HIDDEN FAILED: add({a}, {b}) -> {got!r}, want {want}")
        sys.exit(1)
print(f"hidden: {len(cases)} properties hold")
PY

if [ "$rc" -eq 0 ]; then
  echo "ACCEPTANCE PASSED"
else
  echo "ACCEPTANCE FAILED (project suite or hidden properties)"
fi
exit "$rc"
