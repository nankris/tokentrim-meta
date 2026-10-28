import unittest
from core import SuggestionIndex, highlight
class SuggestionTests(unittest.TestCase):
    def test_ranking_and_removal(self):
        index = SuggestionIndex()
        for word in ('ape','apple','apricot','apple','ape','apple','banana'): index.add(word)
        self.assertEqual(index.suggest('ap'),['apple','ape','apricot'])
        self.assertTrue(index.remove('apple'))
        self.assertEqual(index.suggest('ap',2),['ape','apple'])
        self.assertTrue(index.remove('apricot'))
        self.assertFalse(index.remove('apricot'))
        self.assertEqual(index.suggest('ap',9),['ape','apple'])
    def test_limits_empty_and_snapshot(self):
        index = SuggestionIndex()
        self.assertEqual(index.suggest(''),[])
        for word in ('a','A','','b','c','d','e'): index.add(word)
        self.assertEqual(index.suggest(''),['','A','a','b','c'])
        self.assertEqual(index.suggest('a'),['a'])
        self.assertEqual(index.suggest('',0),[])
        with self.assertRaises(ValueError): index.suggest('',-1)
        result = index.suggest('')
        result.clear()
        self.assertEqual(index.suggest(''),['','A','a','b','c'])
        self.assertEqual(highlight('apple','ap'),'[ap]ple')

if __name__ == "__main__":
    unittest.main()
