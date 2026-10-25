#!/usr/bin/env bash
# The oracle for the cron task. It runs OUTSIDE the agent's tree: `ninny check` stages
# the submission beside this directory and hands the path over in NINNY_TREE. Nothing
# here is readable from inside the tree.
#
# Two directions, and both matter: the frozen instrument must be unchanged, and the
# submission must compile and pass the acceptance corpus. Exit 0 only when both hold.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tree="${NINNY_TREE:?NINNY_TREE must point at the staged submission}"
work=$(mktemp -d) || exit 2
trap 'rm -rf "$work"' EXIT

# 1. the instrument is untouched: the frozen contract and the test harness, byte for byte
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

# 2. the submission compiles, with the warnings the spec froze
if ! g++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -I"$tree/include" \
      "$here/tests/acceptance/cron_acceptance.cpp" "$tree"/src/*.cpp -o "$work/accept"; then
  echo "ORACLE FAILED: the submission does not compile against the frozen contract"
  exit 1
fi
echo "build     acceptance binary built"

# 3. and it passes, judged by the corpus rather than by anything the agent wrote
"$work/accept" > "$work/accept.log" 2>&1
rc=$?
tail -3 "$work/accept.log"
if [ "$rc" -ne 0 ] || ! grep -q "ACCEPTANCE PASSED" "$work/accept.log"; then
  echo "ORACLE FAILED: acceptance did not pass"
  exit 1
fi
echo "accept    ACCEPTANCE PASSED"
exit 0
