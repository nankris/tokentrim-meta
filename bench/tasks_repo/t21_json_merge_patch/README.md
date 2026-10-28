# Json Merge Patch

Implement merge_patch(target, patch) with JSON merge-patch semantics: a non-dict patch replaces the whole target; a dict patch merges recursively into a dict target (or an empty dict for a non-dict target); None-valued members delete keys. Lists replace rather than merge. Never mutate either input, and return data with no mutable containers shared with either input, including untouched branches.

Run `python -m unittest discover -s tests -q` from this directory.
