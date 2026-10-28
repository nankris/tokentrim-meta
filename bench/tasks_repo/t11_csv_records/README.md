# Csv Records

read_records(text) mishandles CSV exports. Parse standard comma-separated CSV, including quoted commas, doubled quotes, and embedded newlines. The first nonblank record is the header; skip blank records, preserve field whitespace and empty fields, and return dict rows. Raise ValueError for duplicate headers or any data row with a different field count. Empty/blank-only input returns [].

Run `python -m unittest discover -s tests -q` from this directory.
