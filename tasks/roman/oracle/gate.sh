#!/usr/bin/env bash
# The acceptance runner for the `roman` task.
#
# The keeper runs this BY HAND, per submission -- never the harness, and never
# inside the agent's run:
#
#     ninny check --task tasks/roman --tree runs/roman/<arm>/tree
#
# ninny check copies the submission into a scratch directory and runs this beside
# the oracle, so judging a submission cannot pollute it.
set -uo pipefail

TREE="${NINNY_TREE:?ninny check sets NINNY_TREE to the submission tree}"
HERE="$(cd "$(dirname "$0")" && pwd)"

exec python3 "$HERE/test_roman.py" "$TREE"
