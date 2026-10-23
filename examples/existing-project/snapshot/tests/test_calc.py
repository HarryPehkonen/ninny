import unittest

from calc.core import add


class CalcTest(unittest.TestCase):
    def test_add_positives(self):
        self.assertEqual(add(2, 3), 5)

    def test_add_negatives(self):
        self.assertEqual(add(-2, -3), -5)

    def test_add_zero(self):
        self.assertEqual(add(0, 0), 0)
