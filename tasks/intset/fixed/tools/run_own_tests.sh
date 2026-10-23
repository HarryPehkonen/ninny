#!/usr/bin/env bash
# YOUR test loop. `run_tests` runs this, and the record of a run is built on it.
#
# Your suite is every tests/own/*.rs, run by `cargo test` -- which also runs any unit tests
# inside src/lib.rs, so both places work, but the record counts tests/own/.
#
# The exit code is the contract the harness reads, so each code means exactly one thing:
#   0  the tests ran and passed
#   1  the tests ran and failed          -- a RED observation
#   2  the suite could not run at all    -- nothing was observed, so not a RED
#
# Cargo does not speak this contract: it exits 101 for a compile error AND for a failing
# test, so this script tells those apart rather than passing Cargo's status through.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

if ! ls tests/own/*.rs >/dev/null 2>&1 && ! grep -q '#\[test\]' src/lib.rs 2>/dev/null; then
  echo "no tests in tests/own/*.rs and no #[test] in src/lib.rs -- nothing to run yet."
  echo "Write one case that fails because the behaviour is not there, then run it."
  exit 2
fi

out=$(cargo test --offline --color never 2>&1)
rc=$?
printf '%s\n' "$out"

# A compile error is not a RED: nothing ran, so nothing was observed.
if printf '%s\n' "$out" | grep -qE "^error(\[E[0-9]+\])?:|^error\[E[0-9]+\]"; then
  echo
  echo "BUILD FAILED -- the suite did not compile, so nothing ran. A build error is not a"
  echo "RED, and exit code 2 is how this script says so."
  exit 2
fi

# "test result: ok. 0 passed" is a green run, so the number of cases that actually ran is
# the only evidence the suite asserted anything. Sum it across every target Cargo built.
passed=$(printf '%s\n' "$out" | sed -n 's/^test result: .* \([0-9][0-9]*\) passed;.*/\1/p' | awk '{total += $1} END {print total + 0}')
if [ "$rc" -eq 0 ] && [ "${passed:-0}" -eq 0 ]; then
  echo "no test cases ran at all -- a crate that builds is not a suite that asserts"
  exit 2
fi

if [ "$rc" -ne 0 ]; then
  exit 1
fi
exit 0
