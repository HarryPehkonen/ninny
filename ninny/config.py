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
    meta: dict = field(default_factory=dict)

    def is_test_path(self, rel: str) -> bool:
        return _matches(rel, self.test_globs)

    def is_src_path(self, rel: str) -> bool:
        return _matches(rel, self.src_globs)

    def is_protected(self, rel: str) -> bool:
        """Paths the agent may not write: the instrument, not the work."""
        return _matches(rel, self.protected_globs)


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
        test_globs=list(data.get("test_globs", ["tests/own/**"])),
        src_globs=list(data.get("src_globs", ["src/**"])),
        protected_globs=list(data.get("protected_globs", [])),
        preflight=list(data.get("preflight", [])),
        step_limit=int(data.get("step_limit", 40)),
        timeout_s=int(data.get("timeout_s", 120)),
        test_timeout_s=int(data.get("test_timeout_s", 120)),
        meta={k: v for k, v in data.items() if k not in _KNOWN_KEYS},
    )


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
    "test_timeout_s", "protected_globs",
}
