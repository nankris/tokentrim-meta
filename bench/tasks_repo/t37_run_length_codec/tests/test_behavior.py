import unittest
from core import encode_runs, decode_runs, encoded_size
from copy import deepcopy
class RunTests(unittest.TestCase):
    def test_round_trip(self):
        values = [1,1,2,1,None,None]
        self.assertEqual(encode_runs(iter(values)),[(1,2),(2,1),(1,1),(None,2)])
        self.assertEqual(decode_runs(iter(encode_runs(values))),values)
        self.assertEqual(encode_runs([]),[])
        self.assertEqual(decode_runs([]),[])
        self.assertEqual(encoded_size([(1,2)]),1)
    def test_unhashable_and_validation(self):
        values = [[1],[1],[2]]
        saved = deepcopy(values)
        self.assertEqual(encode_runs(values),[([1],2),([2],1)])
        self.assertEqual(values,saved)
        for count in (0,-1,True,False,1.5,'2'):
            with self.subTest(count=count), self.assertRaises(ValueError): decode_runs([('a',count)])

if __name__ == "__main__":
    unittest.main()
