#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran", which is the defect that cost
# `tasks/intset` its whole record.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/test_probe.py <<'PY'
"""Planted by oracle/probe.sh. It cannot pass, on purpose."""
import unittest


class InstrumentProbe(unittest.TestCase):
    def test_a_planted_failure_is_reported_as_a_red(self):
        self.assertEqual(1, 2, "planted failure: the runner must call this exit 1, not exit 2")
PY
