"""The command line.

    ninny run         [--task TASK] --model MODEL [options]  one model, one task
    ninny check       [--task TASK] --tree TREE              run the oracle, outside the tree
    ninny verify-task [--task TASK] [--fixed TREE]           prove the task grades correctly
    ninny doctor                                             what this machine can do

`--task` defaults to `./.ninny`, so a project that keeps its fixtures there needs no flag.

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
import tempfile
import time
from pathlib import Path

from ninny import UPSTREAM, UPSTREAM_URL, __version__, logs, verdict
from ninny.agent import Agent
from ninny.artifacts import write_diff
from ninny.config import ConfigError, bash_timeout_for, load_task, repo_task
from ninny.env import Environment
from ninny.model import PROVIDERS, ModelClient, ModelError
from ninny.pricing import Pricing
from ninny.sandbox import SandboxError, build_sandbox, find_bwrap
from ninny.tdd import MODES, TDDPolicy, phases_line


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


DEFAULT_TASK_DIR = ".ninny"


def default_tdd_for(repo: bool, test_globs: list[str] | None) -> str:
    """The mode a run gets when `--tdd` was not passed.

    A benchmark task keeps `request`, which is what every measured arm ran under unless it said
    otherwise. A repository gets `enforce` only once the caller has declared which paths are the
    tests: the gate refuses a write into the source tree until a red has been seen, and on a
    repository whose suite is green, every way to make a red is itself a write. That is a
    deadlock, and a rule that can never be satisfied is indistinguishable from a broken harness.
    """
    return "enforce" if (repo and test_globs) else "request"


def repo_prompt(args: argparse.Namespace) -> str:
    """What to work on, from `--prompt` or `--prompt-file`.

    Required and not defaulted: a repository has no SPEC.md to stand in for it.
    """
    if args.prompt and args.prompt_file:
        raise ConfigError("--prompt and --prompt-file both given; pass one of them")
    if args.prompt_file:
        path = Path(args.prompt_file).expanduser()
        if not path.is_file():
            raise ConfigError(f"no such prompt file: {path}")
        return path.read_text()
    if not args.prompt:
        raise ConfigError(
            "repo mode needs --prompt TEXT or --prompt-file PATH: the prompt is the task, and "
            "there is no SPEC.md in a repository to read it from."
        )
    return args.prompt


def stage_worktree(repo: Path, workdir: Path) -> str:
    """A working copy of the repository at HEAD.

    A worktree rather than a copy: the run is isolated, `diff.patch` is then the run's own work,
    and the repository's own gate can run because git resolves through the main repository --
    which is why `repo_task` binds that path into the sandbox read-only. Measured: without the
    bind, git inside bwrap reports "not a git repository"; with it, status/diff/log work and
    add/commit fail cleanly against the read-only bind.
    """
    workdir.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(workdir), "HEAD"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ConfigError(f"could not stage a worktree of {repo}: {proc.stderr.strip()[:200]}")
    # Return the commit it was staged at: that is the only correct basis for the run's patch,
    # because the live tree moves while a run is going and this one does not.
    return subprocess.run(["git", "-C", str(workdir), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def write_worktree_diff(worktree: Path, base: str, out_path: Path) -> str:
    """The run's own work: `git diff` in the worktree against the commit it was staged at.

    Not a comparison against the live tree. A worktree is pinned to a commit that does not move
    while a run is going, and the live tree does move: a commit landing mid-run reads as the
    delegate having deleted it, and every gitignored file present on disk but absent from a fresh
    checkout reads as another deletion. Measured on the first repository run -- 30.8 MB, 2,224
    file headers, 482,462 removed lines -- for a change of ten lines.

    Staged first, because `git diff` alone misses a file the delegate created, which is usually
    the point: a new test file. `git add -A` respects .gitignore, so build residue stays out. The
    index it writes belongs to a disposable worktree.
    """
    staged = subprocess.run(["git", "-C", str(worktree), "add", "-A"],
                            capture_output=True, text=True)
    if staged.returncode != 0:
        raise ConfigError(f"could not stage the worktree: {staged.stderr.strip()[:200]}")
    diff = subprocess.run(["git", "-C", str(worktree), "diff", "--cached", "--binary", base],
                          capture_output=True, text=True)
    if diff.returncode != 0:
        raise ConfigError(f"could not diff the worktree: {diff.stderr.strip()[:200]}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(diff.stdout or "(no changes)\n")
    stat = subprocess.run(["git", "-C", str(worktree), "diff", "--cached", "--shortstat", base],
                          capture_output=True, text=True).stdout.strip()
    return stat or "no changes"


def preflight_lines(task, workdir: Path, prompt_text: str,
                    args: argparse.Namespace) -> tuple[list[str], str]:
    """What the caller is about to spend, said before the model runs, plus a refusal when the
    invocation cannot be satisfied at all.

    Written after two repository runs spent their whole budget reading a brief that named ten files and
    never wrote anything (40 of 40 and 30 of 30 steps). Both times the reasonable question afterwards was
    "why did it read for forty steps", and both times the answer was a number the caller had not been
    shown -- the brief's own reading list against the budget set for it.

    Every line is a count or a comparison, never a judgement: whether a task is well-posed is not
    mechanically checkable, and a tool that pretends otherwise is worse than one that states facts.

    Returns (lines, refusal); refusal is "" when the invocation can work.
    """
    import re

    tree = Path(workdir)
    units = sorted(p for p in tree.rglob("*") if p.suffix in {".cpp", ".cc", ".cxx", ".c"} and p.is_file())
    tests = sorted(p for p in tree.rglob("*") if p.suffix in {".cpp", ".cc", ".cxx", ".py", ".js", ".ts"}
                   and p.is_file() and "test" in str(p.relative_to(tree)).lower())
    lines = [
        f"{len(units)} translation units, {len(tests)} test sources, budget {args.steps} steps",
        f"suite `{task.test_cmd}` gets {task.test_timeout_s}s; a single bash action gets "
        f"{bash_timeout_for(task.test_timeout_s, args.timeout)}s",
    ]

    # Which paths the brief names, and whether they are there to be read. A brief that names nothing
    # that exists has no entry point to start from, which is a fact worth stating out loud.
    text = prompt_text
    named = sorted(set(re.findall(r"[\w./-]*[\w-]+\.(?:cpp|cc|cxx|hpp|hh|h|py|js|ts|sh|md|txt|json|toml)",
                                  text)))
    missing = [name for name in named if not (tree / name).exists()]
    if named:
        lines.append(f"the brief names {len(named)} paths; {len(named) - len(missing)} exist in the tree"
                     + (f", missing: {', '.join(missing[:4])}" if missing else ""))
        if len(missing) == len(named):
            lines.append("WARNING: the brief names no path that exists in the tree -- there is no entry "
                         "point to start from, which is how a run spends its whole budget reading")
    else:
        lines.append("the brief names no file path at all -- no entry point to start from")

    if args.tdd == "enforce" and not args.test_glob:
        return lines, (
            "REFUSING: --tdd enforce without --test-glob cannot be satisfied. enforce refuses a source "
            "write until a test has been seen failing, and with no test glob the only thing that can make "
            "a red is a write it will refuse. Pass --test-glob (e.g. --test-glob 'tests/*'), or use "
            "--tdd request."
        )
    return lines, ""


def _task_path(raw: str | None) -> Path:
    """`--task`, or the convention directory when the flag is omitted.

    A convention, not magic: the resolved path is echoed in the plan line before anything
    is spent, and a missing `.ninny` names itself instead of failing further in.
    """
    if raw:
        return Path(raw).expanduser()
    default = Path(DEFAULT_TASK_DIR)
    if not (default / "task.toml").is_file():
        raise ConfigError(
            f"no {DEFAULT_TASK_DIR}/task.toml in {Path.cwd()} "
            f"(that is the default when --task is omitted); pass --task PATH"
        )
    return default


def cmd_run(args: argparse.Namespace) -> int:
    if args.repo and args.task:
        raise ConfigError("--repo and --task are different doors: pass one of them")
    args.tdd = args.tdd or default_tdd_for(bool(args.repo), args.test_glob)
    task = (
        repo_task(Path(args.repo), repo_prompt(args), args.test_cmd or "",
                  test_globs=args.test_glob, step_limit=args.steps or 60)
        if args.repo
        else load_task(_task_path(args.task))
    )
    base_url, api_key, wire = resolve_endpoint(args)
    logs.register_secret(api_key)  # the process holding the key writes the log
    pricing = Pricing(base_url, api_key, price_file=args.price_file, fetch=not args.no_price_fetch)
    steps = args.steps or task.step_limit

    out_root = (Path(args.out).expanduser() if args.out else Path("runs")).resolve() / task.name
    name = args.name or _default_name(args.model, args.tdd)
    run_dir = archive_if_exists(out_root / name, args.force)
    workdir = run_dir / "tree"
    base_sha = ""
    if args.repo:
        base_sha = stage_worktree(task.tree_src, workdir)
    else:
        shutil.copytree(task.tree_src, workdir, symlinks=True, dirs_exist_ok=False)

    sandbox = build_sandbox(
        args.sandbox,
        args.bwrap_path,
        share_net=args.sandbox_net,
        binds=task.sandbox_binds,
    )
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
        timeout=bash_timeout_for(task.test_timeout_s, args.timeout),
        test_cmd=task.test_cmd,
        test_timeout=task.test_timeout_s,
        allow_outside=args.allow_outside,
    )
    if args.repo:
        lines, refusal = preflight_lines(task, workdir, repo_prompt(args), args)
        for line in lines:
            print(f"preflight: {line}")
        if refusal:
            print(f"preflight: {refusal}")
            return 2
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
    print(f"  phases   {phases_line()}   (a test that never ran is not a red)")
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
    diff_stat = (
        write_worktree_diff(workdir, base_sha, run_dir / "diff.patch")
        if args.repo
        else write_diff(task.tree_src, workdir, run_dir / "diff.patch")
    )

    print()
    print(f"=== {result.exit_status} ===")
    print(result.summary())
    print(f"  diff:       {diff_stat}")
    print(f"  trajectory: {run_dir / 'trajectory.md'}")
    print(f"  patch:      {run_dir / 'diff.patch'}")
    print(f"  log:        {_log_path()}")
    print()
    print(f"next, BY HAND: ninny check --task {task.root} --tree {workdir}")
    if args.repo:
        print(f"next, BY HAND: ninny verdict {run_dir}")
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
def _default_check_base(task) -> Path:
    """Where `check` and `verify-task` stage trees when no --out is given.

    NOT inside the task directory. Staging there copied the task, built it, and left the
    build output behind: verifying all eight tasks repeatedly grew the repository past
    1 GB, and every `verify-task` added tens of megabytes of gitignored debris to a tree
    that is meant to be source. A check is disposable, so its scratch lives in the OS
    temp dir; pass --out when the artifacts are wanted somewhere specific.
    """
    return Path(tempfile.gettempdir()) / "ninny-checks" / task.name


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


# Exit codes that mean "the oracle ran and said no", and codes that mean "it never ran".
# 2 is the contract's "could not run"; 126/127 are the shell's "not executable"/"not found".
# Anything else non-zero is a program that ran and failed. The distinction matters because
# "the oracle is RED on the starting tree" is a CONTROL: a 127 (a typo'd script name, a
# missing interpreter) would otherwise count as proof that the oracle rejects a stub, when
# in fact it never executed a line.
_NEVER_RAN_CODES = {2, 126, 127}


def _oracle_said_no(code: int) -> bool:
    """True when the oracle ran and rejected the tree -- a real RED."""
    return code != 0 and code not in _NEVER_RAN_CODES


def _oracle_exit_note(code: int) -> str:
    """The parenthetical that goes next to a control's verdict."""
    if code in _NEVER_RAN_CODES:
        return f"exit {code} -- the oracle did not run at all, so this proves nothing"
    return f"exit {code}"


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
    task = load_task(_task_path(args.task))
    tree = Path(args.tree).expanduser().resolve()
    if not tree.is_dir():
        print(f"ninny: {tree} is not a directory", file=sys.stderr)
        return 2
    if not task.oracle_cmd:
        print(f"ninny: task {task.name} declares no oracle_cmd", file=sys.stderr)
        return 2

    base = Path(args.out).expanduser() if args.out else _default_check_base(task)
    work = _stage(task, tree, base)
    print(f"ninny check: {task.oracle_cmd}   (cwd={work}, NINNY_TREE={work / 'tree'})")
    code, output = _run_oracle(task, work)
    print(output.rstrip())
    print(f"\nexit {code}   log: {work / 'oracle.log'}")
    _record(args, task=task.name, verdict=_last_line(output))
    return code


