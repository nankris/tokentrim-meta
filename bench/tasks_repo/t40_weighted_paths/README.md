# Weighted Paths

Implement shortest_path(graph, start, end) to satisfy the provided tests. graph maps string node names to dictionaries of neighbor names and nonnegative integer edge costs; neighbor-only nodes exist too. Return (total_cost, list_of_nodes) for the best directed path, or None if either endpoint is absent or no path exists. Among equal-cost paths choose fewer edges, then the lexicographically smallest complete node sequence. A known node to itself returns (0, [node]). Validate the entire graph and raise ValueError for any negative cost, even in unreachable components. Handle zero-cost cycles without looping and never mutate graph.

Run `python -m unittest discover -s tests -q` from this directory.
