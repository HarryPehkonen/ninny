#!/usr/bin/env bash
# Score every A/B arm by the task's OWN oracle, and write runs/ab-results.tsv.
#
# An arm's own report is not the verdict: `--tdd off` arms have been seen to submit a tree that
# does not pass. Acceptance is decided here, once, by `ninny check`, which runs the hidden
# acceptance corpus against the tree the arm left behind.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

OUT="runs/ab-results.tsv"

python3 - "$OUT" <<'PY'
import json, os, re, subprocess, sys, glob

out_path = sys.argv[1]
rows = []
for res in sorted(glob.glob("runs/*/ab-*/result.json")):
    arm_dir = os.path.dirname(res)
    arm = os.path.basename(arm_dir)
    task = os.path.basename(os.path.dirname(arm_dir))
    d = json.load(open(res))
    tdd = d.get("tdd") or {}

    checked = failed = None
    if os.path.isdir(os.path.join(arm_dir, "tree")):
        p = subprocess.run(["python3", "-m", "ninny", "check", "--task", "tasks/" + task,
                            "--tree", arm_dir + "/tree"],
                           capture_output=True, text=True, timeout=1800)
        # The exit code IS the verdict: `ninny check` returns the oracle's own status, and the
        # oracle's output format is the task's business, not ours. Tasks that compile a frozen
        # harness also print a count; unittest-based oracles print "Ran N tests" instead.
        accepted = "1" if p.returncode == 0 else "0"
        m = re.search(r"ACCEPTANCE:\s*(\d+)\s*checked,\s*(\d+)\s*failed", p.stdout)
        if m:
            checked, failed = int(m.group(1)), int(m.group(2))
        else:
            m = re.search(r"^Ran (\d+) tests?", p.stdout, re.M)
            if m:
                checked = int(m.group(1))
                failed = 0 if re.search(r"^OK$", p.stdout, re.M) else -1
    else:
        accepted = ""

    rows.append(dict(
        task=task, arm=arm,
        mode="enforce" if arm.startswith("ab-enforce") else "off",
        rep=arm.rsplit("-", 1)[-1],
        accepted="" if failed is None else ("1" if failed == 0 else "0"),
        checks="" if checked is None else checked,
        failed="" if failed is None else failed,
        steps=d.get("steps", ""),
        cost="%.4f" % (d.get("cost_usd") or 0.0),
        status=d.get("exit_status", ""),
        verdict=tdd.get("verdict", ""),
        red_step=tdd.get("red_step", ""),
    ))

cols = ["task", "mode", "rep", "arm", "accepted", "checks", "failed", "steps", "cost",
        "status", "verdict", "red_step"]
with open(out_path, "w") as fh:
    fh.write("\t".join(cols) + "\n")
    for r in rows:
        fh.write("\t".join(str(r[c]) for c in cols) + "\n")

print("wrote %s (%d arms)" % (out_path, len(rows)))

# --- the summary the project has been missing
def agg(mode):
    rs = [r for r in rows if r["mode"] == mode]
    if not rs:
        return None
    acc = [r for r in rs if r["accepted"] == "1"]
    red = [r for r in rs if r["verdict"] == "red-first"]
    steps = [r["steps"] for r in rs if isinstance(r["steps"], int)]
    cost = sum(float(r["cost"]) for r in rs)
    sub = [r for r in rs if r["status"] == "Submitted"]
    return dict(n=len(rs), accepted=len(acc), redfirst=len(red), submitted=len(sub),
                mean_steps=(sum(steps) / len(steps) if steps else 0), cost=cost)

print("\n%-9s %4s %9s %10s %10s %11s %8s" % ("mode", "n", "accepted", "red-first", "submitted", "mean steps", "cost"))
for mode in ("off", "enforce"):
    a = agg(mode)
    if a:
        print("%-9s %4d %9s %10s %10s %11.1f %8s" % (
            mode, a["n"], "%d (%d%%)" % (a["accepted"], 100 * a["accepted"] / a["n"]),
            "%d (%d%%)" % (a["redfirst"], 100 * a["redfirst"] / a["n"]),
            a["submitted"], a["mean_steps"], "$%.4f" % a["cost"]))
PY
