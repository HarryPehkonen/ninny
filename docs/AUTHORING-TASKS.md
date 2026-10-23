# Authoring a task: what it costs, and the traps

Written by the agent that authored five tasks for Ninny (a Python CLI, a C++ CLI built with
CMake, a Node CLI, a Rust crate built with cargo, and an x86-64 assembly program built with
nasm) in a single session, and hit every trap below at least once. It is a record of cost,
not a tutorial: the point is that most of the cost is in the *instrument*, not the project.

## What a task actually is

```
tasks/<name>/
  SPEC.md          what the model is given
  task.toml        the declaration
  tree/            the starting tree, copied per run
  oracle/          the acceptance corpus -- never copied into a run
  fixed/           a COMPLETE tree: the answer key, staged exactly like a submission
```

`ninny verify-task --task tasks/<name>` is the gate on your own work, and it answers two
questions that nothing else does:

```
INFO  own test command fails on the tree the agent starts from   (exit 2 -- expected ...)
PASS  oracle is RED on the given tree                            (exit 1)
PASS  oracle is GREEN on the fixed tree                          (exit 0)
```

**The two-way control is the whole value.** An oracle that only ever fails proves nothing.
Twice in one session the corpus or the answer key was wrong and the control caught it:

- a property loop fed the parser a *number* because two tables in the corpus had opposite
  field order (`PARSES` is `[text, seconds]`, `FORMATS` is `[seconds, text]`);
- the assembly answer key rejected `0007` because the digit cap counted leading zeros,
  while its own spec said leading zeros are fine.

And `verify-task` itself stopped a broken task reaching a model:

```
FAIL  oracle is GREEN on the fixed tree  (exit 1 -- it does not pass on the known-good
      tree, so the task may be unsolvable)
BROKEN TASK: oracle is GREEN on the fixed tree
```

## The exit-code contract, and why every harness needs its own guard

The runner the task ships (`tools/run_own_tests.sh`) reports one of three things:

| code | meaning |
|---|---|
| `0` | the tests ran and passed |
| `1` | the tests ran and failed -- a RED observation |
| `2` | nothing ran -- nothing was observed, so not a RED |

No toolchain speaks this contract, so the runner is a translator, and **every harness
reports its evidence differently**:

| harness | what exit 1 looks like | what "nothing ran" looks like |
|---|---|---|
| C++ (own harness) | a `CHECK` failure, exit 1 | `cc1plus: fatal error`, or `OWN: 0 checked` |
| Python `unittest` | `FAIL:`/`ERROR:` tracebacks | `Start directory is not importable`, `Ran 0 tests` |
| Node `node --test` | `not ok` lines, exit 1 | a compile error -- but the count **lies** (below) |
| cargo | a failing test -- and a compile error, both as **101** | `test result: ok. 0 passed` |
| shell (nasm task) | a script exiting 1 | `make` failing, or a script exiting 2 |

Two traps are worth their own headings.

**Node counts the FILE as a test.** A test file containing no `test()` at all reports
`# tests 1, # pass 1`, exit 0 -- a green run that asserted nothing. What cannot be faked is
TAP's nesting: a case that ran appears as an *indented* `ok N - <name>` inside its file's
subtest. Pin the reporter (`--test-reporter=tap`) and count those lines, not the summary:

```sh
n=$(printf '%s\n' "$out" | grep -cE '^ +(not )?ok [0-9]+ - ')
```

This also caught a Node whose *default* reporter is not TAP at all: with no `# tests N`
line to match, a passing suite was reported as "nothing ran". Version-dependent text is a
bad basis for a contract; TAP's structure is a good one.

**cargo exits 101 for both a compile error and a failing test**, so passing its status
through would bank a build error as a RED. The runner separates them -- `error[E...]` means
nothing ran (2), anything else non-zero means tests failed (1) -- and sums `N passed`
across targets, because `0 passed` is a green run.

## Other traps, each hit once

- **`oracle = "oracle"` must be in `task.toml`.** Without it the oracle directory is not
  staged and `verify-task` exits **127** with no explanation of why. The only signal is the
  number. (Say *"no oracle declared"* instead: recorded as a gap, below.)
- **`fixed/` must be a complete tree**, not just the answer file. The harness copies that
  directory *as* the tree, so a `fixed/` holding only `src/answer.py` is a tree with no
  runner, no build files, and no tests.
- **A test write must land in `test_globs`.** In the Rust task, unit tests inside
  `src/lib.rs` do run under `cargo test`, but they are in `src/`, so the record never counts
  them as a test the agent wrote. The spec has to say where tests belong.
- **Ship a stub that builds.** A 25-line stub that compiles and exits 0 makes `red-first`
  reachable in a compiled language: the first own-test run is a test that *ran* and failed
  rather than a build error, which is the difference between a real RED and a miscount.
- **A task whose toolchain lives outside `/usr` is refused, correctly.** `node` at
  `~/.local/bin/node` is invisible inside the sandbox, and the run stops before any model
  call:

  ```
  preflight FAIL node --version   bash: line 1: node: command not found
  ninny: a preflight command does not work inside the sandbox. Refusing to score this run:
  a sandbox that hides the toolchain would blame the model for it.
  ```

  A task now declares what it needs: `sandbox_binds = ["/opt/node"]`, printed in the plan
  line so the record says what the run could see. **Bind the whole prefix**: binding
  `~/.local/bin` alone gave a working `node` and an `npm` that silently printed nothing,
  because npm is a symlink into `~/.local/lib/node_modules`.
- **The oracle runs on the host, outside the sandbox.** Its toolchain is therefore not
  necessarily the agent's: the Node task's runs see the distro `node` 20 because that is
  what `/usr` holds, while the oracle uses whatever is first on the host's `PATH`. Worth
  knowing when a language's behaviour is version-sensitive.
- **`--tdd none` is not a value.** The gate takes `off`; twelve arms died at argument
  parsing before any model call and cost nothing.
- **A refused run costs no money.** Preflight runs *inside* the sandbox before the first
  model call, which is why a toolchain mistake is a refusal rather than a wasted arm.

## What was easy

Worth recording, because it is most of the surface: `ninny run` with a task and a model;
`ninny verify-task`; `ninny check` on a finished tree; four artifacts per run (record, diff,
oracle log, durable log/index); per-arm names and `_open_unique`; the oracle being staged
*outside* the tree so the agent cannot read it; and the preflight refusal. Nothing needed to
be explained twice.

## Gaps this campaign found (still open)

1. **The reported test count is not recorded as a number.** The count appears in observation
   text only, so "my suite quietly got smaller" is invisible in the record -- exactly the
   CMake-explicit-test-list trap, and the Node file-counting trap, in a form a reader can
   see. Proposed: each runner prints `NINNY_TESTS: <n>` and the record stores it.
2. **`verify-task` exit 127 gives no reason.** It should say the manifest declares no
   `oracle`.
3. **`verify-task` treats an empty starting suite as INFO, not as a check.** A runner that
   exits *0* on a tree with no tests at all is a broken runner, and that is decidable
   generically -- it should FAIL rather than INFO.
4. **The same authoring cost repeats per language**: every new harness needs its own
   vacuous-count and build-error guard, written by hand and controlled by hand. The C++
   harness task is the cheapest of the five; assembly is the most expensive, because the
   test harness itself has to be invented and specified.
