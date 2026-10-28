import unittest
from core import split_fields, join_preview
class FieldsTests(unittest.TestCase):
    def test_escapes(self):
        self.assertEqual(split_fields(r'a\,b,c'), ['a,b', 'c'])
        self.assertEqual(split_fields(r'a\\,b'), ['a\\', 'b'])
        self.assertEqual(split_fields('x\\'), ['x\\'])
        self.assertEqual(split_fields(r'\q,z'), ['q', 'z'])
    def test_empty_and_spacing(self):
        for value, expected in [('', ['']), (',,', ['', '', '']), (' a,b,', [' a', 'b', ''])]:
            with self.subTest(value=value):
                self.assertEqual(split_fields(value), expected)
        self.assertEqual(join_preview(['a', 'b']), 'a | b')

if __name__ == "__main__":
    unittest.main()
