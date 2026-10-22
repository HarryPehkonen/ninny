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
  exit 1
fi

exit "$status"
