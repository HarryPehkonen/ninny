#!/usr/bin/env bash
# The oracle for the intset task. It runs OUTSIDE the agent's tree: `ninny check` stages the
# submission beside this directory and hands the path over in NINNY_TREE.
#
# Four directions: the frozen instrument is unchanged, the library passes an acceptance
# test injected into the crate, the crate builds, and the binary a user runs behaves.
#
# The acceptance test is a Rust integration test written INTO the staged copy, so it can
# call the library API directly rather than only through the CLI. The staged tree is a copy
# -- `ninny check` made it -- so writing there touches nothing the agent produced.
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
# An empty manifest would check nothing and then print the same reassuring line: the vacuous
# pass this project exists to refuse. Measured -- the file was emptied by a stray redirect and
# the oracle still reported "every frozen file is unchanged".
entries=$(grep -c . "$here/frozen.sha256" 2>/dev/null || true)
if [ "${entries:-0}" -lt 1 ]; then
  echo "ORACLE FAILED: frozen.sha256 lists no files, so nothing was checked"
  exit 1
fi
if [ "$bad" -ne 0 ]; then
  echo "ORACLE FAILED: the submission edited the instrument that measures it"
  exit 1
fi
echo "frozen    every frozen file is unchanged"

mkdir -p "$tree/tests"
cp "$here/acceptance.rs" "$tree/tests/acceptance.rs"

cd "$tree" || exit 2
out=$(cargo test --offline --color never --test acceptance 2>&1)
rc=$?
printf '%s\n' "$out" | tail -25

passed=$(printf '%s\n' "$out" | sed -n 's/^test result: .* \([0-9][0-9]*\) passed;.*/\1/p' | head -1)
failed=$(printf '%s\n' "$out" | sed -n 's/^test result: .* [0-9][0-9]* passed; \([0-9][0-9]*\) failed.*/\1/p' | head -1)
rm -f "$tree/tests/acceptance.rs"

if [ "${passed:-0}" -eq 0 ] && [ "${failed:-0}" -eq 0 ]; then
  echo "ORACLE FAILED: the acceptance test did not run at all"
  exit 1
fi
echo "library   the acceptance test ran"
if [ "$rc" -ne 0 ] || [ "${failed:-0}" -ne 0 ]; then
  echo "ORACLE FAILED: the acceptance test did not pass"
  exit 1
fi

# The binary, which is what makes it a tool rather than a library.
if ! cargo build --offline --color never --quiet >/dev/null 2>&1; then
  echo "ORACLE FAILED: the crate does not build the binary"
  exit 1
fi
roman="$tree/target/debug/intset"
echo "build     the binary built through cargo"

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
    echo "FAIL cli intset $* -> exit $got_rc stdout '$got_out' (wanted exit $want_rc '$want_out')"
    cli_failed=$((cli_failed + 1))
  fi
}

check_cli 0 "1-5,7,9-10"   normalize "1-3,7,9-10,3-5"
check_cli 0 "0"            normalize "0"
check_cli 0 "4294967295"   normalize "4294967295"
check_cli 0 "yes"          has "1-5" 3
check_cli 0 "no"           has "1-5" 6
check_cli 0 "1-5,7"        add "1-5" 7
check_cli 1 ""             normalize ""
check_cli 1 ""             normalize "11-9"
check_cli 1 ""             normalize "1,,2"
check_cli 1 ""             normalize "1-"
check_cli 1 ""             normalize "007"
check_cli 1 ""             normalize "4294967296"
check_cli 1 ""             has "1-5" x
check_cli 1 ""             has "nope" 1
check_cli 2 ""             normalize
check_cli 2 ""
check_cli 2 ""             nonsense 1
echo "cli       $cli_checks checks, $cli_failed failed"

echo
echo "ACCEPTANCE: $(( passed + cli_checks )) checked, $(( ${failed:-0} + cli_failed )) failed"
if [ "${failed:-0}" -eq 0 ] && [ "$cli_failed" -eq 0 ] && [ "$(( passed + cli_checks ))" -gt 0 ]; then
  echo "ACCEPTANCE PASSED"
  exit 0
fi
echo "ACCEPTANCE FAILED"
exit 1
