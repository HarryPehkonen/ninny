# Task layout (the rules are enforced, not advisory)

> Extracted verbatim from `ninny-harness/SKILL.md` (split by scripts/split_skill.py).
> The body keeps a pointer; this file keeps the detail.

```
tasks/<name>/  task.toml  SPEC.md  tree/  oracle/
```

- **The oracle must live outside `tree/`** — `load_task` refuses it otherwise, and
  `ninny check` refuses to score unless the agent could not see it (escape hatch:
  `--allow-oracle-visible`, which makes the number unattributable).
- `test_globs` = the agent's own tests; `src_globs` = source (writes here are what
  `enforce` gates); `protected_globs` = the instrument (`tools/**`).
- `test_cmd` must FAIL when there are no tests (`run_own_tests.sh` does this on
  purpose) so a vacuous suite cannot be mistaken for a pass.
- `preflight` commands must work INSIDE the sandbox or the run is not scored —
  otherwise a sandbox that hides the compiler scores every model as unable to build.
- **`ninny verify-task --task T` automates both controls**: the oracle must be RED on
  the given tree and GREEN on a solved one (`fixed_tree = "fixed"` in `task.toml`, or
  `--fixed PATH`). Exit 0 verified / 1 broken task / 2 unverified. An oracle that only
  ever fails proves nothing; one that only ever passes grades nothing.
- A red START is not a broken task. A `test_cmd` that fails on an empty suite is doing
  its job, so `verify-task` reports that as INFO and never condemns the task for it.
- **Every harness needs its own "nothing ran" guard, and the count is the evidence.**
  Measured across five tasks: C++ prints `<label>: 0 checked`, Python `Ran 0 tests`,
  cargo `test result: ok. 0 passed`, and a shell harness the author invents. Node is the
  trap: it counts the FILE as a test, so a `*.test.js` containing no `test()` at all
  reports `# tests 1, # pass 1`, exit 0 -- a green run that asserted nothing. Pin the
  reporter (`--test-reporter=tap`) and count the INDENTED lines
  (`grep -cE '^ +(not )?ok [0-9]+ - '`), because TAP's nesting is structural while
  `# tests N` is version-dependent text: on a Node whose default reporter is not TAP,
  "no `# tests N` line" turns a PASSING suite into "nothing ran" -- the mirror image of
  the hole.
- **Map the build error to 2 in the runner; never pass the tool's status through.** cargo
  exits **101 for both** a compile error and a failing test, so a runner that forwards the
  status banks a build error as a RED. Grep for `error[E...]`/`error: could not compile`
  first, then sum `N passed` across targets, because `0 passed` is a green run.
- **Send tests where `test_globs` looks.** Rust unit tests inside `src/lib.rs` do run under
  `cargo test`, but they live under `src/`, so the record never counts them as a test the
  agent wrote. The SPEC has to name the directory.
- **A task with no test framework must invent one, and the SPEC must specify it.** The
  assembly task defines TAP-ish `ok`/`not ok` lines and a per-script 0/1/2 exit, so its
  runner can tell "the program is wrong" from "the script could not run". That cost lands
  on the author and makes it the most expensive of the five tasks.
- **The author's own corpus is where the bugs are.** Three of five tasks authored in one
  session had a *corpus or answer-key* bug that reading did not find and the two-way
  control found at once: two tables in the corpus with opposite field order (a property
  loop fed the parser a number), an expected exit code that contradicted the spec, and an
  answer key that rejected the leading zeros its own spec allowed. Point the corpus at the
  answer key BEFORE a model sees the task; `verify-task`'s GREEN check is that control.
- **A toolchain outside /usr is refused, and that refusal is correct.** The sandbox
  ro-binds `/usr` and `/etc` and hides the home directory, so a per-user toolchain
  (`~/.local/bin/node`) is invisible and the run stops before any model call:
  `preflight FAIL node --version -> node: command not found`. Nothing is spent. The task
  declares what it needs -- `sandbox_binds = ["/opt/node"]` in `task.toml` -- each path is
  bound read-only at the same location and named in the sandbox plan line, so the record
  says what the run could see. **Bind the whole prefix**: binding `~/.local/bin` alone gave
  a working `node` and an `npm` that silently printed nothing, because npm is a symlink
  into `~/.local/lib/node_modules`. Installing the toolchain from the distro so it lives
  under `/usr` needs no declaration at all.
