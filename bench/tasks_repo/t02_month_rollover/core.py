from datetime import date
def next_month(value):
    return date(value.year, value.month + 1, value.day)
def billing_key(value):
    return value.strftime('%Y-%m')
