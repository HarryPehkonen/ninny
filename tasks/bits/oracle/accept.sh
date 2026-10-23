#!/usr/bin/env bash
# The oracle for the bits task. It runs OUTSIDE the agent's tree: `ninny check` stages the
# submission beside this directory and hands the path in as NINNY_TREE.
#
# Three things: the frozen files are unchanged, the submission's own suite exists and
# passes (so the library is actually tested, not just built), and a corpus of its own
# written as gtest and compiled against the submission's header.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TREE=${NINNY_TREE:?the harness must set NINNY_TREE to the staged tree}
cd "$TREE" || exit 1
failures=0
checks=0
fail() { failures=$((failures + 1)); echo "FAIL $*"; }
pass() { checks=$((checks + 1)); echo "ok   $*"; }

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

# 2. The submission's own suite must build and pass. A library that only builds is a
#    library nobody checked.
build_dir=$TREE/.ninny-build-oracle
if ! cmake -S . -B "$build_dir" -DCMAKE_BUILD_TYPE=Debug >"$build_dir.log" 2>&1; then
  fail "the submission's CMake configure failed"
else
  if ! cmake --build "$build_dir" -j 4 >>"$build_dir.log" 2>&1; then
    fail "the submission's own tests do not build"
  else
    out=$(ctest --test-dir "$build_dir" --output-on-failure 2>&1)
    if [ $? -ne 0 ] || printf '%s\n' "$out" | grep -qi "No tests were found"; then
      fail "the submission's own tests do not pass"
      printf '%s\n' "$out" | grep -E "Failed|error" | head -10
    else
      pass "the submission's own tests build and pass"
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
    out=$(ctest --test-dir "$build_dir" --output-on-failure -R ninny_acceptance 2>&1)
    if [ $? -ne 0 ]; then
      fail "the acceptance corpus fails against this submission"
      printf '%s\n' "$out" | grep -E "Failed|Failure" | head -12
    else
      pass "the acceptance corpus builds and passes"
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
