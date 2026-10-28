# Business Days

Add add_business_days(start, offset, holidays=()). Move forward or backward by an integer number of business days, excluding Saturdays, Sundays, and supplied date holidays. Do not count the starting date. Offset zero returns start unchanged even on a holiday/weekend. Do not alter holidays; support date boundaries and leap days.

Run `python -m unittest discover -s tests -q` from this directory.
