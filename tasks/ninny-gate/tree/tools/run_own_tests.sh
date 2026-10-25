#!/usr/bin/env bash
# The agent's own test loop: ninny's whole suite, plus whatever the agent adds.
#
# It fails when the suite is empty, because "no tests" is not "tests passed" and a
# vacuous pass would let a run claim a RED observation it never had.
#
# tools/ is not the agent's to edit.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

output=$(python3 -m unittest discover -s tests -t . 2>&1)
status=$?
echo "$output"

if printf '%s\n' "$output" | grep -qE '^Ran 0 tests'; then
  echo
  echo "FAIL: no tests were found -- this counts as a failure, not as a pass."
  # 2 is the contract's "the suite could not run": nothing was observed, so this is
  # not a RED observation. 1 is reserved for tests that ran and failed.
  exit 2
fi

# No summary line at all means the suite never got as far as running -- an import or
# collection error. That is not a test failure, and calling it one would let a broken
# suite masquerade as a RED observation.
if ! printf '%s\n' "$output" | grep -qE '^Ran [1-9][0-9]* tests?'; then
  echo
  echo "the suite did not run: no test summary was printed, so nothing was observed."
  echo "Fix the suite until it runs, then read its failure."
  exit 2
fi

exit "$status"
