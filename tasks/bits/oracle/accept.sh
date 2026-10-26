#!/usr/bin/env bash
# The oracle for the bits task. It runs OUTSIDE the agent's tree: `ninny check` stages the
# submission beside this directory and hands the path in as NINNY_TREE.
#
# Three things: the frozen files are unchanged, the colour of the submission's own suite
# (recorded, never graded -- see below), and a corpus of its own written as gtest and
# compiled against the submission's header.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TREE=${NINNY_TREE:?the harness must set NINNY_TREE to the staged tree}
cd "$TREE" || exit 1
failures=0
checks=0
fail() { failures=$((failures + 1)); echo "FAIL $*"; }
pass() { checks=$((checks + 1)); echo "ok   $*"; }
# A recorded observation is not a check. It reports something a reader needs and grades
# nothing -- the distinction the `bits` task got wrong, and paid for three times.
note() { echo "note $*"; }

# 1. The frozen instrument did not move. CMakeLists.txt is deliberately NOT hashed: the
#    corpus appends its own target to it below, and only the "YOUR TESTS" region is the
#    model's to edit.
if [ -f "$HERE/frozen.sha256" ]; then
  while read -r want path; do
    [ -n "$want" ] || continue
    got=$(sha256sum "$path" 2>/dev/null | cut -d' ' -f1)
    if [ "$want" = "$got" ]; then pass "frozen: $path"; else fail "frozen file changed: $path"; fi
  done < "$HERE/frozen.sha256"
fi

# 1b. The frozen region of CMakeLists.txt. It cannot be hashed whole -- adding a target per
#     test file is the task -- so the region ends at the marker, and the file's own header is
#     what says so. A missing marker hashes the whole file and fails with it.
if [ -f "$HERE/frozen-cmake.sha256" ]; then
  want=$(grep -v '^#' "$HERE/frozen-cmake.sha256" | head -1 | tr -d '[:space:]')
  got=$(awk '/YOUR TESTS BELOW HERE/{print; exit} {print}' CMakeLists.txt | sha256sum | cut -d' ' -f1)
  if [ "$want" = "$got" ]; then
    pass "frozen: CMakeLists.txt above the marker"
  else
    fail "CMakeLists.txt above the marker was edited, or the marker removed"
  fi
fi

# 2. The colour of the submission's own suite: RECORDED, not graded.
#
#    This used to be a failure, and it failed correct code three times. Once a suite has gone
#    red the seal forbids repairing it, so a model that wrote one wrong assertion -- a boundary
#    guard, say -- can never reach green again however right its implementation is. All three
#    arms had an implementation the acceptance corpus passed. The corpus below decides; this
#    line is what a reader needs in order to know how the handback looked.
build_dir=$TREE/.ninny-build-oracle
if ! cmake -S . -B "$build_dir" -DCMAKE_BUILD_TYPE=Debug >"$build_dir.log" 2>&1; then
  note "shipped suite: the submission's CMake configure failed"
else
  if ! cmake --build "$build_dir" -j 4 >>"$build_dir.log" 2>&1; then
    note "shipped suite: does not build"
  else
    out=$(ctest --test-dir "$build_dir" --output-on-failure 2>&1)
    if [ $? -ne 0 ] || printf '%s\n' "$out" | grep -qi "No tests were found"; then
      note "shipped suite: builds, does not pass"
      printf '%s\n' "$out" | grep -E "Failed|error" | head -10
    else
      pass "shipped suite: builds and passes"
    fi
  fi
fi

# 3. The acceptance corpus: its own gtest, compiled against the submission's header.
#
#    It has to build in the submission's own CMake project, not a fresh one: the project
#    sets up the `bits` include directory relative to its source dir, so re-running
#    `project()` elsewhere finds no headers. The target is therefore appended to a BACKUP
#    copy of CMakeLists.txt and restored afterwards -- the staged tree is throwaway, but a
#    submission that failed should not be left modified for a reader to puzzle over.
cp CMakeLists.txt "$TREE/.CMakeLists.txt.ninny-backup"
cp "$HERE/acceptance.cpp" "$TREE/.ninny-acceptance.cpp"
printf '\nadd_executable(ninny_acceptance ${CMAKE_CURRENT_SOURCE_DIR}/.ninny-acceptance.cpp)\ntarget_link_libraries(ninny_acceptance PRIVATE bits GTest::gtest_main)\ngtest_discover_tests(ninny_acceptance)\n' >> CMakeLists.txt
build_dir=$TREE/.ninny-accept-build
rm -rf "$build_dir"
if ! cmake -S . -B "$build_dir" -DCMAKE_BUILD_TYPE=Debug >"$build_dir.log" 2>&1; then
  fail "the acceptance corpus does not configure against this submission"
else
  if ! cmake --build "$build_dir" -j 4 >>"$build_dir.log" 2>&1; then
    fail "the acceptance corpus does not compile against this submission"
    grep -E "error:" "$build_dir.log" | head -10
  else
    #    Run the corpus's own binary, NOT `ctest -R ninny_acceptance`. gtest discovery
    #    registers nothing under this project, and `ctest` exits 0 saying "No tests were
    #    found!!!" -- which this check read as a pass for the whole campaign, in every tree
    #    including the answer key, until the day check 2 stopped failing first and the
    #    answer-key control caught it. The count is asserted against the corpus source as
    #    well, so it cannot shrink in silence: the same anti-vacuous rule a task applies to
    #    the model's suite.
    want=$(grep -cE '^(TEST|TEST_F|TEST_P)\(' "$HERE/acceptance.cpp")
    out=$("$build_dir/ninny_acceptance" --gtest_color=no 2>&1)
    rc=$?
    ran=$(printf '%s\n' "$out" | sed -n 's/^\[==========\] \([0-9][0-9]*\) tests\? from .*/\1/p' | tail -1)
    if [ "$rc" -ne 0 ]; then
      fail "the acceptance corpus fails against this submission"
      printf '%s\n' "$out" | grep -E "^\[  FAILED  \]" | head -12
    elif [ -z "$ran" ] || [ "$ran" -ne "$want" ]; then
      fail "the acceptance corpus ran ${ran:-no} tests, expected $want -- it did not grade"
    else
      pass "the acceptance corpus ran $ran tests, all passed"
    fi
  fi
fi
mv "$TREE/.CMakeLists.txt.ninny-backup" CMakeLists.txt

echo
echo "ACCEPTANCE: $checks checked, $failures failed"
if [ "$failures" -eq 0 ] && [ "$checks" -gt 0 ]; then
  echo "ACCEPTANCE PASSED"
  exit 0
fi
echo "ACCEPTANCE FAILED"
exit 1
