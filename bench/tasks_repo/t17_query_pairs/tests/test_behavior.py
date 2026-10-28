import unittest
from core import encode_query, append_query
class QueryTests(unittest.TestCase):
    def test_encoding(self):
        self.assertEqual(encode_query([('q','a b&c'),('q','é'),('x/y','+')]),'q=a+b%26c&q=%C3%A9&x%2Fy=%2B')
        self.assertEqual(encode_query([('n',None),('zero',0),('flag',False),('empty','')]),'zero=0&flag=False&empty=')
    def test_empty_iterator_and_append(self):
        self.assertEqual(encode_query(iter([('a',1)])),'a=1')
        self.assertEqual(encode_query([]),'')
        self.assertEqual(append_query('/x',''),'/x')
        self.assertEqual(append_query('/x?a=1','b=2'),'/x?a=1&b=2')

if __name__ == "__main__":
    unittest.main()