# ---------------------------------------------------------------- verdict


def cmd_verdict(args: argparse.Namespace) -> int:
    """Say whether a run's handback is evidence, in one line, and exit with the answer.

    The exit code is the API: 0 artifact present, 1 handed back unproven (`reasons` says how),
    2 nothing was handed back. A caller applies the patch on 0 and can say why; a caller that
    refuses on 1 routes on `reasons`; a caller that sees 2 knows no delegate opinion is being
    graded at all.
    """
    where = Path(args.run).expanduser()
    run_dir = where if where.is_dir() else where.parent
    record = where / "result.json" if where.is_dir() else where
    if not record.is_file():
        print(json.dumps({"verdict": "no-handback", "exit": verdict.EXIT_NO_HANDBACK,
                          "run": str(where), "reasons": [f"no result.json at {where}"]},
                         sort_keys=True))
        return verdict.EXIT_NO_HANDBACK
    try:
        result = json.loads(record.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"verdict": "no-handback", "exit": verdict.EXIT_NO_HANDBACK,
                          "run": str(run_dir), "reasons": [f"unreadable record: {error}"]},
                         sort_keys=True))
        return verdict.EXIT_NO_HANDBACK
    code, line = verdict.verdict_of(result)
    line["run"] = str(run_dir)
    patch = run_dir / "diff.patch"
    line["patch"] = str(patch) if patch.is_file() else None
    print(json.dumps(line, sort_keys=True))
    return code


