# Export Dispatch

Refactor the report exporters to share render(rows, format, columns). Keep as_json(rows) and as_text(rows, columns) byte-for-byte compatible: JSON uses sort_keys=True; text emits tab-joined columns with missing values empty, one line per row, no trailing newline. Add render formats json, text, csv (unknown format raises ValueError). CSV includes a header even with no rows, uses CRLF record endings and standard CSV quoting, writes None/missing as empty, and follows columns order. JSON ignores columns. Support one-shot row iterables.

Run `python -m unittest discover -s tests -q` from this directory.
