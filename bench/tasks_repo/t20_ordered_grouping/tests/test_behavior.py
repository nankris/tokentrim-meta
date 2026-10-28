import unittest
from core import group_rows, select_columns
from copy import deepcopy
class GroupTests(unittest.TestCase):
    def test_order_and_identity(self):
        rows = [{'k':'b','n':1},{'k':'a','n':2},{'k':'b','n':3}]
        saved = deepcopy(rows)
        result = group_rows(iter(rows),'k')
        self.assertEqual(result,[('b',[rows[0],rows[2]]),('a',[rows[1]])])
        self.assertIs(result[0][1][0],rows[0])
        self.assertEqual(rows,saved)
    def test_missing_and_falsey(self):
        rows = [{},{'k':None},{'k':''},{'k':0}]
        self.assertEqual(group_rows(rows,'k'),[(None,rows[:2]),('',[rows[2]]),(0,[rows[3]])])
        self.assertEqual(group_rows([],'k'),[])
        self.assertEqual(select_columns({'a':1},['a','b']),{'a':1})

if __name__ == "__main__":
    unittest.main()
