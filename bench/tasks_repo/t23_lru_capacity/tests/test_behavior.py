import unittest
from core import LRUCache
class LRUTests(unittest.TestCase):
    def test_recency(self):
        c = LRUCache(2)
        c.put('a',1); c.put('b',2)
        self.assertEqual(c.get('a'),1)
        c.put('c',3)
        self.assertEqual(c.get('b','gone'),'gone')
        self.assertEqual(len(c),2)
        c.put('a',4)
        c.get('missing')
        c.put('d',5)
        self.assertIsNone(c.get('c'))
        self.assertEqual(c.get('a'),4)
    def test_falsey_and_capacity(self):
        c = LRUCache(1)
        for value in (None,False,0,''):
            c.put('x',value)
            self.assertEqual(c.get('x','missing'),value)
            self.assertEqual(len(c),1)
        c.put('y',2)
        self.assertEqual(c.get('x','missing'),'missing')
        for capacity in (0,-1):
            with self.assertRaises(ValueError): LRUCache(capacity)

if __name__ == "__main__":
    unittest.main()
