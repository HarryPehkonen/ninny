# Adapters: the one layer that has to know a language

Ninny's loop is language-blind. The whole interface between the harness and a project is
`test_cmd` plus three exit codes, and `ninny/*.py` never parses a compiler's output. That is
what makes it work on a Rust crate and a NASM project it has never seen.

The price is paid in each task's **adapter**: the script `run_tests` calls, which has to answer
the contract on behalf of a toolchain that does not speak it. For the first six tasks those were
hand-written -- 41 to 72 lines each, three to five hand-rolled `exit 2` guards each, no two
alike -- and **every defect of the 2026-10-23 campaign lived in that layer**, not in the harness.
All eight tasks now declare a `[runner]` config; `cron` and `ninny-gate` were converted last, and
they were the only two whose case count never reached the record:

| what went wrong | what it cost |
|---|---|
| `tasks/bits` refused the edit its own README required | the task was unsolvable |
| `tasks/intset` reported a genuine red as exit 2, because its guard matched Cargo's `error: test failed, to rerun pass ...` | the task was unsolvable under `--tdd enforce` |
| `tasks/intset`'s README said to write `tests/own/*.rs`, which Cargo never compiles | an agent following it could not bank a red |
| `tasks/intset`'s `frozen.sha256` was empty, and the oracle still printed "every frozen file is unchanged" | a vacuous pass in the oracle itself |
| `tasks/roman` answers 1 (a red) for a suite that does not import | a broken suite could be banked as evidence |

So the adapter became a **config**: a `[runner]` table in the task's own `task.toml`, rendered
into the tree's `tools/run_own_tests.sh`.

```console
$ python3 -m ninny runner --task tasks/roman          # print the adapter this config renders
$ python3 -m ninny runner --task tasks/roman --write  # write it into the tree
$ python3 -m ninny runner --task tasks/roman --check  # fail when the file on disk differs
```

