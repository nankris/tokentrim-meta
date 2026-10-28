import unittest
from core import histogram, total_count
class HistogramTests(unittest.TestCase):
    def test_boundaries(self):
        values, edges = [-2,0,0,1,2,3,5], [0,2,5]
        self.assertEqual(histogram(iter(values),edges),[1,3,2,1])
        self.assertEqual(values,[-2,0,0,1,2,3,5])
        self.assertEqual(edges,[0,2,5])
        self.assertEqual(histogram([-0.5,0,0.5],[0]),[1,2])
    def test_empty_and_invalid(self):
        self.assertEqual(histogram([1,2],[]),[2])
        self.assertEqual(histogram([],[0,1]),[0,0,0])
        self.assertEqual(total_count(histogram(range(10),[3,7])),10)
        for edges in ([1,1],[2,1],[0,2,1]):
            with self.assertRaises(ValueError): histogram([],edges)

if __name__ == "__main__":
    unittest.main()
