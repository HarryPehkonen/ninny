"""Task and run configuration.

A **task** is a directory containing:

    task.toml      the declaration below
    SPEC.md        what the model is given (name configurable)
    tree/          the starting tree, copied for each run
    oracle/        the real acceptance suite -- NEVER copied into the run

The oracle lives outside the tree on purpose. If the model could read the
acceptance suite it could derive its own tests from the answer key instead of
from the spec, which makes both "did it write tests" and "did it write them
first" meaningless. `load_task` refuses a task that gets this wrong.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path


class ConfigError(Exception):
    """A misconfigured task or run. Always loud: a silently wrong eval is worse."""


def _matches(rel: str, globs: list[str]) -> bool:
    """Match a posix relative path against globs, supporting a 'dir/**' prefix."""
    for g in globs:
        if g.endswith("/**"):
            if rel == g[:-3] or rel.startswith(g[:-3] + "/"):
                return True
        elif fnmatch(rel, g):
            return True
    return False


@dataclass
class Task:
    root: Path
    name: str
    spec: str
    tree_src: Path
    oracle_dir: Path | None
    test_cmd: str
    oracle_cmd: str | None
    test_globs: list[str]
    src_globs: list[str]
    preflight: list[str]
    step_limit: int
    timeout_s: int
    test_timeout_s: int
    protected_globs: list[str] = field(default_factory=list)
    #: Whether the RED has to come from a test file the model wrote.
    #:
    #: True for a benchmark: the suite is the deliverable, and "a test exists to fail" is what
    #: makes the ordering claim mean something rather than a broken command happening to exit 1.
    #: False for a real repository, where the suite is already there and what is graded is that a
    #: red was SEEN (exit 1 -- exit 2 is "nothing ran" and is never banked) before the source
    #: changed, and that the tree was green after the last write.
    require_test_file: bool = True
    # Extra paths this task's toolchain needs, exposed read-only at the same location.
    # A task whose interpreter or compiler lives outside /usr cannot be scored at all,
    # and the failure looks like the model's. Declaring it here means the sandbox plan
    # can print what the run was able to see.
    sandbox_binds: list[str] = field(default_factory=list)
    #: What the acceptance corpus is allowed to grade. One value, on purpose.
    #:
    #: After a red the seal forbids repairing a test file, so an oracle that gates acceptance
    #: on the submission's own suite passing fails correct code it forbade the model to fix.
    #: It did, three times in `bits`: every arm had an implementation the corpus passed, and
    #: failed on "the submission's own tests do not pass" over a boundary guard in a sealed
    #: file. Declared per task so the standard is stated rather than inferred, and refused by
    #: the loader if it says anything else.
    oracle_gate: str = "implementation"
    meta: dict = field(default_factory=dict)

    def is_test_path(self, rel: str) -> bool:
        return _matches(rel, self.test_globs)

    def is_src_path(self, rel: str) -> bool:
        return _matches(rel, self.src_globs)

    def is_protected(self, rel: str) -> bool:
        """Paths the agent may not write: the instrument, not the work."""
        return _matches(rel, self.protected_globs)


def bash_timeout_for(test_timeout_s: int, explicit: int | None = None) -> int:
    """How long one bash action may take, given what the task declares for its suite.

    A repository's gate is routinely slower than the 120 s default -- PROTEKT's `tools/ci.sh fast`
    takes 121 s -- and a delegate that runs the suite through bash then gets a silent kill at the
    exact moment it is looking for evidence, which reads afterwards like "it chose not to look".

    So the floor is the declared test timeout: "the suite is slow" can never masquerade as "nothing
    to see". An explicit `--timeout` still wins, because a caller who names a number means it.
    """
    if explicit:
        return explicit
    return max(120, int(test_timeout_s or 0))


def repo_task(
    repo: str | Path,
    spec: str,
    test_cmd: str,
    *,
    test_globs: list[str] | None = None,
    step_limit: int = 60,
    timeout_s: int = 120,
    test_timeout_s: int = 600,
) -> Task:
    """A `Task` for a real repository: no fixture, no oracle, and no seal.

    The second constructor. `ninny run --repo` is the same run loop -- the same gate, the same
    exit-code contract, the same record, the same `ninny verdict` -- pointed at a working copy
    instead of a benchmark fixture. Four fields carry the difference:

    - `oracle_dir = None`: there is no external corpus to stage or hide. The repository's own
      gate is the acceptance evidence, and what gets graded is the handback, not a score.
    - `test_globs` comes from `--test-glob` and is empty by default. Which files are tests is a
      property of the repository; a glob we guessed would classify the wrong files with
      confidence, so the record says `no-tests` until the caller says otherwise.
    - `src_globs = ["**"]`: every path is the work. A write is only refused while a red has not
      been seen, and `is_test_path` is consulted first, so a declared test path stays writable
      before the red -- in a repository the tests are the model's to extend.
    - `require_test_file = False`: the suite already exists, so a red only has to be seen.

    `sandbox_binds` carries the repository itself. A git worktree's `.git` is a file pointing
    into the main repository, so git inside bwrap cannot resolve HEAD without it -- measured, not
    assumed. The bind is read-only by contract, which is enough for `status`, `diff` and `log`
    and refuses `add`/`commit` with a clean error; a repository whose gate needs git to write
    needs a read-write bind, and that is not built until a measured gate asks for it.
    """
    root = Path(repo).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"{root} is not a directory")
    if not (root / ".git").exists():
        raise ConfigError(f"{root} is not a git repository (--repo stages a worktree of it)")
    if not test_cmd:
        raise ConfigError(
            "repo mode needs --test-cmd: the command that exercises the change. This is not "
            "guessed -- repositories on this machine split between scripts/gate.sh and "
            "tools/ci.sh, and a guess that is wrong half the time is worse than a flag."
        )
    return Task(
        root=root,
        name=root.name,
        spec=spec,
        tree_src=root,
        oracle_dir=None,
        test_cmd=test_cmd,
        oracle_cmd=None,
        test_globs=list(test_globs or []),
        src_globs=["**"],
        preflight=[],
        step_limit=step_limit,
        timeout_s=timeout_s,
        test_timeout_s=test_timeout_s,
        protected_globs=[],
        sandbox_binds=[str(root)],
        require_test_file=False,
    )


def load_task(path: str | Path) -> Task:
    root = Path(path).expanduser().resolve()
    toml_path = root / "task.toml"
    if not toml_path.is_file():
        raise ConfigError(f"no task.toml in {root}")
    data = tomllib.loads(toml_path.read_text())

    spec_file = data.get("spec_file", "SPEC.md")
    spec_path = root / spec_file
    if not spec_path.is_file():
        raise ConfigError(f"spec file {spec_file} not found in {root}")

    tree_src = (root / data.get("tree", "tree")).resolve()
    if not tree_src.is_dir():
        raise ConfigError(f"starting tree {tree_src} is not a directory")

    oracle_dir = None
    if data.get("oracle"):
        oracle_dir = (root / data["oracle"]).resolve()
        if not oracle_dir.is_dir():
            raise ConfigError(f"oracle {oracle_dir} is not a directory")
        _assert_oracle_outside_tree(oracle_dir, tree_src)

    test_cmd = data.get("test_cmd")
    if not test_cmd:
        raise ConfigError(
            "task.toml must declare test_cmd: the command the agent runs to exercise "
            "its own tests. It is what makes a RED observation a mechanical event "
            "rather than a guess at the model's shell history."
        )

    return Task(
        root=root,
        name=data.get("name", root.name),
        spec=spec_path.read_text(),
        tree_src=tree_src,
        oracle_dir=oracle_dir,
        test_cmd=test_cmd,
        oracle_cmd=data.get("oracle_cmd"),
        oracle_gate=_oracle_gate(data),
        test_globs=list(data.get("test_globs", ["tests/own/**"])),
        src_globs=list(data.get("src_globs", ["src/**"])),
        protected_globs=list(data.get("protected_globs", [])),
        preflight=list(data.get("preflight", [])),
        step_limit=int(data.get("step_limit", 40)),
        timeout_s=int(data.get("timeout_s", 120)),
        test_timeout_s=int(data.get("test_timeout_s", 120)),
        # Expanded on the HOST, at load time. The sandbox sets HOME=/tmp, so a manifest
        # written as "$HOME/.hermes/node" has to resolve before the sandbox is entered --
        # resolving it later would point at /tmp/.hermes/node and fail confusingly.
        sandbox_binds=[
            os.path.expandvars(os.path.expanduser(str(p)))
            for p in data.get("sandbox_binds", [])
        ],
        meta={k: v for k, v in data.items() if k not in _KNOWN_KEYS},
    )


def _oracle_gate(data: dict) -> str:
    """The one standard an oracle may declare, or a refusal that explains itself."""
    gate = data.get("oracle_gate", "implementation")
    if gate != "implementation":
        raise ConfigError(
            f'oracle_gate must be "implementation" (got {gate!r}). An oracle may grade the '
            "implementation with an external corpus. It may not gate acceptance on the "
            "submission's own test files passing: once a suite has gone red the seal forbids "
            "repairing it, so that gate fails correct code -- it did, three times in `bits`. "
            "Record the shipped suite's colour in the oracle instead, with a line a reader "
            "can grep; do not fail on it."
        )
    return gate


def _assert_oracle_outside_tree(oracle_dir: Path, tree_src: Path) -> None:
    inside = oracle_dir == tree_src or tree_src in oracle_dir.parents
    if inside:
        raise ConfigError(
            f"the oracle ({oracle_dir}) is inside the task tree ({tree_src}). "
            "The agent would be able to read the acceptance suite and write tests "
            "from the answer key. Move it out of tree/."
        )
    if oracle_dir in tree_src.parents:
        raise ConfigError(
            f"the task tree ({tree_src}) is inside the oracle ({oracle_dir}); the "
            "oracle would be copied into every run. Separate them."
        )


_KNOWN_KEYS = {
    "name", "spec_file", "tree", "oracle", "test_cmd", "oracle_cmd",
    "test_globs", "src_globs", "preflight", "step_limit", "timeout_s",
    "test_timeout_s", "protected_globs", "sandbox_binds", "oracle_gate",
    "sabotage_target",
}
