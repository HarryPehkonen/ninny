# Make the record say which harness produced it

The harness records its version, the spec it ran and a hash of the starting tree. It does not
record **a hash of itself** — and it is not in `result.json` at all, which is the file every
downstream number is read from. So a finished result cannot be traced to the code that produced
it: change a rule in `ninny/tdd.py`, re-run, and the two records look identical.

Close that. One change, in two files, and the harness's own suite has to stay green.

## The API

In `ninny/artifacts.py`, export two names.

```python
def instrument_digest(package_dir: Path | None = None) -> str: ...
def harness_identity() -> dict: ...
```

**`instrument_digest`** returns a **16-character lowercase hex** sha256 over *the harness's own
modules*: the `*.py` files in the package directory, sorted by name, each contributing its name,
a NUL, its bytes, a NUL. Same shape as `tree_digest` a few lines above it, and the same three
properties that function has:

- the same source hashes the same value **whatever the working directory** — so relative names
  only, never an absolute path, never the task tree, never the run directory;
- a change to any module changes it;
- nothing else does. A stale `__pycache__`, a `.pyc`, a stray `.txt` beside the package, or a
  different task: all unchanged.

With no argument, hash the package this code lives in. With `package_dir`, hash that directory,
which is what makes the property testable.

**`harness_identity`** returns exactly:

```python
{"version": ..., "fork_of": ..., "upstream": ..., "instrument_sha256": ...}
```

`version` is `ninny.__version__`, `fork_of` and `upstream` are the two constants the package
already carries, and `instrument_sha256` is `instrument_digest()`.

## The record

Two places, both additive — nothing already in either file may disappear:

- `result.json` gains a **`harness`** key holding `harness_identity()`. This is the point of the
  task: the file a number is read from should say what produced it.
- `trajectory.json`'s existing `ninny` block becomes `harness_identity()`.

## Rules

- `src_globs` is `ninny/**` — the harness's own modules are what you are changing.
- The suite in `tests/` starts **green** here, all 248 of them. It must still be green when you
  finish, and adding to it is expected: this change wants a test that fails before it and passes
  after it, like any other.
- Your tests go in `tests/` beside the harness's own, with the same convention
  (`tests/test_*.py`). Run them with `bash tools/run_own_tests.sh`; its exit codes are the
  contract described in `docs/CONTRIBUTING.md` — `0` passed, `1` ran and failed, `2` nothing ran.
- Keep it small. This is a stamp, not an audit system: no new dependency, no new file format,
  no schema version, no migration.
