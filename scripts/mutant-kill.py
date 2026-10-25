#!/usr/bin/env python3
"""Does the suite an arm SHIPS have teeth?

`ninny check` grades what a submission DOES. This grades the submission's TESTS -- the artifact the
arm is supposed to be producing -- and it is the only measure in the corpus that comes out GRADED
rather than at a ceiling. Acceptance is 100% in every mode; a kill rate is not.

For each arm: copy its tree, drop one sabotage fixture in as the implementation, run the arm's own
frozen test command, and read the exit code.

    1  the tests ran and failed   -> the mutant was KILLED (the suite has teeth)
    0  the tests ran and passed   -> the mutant SURVIVED (the suite cannot see that bug)
    2  nothing ran                -> also survived: no case observed it

The fixtures are the task's own, so a task with no `sabotage/` directory cannot be measured this
way. That is the honest answer, not a failure of the measure: nobody has asked it yet.

Usage:
    python3 scripts/mutant-kill.py spans                 # every arm of tasks/spans that has a tree
    python3 scripts/mutant-kill.py spans runs/spans/ab-enforce-*
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def task_dir(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_dir():
        return candidate.resolve()
    return ROOT / "tasks" / name.lstrip("/")


def arms(task: Path) -> list[Path]:
    return sorted(p for p in (ROOT / "runs" / task.name).glob("ab-*") if (p / "tree").is_dir())


def mode_of(arm: Path) -> str:
    """The mode the arm ran under, read from the arm's own record."""
    record = arm / "result.json"
    if not record.exists():
        return "?"
    import json

    try:
        return (json.load(open(record)).get("tdd") or {}).get("mode") or "?"
    except Exception:
        return "?"


def kill(tree: Path, fixture: Path, target: str, test_cmd: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "tree"
        shutil.copytree(tree, copy)
        shutil.copy(fixture, copy / target)
        try:
            proc = subprocess.run(["bash", "-c", test_cmd], cwd=str(copy),
                                  capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return 99
        return proc.returncode


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 scripts/mutant-kill.py <task> [arm-dir ...]")
        return 2
    task = task_dir(argv[0])
    conf = tomllib.load(open(task / "task.toml", "rb"))
    target = conf.get("sabotage_target")
    test_cmd = conf.get("test_cmd", "")
    fixtures = sorted((task / "sabotage").glob("*")) if (task / "sabotage").is_dir() else []
    if not fixtures:
        print(f"{task.name}: no sabotage/ directory, so the teeth of a suite cannot be measured here")
        return 2
    if not target:
        print(f"{task.name}: task.toml declares no sabotage_target, so a fixture has nowhere to go")
        return 2

    chosen = [Path(a) for a in argv[1:]] or arms(task)
    chosen = [a if a.is_absolute() else ROOT / a for a in chosen]
    chosen = [a for a in chosen if a.is_dir()]
    if not chosen:
        print(f"{task.name}: no arms with a tree")
        return 2

    width = max(len(a.name) for a in chosen)
    names = [f.stem[:16] for f in fixtures]
    print(f"{'arm':{width}s} {'mode':8s} " + " ".join(f"{n:16s}" for n in names))
    totals: dict[str, list[int]] = {}
    for arm in chosen:
        cells = []
        for fixture in fixtures:
            rc = kill(arm / "tree", fixture, target, test_cmd)
            cells.append({1: "KILL", 0: "survive", 2: "none", 99: "timeout"}.get(rc, f"rc{rc}"))
        mode = mode_of(arm)
        totals.setdefault(mode, []).append(sum(1 for c in cells if c == "KILL"))
        print(f"{arm.name:{width}s} {mode:8s} " + " ".join(f"{c:16s}" for c in cells))

    print()
    total = len(fixtures)
    for mode in sorted(totals):
        kills = totals[mode]
        rate = sum(kills) / (len(kills) * total)
        print(f"{mode:9s} {len(kills):2d} arm(s)  kill rate {sum(kills)}/{len(kills) * total} "
              f"= {rate:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
