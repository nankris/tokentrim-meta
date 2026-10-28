import unittest
from core import word_counts, most_common
class WordsTests(unittest.TestCase):
    def test_unicode(self):
        self.assertEqual(word_counts('Straße STRASSE café cafe\u0301'), {'strasse':2,'café':2})
        self.assertEqual(word_counts('İ i\u0307 Ελληνικά'), {'i\u0307':2,'ελληνικά':1})
    def test_boundaries(self):
        self.assertEqual(word_counts('\u0301hello_world42HELLO!'), {'hello':2,'world':1})
        self.assertEqual(word_counts('123_!?'), {})
        self.assertEqual(most_common({'b':1,'a':1}), [('a',1),('b',1)])

if __name__ == "__main__":
    unittest.main()
