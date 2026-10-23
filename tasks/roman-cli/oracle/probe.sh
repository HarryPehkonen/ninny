#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran".
#
# The frozen CMakeLists.txt compiles every tests/own/*.cpp into one `own_tests` target, so a
# planted case is a single file using the frozen harness.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/probe_test.cpp <<'CPP'
// Planted by oracle/probe.sh. It cannot pass, on purpose.
#include "../harness.hpp"

TEST(a_planted_failure_is_reported_as_a_red) {
  CHECK_EQ(1, 2);
}

FROZEN_TEST_MAIN("PROBE")
CPP
