# Nested Lookup

Fix lookup(data, path, default=None) for dotted paths through nested dictionaries and lists. Dictionary segments are literal keys, even numeric ones; list segments must contain only ASCII decimal digits and index from zero (leading zeros allowed). Missing keys, invalid/out-of-range indices, and traversal through scalars return default. Empty path returns the original data. Existing None/False values are valid results.

Run `python -m unittest discover -s tests -q` from this directory.
