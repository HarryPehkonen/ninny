#!/usr/bin/env python3
"""Declare the oracle standard in every task.toml, once, idempotently.

An oracle may grade the IMPLEMENTATION (an external corpus drives the code). It may not
gate acceptance on the submission's own test files passing, because once a suite has gone
red the seal forbids repairing it -- a gate the harness itself blocks is a trap, not a
standard. Three live `bits` arms failed acceptance for exactly that reason with a correct
implementation.

The declaration is per task so the standard is stated rather than inferred, and so
scripts/verify-tasks.sh can refuse a task that never says.
"""

from pathlib import Path

LINE = "oracle_gate = \"implementation\""
COMMENT = (
    "# What the acceptance corpus is allowed to grade: the implementation alone. It does not\n"
    "# gate on the submission's own suite passing -- after a red the seal forbids repairing a\n"
    "# wrong test, so that gate would fail correct code (it did, three times in `bits`).\n"
)

root = Path(__file__).resolve().parent.parent
changed = []
for toml in sorted(root.glob("tasks/*/task.toml")):
    text = toml.read_text()
    if "oracle_gate" in text:
        continue
    lines = text.splitlines(keepends=True)
    at = next((i for i, line in enumerate(lines) if line.startswith("oracle_cmd")), None)
    if at is None:
        print(f"SKIP {toml}: no oracle_cmd line to anchor")
        continue
    lines.insert(at + 1, "\n" + COMMENT + LINE + "\n")
    toml.write_text("".join(lines))
    changed.append(toml.parent.name)

print(f"declared oracle_gate in {len(changed)} tasks: {', '.join(changed)}")
