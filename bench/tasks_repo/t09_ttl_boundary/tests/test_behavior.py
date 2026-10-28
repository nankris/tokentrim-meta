import unittest
from core import TTLCache
class TTLTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.cache = TTLCache(lambda: self.now)
    def test_expiry_boundary(self):
        self.cache.put('a', 7, 5)
        self.now = 14
        self.assertEqual(self.cache.get('a'),7)
        self.now = 15
        self.assertEqual(self.cache.get('a','missing'),'missing')
    def test_falsey_replace_and_invalidate(self):
        for value in (0,False,'',None):
            self.cache.put('a', value, 2)
            self.assertEqual(self.cache.get('a','missing'),value)
        self.now = 11
        self.cache.put('a',9,10)
        self.now = 12
        self.assertEqual(self.cache.get('a'),9)
        self.cache.put('a',8,0)
        self.assertIsNone(self.cache.get('a'))
        self.cache.put('b',1,-1)
        self.assertIsNone(self.cache.get('b'))
        self.assertEqual(self.cache.get('unknown',4),4)

if __name__ == "__main__":
    unittest.main()
