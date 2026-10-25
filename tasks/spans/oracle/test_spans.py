#!/usr/bin/env python3
"""The acceptance suite for the `spans` task.

This file lives OUTSIDE the task tree, and `ninny check` stages the submission
beside it rather than running inside it. The agent never sees this file; if it
could, it could write its own tests from the answer key and both "did it write
tests" and "did it write them first" would stop meaning anything.

Everything here follows from the one axiom in SPEC.md -- a span `(lo, hi)` denotes
`lo <= x < hi` and a list denotes the union -- so nothing is checked that the spec
does not already imply. That is the point of the task: the contract is complete, and
its consequences are easy to miss.

Run it with:

    ninny check --task tasks/spans --tree runs/spans/<arm>/tree
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

TREE = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NINNY_TREE", ".")).resolve()
SRC = TREE / "src" / "spans.py"

LOAD_ERROR = ""
spans = None
if not SRC.is_file():
    LOAD_ERROR = f"there is no file at {SRC} -- src/spans.py is missing"
else:
    try:
        spec = importlib.util.spec_from_file_location("submission_spans", SRC)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {SRC}")
        spans = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(spans)
    except Exception as exc:  # noqa: BLE001 - any import failure is an acceptance failure
        spans = None
        LOAD_ERROR = f"{type(exc).__name__}: {exc}"


def call(name, *args):
    return getattr(spans, name)(*args)


def pairs(value):
    """Any iterable of pairs, as a list of int tuples, so a list of lists is accepted."""
    return [(int(lo), int(hi)) for lo, hi in value]


class TheSubmissionLoads(unittest.TestCase):
    def test_the_file_loads_and_exports_all_three_functions(self):
        if LOAD_ERROR:
            self.fail(f"src/spans.py did not load: {LOAD_ERROR}")
        for name in ("parse", "canonical", "contains"):
            with self.subTest(function=name):
                self.assertTrue(callable(getattr(spans, name, None)),
                                f"src/spans.py does not export a callable {name}")


class Parse(unittest.TestCase):
    """The text form, returned as written -- no sorting, no merging, nothing dropped."""

    def test_the_empty_text_is_the_empty_list(self):
        self.assertEqual(pairs(call("parse", "")), [])

    def test_a_single_integer_is_a_span_of_length_one(self):
        self.assertEqual(pairs(call("parse", "7")), [(7, 8)])

    def test_a_range_is_kept_as_given(self):
        self.assertEqual(pairs(call("parse", "1-3")), [(1, 3)])

    def test_a_touching_pair_is_returned_as_two_spans(self):
        self.assertEqual(pairs(call("parse", "1-3,3-5")), [(1, 3), (3, 5)])

    def test_a_span_of_no_length_survives_parse(self):
        self.assertEqual(pairs(call("parse", "5-5")), [(5, 5)])

    def test_order_is_preserved(self):
        self.assertEqual(pairs(call("parse", "9-10,1-2")), [(9, 10), (1, 2)])

    def test_whitespace_around_parts_and_around_the_hyphen_is_ignored(self):
        self.assertEqual(pairs(call("parse", " 1 - 3 ,  5 ")), [(1, 3), (5, 6)])

    def test_a_longer_text_form(self):
        self.assertEqual(pairs(call("parse", "1,2-4,6-6,7")), [(1, 2), (2, 4), (6, 6), (7, 8)])

    def test_malformed_text_is_refused(self):
        for bad in ("1-", "-3", "1--3", "3-1", "a", "1.5", "1,", ",1", "1,,2", "1 2",
                    "1-2-3", ",", "-", "1-3,x"):
            with self.subTest(text=bad):
                with self.assertRaises(ValueError):
                    call("parse", bad)


class Canonical(unittest.TestCase):
    """The same set, described in the fewest spans, ordered by lo."""

    def test_the_empty_list_stays_empty(self):
        self.assertEqual(pairs(call("canonical", [])), [])

    def test_a_lone_span_is_already_canonical(self):
        self.assertEqual(pairs(call("canonical", [(1, 3)])), [(1, 3)])

    def test_overlapping_spans_become_one(self):
        self.assertEqual(pairs(call("canonical", [(1, 3), (2, 4)])), [(1, 4)])

    def test_touching_spans_become_one(self):
        self.assertEqual(pairs(call("canonical", [(1, 3), (3, 5)])), [(1, 5)])

    def test_a_span_inside_another_disappears(self):
        self.assertEqual(pairs(call("canonical", [(1, 10), (3, 4)])), [(1, 10)])

    def test_a_span_of_no_length_disappears(self):
        self.assertEqual(pairs(call("canonical", [(5, 5)])), [])

    def test_a_reversed_span_is_empty_and_disappears(self):
        self.assertEqual(pairs(call("canonical", [(5, 3)])), [])

    def test_duplicates_become_one(self):
        self.assertEqual(pairs(call("canonical", [(1, 3), (1, 3)])), [(1, 3)])

    def test_an_empty_span_does_not_stop_its_neighbours_touching(self):
        self.assertEqual(pairs(call("canonical", [(1, 3), (3, 3), (3, 5)])), [(1, 5)])

    def test_the_answer_is_ordered_by_lo(self):
        self.assertEqual(pairs(call("canonical", [(9, 10), (1, 2)])), [(1, 2), (9, 10)])

    def test_a_gap_is_not_bridged(self):
        self.assertEqual(pairs(call("canonical", [(1, 3), (4, 6)])), [(1, 3), (4, 6)])

    def test_a_chain_of_touching_spans_becomes_one(self):
        self.assertEqual(pairs(call("canonical", [(1, 2), (2, 3), (3, 4)])), [(1, 4)])

    def test_two_clusters_stay_two(self):
        self.assertEqual(pairs(call("canonical", [(1, 2), (2, 3), (10, 11), (11, 12)])),
                         [(1, 3), (10, 12)])

    def test_negative_integers_are_ordinary_members(self):
        self.assertEqual(pairs(call("canonical", [(-3, -1), (-1, 2)])), [(-3, 2)])

    def test_the_shape_of_every_answer(self):
        cases = [[(1, 3), (3, 5)], [(5, 3)], [(0, 0)], [(7, 9), (1, 2), (2, 7)],
                 [(1, 2), (2, 3), (3, 4)], [(4, 6), (1, 3)], [(2, 2), (3, 3)]]
        for raw in cases:
            with self.subTest(spans=raw):
                out = pairs(call("canonical", raw))
                for lo, hi in out:
                    self.assertLess(lo, hi, f"{raw} -> {out}: a span that denotes nothing")
                for (lo1, hi1), (lo2, _) in zip(out, out[1:]):
                    self.assertLess(hi1, lo2, f"{raw} -> {out}: two spans that could be one")

    def test_canonical_is_idempotent(self):
        cases = [[(1, 3), (3, 5)], [(5, 3)], [(7, 9), (1, 2), (2, 7)], [], [(1, 2), (2, 3)]]
        for raw in cases:
            with self.subTest(spans=raw):
                once = pairs(call("canonical", raw))
                self.assertEqual(pairs(call("canonical", once)), once)

    def test_parse_then_canonical_is_the_shortest_form(self):
        cases = [("1-3,3-5", [(1, 5)]),
                 ("5-5", []),
                 ("3-5,1-3", [(1, 5)]),
                 ("1-3,4-6", [(1, 3), (4, 6)]),
                 ("2,3,4,5", [(2, 6)]),
                 ("", [])]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(pairs(call("canonical", call("parse", text))), expected)


class Contains(unittest.TestCase):
    """Membership, with hi excluded."""

    def test_lo_is_in(self):
        self.assertTrue(call("contains", [(1, 3)], 1))

    def test_a_point_between_them_is_in(self):
        self.assertTrue(call("contains", [(1, 3)], 2))

    def test_hi_is_out(self):
        self.assertFalse(call("contains", [(1, 3)], 3))

    def test_below_is_out(self):
        self.assertFalse(call("contains", [(1, 3)], 0))

    def test_above_is_out(self):
        self.assertFalse(call("contains", [(1, 3)], 4))

    def test_a_span_of_no_length_contains_nothing(self):
        self.assertFalse(call("contains", [(5, 5)], 5))

    def test_the_empty_list_contains_nothing(self):
        self.assertFalse(call("contains", [], 5))

    def test_spans_need_not_be_in_order(self):
        self.assertTrue(call("contains", [(3, 5), (1, 3)], 4))
        self.assertTrue(call("contains", [(3, 5), (1, 3)], 1))

    def test_a_touching_boundary_belongs_to_the_upper_span(self):
        self.assertTrue(call("contains", [(1, 3), (3, 5)], 3))
        self.assertFalse(call("contains", [(1, 3), (3, 5)], 5))

    def test_canonical_does_not_change_membership(self):
        cases = [([(1, 3), (3, 5)], 2), ([(5, 3)], 4), ([(7, 9), (1, 4)], 3),
                 ([(2, 2)], 2), ([(1, 2), (2, 3)], 2)]
        for raw, x in cases:
            with self.subTest(spans=raw, x=x):
                self.assertEqual(call("contains", raw, x),
                                 call("contains", call("canonical", raw), x))


CASES = (TheSubmissionLoads, Parse, Canonical, Contains)


def main() -> int:
    # The suite is built explicitly rather than through unittest.main(): argv[1] is the
    # tree, and unittest.main() would read it as a test selector.
    suite = unittest.TestSuite(
        unittest.TestLoader().loadTestsFromTestCase(case) for case in CASES
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    checks = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nACCEPTANCE: {checks} tests, {failed} failed")
    verdict = "GATE PASSED" if failed == 0 and checks > 0 else "GATE FAILED"
    print(verdict)
    return 0 if verdict == "GATE PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
