#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran", which is the defect that cost
# `tasks/intset` its whole record.
#
# cron's stub tree has an empty src/, and the build globs src/*.cpp, so an unmatched glob is
# itself a build error. The recipe therefore plants a compiling placeholder translation unit
# alongside the failing case. The case touches nothing in cronx, so it links with no
# implementation present -- which is the point: the control must not depend on a solution.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own tree/src
cat > tree/src/probe_placeholder.cpp <<'CPP'
// Planted by oracle/probe.sh: makes `src/*.cpp` match, so the planted case can link.
CPP
cat > tree/tests/own/probe_test.cpp <<'CPP'
// Planted by oracle/probe.sh. It cannot pass, on purpose.
#include "harness.hpp"

TEST(APlantedFailureIsReportedAsARed) {
  // volatile, so this is a runtime comparison the compiler may not fold away under -Werror.
  volatile int planted = 0;
  CHECK(planted == 1);
}

FROZEN_TEST_MAIN("INSTRUMENT_PROBE")
CPP
