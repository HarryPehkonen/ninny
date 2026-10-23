# sum, in assembly

Implement `src/sum.asm`: a Linux x86-64 program with no C library, built by `make` with
`nasm` and `ld`.

```
$ build/sum 2 3 ; echo $?
5
$ build/sum 100 100 ; echo $?
200
$ build/sum 5x 1 ; echo $?
2
```

## The contract

`sum <a> <b>` exits with `(a + b) & 0xFF`, where `a` and `b` are decimal integers in
`0..=127`.

It exits **2** when the arguments are not two such numbers: no arguments, one argument,
three arguments, an empty argument, a non-digit, a sign, or a value above 127. Leading
zeros are fine (`007` is 7).

**It prints nothing at all.** The exit status is the entire interface: stdout and stderr
must both stay empty in every case, including the rejected ones. Nothing is written to the
terminal, not even an error message.

## What you are given

- `_start` is the entry point, and the kernel hands you the usual System V layout:
  `[rsp]` is `argc`, `[rsp+8]` is `argv[0]`, `[rsp+16]` is `argv[1]`, `[rsp+24]` is `argv[2]`.
- `Makefile` builds `build/sum` from `src/sum.asm` with `nasm -f elf64` then `ld -e _start`.
  It is frozen: the target name and the output path are what the tests and the acceptance
  corpus use.
- `src/sum.asm` is the stub you replace. It assembles as it stands and exits 0, so your
  first own-test run is a test that ran and failed.
- `tools/run_own_tests.sh` is frozen. It builds, runs every `tests/own/*.sh`, and reports
  the contract: 0 when the cases ran and passed, 1 when they ran and failed, 2 when nothing
  could run -- a build failure, or a suite where no case ran at all.
- Only `nasm`, `ld` and `make`. No libc, no external symbols, no runtime: `ld` is invoked
  without `-lc` on purpose, and a program that needs it will not link.

## Where things are

- Your implementation: `src/sum.asm`.
- Your tests: `tests/own/*.sh`, one script per area if you like. Each prints a line per
  case -- `ok <what it checked>` or `not ok <what it checked>` -- and exits 0 when all its
  cases passed, 1 when any failed, and 2 or more when it could not run at all. See
  `tests/own/README.md`.
- The acceptance corpus is not in this tree. Think about which cases you would defend, and
  remember that the boundary is the interesting part: 0, 127, 128, `(a+b)` crossing 256, and
  every way two arguments can be wrong.
