# Prefix Suggestions

Implement SuggestionIndex according to the tests. add(word) increments a word’s frequency; remove(word) removes one occurrence and returns True, or False if absent. suggest(prefix, limit=5) returns distinct words starting with prefix, ranked by descending frequency then lexicographically, truncated to limit. Zero limit returns []; negative limit raises ValueError. Matching is case-sensitive, empty words/prefixes are supported, and returned lists must be independent snapshots.

Run `python -m unittest discover -s tests -q` from this directory.
