import unittest
from datetime import date
from core import add_business_days, week_start
class CalendarTests(unittest.TestCase):
    def test_forward_backward(self):
        holidays = {date(2024,1,1),date(2023,12,30)}
        saved = holidays.copy()
        self.assertEqual(add_business_days(date(2023,12,29),1,holidays),date(2024,1,2))
        self.assertEqual(add_business_days(date(2024,1,2),-1,holidays),date(2023,12,29))
        self.assertEqual(holidays,saved)
    def test_weekend_zero_and_leap(self):
        self.assertEqual(add_business_days(date(2024,3,2),0),date(2024,3,2))
        self.assertEqual(add_business_days(date(2024,3,2),-1),date(2024,3,1))
        self.assertEqual(add_business_days(date(2024,2,28),2),date(2024,3,1))
        self.assertEqual(add_business_days(date(2024,3,1),-2),date(2024,2,28))
        self.assertEqual(week_start(date(2024,3,2)),date(2024,2,26))

if __name__ == "__main__":
    unittest.main()
