import unittest
from core import next_month, billing_key
from datetime import date
class BillingTests(unittest.TestCase):
    def test_boundaries(self):
        for before, after in [(date(2024,1,31), date(2024,2,29)), (date(2023,1,30),date(2023,2,28)), (date(2024,12,31),date(2025,1,31)), (date(2024,3,31),date(2024,4,30))]:
            with self.subTest(before=before): self.assertEqual(next_month(before), after)
    def test_regular(self):
        self.assertEqual(next_month(date(2024,5,12)), date(2024,6,12))
        self.assertIs(type(next_month(date(2024,5,12))), date)
        self.assertEqual(billing_key(date(2024,5,12)), '2024-05')

if __name__ == "__main__":
    unittest.main()
