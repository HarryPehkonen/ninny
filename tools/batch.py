#!/usr/bin/env python3
"""Run a grid of arms and keep one row per run in a TSV.

Why a script and not a shell loop: a number produced by hand cannot be re-derived,
and a batch that dies half way through must not lose the half it finished. One row
per run, appended as the run finishes, and an arm whose row is already in the TSV is
skipped unless --force, so a batch can be resumed by running the same command again.

Two rules from the rig this came out of, both deliberate:

  * the gate comes FIRST. Every task is put through `ninny verify-task` before any
    money is spent, and a task that does not pass is not run at all -- an unverified
    task spends money producing numbers that cannot be trusted.
  * the oracle is NOT run here. Judging a submission is the keeper's job, by hand,
    per arm; the batch only prints the exact `ninny check` command for each one. A
    batch that grades its own subject is not evidence.

Usage:
    python3 tools/batch.py --tasks tasks/roman,tasks/ninny-gate --reps 3 --dry-run
    python3 tools/batch.py --tasks tasks/roman,tasks/ninny-gate --reps 3 \
        --sandbox bwrap --bwrap-path /path/to/bwrap
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

COLUMNS = [
    "task", "mode", "rep", "arm", "exit_status", "steps", "cost_usd", "verdict",
    "red_step", "first_src_step", "refusals", "bypasses", "own_gate_red",
    "wall_time_s", "oracle", "note",
]


def load_rows(path: Path) -> dict[str, dict]:
    """Arms already recorded in the TSV, so a resumed batch does not pay twice."""
    if not path.exists() or not path.read_text().strip():
        return {}
    lines = path.read_text().splitlines()
    header = lines[0].split("\t")
    rows = {}
    for line in lines[1:]:
        row = dict(zip(header, line.split("\t")))
        if row.get("arm"):
            rows[row["arm"]] = row
    return rows


def append_row(path: Path, row: dict) -> None:
    fresh = not path.exists() or not path.read_text().strip()
    with path.open("a") as fh:
        if fresh:
            fh.write("\t".join(COLUMNS) + "\n")
        fh.write("\t".join(str(row.get(c, "")) for c in COLUMNS) + "\n")


def read_record(run_dir: Path) -> dict | None:
    """The run's own record, or None if the harness never got far enough to write one."""
    try:
        data = json.loads((run_dir / "trajectory.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    result = data.get("result", {})
    tdd = result.get("tdd", {})

    def num(value, places=4):
        try:
            return f"{float(value):.{places}f}"
        except (TypeError, ValueError):
            return ""

    return {
        "exit_status": result.get("exit_status", "?"),
        "steps": result.get("steps", ""),
        "cost_usd": num(result.get("cost_usd")),
        "verdict": tdd.get("verdict", ""),
        "red_step": tdd.get("red_step") if tdd.get("red_step") is not None else "",
        "first_src_step": tdd.get("first_src_step") if tdd.get("first_src_step") is not None else "",
        "refusals": len(tdd.get("refusals") or []),
        "bypasses": len(tdd.get("bypass_detected") or []),
        "own_gate_red": tdd.get("own_gate_red", ""),
        "wall_time_s": num(result.get("wall_time_s"), 0),
    }


def verify(task_dir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "ninny", "verify-task", "--task", str(task_dir)],
        cwd=REPO, capture_output=True, text=True,
    )
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    verdict = next((l for l in reversed(lines) if l.startswith(("VERIFIED", "UNVERIFIED", "BROKEN"))), "")
    return proc.returncode, verdict


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a grid of Ninny arms into one TSV.")
    ap.add_argument("--tasks", required=True, help="comma-separated task directories")
    ap.add_argument("--modes", default="enforce,request,reverse")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--model", default="deepseek/deepseek-v4.1-flash")
    ap.add_argument("--sandbox", default="bwrap", choices=["none", "bwrap"])
    ap.add_argument("--bwrap-path")
    ap.add_argument("--prefix", default="ds41")
    ap.add_argument("--steps", type=int, help="override the task's own step limit")
    ap.add_argument("--out", help="TSV path (default: runs/batch-<stamp>.tsv)")
    ap.add_argument("--force", action="store_true", help="re-run arms that already have a row")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else REPO / "runs" / f"batch-{time.strftime('%Y%m%d-%H%M%S')}.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = load_rows(out)
    tasks = [Path(t) for t in args.tasks.split(",") if t]
    modes = [m for m in args.modes.split(",") if m]

    print(f"batch: {len(tasks)} tasks x {len(modes)} modes x {args.reps} reps = "
          f"{len(tasks) * len(modes) * args.reps} arms -> {out}")
    print(f"model: {args.model}   sandbox: {args.sandbox}")

    good = []
    for task_dir in tasks:
        code, verdict = verify(task_dir)
        print(f"  verify  {task_dir.name:12} exit {code}  {verdict}")
        if code == 0:
            good.append(task_dir)
    if not good:
        print("nothing to run: no task passed verify-task", file=sys.stderr)
        return 2

    spent = 0.0
    for task_dir in good:
        name = task_dir.name
        for mode in modes:
            for rep in range(1, args.reps + 1):
                arm = f"{args.prefix}-{name}-{mode}-r{rep}"
                if arm in rows and not args.force:
                    print(f"  skip    {arm}  (already in {out.name})")
                    continue

                cmd = [sys.executable, "-m", "ninny", "run", "--task", str(task_dir),
                       "--model", args.model, "--tdd", mode, "--sandbox", args.sandbox,
                       "--name", arm]
                if args.bwrap_path:
                    cmd += ["--bwrap-path", args.bwrap_path]
                if args.steps:
                    cmd += ["--steps", str(args.steps)]
                if args.dry_run:
                    print("  would   " + " ".join(cmd))
                    continue

                print(f"\n=== {arm} ===", flush=True)
                log = out.parent / f"{arm}.log"
                with log.open("w") as fh:
                    proc = subprocess.run(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT)

                record = read_record(REPO / "runs" / name / arm)
                row = {"task": name, "mode": mode, "rep": rep, "arm": arm, "oracle": ""}
                if record is None:
                    row["exit_status"] = f"HARNESS-ERROR(exit {proc.returncode})"
                    row["note"] = str(log)
                else:
                    row.update(record)
                append_row(out, row)
                rows[arm] = row

                try:
                    spent += float(row.get("cost_usd") or 0)
                except ValueError:
                    pass

                print(f"  {row.get('exit_status')}  steps={row.get('steps')}  "
                      f"${row.get('cost_usd')}  verdict={row.get('verdict')}  "
                      f"refusals={row.get('refusals')}  bypasses={row.get('bypasses')}  "
                      f"own_gate_red={row.get('own_gate_red')}", flush=True)
                print(f"  log:   {log}")
                print(f"  judge: python3 -m ninny check --task {task_dir} --tree runs/{name}/{arm}/tree",
                      flush=True)

    if not args.dry_run:
        print(f"\nbatch done: {len(rows)} rows in {out}, ${spent:.4f} spent by this batch")
        print("the oracle column is empty on purpose -- judge each arm by hand, then fill it in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
