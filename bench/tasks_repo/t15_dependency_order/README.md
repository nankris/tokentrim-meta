# Dependency Order

Fix build_order(graph), where each mapping key is a job and its iterable value names prerequisites. Return every key and prerequisite-only job once, prerequisites first. At each step choose the lexicographically smallest currently ready job. Duplicate edges count once. Raise ValueError on any cycle (including disconnected cycles or self-loops), and never mutate graph or its lists.

Run `python -m unittest discover -s tests -q` from this directory.
