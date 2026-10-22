"""What a run leaves behind, so somebody who was not here can audit it.

Two things were missing from the record. A `diff.patch` of the working tree against
the tree it started from -- answering "what did it actually change?" without diffing
two directories by hand, which is also how a model that rewrote a file it meant to
edit gets caught. And a digest of the input tree, so a finished number can be traced
back to the exact starting point it came from.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

# Which files in a tree are real. ONE definition, used by the digest, the diff and the
# test-first gate, because they have to agree: if the gate counts a bytecode cache as
# source, then merely RUNNING the tests looks like editing the code, `first_src_step`
# moves to the red step, and a textbook red-first run is reported as "red-after-code".
SKIP_PARTS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def is_ignored(path: str | Path) -> bool:
    """True for a file that is not part of what a human would call the source."""
    path = Path(path)
    return bool(SKIP_PARTS.intersection(path.parts)) or path.suffix in SKIP_SUFFIXES


def _files(root: Path) -> dict[str, Path]:
    """Every file under `root`, keyed by its relative posix path."""
    out: dict[str, Path] = {}
    root = Path(root)
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file() and not is_ignored(path.relative_to(root)):
            out[path.relative_to(root).as_posix()] = path
    return out


def _read(path: Path) -> list[str] | None:
    """The file's lines, or None when it is not text."""
    try:
        return path.read_text().splitlines(keepends=True)
    except (UnicodeDecodeError, OSError):
        return None


def tree_diff(before: Path, after: Path) -> tuple[str, str]:
    """A unified diff of `after` against `before`, and a one-line summary."""
    old, new = _files(before), _files(after)
    chunks: list[str] = []
    plus = minus = 0
    for rel in sorted(set(old) | set(new)):
        in_old, in_new = rel in old, rel in new
        old_lines = _read(old[rel]) if in_old else []
        new_lines = _read(new[rel]) if in_new else []
        if old_lines is None or new_lines is None:
            chunks.append(f"binary file differs: {rel}\n")
            continue
        if in_old and in_new and old_lines == new_lines:
            continue
        for line in difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{rel}" if in_old else "/dev/null",
            tofile=f"b/{rel}" if in_new else "/dev/null",
            n=3,
        ):
            if not line.endswith("\n"):
                line += "\n"
            if line.startswith("+") and not line.startswith("+++"):
                plus += 1
            elif line.startswith("-") and not line.startswith("---"):
                minus += 1
            chunks.append(line)

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(rel for rel in set(old) & set(new) if _read(old[rel]) != _read(new[rel]))
    stat = f"{len(added)} added, {len(changed)} changed, {len(removed)} deleted (+{plus} -{minus})"
    return "".join(chunks), stat


def write_diff(before: Path, after: Path, out_path: Path) -> str:
    """Write the patch and return its summary line."""
    patch, stat = tree_diff(before, after)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(patch or "(no changes)\n")
    return stat


def tree_digest(root: Path) -> str:
    """A short sha256 over the tree's relative paths and their contents.

    Relative paths, so the same tree hashes the same wherever it is checked out.
    """
    digest = hashlib.sha256()
    for rel, path in sorted(_files(root).items()):
        digest.update(rel.encode())
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
        digest.update(b"\0")
    return digest.hexdigest()[:16]
