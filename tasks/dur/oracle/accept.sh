#!/usr/bin/env bash
# The oracle for the dur task. It runs OUTSIDE the agent's tree: `ninny check` stages the
# submission beside this directory and hands the path over in NINNY_TREE.
#
# Three directions: the frozen instrument must be unchanged, the corpus must pass against
# the submission, and the frozen CLI must behave. Exit 0 only when all three hold.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tree="${NINNY_TREE:?NINNY_TREE must point at the staged submission}"

bad=0
while read -r want path; do
  got=$(sha256sum "$tree/$path" 2>/dev/null | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then
    echo "FROZEN FILE MOVED: $path"
    [ -n "$got" ] || echo "  (missing entirely)"
    bad=1
  fi
done < "$here/frozen.sha256"
if [ "$bad" -ne 0 ]; then
  echo "ORACLE FAILED: the submission edited the instrument that measures it"
  exit 1
fi
echo "frozen    every frozen file is unchanged"

if ! command -v node >/dev/null 2>&1; then
  echo "ORACLE FAILED: node is not on PATH"
  exit 2
fi

node "$here/accept.js" "$tree"
exit $?
