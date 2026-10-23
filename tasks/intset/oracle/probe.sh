#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran" -- which is exactly what this task's
# runner did, for weeks, because its build-error grep matched Cargo's own
# `error: test failed, to rerun pass \`--test own\`` line. This control is the reason that
# class of defect cannot ship again unnoticed.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/main.rs <<'RS'
// Planted by oracle/probe.sh. It cannot pass, on purpose.
//
// tests/own/main.rs is the integration test target Cargo discovers as `own`.
#[test]
fn a_planted_failure_is_reported_as_a_red() {
    assert!(1 == 2, "planted failure: the runner must call this exit 1, not exit 2");
}
RS
