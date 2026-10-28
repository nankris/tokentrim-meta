# Route Matching

Implement Router.add(pattern, handler) and match(path). Patterns and paths start with /, split into slash-separated segments, and ignore trailing slashes; / has no segments. Patterns allow literal segments, :name for exactly one nonempty segment, and final *name for zero or more remaining segments joined by /. Names must be nonempty and unique in a pattern; nonfinal wildcards are invalid (ValueError). match returns (handler, captured_dict) or None. Choose the matching route with the lexicographically highest sequence of segment specificity (literal=2, parameter=1, wildcard=0); if tied, earlier registration wins. An exact route beats its own wildcard extension when the wildcard captures zero segments. Do not decode or normalize other path contents.

Run `python -m unittest discover -s tests -q` from this directory.
