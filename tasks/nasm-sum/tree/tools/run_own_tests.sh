#!/usr/bin/env bash
# YOUR test loop. `run_tests` runs this, and the record of a run is built on it.
#
#   * `make` builds build/sum. A build failure is exit 2: nothing ran, so nothing was
#     observed, and a build error is not a RED.
#   * every tests/own/*.sh is run. Each prints "ok <what>" or "not ok <what>" per case and
#     exits 0 (all passed), 1 (any failed) or 2+ (could not run).
#
# The exit code is the contract the harness reads, so each code means exactly one thing:
#   0  the cases ran and passed
#   1  the cases ran and failed          -- a RED observation
#   2  nothing could run                 -- a build error, or a suite that ran no case
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

if ! ls tests/own/*.sh >/dev/null 2>&1; then
  echo "no tests/own/*.sh yet -- nothing to run."
  echo "Write one case that fails because the behaviour is not there, then run it."
  exit 2
fi

build=$(make 2>&1)
build_rc=$?
printf '%s\n' "$build"
if [ "$build_rc" -ne 0 ]; then
  echo "BUILD FAILED -- the program did not assemble, so nothing ran. A build error is not"
  echo "a RED, and exit code 2 is how this script says so."
  exit 2
fi

checks=0
failures=0
unrunnable=0

for test_script in tests/own/*.sh; do
  echo "--- $test_script"
  out=$(bash "$test_script" 2>&1)
  rc=$?
  printf '%s\n' "$out"

  n_ok=$(printf '%s\n' "$out" | grep -cE '^ok ')
  n_bad=$(printf '%s\n' "$out" | grep -cE '^not ok ')
  checks=$((checks + n_ok + n_bad))
  failures=$((failures + n_bad))

  if [ "$rc" -ge 2 ]; then
    unrunnable=$((unrunnable + 1))
  elif [ "$rc" -eq 1 ] && [ "$n_bad" -eq 0 ]; then
    # It said it failed without saying which case failed. That is a result too.
    failures=$((failures + 1))
    echo "not ok $test_script exited 1 without naming a failing case"
  fi
done

echo
echo "OWN: $checks checked, $failures failed"
# The count as a number on its own line: the harness records it so a suite that shrinks
# without failing leaves a trace. Same convention as the other tasks' runners.
echo "NINNY_TESTS: $checks"

if [ "$unrunnable" -gt 0 ]; then
  echo "a test script could not run at all -- nothing it meant to check was observed"
  exit 2
fi
if [ "$checks" -eq 0 ]; then
  echo "no test cases ran at all -- a build that succeeds is not a suite that asserts"
  exit 2
fi
if [ "$failures" -gt 0 ]; then
  exit 1
fi
exit 0
