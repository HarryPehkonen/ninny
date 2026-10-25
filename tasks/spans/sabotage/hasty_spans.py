"""A plausible-wrong implementation of SPEC.md, kept so the oracle's teeth are testable.

This is what coding to the happy path looks like. Every function works on the examples
the spec prints, and gets the *derivable* consequences wrong:

  * `canonical` merges on strict overlap (`lo < previous hi`) where the model says
    touching spans describe one set, so `[(1, 3), (3, 5)]` stays two spans;
  * `canonical` keeps zero-length spans, though a span that denotes nothing cannot be
    part of the shortest description of a set;
  * `contains` includes `hi`, though the model excludes it.

`parse` is deliberately correct: the point of this file is that the oracle catches the
set-semantics mistakes on their own, not that it catches a parse that breaks first.
"""

from __future__ import annotations

import re

_PART = re.compile(r"(\d+)\s*-\s*(\d+)")
_SINGLE = re.compile(r"(\d+)")


def parse(text: str) -> list[tuple[int, int]]:
    if text.strip() == "":
        return []
    spans: list[tuple[int, int]] = []
    for part in text.split(","):
        token = part.strip()
        m = _PART.fullmatch(token)
        if m is not None:
            lo, hi = int(m.group(1)), int(m.group(2))
        else:
            m = _SINGLE.fullmatch(token)
            if m is None:
                raise ValueError(f"malformed part: {part!r}")
            lo = int(m.group(1))
            hi = lo + 1
        if lo > hi:
            raise ValueError(f"reversed span: {part!r}")
        spans.append((lo, hi))
    return spans


def canonical(spans) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for lo, hi in sorted((int(lo), int(hi)) for lo, hi in spans):
        if out and lo < out[-1][1]:           # WRONG: touching spans are separate sets
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))              # WRONG: a zero-length span is kept
    return out


def contains(spans, x: int) -> bool:
    return any(lo <= x <= hi for lo, hi in spans)   # WRONG: hi is excluded
