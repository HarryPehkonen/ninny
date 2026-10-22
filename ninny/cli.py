"""The command line.

    ninny run         --task TASK --model MODEL [options]   one model, one task
    ninny check       --task TASK --tree TREE               run the oracle, outside the tree
    ninny verify-task --task TASK [--fixed TREE]            prove the task grades correctly
    ninny doctor                                            what this machine can do

Nothing here runs the oracle as part of a run. Deciding whether a submission is
correct is the keeper's job and is done by hand, per run: an evaluation whose
harness grades its own subject is not an evaluation. `verify-task` is the keeper
checking the *task*, deliberately, before any money is spent on it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ninny import UPSTREAM, UPSTREAM_URL, __version__, logs
from ninny.agent import Agent
from ninny.artifacts import write_diff
from ninny.config import ConfigError, load_task
from ninny.env import Environment
from ninny.model import PROVIDERS, ModelClient, ModelError
from ninny.pricing import Pricing
from ninny.sandbox import SandboxError, build_sandbox, find_bwrap
from ninny.tdd import MODES, TDDPolicy


# ------------------------------------------------------------------------ run
def resolve_prompt_mode(tdd: str, prompt: str) -> str:
    """Which `## Testing` block the model reads.

    The gate and the words are separate axes. `request` is the loose gate: it measures the
    order without refusing anything. On its own it used to ship a block that said there
    was no rule about the order -- measured at red-first 2/6 and $0.0245 an arm, against
    6/6 and $0.0140 for the same gate with the enforced wording, with zero refusals in
    either cell. The wording was the whole intervention, so the wording is what a run that
    asks for nothing now carries: TOLD by default, and blocked only if you say `enforce`.

    Two modes are exempt, for different reasons. `off` promises not to mention testing at
    all. `reverse` keeps its own block because the enforced text describes the opposite
    sequence (test, fail, then implement) and telling a reverse run that would be a lie.
    """
    if prompt:
        return prompt
    return "enforce" if tdd == "request" else tdd


def cmd_run(args: argparse.Namespace) -> int:
    task = load_task(args.task)
    base_url, api_key, wire = resolve_endpoint(args)
    logs.register_secret(api_key)  # the process holding the key writes the log
    pricing = Pricing(base_url, api_key, price_file=args.price_file, fetch=not args.no_price_fetch)
    steps = args.steps or task.step_limit

    out_root = (Path(args.out).expanduser() if args.out else Path("runs")).resolve() / task.name
    name = args.name or _default_name(args.model, args.tdd)
    run_dir = archive_if_exists(out_root / name, args.force)
    workdir = run_dir / "tree"
    shutil.copytree(task.tree_src, workdir, symlinks=True, dirs_exist_ok=False)

    sandbox = build_sandbox(args.sandbox, args.bwrap_path, share_net=args.sandbox_net)
    ok, note = sandbox.plan(workdir)
    print(f"ninny {__version__}: {note}")
    if not ok:
        print("ninny: refusing to run without a working sandbox that was asked for", file=sys.stderr)
        return 2
    if task.preflight:
        failures = [item for item in sandbox.check(task.preflight, workdir) if not item[1]]
        for command, good, output in sandbox.check(task.preflight, workdir):
            print(f"  preflight {'ok  ' if good else 'FAIL'} {command}  {output[:80]}")
        if failures:
            print(
                "ninny: a preflight command does not work inside the sandbox. Refusing to score "
                "this run: a sandbox that hides the toolchain would blame the model for it.",
                file=sys.stderr,
            )
            return 2
    if task.oracle_dir is not None:
        visible = sandbox.hides(task.oracle_dir, workdir)
        if visible is False and not args.allow_oracle_visible:
            print(
                f"ninny: the oracle at {task.oracle_dir} IS readable from the working tree. The "
                "agent could write its tests from the answer key, which makes the test-first "
                "record meaningless. Use --sandbox bwrap, or pass --allow-oracle-visible to "
                "proceed and accept an unattributable result.",
                file=sys.stderr,
            )
            return 2

    environment = Environment(
        workdir,
        sandbox,
        timeout=args.timeout or task.timeout_s,
        test_cmd=task.test_cmd,
        test_timeout=task.test_timeout_s,
        allow_outside=args.allow_outside,
    )
    policy = TDDPolicy(args.tdd, task, workdir, require_green=not args.allow_red_submit)
    client = ModelClient(
        model=args.model,
        base_url=base_url,
        api_key=api_key,
        wire=wire,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.request_timeout,
    )

    print(f"  task     {task.name}  ({task.root})")
    print(f"  model    {args.model}  via {base_url}  wire={wire}")
    print(f"  pricing  {pricing.describe(args.model)}")
    print(f"  tdd      {args.tdd}   steps<={steps}   workdir={workdir}")
    print(f"  run      {run_dir}")
    print()

    agent = Agent(
        client=client,
        environment=environment,
        policy=policy,
        task=task,
        workdir=workdir,
        run_dir=run_dir,
        pricing=pricing,
        step_limit=steps,
        wall_time_limit=args.wall_time,
        sandbox_note=sandbox.plan(workdir)[1],
        prompt_mode=resolve_prompt_mode(args.tdd, args.tdd_prompt),
        log=(lambda _line: None) if args.quiet else print,
    )
    result = agent.run()
    diff_stat = write_diff(task.tree_src, workdir, run_dir / "diff.patch")

    print()
    print(f"=== {result.exit_status} ===")
    print(result.summary())
    print(f"  diff:       {diff_stat}")
    print(f"  trajectory: {run_dir / 'trajectory.md'}")
    print(f"  patch:      {run_dir / 'diff.patch'}")
    print(f"  log:        {_log_path()}")
    print()
    print(f"next, BY HAND: ninny check --task {task.root} --tree {workdir}")
    _record(
        args,
        task=task.name,
        model=args.model,
        exit_status=result.exit_status,
        steps=result.steps,
        cost_usd=result.cost,
        verdict=(result.tdd or {}).get("verdict") if isinstance(result.tdd, dict) else None,
        run_dir=run_dir,
    )
    return 0 if result.exit_status == "Submitted" else 1


# -------------------------------------------------------------------- staging
def _stage(task, tree: Path, base: Path, label: str = "") -> Path:
    """A submission and the oracle, side by side, outside the submission.

    Absolute paths throughout: NINNY_TREE is handed to the oracle, which runs with
    cwd inside the staging directory, so a relative path would resolve against the
    wrong place and the oracle would grade a directory that is not there. That bug
    produced a confident pass that meant nothing, which is why it is spelled out.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S") + (f"-{label}" if label else "")
    work = (base / stamp).resolve()
    index = 1
    while work.exists():  # two checks in the same second must not collide
        work = (base / f"{stamp}-{index}").resolve()
        index += 1
    work.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tree, work / "tree", symlinks=True)
    if task.oracle_dir is not None:
        shutil.copytree(task.oracle_dir, work / "oracle", symlinks=True)
    return work


