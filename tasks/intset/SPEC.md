# Integer sets

Implement `src/lib.rs` so that the frozen command line works.

```
$ intset normalize 1-3,7,9-10,3-5
1-5,7,9-10
$ intset has 1-5 3
yes
$ intset add 1-5 7
1-5,7
```

## The notation

A set is written as comma-separated items with no spaces: an item is either a single
non-negative integer (`7`) or an inclusive range (`1-5`). The canonical form is ascending,
with overlapping and touching items merged, and a single value printed bare rather than as
a one-element range.

So `1-3,7,9-10,3-5` is not canonical; its canonical form is `1-5,7,9-10`. `11-9` is not a
range at all -- the lower bound must not exceed the upper. Leading zeros, spaces, empty
items, signs, fractions and an empty string are all invalid.

Values are in `0..=4294967295` (`u32`); anything larger is invalid.

## The API, in `src/lib.rs`

```rust
pub fn normalize(text: &str) -> Option<String>;           // canonical text, or None
pub fn contains(text: &str, value: u32) -> Option<bool>;  // None when text is invalid
pub fn add(text: &str, value: u32) -> Option<String>;     // canonical text, or None
```

## Requirements

1. `normalize` returns the canonical form of any valid set, and `None` for anything that is
   not one -- including the empty string, a reversed range, a leading zero, a space, a
   trailing comma, and a value above `u32::MAX`.
2. `normalize` is idempotent: `normalize(normalize(s).unwrap()) == normalize(s)`.
3. `contains` answers for every value, and returns `None` rather than `false` when the set
   itself is invalid.
4. `add` returns the canonical form of the set with that value included, and `None` when
   the set is invalid.
5. No dependencies. `Cargo.toml` declares none and none may be added: the suite runs
   offline inside a sandbox with no registry, so a third-party crate cannot even be
   fetched. Standard library only.

## The command line contract

- `intset normalize <set>` -- canonical set on stdout, exit 0; invalid prints to stderr and
  exits 1.
- `intset has <set> <n>` -- `yes` or `no` on stdout, exit 0; an invalid set or a
  non-numeric value prints to stderr and exits 1.
- `intset add <set> <n>` -- canonical set on stdout, exit 0; invalid input prints to stderr
  and exits 1.
- Any other invocation -- usage on stderr, exit 2.

## Where things are

- Your implementation: `src/lib.rs`. `Cargo.toml`, `src/main.rs` and `tools/` are frozen.
- Your own tests: `tests/own/*.rs` (Cargo's integration tests), run with the `run_tests`
  action. That runs `cargo test`, so unit tests inside `src/lib.rs` would also run -- but
  put them in `tests/own/`, because that is what the record counts as a test.
- `tools/run_own_tests.sh` maps Cargo's exit status onto the contract: 0 ran and passed,
  1 ran and failed, 2 could not run. Cargo exits 101 for a compile error *and* for a failing
  test, so the runner tells those apart for you -- a build error is 2, not a RED.
- The acceptance corpus is not in this tree. Write the cases you would want to defend.
