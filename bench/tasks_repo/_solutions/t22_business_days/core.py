from datetime import timedelta
def add_business_days(start, offset, holidays=()):
    excluded = set(holidays)
    remaining = abs(offset)
    step = timedelta(days=1 if offset >= 0 else -1)
    current = start
    while remaining:
        current += step
        if current.weekday() < 5 and current not in excluded: remaining -= 1
    return current
def week_start(day):
    return day - timedelta(days=day.weekday())
