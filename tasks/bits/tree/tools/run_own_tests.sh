#!/usr/bin/env bash
# YOUR test loop. `run_tests` runs this, and the record of a run is built on it.
#
# Your suite is every test target registered in CMakeLists.txt, run by ctest. gtest does
# the asserting; CMake does the discovering; this script only reports what happened.
#
# The exit code is the contract the harness reads, so each code means exactly one thing:
#   0  the tests ran and passed
#   1  the tests ran and failed          -- a RED observation
#   2  the suite could not run at all    -- nothing was observed, so not a RED
#
# A build error is 2: nothing ran. ctest's exit 8 covers BOTH "some tests failed" and "No
# tests were found", so the two cannot be told apart from the code -- the output has to say
# which. tools/ and CMakeLists.txt (above the marked line) are not yours to edit.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

build_dir=.ninny-build

# Configure and build first. A failure here means no test ever ran.
if ! cmake -S . -B "$build_dir" -DCMAKE_BUILD_TYPE=Debug >"$build_dir.log" 2>&1; then
  echo "cmake configure FAILED -- nothing ran:"
  tail -30 "$build_dir.log"
  exit 2
fi
if ! cmake --build "$build_dir" -j 4 >>"$build_dir.log" 2>&1; then
  echo "the build FAILED -- nothing ran:"
  grep -E "error:|Error" "$build_dir.log" | head -20
  exit 2
fi

out=$(ctest --test-dir "$build_dir" --output-on-failure 2>&1)
rc=$?
printf '%s\n' "$out"

# "No tests were found" is a green-looking exit for a suite that asserts nothing.
if printf '%s\n' "$out" | grep -qi "No tests were found"; then
  echo "ctest found no tests at all -- a build that succeeds is not a suite that asserts"
  exit 2
fi

# The count, so the harness records it as a number. ctest prints "N tests failed out of M"
# or "All tests passed (M tests)" -- count the cases it actually ran. A gtest file the
# model forgot to add to CMakeLists.txt is exactly the case this makes visible.
n=$(printf '%s\n' "$out" | grep -oE "out of [0-9]+|\(([0-9]+) tests?\)" | grep -oE "[0-9]+" | head -1)
echo "NINNY_TESTS: ${n:-0}"

if [ "$rc" -ne 0 ]; then
  exit 1
fi
exit 0
