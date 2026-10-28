# Stream Windows

windows(iterable, size) should lazily yield overlapping full windows as tuples. Validate size > 0 with ValueError before consuming input. Consume exactly size elements for the first result, then one per subsequent result, and work with one-shot iterators. No partial windows; too-short input yields nothing.

Run `python -m unittest discover -s tests -q` from this directory.
