#!/usr/bin/env bash
#
# stdlib - the two claims in the README that a dependency would quietly falsify:
#
#   1. every module in the package imports with no site-packages (`python3 -S`);
#   2. the whole suite runs under `python3 -S` too.
#
# The second is the stronger half: a third-party import hidden inside a function only fails
# when that function runs, so importing the modules is not enough. It is also the stage that
# would fail if a test file ever grew a pytest dependency.
#
# Cost is ~1 s. Denying site-packages is the whole check - no import scanner to get wrong.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

python3 -S - <<'PY' || exit 1
import importlib
import pkgutil
import sys

import ninny

mods = sorted(m.name for m in pkgutil.walk_packages(ninny.__path__, "ninny."))
if not mods:
    sys.exit("stdlib: no modules found under ninny/ - the scan is vacuous")
for name in mods:
    importlib.import_module(name)
print(f"stdlib: {len(mods)} modules import with no site-packages")
PY

PY="python3 -S" exec "$(dirname "$0")/run-tests.sh"
