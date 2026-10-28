import unittest
from core import Memo
class CacheTests(unittest.TestCase):
    def test_falsey_hits_and_clear(self):
        for value in (None, False, 0, '', []):
            with self.subTest(value=value):
                calls = []
                cache = Memo(lambda key: (calls.append(key), value)[1])
                self.assertEqual(cache.get('a'), value)
                self.assertEqual(cache.get('a'), value)
                self.assertEqual(calls, ['a'])
                cache.get('b')
                cache.clear()
                cache.get('a')
                self.assertEqual(calls, ['a','b','a'])
    def test_retry(self):
        calls = []
        def load(key):
            calls.append(key)
            if len(calls) == 1: raise ValueError('temporary')
            return 9
        cache = Memo(load)
        with self.assertRaises(ValueError): cache.get('x')
        self.assertEqual(cache.get('x'),9)
        self.assertEqual(cache.get('x'),9)
        self.assertEqual(len(calls),2)

if __name__ == "__main__":
    unittest.main()