# ---------------------------------------------------------------- verify-task
def cmd_verify(args: argparse.Namespace) -> int:
    """Prove a task grades the way it must, before any money is spent on it.

    Both directions, because either one alone is a trap. An oracle that never fails
    cannot tell you a submission is right -- it would say the task was solved by the
    stub. An oracle that never passes cannot tell you the task is solvable at all.
    A task that has not passed both is untrusted, and says so.
    """
    task = load_task(_task_path(args.task))
    base = Path(args.out).expanduser() if args.out else _default_check_base(task)

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
        if _oracle_said_no(code):
            checks.append(("PASS", "oracle is RED on the given tree", _oracle_exit_note(code)))
        elif code != 0:
            # The oracle never ran. That is a broken oracle, not a passing control, and the
            # difference decides whether the task gets a model's money spent on it.
            checks.append(("FAIL", "oracle is RED on the given tree", _oracle_exit_note(code)))
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
            checks.append(("PASS", "oracle is GREEN on the fixed tree", _oracle_exit_note(code)))
        elif not _oracle_said_no(code):
            checks.append(("FAIL", "oracle is GREEN on the fixed tree", _oracle_exit_note(code)))
        else:
            checks.append(
                ("FAIL", "oracle is GREEN on the fixed tree",
                 f"exit {code} -- it does not pass on the known-good tree, so the task may be unsolvable")
            )

    # The third control: the task's own runner must report a planted failing test as a red.
    #
    # Both controls above grade the ORACLE, and neither ever runs test_cmd against a case it
    # can see failing -- which is how `tasks/intset` shipped a genuine red reported as exit 2
    # ("nothing ran") and `tasks/bits` shipped refusing the edit it required, while both
    # passed every control here for weeks.
    #
    # The dataset has to be a PLANTED test, not a broken answer key: the answer key carries no
    # suite (the agent writes that), so `test_cmd` on it correctly answers 2 -- "nothing ran" --
    # and asks the runner nothing. Measured on all four tasks that were tried that way.
    control_red = "own test command reports a planted failing test as a red"
    recipe = str(task.meta.get("probe_cmd") or "").strip()
    if not recipe:
        checks.append(("INFO", control_red,
                       "no probe_cmd in task.toml, so this control did not run"))
    else:
        # A separate staged copy of the tree the agent starts from: the probe must never
        # touch the task on disk.
        probed = _stage(task, task.tree_src, base, "probe")
        try:
            done = subprocess.run(recipe, shell=True, cwd=str(probed), capture_output=True,
                                  text=True, timeout=max(600, task.test_timeout_s))
        except subprocess.TimeoutExpired:
            checks.append(("FAIL", control_red,
                           f"the probe recipe timed out after {max(600, task.test_timeout_s)}s"))
        else:
            if done.returncode != 0:
                # A recipe that did not land plants nothing, and the suite is then green for a
                # reason that has nothing to do with the runner: say which it was.
                checks.append(("FAIL", control_red,
                               f"the probe recipe exited {done.returncode} -- it did not land, "
                               "so no failing test was planted"))
            else:
                code, output = _run_own_suite(task, probed)
                (probed / "own-tests.log").write_text(output)
                if code == 1:
                    checks.append(("PASS", control_red,
                                   "exit 1 -- it ran, and failed, which is what a red is"))
                elif code == 0:
                    checks.append(("FAIL", control_red,
                                   "exit 0 -- the suite passed with a failing test planted, so "
                                   "it cannot see a red"))
                elif code in (126, 127):
                    checks.append(("FAIL", control_red,
                                   f"exit {code} -- the test command could not be run at all in "
                                   "the probed tree"))
                else:
                    checks.append(("FAIL", control_red,
                                   f"exit {code} -- nothing ran for a planted failing test: the "
                                   "runner misreports a red as a build error"))

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
    # Say how much was actually proven. A task with no sabotage recipe is not a task with a
    # runner that lies -- it is a task whose runner nobody has asked yet.
    ran = [c for c in checks if c[0] == "PASS"]
    absent = [c for c in checks if c[0] == "INFO" and "did not run" in c[2]]
    note = f"{len(ran)} controls ran"
    if absent:
        note += f"; {len(absent)} did not: {absent[0][1]} ({absent[0][2]})"
    print(f"VERIFIED: the oracle fails where it must, and passes where it must.  ({note})")
    return 0


