# Unicode Counts

word_counts(text) should count case-insensitive Unicode words. Normalize text to NFC then casefold. A word is a maximal run of alphabetic characters or Unicode combining marks attached after a letter; digits, underscores, punctuation and whitespace separate words. Ignore unattached marks. Return a plain dict of counts.

Run `python -m unittest discover -s tests -q` from this directory.
