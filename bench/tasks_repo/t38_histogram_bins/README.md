# Histogram Bins

Implement histogram(values, edges) from the supplied tests. For n strictly increasing numeric edges return n+1 counts: below edge[0], then half-open intervals [edge[i], edge[i+1]), then values >= the last edge. With no edges every value belongs to the single bin. Values/edges contain finite numbers. Reject duplicate or unsorted edges with ValueError, do not mutate inputs, and support one-shot values iterators.

Run `python -m unittest discover -s tests -q` from this directory.
