from datetime import timedelta
def add_business_days(start, offset, holidays=()):
    raise NotImplementedError('business calendar')
def week_start(day):
    return day - timedelta(days=day.weekday())
