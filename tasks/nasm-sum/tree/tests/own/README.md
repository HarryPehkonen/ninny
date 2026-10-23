# Your tests go here

One shell script per area, named `tests/own/*.sh`. Each prints a line per case and exits
with the same contract the runner reports, one level down:

```sh
#!/usr/bin/env bash
# tests/own/arguments.sh
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
sum=build/sum
[ -x "$sum" ] || { echo "no binary at $sum"; exit 2; }

case_() {  # <expected exit> <what> <args...>
  want="$1"; shift
  what="$1"; shift
  "$sum" "$@" >/dev/null 2>&1
  got=$?
  if [ "$got" -eq "$want" ]; then echo "ok $what"; else echo "not ok $what (exit $got, wanted $want)"; fi
}

case_ 5  "2 + 3" 2 3
case_ 0  "0 + 0" 0 0
case_ 2  "a letter is not a number" 5x 1
```

Exit **0** when every case passed, **1** when any failed, and **2 or more** when the script
could not run at all -- so the runner can tell "the program is wrong" apart from "the test
never ran", which is the difference between a RED and a broken suite.

Two things the runner will not accept, because they would be a green suite that observed
nothing: a file with no `ok`/`not ok` lines in it, and a script that exits 1 without saying
which case failed.

These scripts are the only tests anybody will read when they ask whether this program can
be trusted. The boundary is the interesting part.
