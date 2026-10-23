#!/usr/bin/env bash
#
# The suite, with Ninny's own exit-code contract applied to Ninny:
#
#     0   the tests ran and passed
#     1   the tests ran and failed          (a real RED)
#     2   nothing ran                       (never a RED, never a pass)
#
# The guard is the point. `python3 -m unittest discover` in a directory with no tests prints
# "Ran 0 tests in 0.000s / NO TESTS RAN" and exits 0 - measured, and it is exactly the
# vacuous pass Ninny refuses from the models it grades. A suite that quietly stopped being
# collected must not read as green here either.
#
# PY overrides the interpreter, so the stdlib stage can run the same suite under `python3 -S`
# instead of re-implementing this guard in a second file.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
py=${PY:-python3}

out=$($py -m unittest discover -s tests 2>&1); rc=$?   # rc on the NEXT line, always
printf '%s\n' "$out"

ran=$(printf '%s\n' "$out" | sed -n 's/^Ran \([0-9][0-9]*\) tests\?.*/\1/p' | tail -1)

if [ -z "${ran:-}" ]; then
    printf 'tests: no "Ran N tests" line in the output - the suite did not run\n' >&2
    exit 2
fi
if [ "$ran" -eq 0 ]; then
    printf 'tests: 0 tests ran - a green suite of zero tests is the failure this guards\n' >&2
    exit 2
fi

echo "tests: $ran ran, exit $rc"
exit "$rc"
