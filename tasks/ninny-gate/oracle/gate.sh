#!/usr/bin/env bash
# The acceptance runner for the `ninny-gate` task.
#
# Run by hand, per submission:
#     ninny check --task tasks/ninny-gate --tree runs/ninny-gate/<arm>/tree
set -uo pipefail

TREE="${NINNY_TREE:?ninny check sets NINNY_TREE to the submission tree}"
HERE="$(cd "$(dirname "$0")" && pwd)"

exec python3 "$HERE/test_gate_bypass.py" "$TREE"
