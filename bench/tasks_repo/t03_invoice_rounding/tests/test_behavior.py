import unittest
from core import invoice_total, invoice_label
from decimal import Decimal
class MoneyTests(unittest.TestCase):
    def test_per_line(self):
        self.assertEqual(invoice_total([('0.005', 1), ('0.005',1)]), Decimal('0.02'))
        self.assertEqual(invoice_total([('1.005',3), ('-0.005',1)]), Decimal('3.01'))
    def test_precision_and_empty(self):
        self.assertEqual(invoice_total([('9007199254740993.01',1)]), Decimal('9007199254740993.01'))
        self.assertEqual(invoice_total([]).as_tuple().exponent, -2)
        self.assertEqual(invoice_total([('2.50',2)]), Decimal('5.00'))
        self.assertEqual(invoice_label(7), 'INV-000007')

if __name__ == "__main__":
    unittest.main()
