import unittest
from core import sales_total, sales_by_region
from copy import deepcopy
class SalesTests(unittest.TestCase):
    def test_legacy(self):
        rows = [{'region':'west','amount':3},{'region':'east','amount':4}]
        self.assertEqual(sales_total(iter(rows)),7)
        self.assertEqual(sales_by_region(iter(rows)),{'west':3,'east':4})
        self.assertEqual(sales_total([]),0)
    def test_kinds_and_order(self):
        rows = [{'kind':'void'}, {'region':'b','amount':5}, {'region':'a','amount':2,'kind':'refund'}, {'region':'b','amount':5,'kind':'refund'}]
        saved = deepcopy(rows)
        self.assertEqual(sales_total(iter(rows)),-2)
        grouped = sales_by_region(iter(rows))
        self.assertEqual(list(grouped.items()),[('b',0),('a',-2)])
        self.assertEqual(rows,saved)
    def test_unknown(self):
        for fn in (sales_total,sales_by_region):
            with self.assertRaises(ValueError): fn([{'region':'x','amount':1,'kind':'mystery'}])

if __name__ == "__main__":
    unittest.main()
