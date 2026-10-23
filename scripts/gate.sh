#!/usr/bin/env bash
#
# The gate - run this before you push (and before you publish).
#
# The POLICY is gate.toml (the stages, their tiers, their failure rules). The ENGINE is
# kit-ci, one binary installed once per machine:
#
#     cmake -S ~/hermes-workspace/KitCI -B build-release -DCMAKE_BUILD_TYPE=Release
#     cmake --build build-release && cmake --install build-release --prefix ~/.local
#
# This file is what every caller runs, so "the gate passed" means one thing no matter who
# says it:
#
#   1. a human, by hand            scripts/gate.sh [--tier fast]
#   2. git, on commit and on push  .githooks/pre-commit (fast) and pre-push (full)
#   3. the publish path            the filtered clone is a FRESH clone, so its hooks are not
#                                  armed; run this script by hand there before pushing
#
# Bypass deliberately, never accidentally:  git push --no-verify
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

# git's TEMPORARY index - exported to the pre-commit hook by `git commit -- <path>` - must
# reach no stage: a `git` command the gate runs in ANOTHER repository then reads this repo's
# entries against that repository's object store and dies on the first blob it does not have.
unset GIT_INDEX_FILE

# A gate that cannot find its engine must fail loudly rather than read as green.
if ! type -P kit-ci >/dev/null 2>&1; then
    printf 'gate: kit-ci is not installed. Build KitCI, then: cmake --install build-release --prefix ~/.local\n' >&2
    exit 1
fi

# With no arguments: the tier the caller names (GATE_TIER still works) and otherwise full.
[ "$#" -gt 0 ] && exec kit-ci "$@"
exec kit-ci --tier "${GATE_TIER:-full}"
