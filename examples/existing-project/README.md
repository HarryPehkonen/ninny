# An existing project that must not gain files

This is the runnable version of the recipe in the README's *Starting a new project, or
adopting an existing one*. The point of it is what is **not** here: the fixture is entirely
outside the project, `test_cmd` is an inline shell command rather than a runner file dropped
into the tree, and the oracle stays here instead of in the checkout.

```
examples/existing-project/
├── task.toml        the manifest -- tree = "snapshot", test_cmd is inline
├── SPEC.md          the contract, as the model sees it
├── oracle/
│   └── accept.sh    the project's suite plus properties the agent never sees
├── snapshot/        the project, frozen at the commit before the work
│   ├── calc/core.py       the stub (returns None)
│   └── tests/test_calc.py the project's own suite, which the agent may not edit
└── fixed/           the control: the same tree with the function implemented
```

Prove it grades the way it must, before spending anything:

```bash
ninny verify-task --task examples/existing-project
#   PASS  oracle is RED on the given tree    (exit 1)
#   PASS  oracle is GREEN on the fixed tree  (exit 0)
```

Measured on the three trees (the inline command, run by hand):

| tree | exit | `NINNY_TESTS` | what it means |
|---|---|---|---|
| `snapshot/` with an empty suite file | `2` | `0` | nothing ran -- never banked as a RED |
| `snapshot/` | `1` | `3` | tests ran and failed: a real RED |
| `fixed/` | `0` | `3` | tests ran and passed |

Two things this example is honest about. It uses `pytest` as "the project's own suite"
because that is what this pretend project has; the shape is the same for `ctest`, `cargo
test`, `go test`, `node --test` -- run it, keep the exit code, count what it collected,
print `NINNY_TESTS: <n>`, and `exit 2` when the count is zero. And there is no
`oracle/frozen.sha256` here, because there is no frozen file in the tree to hash: the
manifest's `protected_globs` refuses an edit to `tests/**` instead of detecting one
afterwards. That trade is spelled out in the README section.

`snapshot/` is what `git -C yourproject archive HEAD | tar -x -C snapshot` produced. Refresh
it that way rather than pointing `tree` at a live checkout: every arm has to start from the
same tree, or the arms are not comparable.
