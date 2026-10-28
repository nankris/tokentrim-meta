# Escaped Fields

Fix split_fields(line): split on unescaped commas. A backslash escapes the next character (including comma or backslash); a final unmatched backslash is literal. Preserve empty fields and whitespace. Empty input means one empty field.

Run `python -m unittest discover -s tests -q` from this directory.
