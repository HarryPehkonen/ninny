"""The acceptance corpus for the dogfood-stamp task.

Two graders, one verdict.

1. **The harness's own suite, pristine.** `oracle/frozen/` is a byte copy of the 248 tests the
   submission was given -- kept out here, run against the submission's `ninny/`. What the
   submission does to its own `tests/` is reported and never graded, which is the rule the corpus
   learned the hard way: a gate the seal forbids meeting is a trap.

2. **The stamp contract.** The API, its properties, and -- the point of the task -- the artifact
   a real run writes: a genuine `cli.main(["run", ...])` with a stub model, no network, no money,
   then `result.json` read back off disk.

Nothing is graded on a fixed digest value: a hash is not a number anyone can predict, so the
corpus grades its *properties*. That is the difference between judging a claim and judging an
artifact.

Run by `oracle/accept.sh`, which sets NINNY_TREE and PYTHONPATH.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

TREE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
HERE = Path(__file__).resolve().parent
HEX16 = re.compile(r"\A[0-9a-f]{16}\Z")

CHECKS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def load_artifacts():
    """The submission's own module, not the one this script was written against."""
    if str(TREE) not in sys.path:
        sys.path.insert(0, str(TREE))
    for name in [m for m in sys.modules if m == "ninny" or m.startswith("ninny.")]:
        del sys.modules[name]
    import ninny
    import ninny.artifacts as artifacts

    return ninny, artifacts


