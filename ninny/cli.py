"""The command line.

    ninny run    --task TASK --model MODEL [options]   one model, one task
    ninny check  --task TASK --tree TREE               run the oracle, outside the tree
    ninny doctor                                       what this machine can do

Nothing here runs the oracle as part of a run. Deciding whether a submission is
correct is the keeper's job and is done by hand, per run: an evaluation whose
harness grades its own subject is not an evaluation.
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

from ninny import UPSTREAM, UPSTREAM_URL, __version__
from ninny.agent import Agent
from ninny.config import ConfigError, load_task
from ninny.env import Environment
from ninny.model import PROVIDERS, ModelClient, ModelError
from ninny.pricing import Pricing
from ninny.sandbox import SandboxError, build_sandbox, find_bwrap
from ninny.tdd import MODES, TDDPolicy


# ------------------------------------------------------------------------ run
def cmd_run(args: argparse.Namespace) -> int:
    task = load_task(args.task)
    base_url, api_key, wire = resolve_endpoint(args)
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
    policy = TDDPolicy(args.tdd, task, workdir)
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
        log=(lambda _line: None) if args.quiet else print,
    )
    result = agent.run()

    print()
    print(f"=== {result.exit_status} ===")
    print(result.summary())
    print(f"  trajectory: {run_dir / 'trajectory.md'}")
    print()
    print(f"next, BY HAND: ninny check --task {task.root} --tree {workdir}")
    return 0 if result.exit_status == "Submitted" else 1


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

    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = Path(args.out).expanduser() if args.out else (Path(args.task).expanduser() / "checks")
    # Absolute from here on: NINNY_TREE is handed to the oracle, which runs with
    # cwd inside the staging directory, so a relative path would resolve against
    # the wrong place and the oracle would grade a directory that isn't there.
    work = (base / stamp).resolve()
    index = 1
    while work.exists():  # two checks in the same second must not collide
        work = (base / f"{stamp}-{index}").resolve()
        index += 1
    work.mkdir(parents=True, exist_ok=True)
    # The oracle runs beside a COPY of the submission, never inside it, so a
    # checking script cannot pollute the artifact it is judging.
    shutil.copytree(tree, work / "tree", symlinks=True)
    if task.oracle_dir is not None:
        shutil.copytree(task.oracle_dir, work / "oracle", symlinks=True)

    env = dict(os.environ)
    env["NINNY_TREE"] = str(work / "tree")
    env["NINNY_ORACLE"] = str(work / "oracle")
    print(f"ninny check: {task.oracle_cmd}   (cwd={work}, NINNY_TREE={work / 'tree'})")
    completed = subprocess.run(task.oracle_cmd, shell=True, cwd=str(work), env=env,
                               capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    (work / "oracle.log").write_text(output)
    print(output.rstrip())
    print(f"\nexit {completed.returncode}   log: {work / 'oracle.log'}")
    return completed.returncode


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
                     help="request: measure only (default) | enforce: refuse src writes until RED "
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
    run.add_argument("--force", action="store_true", help="archive an existing run and rerun")
    run.add_argument("--quiet", action="store_true")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", help="run the task's oracle on a submission, outside the tree")
    check.add_argument("--task", required=True)
    check.add_argument("--tree", required=True, help="the submission to judge")
    check.add_argument("--out", help="where to stage the check (default: <task>/checks)")
    check.set_defaults(func=cmd_check)

    doctor = sub.add_parser("doctor", help="what this machine can do")
    doctor.add_argument("--provider")
    doctor.add_argument("--base-url")
    doctor.add_argument("--bwrap-path")
    doctor.add_argument("--out")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, SandboxError, ModelError) as exc:
        print(f"ninny: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ninny: interrupted", file=sys.stderr)
        return 130