# ---------------------------------------------------------------------- runner
def cmd_runner(args: argparse.Namespace) -> int:
    """A task's adapter, from its config: print it, write it, or check the one on disk.

    The adapter is the only part of Ninny that has to know a language: it turns a toolchain's
    output into the 0/1/2 contract. Six of them were hand-written, 41-72 lines each, and every
    defect of the 2026-10-23 campaign lived in that layer -- so it became a nine-key config
    (`ninny/runner.py`) rendered into the tree. Rendered, not interpreted: the file stays real,
    the agent still reads it, the gate checks it against its config, and `test_cmd` is unchanged.
    """
    from .runner import config_for, drift, render, rendered_path

    task = load_task(_task_path(args.task))
    config = config_for(task.meta)
    if config is None:
        print(f"ninny runner: {task.name} declares no [runner] table -- it brings its own adapter")
        return 0
    if args.check:
        ok, note = drift(task.root, task.meta)
        print(f"  {'ok  ' if ok else 'FAIL'}  {task.name}: {note}")
        _record(args, task=task.name, verdict="RUNNER-OK" if ok else "RUNNER-DRIFT")
        return 0 if ok else 1
    script = render(config)
    if args.write:
        from .runner import rendered_paths

        for target in rendered_paths(task.root, task.meta):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(script)
            target.chmod(0o755)
            print(f"wrote {target}  ({len(script.splitlines())} lines, rendered from [runner])")
        return 0
    print(script, end="")
    return 0