# ------------------------------------------------------------------ 1. the frozen suite
def the_frozen_suite() -> None:
    scratch = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(HERE / "frozen", scratch / "tests")
        env = dict(os.environ, PYTHONPATH=str(TREE))
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=scratch, env=env, capture_output=True, text=True, timeout=300,
        )
        text = proc.stdout + proc.stderr
        summary = next((ln for ln in text.splitlines() if ln.startswith("Ran ")), "no summary line")
        ok = proc.returncode == 0 and "OK" in text.splitlines()
        check("the harness's own frozen suite still passes", ok, summary)
        if not ok:
            breaks = [ln for ln in text.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
            check("no frozen test was broken", False, "; ".join(breaks[:4]) or "see the suite output")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 2. the stamp contract
def the_stamp_contract() -> None:
    try:
        ninny, artifacts = load_artifacts()
    except Exception as exc:  # a submission that cannot even be imported fails here, loudly
        check("ninny.artifacts imports", False, f"{type(exc).__name__}: {exc}")
        return
    check("ninny.artifacts imports", True)

    digest = getattr(artifacts, "instrument_digest", None)
    identity = getattr(artifacts, "harness_identity", None)
    check("instrument_digest is exported", callable(digest))
    check("harness_identity is exported", callable(identity))
    if not (callable(digest) and callable(identity)):
        return

    try:
        value = digest()
    except Exception as exc:
        check("instrument_digest() returns", False, f"{type(exc).__name__}: {exc}")
        return
    check("instrument_digest() returns", True)
    check("the digest is 16 lowercase hex characters", bool(HEX16.match(str(value))), str(value))

    # Stable, and blind to where it is computed from.
    check("the digest is stable across calls", digest() == value)
    origin = os.getcwd()
    try:
        os.chdir(tempfile.mkdtemp())
        check("the digest does not depend on the working directory", digest() == value)
    finally:
        os.chdir(origin)

    # Same source, different directory: the digest must not carry a path with it.
    twin = Path(tempfile.mkdtemp()) / "a" / "b" / "ninny"
    shutil.copytree(TREE / "ninny", twin)
    shutil.rmtree(twin / "__pycache__", ignore_errors=True)
    check("the same source in a different directory hashes the same", digest(twin) == value)

    # Sensitive to a module, blind to anything else.
    copy = Path(tempfile.mkdtemp()) / "ninny"
    shutil.copytree(TREE / "ninny", copy)
    before = digest(copy)
    check("instrument_digest(package_dir) hashes that directory", isinstance(before, str) and before != "")
    module = sorted(copy.glob("*.py"))[0]
    module.write_text(module.read_text() + "\n# a change the digest must see\n")
    changed = digest(copy)
    check("a changed module changes the digest", changed != before, f"{before} -> {changed}")

    shutil.rmtree(copy / "__pycache__", ignore_errors=True)  # a copy carries one: start clean
    (copy / "__pycache__").mkdir(exist_ok=True)
    (copy / "__pycache__" / "artifacts.cpython-313.pyc").write_bytes(b"\x00\x01\x02")
    (copy / "notes.txt").write_text("not a module\n")
    check("a stale .pyc and a stray file change nothing", digest(copy) == changed)

    # The identity dict, exactly.
    try:
        who = identity()
    except Exception as exc:
        check("harness_identity() returns", False, f"{type(exc).__name__}: {exc}")
        return
    check("harness_identity() returns", True)
    check(
        "harness_identity carries exactly the four keys",
        isinstance(who, dict) and set(who) == {"version", "fork_of", "upstream", "instrument_sha256"},
        str(sorted(who) if isinstance(who, dict) else type(who).__name__),
    )
    check("the version is the package's own", who.get("version") == ninny.__version__, str(who.get("version")))
    check("the identity's digest is instrument_digest()", who.get("instrument_sha256") == digest())


# ------------------------------------------------------------------ 3. the artifact
STUB_TASK = """
name = "tiny"
spec_file = "SPEC.md"
tree = "tree"
test_cmd = "bash tools/run_own_tests.sh"
test_globs = ["tests/own/**"]
src_globs = ["src/**"]
protected_globs = ["tools/**"]
preflight = ["python3 -V"]
step_limit = 2
timeout_s = 30
test_timeout_s = 30
"""


def the_artifact() -> None:
    """A real run, offline, and the file a downstream number is read from."""
    scratch = Path(tempfile.mkdtemp())
    task = scratch / "tiny"
    (task / "tree" / "src").mkdir(parents=True)
    (task / "tree" / "tools").mkdir()
    (task / "tree" / "src" / "thing.py").write_text("value = 0\n")
    (task / "tree" / "tools" / "run_own_tests.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    (task / "SPEC.md").write_text("A tiny task, so a run can happen without a model.\n")
    (task / "task.toml").write_text(STUB_TASK)

    os.environ["NINNY_LOG_DIR"] = str(scratch / "logs")
    sys.path.insert(0, str(TREE))

    from ninny import SUBMIT_SENTINEL, cli
    from ninny.model import Response, ToolCall

    class StubClient:
        def __init__(self, model="stub/model", base_url="", api_key="", wire="chat", **kwargs):
            self.model, self.wire, self.calls = model, wire, 0

        def complete(self, messages, tools=None):
            self.calls += 1
            call = ToolCall(name="bash", arguments={"command": f"echo {SUBMIT_SENTINEL}"}, id="call-1")
            return Response(text="submitting", tool_calls=[call],
                            usage={"prompt_tokens": 10, "completion_tokens": 5},
                            finish_reason="stop", latency_s=0.01)

    class StubPricing:
        def __init__(self, *args, **kwargs):
            pass

        def describe(self, model_id):
            return "stub: $0/M"

        def cost(self, model_id, usage):
            return 0.0

    out = scratch / "runs"
    try:
        with mock.patch.object(cli, "ModelClient", StubClient), mock.patch.object(cli, "Pricing", StubPricing):
            cli.main(["run", "--task", str(task), "--model", "stub/model", "--sandbox", "none",
                      "--tdd", "off", "--out", str(out), "--name", "stamp-arm", "--steps", "2"])
    except SystemExit as exc:  # a refused run is still a run that should have written its record
        check("the run completed", False, f"SystemExit({exc.code})")
    except Exception as exc:
        check("the run completed", False, f"{type(exc).__name__}: {exc}")
    else:
        check("the run completed", True)

    found = sorted(out.rglob("result.json"))
    check("the run wrote result.json", bool(found), str(found[0] if found else out))
    if not found:
        return

    result = json.loads(found[0].read_text())
    check("result.json carries a harness key", "harness" in result, str(sorted(result)))
    if "harness" not in result:
        return

    block = result["harness"]
    check("the recorded harness block has the four keys",
          set(block) == {"version", "fork_of", "upstream", "instrument_sha256"}, str(sorted(block)))
    check("the recorded digest is the package's", block.get("instrument_sha256") == _fresh_digest(),
          f"{block.get('instrument_sha256')} vs {_fresh_digest()}")
    check("nothing that was in result.json was dropped",
          {"exit_status", "steps", "cost_usd", "tdd"} <= set(result))

    trajectory = found[0].with_name("trajectory.json")
    if trajectory.exists():
        payload = json.loads(trajectory.read_text())
        block = payload.get("ninny", {})
        check("trajectory.json keeps version, fork_of and upstream",
              {"version", "fork_of", "upstream"} <= set(block), str(sorted(block)))
        check("trajectory.json carries the instrument hash",
              "instrument_sha256" in block, str(sorted(block)))


def _fresh_digest() -> str:
    try:
        _, artifacts = load_artifacts()
        return str(artifacts.instrument_digest())
    except Exception:
        return ""


def main() -> int:
    the_frozen_suite()
    the_stamp_contract()
    the_artifact()

    failed = 0
    for name, ok, detail in CHECKS:
        if ok:
            print(f"ok   {name}")
        else:
            failed += 1
            print(f"FAIL {name}" + (f" -- {detail}" if detail else ""))
    print(f"ACCEPTANCE: {len(CHECKS)} checked, {failed} failed")
    print("ACCEPTANCE PASSED" if failed == 0 else "ACCEPTANCE FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
