#!/usr/bin/env bash
# Record what each toolchain actually says, so the adapters can be tested without a compiler.
#
# For every task and every state a suite can be in, this runs the task's OWN adapter in a scratch
# copy of its tree and saves the transcript plus the exit code. The states are the four that
# matter, and the first three are the whole point of the contract:
#
#   empty    nothing to run (the tree as shipped)                 -> must be 2
#   red      one planted test that cannot pass                    -> must be 1
#   green    one planted test that passes                         -> must be 0
#   broken   a suite that does not compile                        -> must be 2, never 1
#
# The output files are committed under tests/fixtures/runners/ and are replayed by
# `tests/test_runner_config.py`, which drives the rendered adapter through
# NINNY_RUNNER_REPLAY. Re-run this script when a toolchain is upgraded and read the diff:
# a changed transcript is a changed contract.
#
#   bash tests/fixtures/runners/capture.sh [task ...]
#
# No network, no model, no money. The CMake tasks are the slow ones (~45 s per state).

set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
work=${CAPTURE_WORK:-/tmp/runner-capture}
tasks=${*:-"roman dur intset nasm-sum bits roman-cli"}

capture() {  # capture <task> <state> <code that plants the state>
  local task=$1 state=$2 plant=$3
  local dir="$work/$task/$state"
  rm -rf "$dir"
  mkdir -p "$dir"
  cp -r "$repo/tasks/$task/tree" "$dir/tree"
  rm -rf "$dir/tree/target" "$dir/tree/.ninny-build" "$dir/tree/build"
  ( cd "$dir" && eval "$plant" )
  ( cd "$dir/tree" && bash tools/run_own_tests.sh ) > "$dir/out.txt" 2>&1
  local rc=$?
  {
    echo "# task:   $task"
    echo "# state:  $state"
    echo "# rc:     $rc"
    echo "# what this state is: $4"
    echo "# ---------------------------------------- transcript follows"
    cat "$dir/out.txt"
  } > "$here/$task.$state.txt"
  printf '%-10s %-8s rc=%s\n' "$task" "$state" "$rc"
}