def _run_oracle(task, work: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["NINNY_TREE"] = str(work / "tree")
    env["NINNY_ORACLE"] = str(work / "oracle")
    completed = subprocess.run(task.oracle_cmd, shell=True, cwd=str(work), env=env,
                               capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    (work / "oracle.log").write_text(output)
    return completed.returncode, output


def _run_own_suite(task, work: Path) -> tuple[int, str]:
    """The task's own test command, in a staged tree, with no sandbox.

    This is about the task, not about a model: a tree whose own suite already fails
    sends the agent chasing pre-existing failures instead of the actual work.
    """
    try:
        completed = subprocess.run(task.test_cmd, shell=True, cwd=str(work / "tree"),
                                   capture_output=True, text=True,
                                   timeout=max(600, task.test_timeout_s))
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {max(600, task.test_timeout_s)}s\n"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


# ---------------------------------------------------------------------- check
def cmd_check(args: argparse.Namespace) -> int:
    task = load_task(args.task)
    tree = Path(args.tree).expanduser().resolve()
    if not tree.is_dir():
        print(f"ninny: {tree} is not a directory", file=sys.stderr)
        return 2
    if not task.oracle_cmd:
        print(f"ninny: task {task.name} declares no oracle_cmd", file=sys.stderr)
        return 2

    base = Path(args.out).expanduser() if args.out else (Path(args.task).expanduser() / "checks")
    work = _stage(task, tree, base)
    print(f"ninny check: {task.oracle_cmd}   (cwd={work}, NINNY_TREE={work / 'tree'})")
    code, output = _run_oracle(task, work)
    print(output.rstrip())
    print(f"\nexit {code}   log: {work / 'oracle.log'}")
    _record(args, task=task.name, verdict=_last_line(output))
    return code


# ---------------------------------------------------------------- verify-task
def cmd_verify(args: argparse.Namespace) -> int:
    """Prove a task grades the way it must, before any money is spent on it.

    Both directions, because either one alone is a trap. An oracle that never fails
    cannot tell you a submission is right -- it would say the task was solved by the
    stub. An oracle that never passes cannot tell you the task is solvable at all.
    A task that has not passed both is untrusted, and says so.
    """
    task = load_task(args.task)
    base = Path(args.out).expanduser() if args.out else (Path(args.task).expanduser() / "checks")

    fixed: Path | None = None
    if args.fixed:
        fixed = Path(args.fixed).expanduser().resolve()
    elif task.meta.get("fixed_tree"):
        fixed = (task.root / str(task.meta["fixed_tree"])).resolve()

    print(f"ninny verify-task: {task.name}  ({task.root})")
    checks: list[tuple[str, str, str]] = []

    given = _stage(task, task.tree_src, base, "given")

    code, output = _run_own_suite(task, given)
    (given / "own-tests.log").write_text(output)
    # Informational, never fatal. A runner that fails on an empty suite is a good
    # runner -- that is what stops a vacuous suite from counting as a pass -- so a
    # red start is expected for a task whose suite begins empty, and the keeper is
    # the one who knows which case this is.
    if code == 0:
        checks.append(("INFO", "the tree the agent starts from is already green under its own test command", f"exit {code}"))
    else:
        checks.append((
            "INFO",
            "own test command fails on the tree the agent starts from",
            f"exit {code} -- expected when the suite starts empty and the runner fails on an "
            "empty suite; otherwise the agent will chase failures it did not cause",
        ))

    if not task.oracle_cmd:
        checks.append(("FAIL", "the task declares an oracle_cmd", "no oracle_cmd in task.toml"))
    else:
        code, _ = _run_oracle(task, given)
        if code != 0:
            checks.append(("PASS", "oracle is RED on the given tree", f"exit {code}"))
        else:
            checks.append(
                ("FAIL", "oracle is RED on the given tree",
                 "exit 0 -- it passes on the tree the agent starts from, so it grades nothing")
            )

    if not task.oracle_cmd or fixed is None or not fixed.is_dir():
        detail = ("no oracle_cmd" if not task.oracle_cmd else
                  "no fixed tree: pass --fixed PATH, or set fixed_tree in task.toml")
        checks.append(("SKIP", "oracle is GREEN on the fixed tree", detail))
    else:
        good = _stage(task, fixed, base, "fixed")
        code, _ = _run_oracle(task, good)
        if code == 0:
            checks.append(("PASS", "oracle is GREEN on the fixed tree", f"exit {code}"))
        else:
            checks.append(
                ("FAIL", "oracle is GREEN on the fixed tree",
                 f"exit {code} -- it does not pass on the known-good tree, so the task may be unsolvable")
            )

    print()
    for verdict, name, detail in checks:
        print(f"  {verdict:4}  {name}   ({detail})")
    print()

    failed = [c for c in checks if c[0] == "FAIL"]
    if failed:
        _record(args, task=task.name, verdict="BROKEN TASK")
        print(f"BROKEN TASK: {failed[0][1]}")
        return 1
    if any(c[0] == "SKIP" for c in checks):
        _record(args, task=task.name, verdict="UNVERIFIED")
        print("UNVERIFIED: not every control has been run, so this task is not trusted yet.")
        return 2
    _record(args, task=task.name, verdict="VERIFIED")
    print("VERIFIED: the oracle fails where it must, and passes where it must.")
    return 0


# --------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"ninny {__version__}  (a fork of {UPSTREAM} -- {UPSTREAM_URL})")
    print(f"python {sys.version.split()[0]} at {sys.executable}")
    third_party = _third_party_imports()
    print(f"third-party imports in ninny/: {third_party or 'none (standard library only)'}")
    bwrap = find_bwrap(args.bwrap_path)
    print(f"bubblewrap: {bwrap or 'not found (sandbox none is the only option)'}")
    if bwrap:
        probe = Path(args.out or ".").expanduser().resolve()
        sandbox = build_sandbox("bwrap", bwrap)
        ok, note = sandbox.plan(probe)
        print(f"  probe: {'ok' if ok else 'FAILED'} -- {note}")
    base_url, api_key, _ = resolve_endpoint(args)
    print(f"endpoint: {base_url}")
    pricing = Pricing(base_url, api_key, fetch=True)
    catalog = pricing._catalog_models()
    print(f"  catalogue: {len(catalog)} models" if catalog else "  catalogue: unavailable")
    for tool in ("g++", "clang++", "cmake", "ninja", "make", "git"):
        print(f"  tool {tool}: {shutil.which(tool) or 'MISSING'}")
    return 0


# -------------------------------------------------------------------- helpers
def resolve_endpoint(args) -> tuple[str, str, str]:
    if getattr(args, "base_url", None):
        base_url = args.base_url
        wire = getattr(args, "wire", "chat")
        key = getattr(args, "api_key", "") or os.environ.get("NINNY_API_KEY", "")
        return base_url.rstrip("/"), key, wire
    provider = getattr(args, "provider", None) or os.environ.get("NINNY_PROVIDER") or "local"
    if provider not in PROVIDERS:
        raise ModelError(
            f"unknown provider {provider!r}. Known: {', '.join(sorted(PROVIDERS))}. "
            "For anything else pass --base-url."
        )
    preset = PROVIDERS[provider]
    key = getattr(args, "api_key", "") or os.environ.get(preset["key_env"], "")
    wire = getattr(args, "wire", None) or preset["wire"]
    return preset["base_url"].rstrip("/"), key, wire


def _default_name(model: str, tdd: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-").split("-")[-1] or "run"
    return f"{slug}-{tdd}"


def archive_if_exists(run_dir: Path, force: bool) -> Path:
    if not run_dir.exists():
        return run_dir
    if not force:
        raise ConfigError(f"{run_dir} already exists; use --force to archive it and rerun")
    index = 1
    while (run_dir.parent / f"{run_dir.name}.rep{index}").exists():
        index += 1
    target = run_dir.parent / f"{run_dir.name}.rep{index}"
    run_dir.rename(target)
    print(f"archived previous run -> {target}")
    return run_dir


def _third_party_imports() -> list[str]:
    import ast

    package = Path(__file__).parent
    stdlib = set(sys.stdlib_module_names)
    found: set[str] = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name and name != "ninny" and name not in stdlib:
                    found.add(name)
    return sorted(found)


def _log_path() -> str:
    """Where this invocation's transcript is going, for the reader who has to find it."""
    session_log = logs.current()
    return str(session_log.path) if session_log is not None and session_log.path else "(no log)"


def _last_line(text: str) -> str:
    """The oracle's own last word -- its verdict, not a summary of ours."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:80] if lines else ""


def _log_name(args) -> str:
    """What to call this invocation in the log file name."""
    named = getattr(args, "name", None) or getattr(args, "task", None) or ""
    return Path(named).expanduser().name if named else ""


def _record(args, **fields: object) -> None:
    """Hand facts to `main`, which writes the one history line for this invocation.

    The write lives in one place on purpose. A run that dies in the middle still gets its
    line, because the line is written by the code that did not die -- otherwise the index
    would be a list of the runs that succeeded, which is exactly backwards.
    """
    current = dict(getattr(args, "_record", None) or {})
    current.update({key: value for key, value in fields.items() if value is not None})
    args._record = current


# -------------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ninny", description="a tiny coding-agent harness")
    parser.add_argument("--version", action="version", version=f"ninny {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="one model, one task")
    run.add_argument("--task", required=True, help="task directory (contains task.toml)")
    run.add_argument("--model", required=True, help="model id as the endpoint spells it")
    run.add_argument("--provider", help=f"one of {', '.join(sorted(PROVIDERS))}")
    run.add_argument("--base-url", help="any OpenAI-compatible endpoint; overrides --provider")
    run.add_argument("--api-key", help="defaults to the provider's environment variable")
    run.add_argument("--wire", choices=["chat", "completions"], help="protocol shape")
    run.add_argument("--tdd", choices=list(MODES), default="request",
                     help="what the gate does. request: measure the order, refuse nothing "
                          "(default) | enforce: also refuse src writes until a RED is seen "
                          "| reverse: code first, tests required before submit | off")
    run.add_argument("--sandbox", choices=["none", "bwrap"], default="none")
    run.add_argument("--bwrap-path", help="path to a bwrap binary, if it is not on PATH")
    run.add_argument("--sandbox-net", action="store_true", help="let the sandbox reach the network")
    run.add_argument("--steps", type=int, help="step limit (default: the task's)")
    run.add_argument("--wall-time", type=int, default=0, help="seconds; 0 = no limit")
    run.add_argument("--timeout", type=int, help="per bash action, seconds")
    run.add_argument("--request-timeout", type=int, default=600, help="per model call, seconds")
    run.add_argument("--temperature", type=float)
    run.add_argument("--max-tokens", type=int)
    run.add_argument("--out", help="output root (default: ./runs)")
    run.add_argument("--name", help="arm name (default: <model>-<tdd mode>)")
    run.add_argument("--price-file", help="JSON prices, overriding the endpoint's")
    run.add_argument("--no-price-fetch", action="store_true", help="do not ask /models for prices")
    run.add_argument("--allow-outside", action="store_true",
                     help="let the file tools touch paths outside the working tree")
    run.add_argument("--allow-oracle-visible", action="store_true",
                     help="run even though the agent can read the oracle (result is unattributable)")
    run.add_argument("--tdd-prompt", choices=MODES, default="",
                     help="which Testing block the model READS. Default: told -- the "
                          "enforced wording for --tdd request, and --tdd itself otherwise. "
                          "Setting it apart from --tdd is how 'told' and 'blocked' are "
                          "separated when you are measuring instead of working")
    run.add_argument("--allow-red-submit", action="store_true",
                     help="let a run submit while its own tests are still failing")
    run.add_argument("--force", action="store_true", help="archive an existing run and rerun")
    run.add_argument("--quiet", action="store_true")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", help="run the task's oracle on a submission, outside the tree")
    check.add_argument("--task", required=True)
    check.add_argument("--tree", required=True, help="the submission to judge")
    check.add_argument("--out", help="where to stage the check (default: <task>/checks)")
    check.set_defaults(func=cmd_check)

    verify = sub.add_parser(
        "verify-task",
        help="prove a task's oracle fails where it must and passes where it must",
    )
    verify.add_argument("--task", required=True)
    verify.add_argument("--fixed", help="a tree the task is known to be solvable on (the GREEN control)")
    verify.add_argument("--out", help="where to stage the checks (default: <task>/checks)")
    verify.set_defaults(func=cmd_verify)

    doctor = sub.add_parser("doctor", help="what this machine can do")
    doctor.add_argument("--provider")
    doctor.add_argument("--base-url")
    doctor.add_argument("--bwrap-path")
    doctor.add_argument("--out")
    doctor.set_defaults(func=cmd_doctor)

    # One flag on every subcommand, spelled once. A harness that writes into your home
    # directory had better have an off switch.
    for subparser in (run, check, verify, doctor):
        subparser.add_argument("--no-log", action="store_true",
                               help="no transcript log and no history line for this invocation")
    return parser


def main(argv: list[str] | None = None) -> int:
    """One invocation: a transcript, and one line in the index.

    The log wraps the whole command, the failure paths included, so a run that dies still
    leaves both. Otherwise "what has Ninny been doing?" would be answerable only for the
    runs that went right, which is exactly backwards.
    """
    args = build_parser().parse_args(argv)
    with logs.session(args.command, _log_name(args), enabled=not args.no_log) as session_log:
        try:
            code = args.func(args)
        except (ConfigError, SandboxError, ModelError) as exc:
            print(f"ninny: {exc}", file=sys.stderr)
            code = 2
        except KeyboardInterrupt:
            print("ninny: interrupted", file=sys.stderr)
            code = 130
    if not args.no_log:
        fields = dict(getattr(args, "_record", None) or {})
        fields.setdefault("exit_status", code)
        fields["log_file"] = session_log.path
        logs.record(args.command, **fields)
    return code
