# Slug Suffix

Implement unique_slug(title, used). Normalize title with NFKD, drop non-ASCII characters, lowercase, replace each run of non-alphanumeric characters with a hyphen, and trim hyphens. Use "item" if empty. If taken, try base-2, base-3, etc. and return the first free slug without changing used. Treat used slugs as exact, case-sensitive strings.

Run `python -m unittest discover -s tests -q` from this directory.
