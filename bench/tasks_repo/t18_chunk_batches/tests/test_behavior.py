import unittest
from core import batches, batch_label
class BatchTests(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(list(batches(iter(range(5)),2)),[[0,1],[2,3],[4]])
        self.assertEqual(list(batches([],3)),[])
        self.assertEqual(list(batches([1,2],1)),[[1],[2]])
        self.assertEqual(batch_label(2),'batch-0002')
    def test_lazy_independent(self):
        seen = []
        def source():
            for n in range(9):
                seen.append(n)
                yield n
        stream = batches(source(),2)
        self.assertEqual(seen,[])
        first = next(stream)
        self.assertEqual(seen,[0,1])
        first.append(99)
        self.assertEqual(next(stream),[2,3])
        self.assertEqual(seen,[0,1,2,3])
        for size in (0,-1):
            seen.clear()
            with self.assertRaises(ValueError): list(batches(source(),size))
            self.assertEqual(seen,[])

if __name__ == "__main__":
    unittest.main()
