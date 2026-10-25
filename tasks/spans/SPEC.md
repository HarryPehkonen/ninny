# Spans: half-open integer ranges

Implement `src/spans.py` so that it exports three functions.

```python
def parse(text: str) -> list[tuple[int, int]]: ...
def canonical(spans) -> list[tuple[int, int]]: ...
def contains(spans, x: int) -> bool: ...
```

## The model

A **span** is a pair of integers `(lo, hi)` denoting every integer `x` with
`lo <= x < hi`: `lo` is in the set and `hi` is not. So `(1, 3)` denotes `{1, 2}`,
`(3, 3)` denotes nothing at all, and a list of spans denotes the union of what its
spans denote.

Everything below follows from that one sentence. Where a requirement spells out a
consequence, it does so because the consequence is easy to get wrong — not because
it is the only one.

## Requirements

1. `parse(text)` turns the text form into spans and returns them **exactly as they
   appear**: in the order given, not sorted, not merged, nothing dropped.
   - A part is either `lo-hi`, or a single integer `n` meaning the span `(n, n + 1)`.
   - Parts are separated by commas. Whitespace around a part and around the hyphen
     is ignored.
   - The empty text `""` is the empty list `[]`.
   - `"1-3,3-5"` is `[(1, 3), (3, 5)]` — two spans, not one.
   - `"5-5"` is `[(5, 5)]` — a span, however empty the set it denotes.
2. `parse` raises `ValueError` for a part that is not well formed — an empty part, a
   missing or repeated hyphen, a non-integer, a negative number — and for `lo > hi`.
3. `canonical(spans)` returns the list of spans that denotes **the same set** and is
   the **shortest such list**, ordered by `lo`. It accepts spans in any order, and it
   accepts spans that no text form could carry: a span with `hi <= lo` denotes the
   empty set and is not an error, it simply cannot appear in the answer.
4. `contains(spans, x)` is `True` when the integer `x` is in the set a list of spans
   denotes, for any list of spans, in any order.
5. Where a round trip is defined, it must hold:
   `canonical(canonical(s)) == canonical(s)` for any list of spans, and for any text
   `t` that `parse` accepts, `canonical(parse(t))` is the shortest span list denoting
   the set `t` describes.
6. Standard library only. No third-party imports.

## Where things are

- Put your implementation in `src/spans.py`.
- Put your own tests in `tests/own/` and run them with the `run_tests` action, which
  runs `tools/run_own_tests.sh`. That script fails when `tests/own/` contains no
  tests at all, because "no tests" is not "tests passed".
- `tools/` is not yours to edit.