# --------------------------------------------------------------------- doctor
def _task_tools(task_root: Path) -> list[str]:
    """The executables a task actually asks for: its preflight, and its adapter's own commands.

    Doctor used to name a fixed list of C++ tools, which is the one place the harness knew a
    language. A task declares what it needs; this reads that instead.
    """
    task = load_task(task_root)
    tools: list[str] = []
    for entry in task.meta.get("preflight", []) or []:
        tools.append(str(entry).split()[0])
    table = task.meta.get("runner") or {}
    for key in ("build", "run"):
        command = str(table.get(key) or "").strip()
        if not command:
            continue
        first = command.split(";")[0].split("&&")[0].strip().split()[0]
        # A leading VAR=value is a shell assignment, and ./x is the task's own built artefact:
        # neither is a tool this machine must have before the task can run.
        if "=" in first or first.startswith((".", "/", "$")):
            continue
        tools.append(first)
    return [tool for tool in dict.fromkeys(tools) if tool]


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
    for tool in ("python3", "git"):
        print(f"  tool {tool}: {shutil.which(tool) or 'MISSING'}")
    roots: list[Path] = []
    if getattr(args, "task", None):
        roots = [_task_path(args.task)]
    elif Path("tasks").is_dir():
        roots = sorted(p for p in Path("tasks").iterdir() if p.is_dir())
    for root in roots:
        try:
            tools = _task_tools(root)
        except Exception as exc:  # a task this machine cannot even read is worth saying
            print(f"  task {root.name}: unreadable ({exc})")
            continue
        state = ", ".join(f"{tool} {'ok' if shutil.which(tool) else 'MISSING'}" for tool in tools)
        print(f"  task {root.name} needs: {state or 'nothing declared'}")
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
                if node.level:  # a relative import: `from .runner import ...` is ours
                    continue
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
    run.add_argument("--task", help="task directory (contains task.toml); default ./.ninny")
    run.add_argument("--repo", help="work on a git repository directly: a worktree at HEAD, no "
                                    "fixture, no oracle. Needs --prompt (or --prompt-file) and "
                                    "--test-cmd; see --test-glob for the red-first gate")
    run.add_argument("--prompt", help="what to do, for --repo: the task text")
    run.add_argument("--prompt-file", help="what to do, for --repo: a file to read it from")
    run.add_argument("--test-cmd", help="how the change is exercised, for --repo. Required, and "
                                       "never guessed: repos differ, and a wrong guess is worse")
    run.add_argument("--test-glob", action="append",
                     help="a path pattern that is a test file, for --repo (repeatable). Declaring "
                          "one turns on the red-first gate; without it the run records the order "
                          "and enforces the handback instead")
    run.add_argument("--model", required=True, help="model id as the endpoint spells it")
    run.add_argument("--provider", help=f"one of {', '.join(sorted(PROVIDERS))}")
    run.add_argument("--base-url", help="any OpenAI-compatible endpoint; overrides --provider")
    run.add_argument("--api-key", help="defaults to the provider's environment variable")
    run.add_argument("--wire", choices=["chat", "completions"], help="protocol shape")
    run.add_argument("--tdd", choices=list(MODES), default=None,
                     help="what the gate does. request: measure the order, refuse nothing "
                          "(default for a task) | enforce: also refuse src writes until a RED is "
                          "seen (default for --repo once --test-glob is given)"
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
    check.add_argument("--task", help="task directory (contains task.toml); default ./.ninny")
    check.add_argument("--tree", required=True, help="the submission to judge")
    check.add_argument("--out", help="where to stage the check (default: $TMPDIR/ninny-checks/<task>)")
    check.set_defaults(func=cmd_check)

    verdict_parser = sub.add_parser(
        "verdict", help="say whether a run's handback is evidence, in one line")
    verdict_parser.add_argument("run", help="a run directory, or the path to its result.json")
    verdict_parser.set_defaults(func=cmd_verdict)

    verify = sub.add_parser(
        "verify-task",
        help="prove a task's oracle fails where it must and passes where it must",
    )
    verify.add_argument("--task", help="task directory (contains task.toml); default ./.ninny")
    verify.add_argument("--fixed", help="a tree the task is known to be solvable on (the GREEN control)")
    verify.add_argument("--out", help="where to stage the checks (default: $TMPDIR/ninny-checks/<task>)")
    verify.set_defaults(func=cmd_verify)

    runner = sub.add_parser("runner", help="a task's adapter, rendered from its [runner] config")
    runner.add_argument("--task", help="task directory (contains task.toml); default ./.ninny")
    runner.add_argument("--write", action="store_true",
                        help="write the rendered adapter into the tree")
    runner.add_argument("--check", action="store_true",
                        help="fail when the adapter on disk differs from the config")
    runner.set_defaults(func=cmd_runner)

    doctor = sub.add_parser("doctor", help="what this machine can do")
    doctor.add_argument("--task", help="report the tools one task needs; default: every task here")
    doctor.add_argument("--provider")
    doctor.add_argument("--base-url")
    doctor.add_argument("--bwrap-path")
    doctor.add_argument("--out")
    doctor.set_defaults(func=cmd_doctor)

    # One flag on every subcommand, spelled once. A harness that writes into your home
    # directory had better have an off switch. `build_parser`'s own test walks the commands and
    # refuses a subparser that never joined this loop -- `verdict` shipped without it once and
    # every unit test passed while the real command died in `main()`.
    for subparser in (run, check, verdict_parser, verify, doctor, runner):
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
