from datetime import date
from calendar import monthrange
def next_month(value):
    year = value.year + (value.month == 12)
    month = value.month % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))
def billing_key(value):
    return value.strftime('%Y-%m')
