# Roman numerals

Implement `src/roman.py` so that it exports two functions.

```python
def to_roman(n: int) -> str: ...
def from_roman(s: str) -> int: ...
```

## Requirements

1. `to_roman` returns the standard Roman form of any integer in `1..3999`, using
   the subtractive forms `IV`, `IX`, `XL`, `XC`, `CD`, `CM`.
2. `to_roman` raises `ValueError` for any integer outside `1..3999` — including
   `0`, negatives, and `4000` or more.
3. `from_roman` parses a Roman numeral and returns its integer value.
4. `from_roman` raises `ValueError` for anything that is not a valid numeral.
   A string is valid **if and only if it is exactly the canonical form of its own
   value** — so the empty string, lowercase letters, unknown letters, `IIII`,
   `VV`, `LL`, `DD`, `MMMM` and `IVI` are all invalid. Non-string input (for
   example an `int`) raises `ValueError` too.
5. Round-tripping must hold for every value:
   `from_roman(to_roman(n)) == n` for all `n` in `1..3999`.
6. Standard library only. No third-party imports.

## Where things are

- Put your implementation in `src/roman.py`.
- Put your own tests in `tests/own/` and run them with the `run_tests` action,
  which runs `tools/run_own_tests.sh`. That script fails when `tests/own/`
  contains no tests at all, because "no tests" is not "tests passed".
- `tools/` is not yours to edit.
