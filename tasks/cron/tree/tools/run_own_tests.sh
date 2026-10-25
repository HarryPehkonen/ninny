#!/usr/bin/env bash
# YOUR test loop. `run_tests` runs this, and the record of this run is built on it:
# a non-zero exit here is a RED observation, not a guess at shell history.
#
# The acceptance corpus is NOT in this tree. Do not go looking for an answer key --
# write the cases you would want to defend, and watch them fail first.
#
# Your suite is every tests/own/*.cpp, compiled together with every src/*.cpp.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

STD="-std=c++17"
WARN="-Wall -Wextra -Wpedantic -Werror"
INC="-Iinclude -Itests"
mkdir -p build

if ! ls tests/own/*.cpp >/dev/null 2>&1; then
  echo "no tests in tests/own/*.cpp -- there is nothing to run yet."
  echo "Start with one case that fails because the behaviour is not there, then run it."
  exit 2
fi

if ! g++ $STD $WARN $INC src/*.cpp tests/own/*.cpp -o build/own 2>&1; then
  echo
  echo "BUILD FAILED -- the suite did not compile, so nothing ran and nothing was"
  echo "observed. A build error is not a RED. In C++ the fix is a stub: declare each"
  echo "function with its frozen signature and return a placeholder, so the case"
  echo "compiles and fails on its CHECK instead."
  # The exit code is the contract Ninny reads, not these words: 2 means "the suite
  # could not run, so nothing was observed", 1 means "the tests ran and then failed".
  # A build error is the first kind. Exiting 1 here is what made a live run's build
  # error the RED it was then reported red-first off.
  exit 2
fi

out=$(./build/own 2>&1)
rc=$?
printf '%s\n' "$out"

# Anti-vacuous, and label-agnostic on purpose: the harness prints
# "<label>: N checked, M failed" whatever label the author chose, so require an exit
# code of 0 AND at least one check actually reported. A suite that ran nothing is not
# a pass, and the author's suite label is not part of the contract.
n=$(printf '%s\n' "$out" | sed -n 's/.*: \([0-9][0-9]*\) checked, [0-9][0-9]* failed.*/\1/p' | head -1)
if [ "$rc" -eq 0 ] && { [ -z "$n" ] || [ "$n" -eq 0 ]; }; then
  echo "the suite reported no checks at all -- a vacuous run is not a pass"
  # Nothing was observed, which is the contract's second code, not a failure.
  exit 2
fi
exit "$rc"
