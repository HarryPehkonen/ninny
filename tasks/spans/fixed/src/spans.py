"""Spans -- the answer key for `tasks/spans`. See SPEC.md.

Kept outside tree/ so that it is never copied into a run: it exists for
`ninny verify-task`'s answer-key control, and for the oracle's teeth test.
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
        if hi <= lo:
            # The empty set cannot appear in the shortest description of a set.
            continue
        if out and lo <= out[-1][1]:
            # lo <= previous hi covers both overlapping and merely touching spans.
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return out


def contains(spans, x: int) -> bool:
    # hi is excluded -- that is the whole of the model.
    return any(lo <= x < hi for lo, hi in spans)
