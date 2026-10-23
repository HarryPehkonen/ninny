#!/usr/bin/env bash
# YOUR test loop. `run_tests` runs this, and the record of a run is built on it.
#
# It configures and builds the `own_tests` target from the frozen CMakeLists.txt and runs
# it. Your suite is every tests/own/*.cpp, compiled together with every src/*.cpp.
#
# The exit code is the contract the harness reads, so each code means exactly one thing:
#   0  the tests ran and passed
#   1  the tests ran and failed          -- a RED observation
#   2  the suite could not run at all    -- nothing was observed, so not a RED
#
# That is why a configure failure and a build failure are both 2: nothing ran. tools/ and
# CMakeLists.txt are not yours to edit.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

if ! ls tests/own/*.cpp >/dev/null 2>&1; then
  echo "no tests in tests/own/*.cpp -- there is nothing to run yet."
  echo "Write one case that fails because the behaviour is not there, then run it."
  exit 2
fi

mkdir -p build

if ! cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug > build/configure.log 2>&1; then
  tail -20 build/configure.log
  echo
  echo "CONFIGURE FAILED -- nothing was built and nothing ran, so this is exit code 2"
  echo "rather than 1. A broken build is not a RED."
  exit 2
fi

if ! cmake --build build --target own_tests 2>&1; then
  echo
  echo "BUILD FAILED -- the suite did not compile, so nothing ran and nothing was observed."
  echo "A build error is not a RED, and exit code 2 is how this script says so."
  exit 2
fi

out=$(./build/own_tests 2>&1)
rc=$?
printf '%s\n' "$out"

# Anti-vacuous and label-agnostic on purpose: the harness prints "<label>: N checked,
# M failed" whatever label the author chose, so require exit 0 AND at least one check
# actually reported. A count of zero is the same finding as no count at all: "0 checked,
# 0 failed" is a suite that asserts nothing, and a pass it did not earn.
n=$(printf '%s\n' "$out" | sed -n 's/.*: \([0-9][0-9]*\) checked, [0-9][0-9]* failed.*/\1/p' | head -1)
if [ "$rc" -eq 0 ] && { [ -z "$n" ] || [ "$n" -eq 0 ]; }; then
  echo "the suite reported no checks at all -- a vacuous run is not a pass"
  exit 2
fi
exit "$rc"
