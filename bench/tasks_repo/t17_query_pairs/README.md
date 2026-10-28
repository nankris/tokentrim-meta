# Query Pairs

Add encode_query(pairs) for ordered (key, value) pairs. Percent-encode UTF-8 keys and values using URL query rules (spaces become +). Preserve duplicate keys and order. Skip None values, stringify other values, and return an empty string when there are no emitted pairs. Keep append_query behavior for existing encoded strings.

Run `python -m unittest discover -s tests -q` from this directory.
