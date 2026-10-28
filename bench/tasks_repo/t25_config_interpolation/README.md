# Config Interpolation

Implement resolve_config(values) for a mapping of string keys to strings. Expand ${name} references recursively, regardless of key order. $$ emits a literal dollar and must not start a reference (so $${x} becomes literal ${x}); inserted results are not scanned again. A lone dollar is literal. Empty values are valid. Raise ValueError for unknown references, unclosed ${...}, or any reference cycle, including unused/disconnected cycles. Return a new dict without mutating input. Reference names are the exact text between braces.

Run `python -m unittest discover -s tests -q` from this directory.
