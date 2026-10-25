#!/usr/bin/env bash
# The oracle for the jsonptr task. It runs OUTSIDE the agent's tree: `ninny check` stages the
# submission beside this directory and hands the path over in NINNY_TREE.
#
# Two things, in this order:
#   1. the frozen instrument -- the command line, the runner, the suite's README. A submission that
#      edited them is not being graded on the contract, so it is not graded at all;
#   2. the corpus, in oracle/accept.js.
#
# Exit 0 when the submission behaves, 1 when it does not, 2 when nothing could be run.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
tree=${NINNY_TREE:-}
if [ -z "$tree" ]; then
  echo "oracle: NINNY_TREE is not set" >&2
  exit 2
fi

if [ -f "$here/frozen.sha256" ]; then
  if ! (cd "$tree" && sha256sum --check --quiet "$here/frozen.sha256"); then
    echo "ACCEPTANCE: the frozen files are not the ones the task shipped"
    echo "GATE FAILED"
    exit 1
  fi
fi

node "$here/accept.js" "$tree"
rc=$?

if [ "$rc" -eq 0 ]; then
  echo "GATE PASSED"
else
  echo "GATE FAILED"
fi
exit "$rc"
