# Your tests go here

`tests/own/main.rs` is the integration test target Cargo discovers, and it is the only file in
this directory that is compiled by itself. Everything you want to run must be reachable from it:

* put your cases in `main.rs` as `#[test]` functions, or
* split them across sibling files and declare each one in `main.rs` with `mod merging;`.

A sibling file that `main.rs` does not declare is never compiled, so `cargo test` runs nothing
and `tools/run_own_tests.sh` answers exit 2 -- "nothing ran", which is not a red. Unit tests
inside `src/lib.rs` are run as well, so both places work.

No dependencies, and none may be added:

```rust
use intset::{add, contains, normalize};

#[test]
fn a_reversed_range_is_not_a_set() {
    assert_eq!(normalize("11-9"), None);
}

#[test]
fn merging_is_ascending() {
    assert_eq!(normalize("1-3,7,9-10,3-5"), Some("1-5,7,9-10".to_string()));
}
```

`tools/run_own_tests.sh` runs `cargo test` and reports the contract: exit 0 when the tests
ran and passed, 1 when they ran and failed, 2 when nothing could run -- a compile error, or
a suite where no case ran at all. Cargo itself exits 101 for both a compile error and a
failing test, so the runner separates them; a build error is never banked as a RED.

These cases are the only tests anybody will read when they ask whether the implementation
can be trusted. Write the ones you would want to defend: the boundaries of the notation,
the rejected input, and at least one property that has to hold for every set rather than
for the examples you happened to pick.
