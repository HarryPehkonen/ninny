"""The run verdict: what a diff came with, in one line an orchestrator can read.

`result.json` carries 25 fields under `tdd` plus an `exit_status`, and every one of them is
meaningful to somebody -- but a caller that wants to know "may I apply this patch?" had to know
which five to AND together, and `ninny run` printed prose. The exit code is the API:

    0  artifact present       submitted, red before the first source write, the suite handed back
                              is the suite that went red, green observed after the last write
    1  handed back, unproven  submitted, but at least one of those is false; `reasons` names them
    2  did not hand back      nothing to grade (StepLimit, wall clock, repeated format errors)

Three rules, each with a test on it.

**Which clauses apply is a property of the run, not of the reader.** A benchmark required a test
file of the model's own, so it is held to both its order (a red before the first source write) and
its artifact (the suite handed back is the suite that went red). A repository run is held to the
handback only: green observed after the last source write, and no write that went round the tools.
It still reports its order and whether the suite was frozen; it is just not refused for developing
the way development works. Every record written before the field existed defaults to the
benchmark's reading, which is how it was read when it was written.

A **missing field is 2**, with `record incomplete: <field>`, never a silent pass -- a verifier that
passes on absent evidence is the failure this repo has a lesson about, and an orchestrator that
applies a patch because a key it never read was absent is worse off than one that read nothing.

**Reasons are plural and specific.** "unproven" tells a caller to stop; it does not tell them what
to do, and a delegate that was refused for a stale tree and one that was refused for a bypass are
different conversations.

**The line is deterministic**, so it can be diffed, replayed and compared across runs.

The judgement is a pure function of a dict a record already contains: nothing here decides
anything the harness did not observe, and nothing here re-runs a test.
"""

EXIT_ARTIFACT = 0
EXIT_UNPROVEN = 1
EXIT_NO_HANDBACK = 2

#: The fields the verdict is a function of. Missing any one of them is exit 2: absence is not
#: evidence, and the alternative -- defaulting them -- is how "0 tests collected" read as green.
REQUIRED_TDD = (
    "red_step",
    "first_src_step",
    "red_before_code",
    "suite_frozen_since_red",
    "green_after_last_write",
    "bypass_detected",
)


def verdict_of(result: dict) -> tuple[int, dict]:
    """(exit code, the line). The line carries the evidence, not just the label."""
    tdd = result.get("tdd") or {}
    line = {
        "verdict": None,
        "exit": None,
        "exit_status": result.get("exit_status"),
        "order": tdd.get("verdict"),
        "red_step": tdd.get("red_step"),
        "first_src_step": tdd.get("first_src_step"),
        "last_src_step": tdd.get("last_src_step"),
        "green_after_last_write": tdd.get("green_after_last_write"),
        "suite_frozen_since_red": tdd.get("suite_frozen_since_red"),
        "bypass_detected": tdd.get("bypass_detected"),
        "harness_runs": tdd.get("harness_runs"),
        "require_test_file": tdd.get("require_test_file", True),
        "steps": result.get("steps"),
        "cost_usd": result.get("cost_usd"),
        "reasons": [],
    }

    missing = [f"tdd.{name}" for name in REQUIRED_TDD if name not in tdd]
    if "exit_status" not in result:
        missing.insert(0, "exit_status")
    if missing:
        return _answer(line, EXIT_NO_HANDBACK, "no-handback",
                       [f"record incomplete: {name}" for name in missing])

    if result.get("exit_status") != "Submitted":
        return _answer(line, EXIT_NO_HANDBACK, "no-handback",
                       [f"did not submit: {result.get('exit_status')}"])

    reasons = []
    # The order clause is a benchmark's claim too. A benchmark's deliverable IS the test-first
    # suite, so "a red was seen before the source changed" is what it grades. A repository run is
    # graded on the handback -- a green observed after the last source write, and no write that
    # went round the tools -- and reports its order in `order` for anyone who wants it.
    if tdd.get("require_test_file", True) and not tdd.get("red_before_code"):
        reasons.append(f"no red before the first source write (order: {tdd.get('verdict')})")
    # The seal's claim belongs to the runs that make it. A benchmark required a test file of its
    # own, so the suite handed back has to be the suite that went red; a repository's suite is
    # the model's to extend -- which is exactly why the read-only bind is split-only -- so it
    # reports `suite_frozen_since_red` without being held to it. Defaulting to True reads every
    # record written before the field existed the way it was read then.
    if tdd.get("require_test_file", True) and tdd.get("suite_frozen_since_red") is not True:
        reasons.append("the suite handed back is not the suite that went red")
    if not tdd.get("green_after_last_write"):
        reasons.append("no green observed after the last source write")
    if tdd.get("bypass_detected"):
        reasons.append(f"{len(tdd['bypass_detected'])} write(s) went round the tools: "
                       f"{tdd['bypass_detected']}")

    if reasons:
        return _answer(line, EXIT_UNPROVEN, "unproven", reasons)
    return _answer(line, EXIT_ARTIFACT, "artifact", [])


def _answer(line: dict, code: int, name: str, reasons: list[str]) -> tuple[int, dict]:
    line["verdict"] = name
    line["exit"] = code
    line["reasons"] = reasons
    return code, line
