# Month Rollover

Repair next_month(date) for billing dates: move to the next calendar month, clamping the day to that month’s last day. Support leap years and December rollover; return a datetime.date.

Run `python -m unittest discover -s tests -q` from this directory.