for task in $tasks; do
  case "$task" in
    roman)
      plant_test() { printf 'import unittest\n\nclass P(unittest.TestCase):\n    def test_p(self):\n        self.assertEqual(1, %s)\n' "$1" > "$2"; }
      mkdir -p "$work/roman/_gen"
      capture roman empty  'true'                                          "the tree as shipped: no tests"
      capture roman red    'mkdir -p tree/tests/own; printf "import unittest\n\nclass P(unittest.TestCase):\n    def test_p(self):\n        self.assertEqual(1, 2)\n" > tree/tests/own/test_probe.py' "one planted test that cannot pass"
      capture roman green  'mkdir -p tree/tests/own; printf "import unittest\n\nclass P(unittest.TestCase):\n    def test_p(self):\n        self.assertEqual(1, 1)\n" > tree/tests/own/test_probe.py' "one planted test that passes"
      capture roman broken 'mkdir -p tree/tests/own; printf "import unittest\n\nclass P(unittest.TestCase:\n" > tree/tests/own/test_probe.py' "a suite that does not import"
      ;;
    dur)
      capture dur empty  'true' "the tree as shipped: no tests"
      capture dur red    'mkdir -p tree/tests/own; printf "const test = require(\x27node:test\x27);\nconst assert = require(\x27node:assert\x27);\ntest(\x27p\x27, () => { assert.strictEqual(1, 2); });\n" > tree/tests/own/probe.test.js' "one planted test that cannot pass"
      capture dur green  'mkdir -p tree/tests/own; printf "const test = require(\x27node:test\x27);\nconst assert = require(\x27node:assert\x27);\ntest(\x27p\x27, () => { assert.strictEqual(1, 1); });\n" > tree/tests/own/probe.test.js' "one planted test that passes"
      capture dur emptyish 'mkdir -p tree/tests/own; printf "// a file with no cases at all\n" > tree/tests/own/probe.test.js' "a test FILE with no cases (the count_minus wart)"
      ;;
    intset)
      capture intset empty  'true' "the tree as shipped: no tests"
      capture intset red    'mkdir -p tree/tests/own; printf "#[test]\nfn p() { assert!(1 == 2); }\n" > tree/tests/own/main.rs' "one planted test that cannot pass"
      capture intset green  'mkdir -p tree/tests/own; printf "#[test]\nfn p() { assert!(1 == 1); }\n" > tree/tests/own/main.rs' "one planted test that passes"
      capture intset broken 'mkdir -p tree/tests/own; printf "#[test]\nfn p() { let x: u32 = \x22nope\x22; }\n" > tree/tests/own/main.rs' "a suite that does not compile"
      ;;
    nasm-sum)
      capture nasm-sum empty  'true' "the tree as shipped: no tests"
      capture nasm-sum red    'mkdir -p tree/tests/own; printf "#!/usr/bin/env bash\necho \x22not ok p\x22\nexit 1\n" > tree/tests/own/probe.sh' "one planted case that fails"
      capture nasm-sum green  'mkdir -p tree/tests/own; printf "#!/usr/bin/env bash\necho \x22ok p\x22\nexit 0\n" > tree/tests/own/probe.sh' "one planted case that passes"
      capture nasm-sum broken 'mkdir -p tree/tests/own; printf "#!/usr/bin/env bash\nexit 2\n" > tree/tests/own/probe.sh' "a test script that could not run at all"
      ;;
    bits)
      capture bits empty  'true' "the tree as shipped: no tests"
      capture bits red    'mkdir -p tree/tests/own; printf "#include <gtest/gtest.h>\nTEST(P, P) { EXPECT_EQ(1, 2); }\n" > tree/tests/own/probe_test.cpp; printf "\nadd_executable(own_probe tests/own/probe_test.cpp)\ntarget_link_libraries(own_probe PRIVATE bits GTest::gtest_main)\ngtest_discover_tests(own_probe)\n" >> tree/CMakeLists.txt' "one planted test that cannot pass"
      capture bits green  'mkdir -p tree/tests/own; printf "#include <gtest/gtest.h>\nTEST(P, P) { EXPECT_EQ(1, 1); }\n" > tree/tests/own/probe_test.cpp; printf "\nadd_executable(own_probe tests/own/probe_test.cpp)\ntarget_link_libraries(own_probe PRIVATE bits GTest::gtest_main)\ngtest_discover_tests(own_probe)\n" >> tree/CMakeLists.txt' "one planted test that passes"
      capture bits broken 'mkdir -p tree/tests/own; printf "#include <gtest/gtest.h>\nTEST(P, P) { this is not c++ }\n" > tree/tests/own/probe_test.cpp; printf "\nadd_executable(own_probe tests/own/probe_test.cpp)\ntarget_link_libraries(own_probe PRIVATE bits GTest::gtest_main)\ngtest_discover_tests(own_probe)\n" >> tree/CMakeLists.txt' "a suite that does not compile"
      ;;
    roman-cli)
      capture roman-cli empty  'true' "the tree as shipped: no tests"
      capture roman-cli red    'mkdir -p tree/tests/own; printf "#include \x22../harness.hpp\x22\nTEST(P) { CHECK_EQ(1, 2); }\nFROZEN_TEST_MAIN(\x22PROBE\x22)\n" > tree/tests/own/probe_test.cpp' "one planted test that cannot pass"
      capture roman-cli green  'mkdir -p tree/tests/own; printf "#include \x22../harness.hpp\x22\nTEST(P) { CHECK_EQ(1, 1); }\nFROZEN_TEST_MAIN(\x22PROBE\x22)\n" > tree/tests/own/probe_test.cpp' "one planted test that passes"
      capture roman-cli broken 'mkdir -p tree/tests/own; printf "#include \x22../harness.hpp\x22\nTEST(P) { this is not c++ }\nFROZEN_TEST_MAIN(\x22PROBE\x22)\n" > tree/tests/own/probe_test.cpp' "a suite that does not compile"
      ;;
  esac
done

echo
echo "fixtures written to $here"
echo "read the rc column: empty/broken must be 2, red 1, green 0."
