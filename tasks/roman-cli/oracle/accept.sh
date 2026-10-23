#!/usr/bin/env bash
# The oracle for the roman-cli task. It runs OUTSIDE the agent's tree: `ninny check`
# stages the submission beside this directory and hands the path over in NINNY_TREE.
# Nothing here is readable from inside the tree.
#
# Four directions, and all of them matter: the frozen instrument must be unchanged, the
# library must satisfy the corpus, the project must build the way it says it builds, and
# the binary a user actually runs must behave. Exit 0 only when every one of them holds.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tree="${NINNY_TREE:?NINNY_TREE must point at the staged submission}"
work=$(mktemp -d) || exit 2
trap 'rm -rf "$work"' EXIT

# 1. the instrument is untouched: the frozen contract, the CLI, the build and the harness
bad=0
while read -r want path; do
  got=$(sha256sum "$tree/$path" 2>/dev/null | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then
    echo "FROZEN FILE MOVED: $path"
    [ -n "$got" ] || echo "  (missing entirely)"
    bad=1
  fi
done < "$here/frozen.sha256"
if [ "$bad" -ne 0 ]; then
  echo "ORACLE FAILED: the submission edited the instrument that measures it"
  exit 1
fi
echo "frozen    every frozen file is unchanged"

# 2. the library, judged by the corpus rather than by anything the agent wrote
if ! g++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -I"$tree/include" -I"$here" \
      "$here/accept.cpp" "$tree/src/romanx.cpp" -o "$work/accept"; then
  echo "ORACLE FAILED: the submission does not compile against the frozen contract"
  exit 1
fi
"$work/accept" > "$work/library.log" 2>&1
rc=$?
tail -2 "$work/library.log"

# 3. the project builds itself, through the build system it ships
if ! cmake -S "$tree" -B "$work/build" > "$work/cmake.log" 2>&1; then
  tail -15 "$work/cmake.log"
  echo "ORACLE FAILED: the frozen build does not configure"
  exit 1
fi
if ! cmake --build "$work/build" --target roman > "$work/build.log" 2>&1; then
  tail -20 "$work/build.log"
  echo "ORACLE FAILED: the command line target does not build"
  exit 1
fi
roman="$work/build/roman"
echo "build     the roman target built through CMake"

# 4. the command line itself, which is what makes it a tool rather than a header
cli_checks=0
cli_failed=0
check_cli() {  # <expected exit> <expected stdout> <args...>
  want_rc="$1"
  want_out="$2"
  shift 2
  cli_checks=$((cli_checks + 1))
  got_out=$("$roman" "$@" 2>/dev/null)
  got_rc=$?
  if [ "$got_rc" -ne "$want_rc" ] || [ "$got_out" != "$want_out" ]; then
    echo "FAIL cli roman $* -> exit $got_rc stdout '$got_out' (wanted exit $want_rc '$want_out')"
    cli_failed=$((cli_failed + 1))
  fi
}

check_cli 0 "I"           to-roman 1
check_cli 0 "IV"          to-roman 4
check_cli 0 "MCMLXXXVII"  to-roman 1987
check_cli 0 "MMMCMXCIX"   to-roman 3999
check_cli 0 "3999"        to-number MMMCMXCIX
check_cli 0 "1987"        to-number MCMLXXXVII
check_cli 0 "1"           to-number I
check_cli 1 ""            to-roman 0
check_cli 1 ""            to-roman 4000
check_cli 1 ""            to-roman twelve
check_cli 1 ""            to-number IIII
check_cli 1 ""            to-number ix
check_cli 1 ""            to-number ""
check_cli 2 ""            to-roman
check_cli 2 ""
check_cli 2 ""            nonsense 12
echo "cli       $cli_checks checks, $cli_failed failed"

lib_checks=$(sed -n 's/.*: \([0-9][0-9]*\) checked, .*/\1/p' "$work/library.log" | head -1)
lib_failed=$(sed -n 's/.*: [0-9][0-9]* checked, \([0-9][0-9]*\) failed.*/\1/p' "$work/library.log" | head -1)
total=$(( ${lib_checks:-0} + cli_checks ))
failed=$(( ${lib_failed:-1} + cli_failed ))
echo
echo "ACCEPTANCE: $total checked, $failed failed"
if [ "$rc" -eq 0 ] && [ "$failed" -eq 0 ] && [ "$total" -gt 0 ]; then
  echo "ACCEPTANCE PASSED"
  exit 0
fi
echo "ACCEPTANCE FAILED"
exit 1
