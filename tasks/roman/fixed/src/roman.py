"""A reference implementation of the roman task.

It exists for one reason: to prove the acceptance suite can pass. An oracle that
only ever fails is not evidence of anything, so this is the positive control.
"""

_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]
_DIGITS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def to_roman(n: int) -> str:
    if not isinstance(n, int):
        raise ValueError(f"not an integer: {n!r}")
    if not 1 <= n <= 3999:
        raise ValueError(f"out of range: {n!r}")
    out = []
    for value, text in _VALUES:
        while n >= value:
            out.append(text)
            n -= value
    return "".join(out)


def from_roman(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError(f"not a string: {s!r}")
    total = 0
    previous = 0
    for char in reversed(s):
        if char not in _DIGITS:
            raise ValueError(f"not a roman digit: {char!r}")
        value = _DIGITS[char]
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    if to_roman(total) != s:  # accepts exactly the canonical form of its own value
        raise ValueError(f"not a canonical numeral: {s!r}")
    return total
