#!/usr/bin/env bash
# A planted failing test, for `ninny verify-task`'s third control.
#
# The suite must answer 1 -- ran and failed -- because that is what a red is. A 2 here means
# this task's runner misreports a red as "nothing ran".
#
# This task's cases are bash scripts printing "ok <what>" / "not ok <what>", so a planted case
# is a script that says its one case failed and exits 1.
#
# Runs with cwd = the staging directory, like oracle_cmd, so the paths are tree/...
set -eu
mkdir -p tree/tests/own
cat > tree/tests/own/probe.sh <<'SH'
#!/usr/bin/env bash
# Planted by oracle/probe.sh. It cannot pass, on purpose.
echo "not ok a planted failure is reported as a red"
exit 1
SH