**Rendered, not interpreted.** The script stays a real file in the tree -- because the tree's own
files are what teaches an agent the rules (measured: all three `bits` arms learned the
register-your-test rule from `tests/own/README.md` and the runner's header, without being told).
Nothing new runs inside the sandbox, no dependency is added, and `test_cmd` still points at the
same file. The config is the source of truth; the gate checks the file against it
(`scripts/tree-check.sh`, stage `tree`), so a hand-edited adapter and a stale config cannot
silently disagree.

## The contract

| exit | meaning |
|---|---|
| `0` | the tests ran and passed |
| `1` | the tests ran and failed -- **this is the RED observation** |
| `2` | nothing ran -- a build error, an empty suite, a suite that asserts nothing |

Exit `2` is never a RED. That single rule is why a stub with a missing symbol cannot be banked as
evidence, why an empty suite cannot look like a pass, and why "the suite did not compile" cannot
be mistaken for "the tests failed".

Every adapter also prints its case count on a line of its own:

```
NINNY_TESTS: 7
```

The number is the *evidence*, not a nicety: a suite that shrank asserts less without failing, and
this is the only place the harness learns it. The count is printed in every state, including
zero, because "collected nothing" and "failed on something" are different facts.

## The four questions

Every toolchain is described by answering the same four questions. That is the whole abstraction:

1. **How do you build it, and what does a build failure look like?** (`build`, `build_fail`)
2. **How do you run it, and what must exist before running is worth it?** (`run`, `require`)
3. **How do you know a case actually ran?** (the count: `sum`, `count`, `count_minus`)
4. **How do you know it failed locally?** (`rc_unrunnable`, or just the tool's own exit code)

## The schema

| key | meaning |
|---|---|
| `about` | one line naming the toolchain; rendered into the file's header |
| `note` | the task's own prose, kept verbatim in the header: the traps a schema cannot express |
| `require` | a glob that must match at least one file, or there is nothing to run (exit 2) |
| `build` | a detached build step; a non-zero exit is 2, never a red. It is ALSO the cheap check the harness runs on its own: after every write that lands, and again if a run ends at the step limit |
| `run` | the test command |
| `build_fail` | a regex proving the suite did not compile -- the case a toolchain hides behind its ordinary "tests failed" code |
| `sum` | a regex whose captured group is **summed** (cases that ran) |
| `count` | a regex whose **matches** are counted |
| `count_minus` | a regex whose matches are **subtracted** |
| `rc_unrunnable` | the exit code meaning "could not run at all" when it is not the ordinary failure code |

**No key exists speculatively.** Each one is needed by a task in this repo, and the four keys that
were in the first draft but are in nobody's config -- `empty`, `ran`, `failed`, `rc_fail` -- were
removed rather than kept "just in case":

- `empty` and `ran` collapse into one rule: **if the case count comes out zero, nothing was
  observed, whatever the exit code said.** That is what `unittest`'s `Ran 0 tests`, ctest's
  `No tests were found` and the frozen C++ harness's `0 checked, 0 failed` have in common.
- `failed` is unnecessary because every one of the six toolchains exits non-zero when a case
  fails -- and the count had to be parsed anyway, so the failure signal is free.
- `rc_fail` is unnecessary for the same reason: ctest's `8` is already non-zero.

## The verdict, in one order, for every toolchain

```
require not met          -> 2   (and NINNY_TESTS: 0)
build failed             -> 2   (and NINNY_TESTS: 0)
build_fail matched       -> 2   (and NINNY_TESTS: 0)
rc == rc_unrunnable      -> 2   (and NINNY_TESTS: 0)
count computed           -> print NINNY_TESTS: <n>
count == 0               -> 2
rc != 0                  -> 1
otherwise                -> 0
```

## The eight adapters, as they are

```toml
# roman -- Python / unittest
run        = 'python3 -m unittest discover -s tests/own -t tests/own -v'
build_fail = '_FailedTest|Failed to import test module|^SyntaxError|^IndentationError'
sum        = '^Ran ([0-9]+) tests?'

# dur -- Node / node --test
require     = 'tests/own/*.test.js'
run         = 'node --test --test-reporter=tap tests/own/'
sum         = '^# tests ([0-9]+)$'
count_minus = '^(not )?ok [0-9]+ - .*(/|\.js)$'

# intset -- Rust / cargo
require    = 'tests/own/main.rs'
run        = 'cargo test --offline --color never'
build_fail = '^error\[E[0-9]+\]:|^error: could not compile|^error: expected '
sum        = ['^test result: .* ([0-9]+) passed;', '^test result: .* [0-9]+ passed; ([0-9]+) failed;']

# nasm-sum -- x86-64 assembly / make + bash cases
require       = 'tests/own/*.sh'
build         = 'make'
run           = 'worst=0; for t in tests/own/*.sh; do ...; done; exit $worst'
count         = ['^ok ', '^not ok ']
rc_unrunnable = 2

# bits -- C++ / CMake + GoogleTest, run by ctest
build = 'cmake -S . -B .ninny-build -DCMAKE_BUILD_TYPE=Debug && cmake --build .ninny-build -j 4'
run   = 'ctest --test-dir .ninny-build --output-on-failure'
sum   = ['All tests passed \(([0-9]+) tests?\)', 'out of ([0-9]+)']

# roman-cli -- C++ / CMake, one own_tests target
require = 'tests/own/*.cpp'
build   = 'cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug && cmake --build build --target own_tests'
run     = './build/own_tests'
sum     = '.*: ([0-9]+) checked,'

# cron -- C++17 / g++, a direct compile with the frozen harness
require = 'tests/own/*.cpp'
build   = 'mkdir -p build && g++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -Iinclude -Itests src/*.cpp tests/own/*.cpp -o build/own'
run     = './build/own'
sum     = '.*: ([0-9]+) checked,'

# ninny-gate -- Python / unittest over this repo's own suite
run        = 'python3 -m unittest discover -s tests -t .'
build_fail = '_FailedTest|Failed to import test module|^SyntaxError|^IndentationError'
sum        = '^Ran ([0-9]+) tests?'
```

## The traps, each with the transcript that proves it

The rule is not "these tools are strange"; it is that **a tool's exit code is not the contract**,
and the config says where it lies. Recorded transcripts live in `tests/fixtures/runners/`
(`cron` and `ninny-gate` have no recordings yet: their verdicts are exercised by `verify-task`'s
third control, which plants a failing case in the tree, rather than by a replay).

- **Cargo exits `101` for a compile error and for a failing test.** `build_fail` is what separates
  them: `error[E0308]: mismatched types` and `error: could not compile` mean nothing ran;
  `test result: FAILED. 0 passed; 1 failed` means a case ran and failed. The guard has to be
  bounded to compiler diagnostics -- Cargo also prints `error: test failed, to rerun pass ...` on
  an ordinary failure, and a loose guard matched that and reported every real red as "nothing ran".
- **ctest exits `8` for "some tests failed" and for "No tests were found".** Same code, opposite
  meanings; only the count distinguishes them.
- **`node --test` counts a test *file* with no cases as a case**, named by its path. That is the
  `count_minus` wart: entries whose name is a path are subtracted, and a run that still has no
  cases is exit 2.
- **`unittest` reports a module that fails to import as `Ran 1 test` -- a synthetic
  `_FailedTest`.** So an unimportable suite answers `1` (a red) with no guard, which is why
  `roman`'s config carries `build_fail`. Its hand-written predecessor did not, and answered `1`.
- **`unittest` also prints `Ran 0 tests` and exits 0**; the count rule catches it.
- **A bash case loop's exit code is its last command's, not its worst.** `nasm-sum`'s `run`
  keeps the worst code, and `rc_unrunnable = 2` maps "a case script could not run" to exit 2
  rather than 1.

## The 15-minute recipe for a project Ninny has never seen

A config cannot be written from a project alone: **"what does your toolchain print when it fails"
is empirical**. Three observations answer all four questions, and they are the same three the
third control automates for the red one:

1. **Run it green** (or with no tests at all). Note the exit code and the summary line: that is
   your `sum`/`count` pattern and your evidence that zero cases is detectable.
2. **Run it red** -- plant one failing case. Note the exit code and whether the output
   distinguishes "a case failed" from "it did not compile". That is `build_fail`, or the lack of it.
3. **Run it broken** -- make it not compile. If the tool exits the same code as in step 2, you have
   found why `build_fail` exists.

Then write the `[runner]` table, `ninny runner --task <dir> --write`, and `ninny verify-task`:
its third control plants a failing test and requires exit 1 from **your** adapter. If that control
does not run, the task is grey, never green.

## Testing an adapter without the toolchain

A rendered adapter honours two environment variables:

```console
$ NINNY_RUNNER_REPLAY=tests/fixtures/runners/intset.red.txt NINNY_RUNNER_REPLAY_RC=101 \
    bash tasks/intset/tree/tools/run_own_tests.sh; echo $?
1
```

With `NINNY_RUNNER_REPLAY` set, the script skips `require`/`build`/`run` and classifies the
recorded transcript instead. `tests/test_runner_config.py` drives **the rendered script itself**
through every recorded state, so the corpus tests the artifact that runs in a sandbox rather than
a Python mirror of it that could drift.

## What this is not

No registry, no plugins, no adapter store, no language-by-build-system matrix, no code generation
beyond the one runner file, no new dependency. A task declares its adapter in its own manifest;
nothing is discovered, loaded, or registered. A task without a `[runner]` table keeps its own
hand-written script -- `ninny runner` says so and exits 0.
