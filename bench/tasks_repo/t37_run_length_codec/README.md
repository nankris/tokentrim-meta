# Run Length Codec

Complete encode_runs(values) and decode_runs(runs) to satisfy the supplied behavioral tests. encode_runs returns (value, count) tuples for consecutive equal values, preserving order (do not combine separated runs). Values can be unhashable. decode_runs returns the expanded list; counts must be positive ints, excluding bool, otherwise ValueError. Both accept one-shot iterables and empty input; neither mutates input.

Run `python -m unittest discover -s tests -q` from this directory.
