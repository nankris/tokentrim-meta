import unittest
from decimal import Decimal
from money import to_cents, format_cents
from ledger import Ledger
class LedgerTests(unittest.TestCase):
    def test_money(self):
        for value,expected in [('1.005',101),('-1.005',-101),(Decimal('0.005'),1),('9007199254740993.01',900719925474099301)]:
            self.assertEqual(to_cents(value),expected)
        self.assertEqual(format_cents(-1),'-0.01')
        self.assertEqual(format_cents(900719925474099301),'9007199254740993.01')
        for value in ('bad','NaN','Infinity','-Infinity'):
            with self.assertRaises(ValueError): to_cents(value)
    def test_transfer(self):
        opening = {'a':'10.00','b':'0'}
        ledger = Ledger(opening)
        ledger.transfer('a','b','1.005')
        self.assertEqual((ledger.balance('a'),ledger.balance('b')),('8.99','1.01'))
        ledger.transfer('a','a','8.99')
        self.assertEqual(ledger.balance('a'),'8.99')
        self.assertEqual(opening,{'a':'10.00','b':'0'})
    def test_failed_transfers_atomic(self):
        ledger = Ledger({'a':'2','b':'0'})
        for source,target,amount,error in [('a','b','3',ValueError),('a','b','0.004',ValueError),('a','b','-1',ValueError),('a','x','1',KeyError),('x','b','1',KeyError),('a','a','3',ValueError)]:
            with self.subTest(source=source,target=target,amount=amount), self.assertRaises(error): ledger.transfer(source,target,amount)
            self.assertEqual((ledger.balance('a'),ledger.balance('b')),('2.00','0.00'))
        with self.assertRaises(ValueError): Ledger({'a':'-1'})
        with self.assertRaises(KeyError): ledger.balance('missing')

if __name__ == "__main__":
    unittest.main()
