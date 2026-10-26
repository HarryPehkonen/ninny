"""A durable log of what Ninny did, for whoever has to audit it afterwards.

Two questions get asked about a harness like this, and they are not the same question.

    "What happened in this run?"   answered by the run directory: trajectory.json,
                                   trajectory.md, result.json, diff.patch, tree/.

    "What has Ninny been doing,   answered here: one transcript per invocation, plus a
     and where is the log of it?"  one-line-per-invocation index over all of them.

The second question is the one an agent asks, because by the time it needs the answer the
terminal output is gone. So a log is written every time, without being asked for, into
the state directory rather than the working tree: a log inside the tree would be a file
the *next* model reads, and a log of a run is a record of that run's reasoning about the
task. That would be context about the task, which is the one thing a run must not get.

    $XDG_STATE_HOME/ninny/logs/       (default: ~/.local/state/ninny/logs/)
        20261022-161203-cron-cpp-told-r1.log     the full transcript of one invocation
        history.tsv                              one line per invocation, appended

`history.tsv` is tab-separated, one record per line, in this fixed order:

    timestamp  subcommand  task  model  exit  steps  cost_usd  verdict  run_dir  log_file

The first line names those columns. Every field is written on every line, empty when it
does not apply, so the positions hold and a reader can take the fifth column without first
working out what is missing. A line you cannot read positionally is not an index, it is a
sentence.

The one thing a log must never carry is a credential. The process that writes these logs
is the process holding the API key, and the reader may paste the file into a context
window -- so a registered secret is scrubbed on the way to disk instead of being left to
the care of whoever wrote the print statement.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import os
import sys
import time
from pathlib import Path
from typing import TextIO

REDACTED = "[redacted]"

# Fields of a history line, in the order they are written. `record` takes exactly these,
# so the schema is the signature and a reader can trust the positions.
HISTORY_FIELDS = (
    "subcommand",
    "task",
    "model",
    "exit_status",
    "steps",
    "cost_usd",
    "verdict",
    "run_dir",
    "log_file",
)

_HISTORY_NAME = "history.tsv"
_STAMP = "%Y%m%d-%H%M%S"
_SECRETS: set[str] = set()
_CURRENT: "Session | None" = None

# Shorter than this and a "secret" is a substring of ordinary text: registering `""` would
# scrub every character out of every log.
_MIN_SECRET = 4


# ------------------------------------------------------------------ credentials
def register_secret(value: str | None) -> None:
    """Remember a credential so no log can ever contain it."""
    if value and len(value) >= _MIN_SECRET:
        _SECRETS.add(value)


def clear_secrets() -> None:
    _SECRETS.clear()


def scrub(text: str) -> str:
    for secret in _SECRETS:
        text = text.replace(secret, REDACTED)
    return text


# --------------------------------------------------------------------- where
def log_dir() -> Path:
    """The state directory logs go in, created if needed and private if we made it.

    An explicit `NINNY_LOG_DIR` is used exactly as given -- someone who names a directory
    means that directory. Whatever we create is made 0700; whatever already exists keeps
    the mode it has. A log of what a model wrote, including its failures, is nobody else's
    business on this machine -- but a directory somebody else made is not ours to
    re-permission.
    """
    override = os.environ.get("NINNY_LOG_DIR")
    if override:
        base = Path(override).expanduser()
    else:
        state = os.environ.get("XDG_STATE_HOME")
        root = Path(state).expanduser() if state else Path.home() / ".local" / "state"
        base = root / "ninny" / "logs"
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        # `mkdir(mode=...)` is masked by the umask, so 0755 under the usual umask 022.
        with contextlib.suppress(OSError):
            os.chmod(base, 0o700)
    return base


def history_path() -> Path:
    return log_dir() / _HISTORY_NAME


def _slug(text: str) -> str:
    keep = [char if (char.isalnum() or char in "._-") else "-" for char in text.strip()]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60]


# -------------------------------------------------------------------- the log
class Session:
    """The log of one invocation. Holds the path, so it is readable after the fact."""

    def __init__(self, path: Path | None, started: float):
        self.path = path
        self.started = started

    @property
    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    def write(self, text: str) -> None:
        """Log something that is not an echo of the terminal."""
        if self.path is None:
            return
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(scrub(text if text.endswith("\n") else text + "\n"))


def current() -> "Session | None":
    """The log of the invocation that is running, if there is one.

    Callers need this to *print* where the log went. A path the reader is told about is the
    difference between a record and a rumour.
    """
    return _CURRENT


class _Tee:
    """stdout, and a file. The file is written first: a broken pipe is not a lost log."""

    def __init__(self, terminal: TextIO, handle: TextIO):
        self._terminal = terminal
        self._handle = handle

    def write(self, text: str) -> int:
        self._handle.write(scrub(text))
        self._handle.flush()
        self._terminal.write(text)
        return len(text)

    def flush(self) -> None:
        with contextlib.suppress(Exception):
            self._terminal.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._terminal, "isatty", lambda: False)())


def _open_unique(directory: Path, stem: str) -> tuple[TextIO, Path]:
    """Exclusive create, so two invocations in the same second cannot share a file."""
    attempt = 0
    while True:
        path = directory / f"{stem if attempt == 0 else f'{stem}-{attempt}'}.log"
        try:
            handle = open(path, "x", encoding="utf-8")
        except FileExistsError:
            attempt += 1
            if attempt > 10_000:
                raise
            continue
        # `open(..., "x")` makes 0666 & umask -- 0644 under the usual umask 002. A log holds
        # the source a model wrote and the commands it ran, so it is 0600 like the directory.
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
        return handle, path


@contextlib.contextmanager
def session(subcommand: str, name: str = "", enabled: bool = True):
    """Everything printed -- or complained about -- inside this block also lands in a log.

    Both streams, not just stdout: the interesting line in a run that failed is usually the
    one on stderr, and an audit that stops at stdout is an audit of the happy path.

    Failing to open a log never fails the run: a harness that refuses to work because it
    could not write a diary is worse than one with no diary.
    """
    global _CURRENT
    started = time.monotonic()
    if not enabled:
        _CURRENT = Session(None, started)
        try:
            yield _CURRENT
        finally:
            _CURRENT = None
        return

    stem = "-".join(part for part in (_dt.datetime.now().strftime(_STAMP),
                                      _slug(subcommand), _slug(name)) if part)
    try:
        handle, path = _open_unique(log_dir(), stem)
    except OSError as error:
        print(f"ninny: no log for this invocation ({error.strerror or error})", file=sys.stderr)
        _CURRENT = Session(None, started)
        try:
            yield _CURRENT
        finally:
            _CURRENT = None
        return

    session_log = Session(path, started)
    _CURRENT = session_log
    header = (
        f"# ninny {subcommand} {name}".rstrip() + "\n"
        f"# started {_dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"# cwd {os.getcwd()}\n"
        f"# argv {' '.join(sys.argv)}\n"
    )
    try:
        handle.write(scrub(header))
        with contextlib.redirect_stdout(_Tee(sys.stdout, handle)), \
                contextlib.redirect_stderr(_Tee(sys.stderr, handle)):
            yield session_log
    finally:
        handle.write(scrub(f"# end {_dt.datetime.now().isoformat(timespec='seconds')}"
                           f"  after {session_log.elapsed:.1f}s\n"))
        handle.close()
        _CURRENT = None


# ----------------------------------------------------------------- the index
def _clean(value: object) -> str:
    """A cell, ready for a tab-separated line: no tabs, no newlines, no secret, no noise.

    Floats are rounded to six decimals. A cost is a measurement, not a float artifact --
    `0.003846346` in a column a reader has to eyeball is one digit of information and eight
    of noise.
    """
    if isinstance(value, float):
        return f"{value:.6f}"
    return scrub(str(value).replace("\t", " ").replace("\n", " "))


def record(subcommand: str, **fields: object) -> Path:
    """Append one line to the index. Appends only: earlier lines are never rewritten.

    Every field is written, empty when it does not apply, so column five is column five on
    every line. The header is created once, with `"x"`, so two invocations racing to write
    the first line cannot truncate each other.
    """
    values = []
    for field in HISTORY_FIELDS:
        value = subcommand if field == "subcommand" else fields.get(field)
        values.append("" if value is None else _clean(value))
    path = history_path()
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write("# " + "\t".join(("timestamp", *HISTORY_FIELDS)) + "\n")
    except FileExistsError:
        pass
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\t".join([_dt.datetime.now().isoformat(timespec="seconds"), *values]) + "\n")
    return path
