#!/usr/bin/env bash
# The probe for the dogfood-stamp task.
#
# Its only job is to land: plant a failing test in the suite and exit 0. `ninny verify-task` runs
# the suite itself afterwards, on a staged copy, and requires the runner to call that RED -- which
# is why this recipe's exit code means "planted" and not "red". Getting that backwards makes the
# control report "it did not land" on a probe that landed perfectly.
#
# It runs with its cwd inside a staged copy of the tree and does NOT set NINNY_TREE, so the tree
# is the cwd; NINNY_TREE is honoured when a human runs it by hand.
set -uo pipefail

TREE="${NINNY_TREE:-$PWD/tree}"
PLANT="$TREE/tests/test_zz_probe_planted.py"

mkdir -p "$TREE/tests"
cat > "$PLANT" <<'PY'
"""Planted by oracle/probe.sh. It cannot pass, on purpose."""
import unittest


class InstrumentProbe(unittest.TestCase):
    def test_a_planted_failure_is_reported_as_a_red(self):
        self.assertEqual(1, 2, "planted failure: this must be exit 1, not exit 2")
PY
rm -rf "$TREE/tests/__pycache__"

# A plant that did not land proves nothing: report that as a failure, not as success.
if [ ! -s "$PLANT" ]; then
  echo "FAIL nothing was planted at $PLANT -- is the tree where this script thinks it is?"
  exit 1
fi

echo "planted a failing test at $PLANT"
exit 0
