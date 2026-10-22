#!/usr/bin/env python3
"""The acceptance suite for the `roman` task.

This file lives OUTSIDE the task tree, and `ninny check` stages the submission
beside it rather than running inside it. The agent never sees this file; if it
could, it could write its own tests from the answer key and both "did it write
tests" and "did it write them first" would stop meaning anything.

Run it with:

    ninny check --task tasks/roman --tree runs/roman/<arm>/tree
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

TREE = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NINNY_TREE", ".")).resolve()
SRC = TREE / "src" / "roman.py"

LOAD_ERROR = ""
roman = None
if not SRC.is_file():
    LOAD_ERROR = f"there is no file at {SRC} -- src/roman.py is missing"
else:
    try:
        spec = importlib.util.spec_from_file_location("submission_roman", SRC)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {SRC}")
        roman = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(roman)
    except Exception as exc:  # noqa: BLE001 - any import failure is an acceptance failure
        roman = None
        LOAD_ERROR = f"{type(exc).__name__}: {exc}"

SMALL = [(1, "I"), (2, "II"), (3, "III"), (4, "IV"), (5, "V"), (6, "VI"), (7, "VII"),
         (8, "VIII"), (9, "IX"), (10, "X")]
MEDIUM = [(11, "XI"), (14, "XIV"), (19, "XIX"), (40, "XL"), (44, "XLIV"), (49, "XLIX"),
          (50, "L"), (90, "XC"), (99, "XCIX"), (100, "C")]
LARGE = [(400, "CD"), (444, "CDXLIV"), (500, "D"), (900, "CM"), (999, "CMXCIX"), (1000, "M"),
         (1987, "MCMLXXXVII"), (2026, "MMXXVI"), (3888, "MMMDCCCLXXXVIII"), (3999, "MMMCMXCIX")]
INVALID = ["", "A", "IIII", "VV", "LL", "DD", "MMMM", "IVI", "XIIX", "ix", "12", "M M", "CMCMC"]


class Acceptance(unittest.TestCase):
    def setUp(self):
        if roman is None:
            self.fail(f"could not import src/roman.py: {LOAD_ERROR}")
        for name in ("to_roman", "from_roman"):
            if not callable(getattr(roman, name, None)):
                self.fail(
                    f"src/roman.py must export a callable {name}(), found {getattr(roman, name, None)!r}"
                )

    def assert_table(self, cases):
        for value, text in cases:
            with self.subTest(value=value):
                self.assertEqual(roman.to_roman(value), text)

    def test_to_roman_small(self):
        self.assert_table(SMALL)

    def test_to_roman_medium(self):
        self.assert_table(MEDIUM)

    def test_to_roman_large(self):
        self.assert_table(LARGE)

    def test_to_roman_out_of_range(self):
        for value in (0, -1, -3999, 4000, 5000, 10 ** 9):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    roman.to_roman(value)

    def test_from_roman(self):
        for value, text in SMALL + MEDIUM + LARGE:
            with self.subTest(text=text):
                self.assertEqual(roman.from_roman(text), value)

    def test_from_roman_invalid(self):
        for text in INVALID:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    roman.from_roman(text)

    def test_from_roman_non_string(self):
        for value in (123, None, 1.5, b"X", ["X"]):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    roman.from_roman(value)

    def test_roundtrip_every_value(self):
        for n in range(1, 4000):
            got = roman.from_roman(roman.to_roman(n))
            if got != n:
                self.fail(f"round-trip failed at {n}: {roman.to_roman(n)} -> {got}")

    def test_standard_library_only(self):
        text = SRC.read_text()
        for banned in ("import requests", "import numpy", "import pytest", "import roman"):
            self.assertNotIn(banned, text)


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromTestCase(Acceptance)
    )
    checks = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nACCEPTANCE: {checks} tests, {failed} failed")
    verdict = "GATE PASSED" if failed == 0 and checks > 0 else "GATE FAILED"
    print(verdict)
    return 0 if verdict == "GATE PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
