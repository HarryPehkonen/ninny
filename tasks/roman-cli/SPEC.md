# A Roman numeral command line tool

Implement `src/romanx.cpp` so that the frozen command line works in both directions.

```
$ roman to-roman 1987
MCMLXXXVII
$ roman to-number MCMLXXXVII
1987
```

## Frozen -- do not modify

- `include/romanx/romanx.hpp` -- the API your implementation defines.
- `src/main.cpp` -- the command line itself. It is already written; argument parsing is
  deliberately not part of this exercise.
- `CMakeLists.txt` -- the build. Two targets: `roman` (the tool) and `own_tests` (your
  suite, which is every `tests/own/*.cpp`), both under `-Wall -Wextra -Wpedantic -Werror`.
- `tests/harness.hpp` -- the harness your own tests use.

## Requirements

1. `to_roman(n)` returns the standard Roman form of every integer in `1..3999`, using
   the subtractive pairs `IV`, `IX`, `XL`, `XC`, `CD`, `CM`.
2. `to_roman` returns `std::nullopt` for everything else: `0`, negatives, `4000`, larger.
3. `to_number(s)` returns the value of a Roman numeral.
4. `to_number` returns `std::nullopt` unless `s` is **exactly the canonical form of its
   own value**. `IIII`, `VV`, `LL`, `DD`, `MMMM`, `IVI`, `XIIX`, `IC`, `ix`, `12`, `M M`
   and the empty string are all rejected: they may parse, but they are not what the tool
   prints, and this tool accepts exactly what it prints.
5. Round-tripping holds for every value: `to_number(to_roman(n)) == n` for all `n` in
   `1..3999`.
6. The standard library only. No third-party code, no external commands, no files.

## The command line contract

- `roman to-roman <n>` -- the numeral on stdout, exit 0. Rejected input: a message on
  stderr, exit 1.
- `roman to-number <s>` -- the value on stdout, exit 0. Rejected input: a message on
  stderr, exit 1.
- Any other invocation -- usage on stderr, exit 2.

## Where things are

- Your implementation: `src/romanx.cpp`. Everything you write goes in `src/`.
- Your own tests: `tests/own/`, run with the `run_tests` action. That runs
  `tools/run_own_tests.sh`, which configures and builds the `own_tests` target and then
  runs it. It exits 2 when `tests/own/` holds no tests at all -- "no tests" is not "tests
  passed" -- and exits 2 rather than 1 when the configure step or the build fails, because
  a build error observes nothing.
- `tools/`, `include/`, `src/main.cpp`, `CMakeLists.txt` and `tests/harness.hpp` are not
  yours to edit.
- The acceptance corpus is not in this tree. Do not go looking for an answer key: write
  the cases you would want to defend, watch them fail, then make them pass.
