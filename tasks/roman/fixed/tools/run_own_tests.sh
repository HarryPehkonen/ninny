#!/usr/bin/env bash
# Run the agent's own tests from tests/own/.
#
# This script FAILS when there are no tests, on purpose. "No tests" is not "tests
# passed", and a suite that passes vacuously would let a run claim a RED
# observation it never had. The harness counts a non-zero exit here as the RED
# event, so a vacuous pass would corrupt the test-first record.
#
# tools/ is not the agent's to edit.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

output=$(python3 -m unittest discover -s tests/own -t . -v 2>&1)
status=$?
echo "$output"

if printf '%s\n' "$output" | grep -qE '^Ran 0 tests'; then
  echo
  echo "FAIL: no tests were found under tests/own/ -- this counts as a failure,"
  echo "      not as a pass. Write a test first."
  # 2 is the contract's "the suite could not run": nothing was observed, so this is
  # not a RED observation either. 1 is reserved for tests that ran and failed.
  exit 2
fi

# No summary line at all means the suite never got as far as running -- an import or
# collection error. That is not a test failure either, and calling it one would let a
# broken suite masquerade as a RED observation.
if ! printf '%s\n' "$output" | grep -qE '^Ran [0-9]+ tests?'; then
  echo
  echo "the suite did not run: no test summary was printed, so nothing was observed."
  echo "Fix the suite until it runs, then read its failure."
  exit 2
fi

exit "$status"
