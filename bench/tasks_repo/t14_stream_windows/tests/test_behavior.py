import unittest
from core import windows, pair_deltas
class WindowTests(unittest.TestCase):
    def test_overlap(self):
        self.assertEqual(list(windows(iter([1,2,3,4]),3)),[(1,2,3),(2,3,4)])
        self.assertEqual(list(windows([1],2)),[])
        self.assertEqual(list(windows([],1)),[])
        self.assertEqual(list(windows([1,2],1)),[(1,),(2,)])
        self.assertEqual(pair_deltas([1,4,9]),[3,5])
    def test_consumption(self):
        seen = []
        def source():
            for n in range(20):
                seen.append(n)
                yield n
        stream = windows(source(),3)
        self.assertEqual(seen,[])
        self.assertEqual(next(stream),(0,1,2))
        self.assertEqual(seen,[0,1,2])
        self.assertEqual(next(stream),(1,2,3))
        self.assertEqual(seen,[0,1,2,3])
        for size in (0,-2):
            seen.clear()
            with self.assertRaises(ValueError): list(windows(source(),size))
            self.assertEqual(seen,[])

if __name__ == "__main__":
    unittest.main()
