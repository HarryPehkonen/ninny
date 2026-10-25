#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means the
# task's runner misreports a red as "nothing ran", which is the defect that cost `tasks/intset`
# its whole record.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
# The file is named probe.test.js, not test_probe.js: the runner's `require` pattern is
# tests/own/*.test.js, so a planted file the runner cannot see makes this control fail for a
# scaffolding reason -- which reads exactly like a runner that misreports a red.
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/probe.test.js <<'JS'
'use strict';
// Planted by oracle/probe.sh. It cannot pass, on purpose.
const test = require('node:test');
const assert = require('node:assert');

test('a planted failure is reported as a red', () => {
  assert.strictEqual(1, 2, 'planted failure: the runner must call this exit 1, not exit 2');
});
JS
