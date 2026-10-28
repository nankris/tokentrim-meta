# Falsey Cache

Memo.get(key) should call its loader only on a cache miss. Cached None, False, zero, and empty strings are valid hits. A loader exception must propagate and must not cache a value; a later call can retry. clear() invalidates all keys.

Run `python -m unittest discover -s tests -q` from this directory.
