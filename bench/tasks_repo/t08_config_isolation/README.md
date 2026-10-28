# Config Isolation

load_config(overrides) leaks changes between requests. Return a fresh deep copy of DEFAULTS with top-level overrides replacing entire values. Neither defaults nor any nested override objects may be shared with the returned config. None means no overrides; preserve falsey overrides and unknown keys.

Run `python -m unittest discover -s tests -q` from this directory.
