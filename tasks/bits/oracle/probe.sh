#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran".
#
# A gtest file alone is never compiled here: CMake has to be told about it, which is why this
# recipe also appends the three lines the frozen CMakeLists.txt documents, BELOW its marker.
# Everything above that marker is untouched, so the frozen-prefix hash still matches.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/probe_test.cpp <<'CPP'
// Planted by oracle/probe.sh. It cannot pass, on purpose.
#include <gtest/gtest.h>

TEST(InstrumentProbe, APlantedFailureIsReportedAsARed) {
  EXPECT_EQ(1, 2) << "planted failure: the runner must call this exit 1, not exit 2";
}
CPP
cat >> tree/CMakeLists.txt <<'CMAKE'

# Planted by oracle/probe.sh for `ninny verify-task`.
add_executable(own_probe tests/own/probe_test.cpp)
target_link_libraries(own_probe PRIVATE bits GTest::gtest_main)
gtest_discover_tests(own_probe)
CMAKE
