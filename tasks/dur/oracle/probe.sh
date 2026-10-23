#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran".
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/probe.test.js <<'JS'
// Planted by oracle/probe.sh. It cannot pass, on purpose.
'use strict';
const test = require('node:test');
const assert = require('node:assert');

test('a planted failure is reported as a red', () => {
  assert.strictEqual(1, 2);
});
JS
