#!/usr/bin/env bash
# The acceptance runner for the dogfood-stamp task.
#
# Run by hand, per submission:
#     ninny check --task tasks/dogfood-stamp --tree runs/dogfood-stamp/<arm>/tree
#
# Two graders, and neither of them trusts the tree: the harness's own frozen suite, kept pristine
# out here and run against the submission's `ninny/`, and the stamp contract, which drives a real
# offline run and reads the artifact it wrote. Everything is counted in the contract script, so
# there is one ACCEPTANCE line and one verdict.
set -uo pipefail

TREE="${NINNY_TREE:?ninny check sets NINNY_TREE to the submission tree}"
HERE="$(cd "$(dirname "$0")" && pwd)"

exec env PYTHONPATH="$TREE" python3 "$HERE/test_stamp_contract.py" "$TREE"
