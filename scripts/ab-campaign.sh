#!/usr/bin/env bash
# The A/B: does enforcing test-first change the OUTCOME, not just the process?
#
# Every number Ninny has is a process number -- did a red precede the source. This runs the same
# six tasks with the same model twice: --tdd off (nothing is enforced) and --tdd enforce (a source
# write before a red is refused). The arms are then scored by the task's own oracle, by hand, so
# an arm that submits a tree that does not pass is counted as a failure however it describes itself.
#
# Resumable: an arm whose result.json exists is skipped, so an interrupted run costs only the arms
# it had not reached. One build at a time on purpose -- a cold C++ build in parallel is what killed
# an earlier arm at the 180s action timeout.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

MODEL="${AB_MODEL:-deepseek/deepseek-v4.1-flash}"
BWRAP="${AB_BWRAP:-/home/harri/.local/opt/bwrap/usr/bin/bwrap}"
TASKS="${AB_TASKS:-roman dur nasm-sum intset bits roman-cli}"
ARMS="${AB_ARMS:-3}"
STATES="${AB_STATES:-off enforce}"

[ -x "$BWRAP" ] || { echo "no bwrap at $BWRAP -- every scored run must be sandboxed"; exit 1; }

for t in $TASKS; do
  for mode in $STATES; do
    for i in $(seq 1 "$ARMS"); do
      name="ab-${AB_LABEL:-$mode}-$i"
      dir="runs/$t/$name"
      if [ -f "$dir/result.json" ]; then
        echo "skip  $t/$name  (already recorded)"
        continue
      fi
      echo "===   $t/$name   tdd=$mode"
      python3 -m ninny run --task "tasks/$t" --model "$MODEL" --tdd "$mode" \
        --sandbox bwrap --bwrap-path "$BWRAP" --name "$name" 2>&1 | tail -4
    done
  done
done

echo
echo "all arms recorded. now score them:  bash scripts/ab-score.sh"
