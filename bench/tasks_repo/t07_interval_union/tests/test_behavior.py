import unittest
from core import merge_ranges, covered_length
class RangeTests(unittest.TestCase):
    def test_merge_and_input(self):
        ranges = [(5,8),(1,10),(2,3),(10,12),(14,14)]
        saved = list(ranges)
        self.assertEqual(merge_ranges(ranges), [(1,12)])
        self.assertEqual(ranges, saved)
    def test_empty_disjoint_invalid(self):
        self.assertEqual(merge_ranges([]), [])
        self.assertEqual(merge_ranges([(3,4),(-2,0)]), [(-2,0),(3,4)])
        self.assertEqual(covered_length([(1,3),(3,5)]),4)
        with self.assertRaises(ValueError): merge_ranges([(0,10),(7,6)])

if __name__ == "__main__":
    unittest.main()
