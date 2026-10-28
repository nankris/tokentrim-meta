# Interval Union

merge_ranges(ranges) must merge overlapping or touching half-open numeric ranges, return sorted (start, end) tuples, and leave caller input unchanged. Ignore empty ranges (start == end). Raise ValueError for reversed ranges even if they would otherwise be swallowed by a larger range.

Run `python -m unittest discover -s tests -q` from this directory.
