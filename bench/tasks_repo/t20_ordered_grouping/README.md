# Ordered Grouping

Implement group_rows(rows, key), returning a list of (group_value, rows_in_group) tuples in order of each group’s first appearance. Within groups preserve row order and original row objects. Missing key and explicit None belong to one None group; other falsey keys remain distinct according to normal Python equality. Consume an iterable once and do not mutate rows. Group values are hashable.

Run `python -m unittest discover -s tests -q` from this directory.
