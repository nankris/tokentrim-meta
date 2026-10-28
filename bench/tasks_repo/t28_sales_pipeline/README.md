# Sales Pipeline

Refactor sales_total(rows) and sales_by_region(rows) to share the same row interpretation. Preserve existing sale behavior: rows have region and integer amount, missing kind means sale. Add kind="refund", which subtracts amount, and kind="void", which is ignored even if region/amount are missing. Unknown kinds raise ValueError. Keep zero-total regions, preserve region first-seen order among nonvoid rows, accept one-shot iterables, and do not mutate rows.

Run `python -m unittest discover -s tests -q` from this directory.
