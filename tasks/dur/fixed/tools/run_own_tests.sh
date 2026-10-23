#!/usr/bin/env bash
# YOUR test loop. `run_tests` runs this, and the record of a run is built on it.
#
# Your suite is every tests/own/*.test.js, run by Node's built-in runner.
#
# The exit code is the contract the harness reads, so each code means exactly one thing:
#   0  the tests ran and passed
#   1  the tests ran and failed          -- a RED observation
#   2  the suite could not run at all    -- nothing was observed, so not a RED
#
# tools/ and src/cli.js are not yours to edit.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

if ! ls tests/own/*.test.js >/dev/null 2>&1; then
  echo "no tests in tests/own/*.test.js -- there is nothing to run yet."
  echo "Write one case that fails because the behaviour is not there, then run it."
  exit 2
fi

out=$(node --test --test-reporter=tap tests/own/ 2>&1)
rc=$?
printf '%s\n' "$out"

# Counting is not as simple as it looks, and the summary cannot be taken at face value: a
# test file holding nothing but a comment reports "# tests 1, # pass 1", exit 0 -- a green
# run that asserted nothing. Measured against Node 20 and 26: a file whose cases all ran
# contributes its cases, while a file with no cases contributes ITSELF, as an entry named by
# its path. So subtract the entries whose name is a path; those are exactly the files that
# asserted nothing.
total=$(printf '%s\n' "$out" | sed -n 's/^# tests \([0-9][0-9]*\)$/\1/p' | tail -1)
files=$(printf '%s\n' "$out" | grep -cE '^(not )?ok [0-9]+ - .*(/|\.js)$' || true)
n=$(( ${total:-0} - ${files:-0} ))
# The case count on a line of its own, so the harness records it as a number. A suite that
# shrank asserts less without failing, and this is the only evidence of it.
echo "NINNY_TESTS: ${n:-0}"
if [ "$rc" -eq 0 ] && [ "${n:-0}" -eq 0 ]; then
  echo "the suite ran no test cases at all -- a file that loads is not a suite that asserts"
  exit 2
fi
exit "$rc"
