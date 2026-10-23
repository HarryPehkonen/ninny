#!/usr/bin/env bash
# The oracle for the nasm-sum task. It runs OUTSIDE the agent's tree: `ninny check` stages
# the submission beside this directory and hands the path over in NINNY_TREE.
#
# The program prints nothing, so there is nothing to compare but the exit status -- which
# is the whole interface, and therefore the whole corpus.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tree="${NINNY_TREE:?NINNY_TREE must point at the staged submission}"

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

if ! build=$(cd "$tree" && make 2>&1); then
  printf '%s\n' "$build" | tail -10
  echo "ORACLE FAILED: the program does not build"
  exit 1
fi
binary="$tree/build/sum"
if [ ! -x "$binary" ]; then
  echo "ORACLE FAILED: no executable at build/sum"
  exit 1
fi
echo "build     assembled and linked"

checks=0
failures=0

# <expected exit code> <what> <args...>
expect() {
  want="$1"
  shift
  what="$1"
  shift
  checks=$((checks + 1))
  out=$("$binary" "$@" 2>&1)
  got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL $what -> exit $got (wanted $want)"
    failures=$((failures + 1))
  fi
  if [ -n "$out" ]; then
    echo "FAIL $what -> printed something, and the contract says silence: $(printf '%s' "$out" | head -c 60)"
    failures=$((failures + 1))
  fi
}

# The examples from the spec.
expect 5   "2 + 3" 2 3
expect 0   "0 + 0" 0 0
expect 200 "100 + 100" 100 100
expect 2   "5x is not a number" 5x 1

# The boundaries, which are the interesting part.
expect 0   "0 + 0, again, at the bottom" 0 0
expect 127 "0 + 127" 0 127
expect 127 "127 + 0" 127 0
expect 254 "127 + 127" 127 127
expect 2   "128 is out of range, so this is a refusal" 127 128
expect 2   "128 alone" 128 0
expect 2   "999 alone" 999 0
expect 2   "a huge value" 99999999999999999999 0

# Forms of the same number.
expect 7   "leading zeros are fine" 007 0
expect 7   "and on the right" 0 0007
expect 2   "a sign is not a digit" +1 2
expect 2   "nor is a minus" -1 2
expect 2   "a space is not a digit" " 1" 2
expect 2   "nor a trailing space" "1 " 2
expect 2   "an empty argument" "" 2
expect 2   "a decimal point" 1.0 2
expect 2   "hex is not decimal" 0x10 2
expect 2   "letters" abc def
expect 2   "unicode digits are not ASCII digits" "١" 0

# The argument count.
expect 2   "no arguments"
expect 2   "one argument" 1
expect 2   "three arguments" 1 2 3

# The property: every pair in range, and nothing outside it.
for a in 0 1 2 3 63 64 65 100 126 127; do
  for b in 0 1 2 3 63 64 65 100 126 127; do
    expect $(( (a + b) & 255 )) "a property: $a + $b" "$a" "$b"
  done
done

echo
echo "ACCEPTANCE: $checks checked, $failures failed"
if [ "$failures" -eq 0 ] && [ "$checks" -gt 0 ]; then
  echo "ACCEPTANCE PASSED"
  exit 0
fi
echo "ACCEPTANCE FAILED"
exit 1
