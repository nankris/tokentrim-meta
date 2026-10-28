import unittest
from core import Inventory
class InventoryTests(unittest.TestCase):
    def test_idempotency_and_copies(self):
        stock, items = {'a':5}, {'a':2}
        inv = Inventory(stock)
        inv.reserve('r',items); inv.reserve('r',{'a':2})
        stock['a'] = 100; items['a'] = 4
        self.assertEqual(inv.available('a'),3)
        with self.assertRaises(ValueError): inv.reserve('r',{'a':1})
        self.assertTrue(inv.release('r'))
        self.assertEqual(inv.available('a'),5)
        self.assertFalse(inv.release('r'))
        inv.reserve('r',{'a':1})
        self.assertEqual(inv.available('a'),4)
    def test_atomic_failures(self):
        inv = Inventory({'a':5,'b':1})
        for items in ({'a':2,'b':2},{'a':2,'missing':0},{'a':-1}):
            with self.subTest(items=items), self.assertRaises(ValueError): inv.reserve('r',items)
            self.assertEqual((inv.available('a'),inv.available('b')),(5,1))
            self.assertFalse(inv.release('r'))
        inv.reserve('r',{})
        self.assertTrue(inv.release('r'))
        self.assertEqual(inv.available('missing'),0)

if __name__ == "__main__":
    unittest.main()
