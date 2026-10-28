# Tagged Records

Add tags to Record and its JSON storage. Record(id, text, tags=()) must store an independent list of unique tags in first-seen order, trimming whitespace and dropping empty tags; preserve case. dumps(records) writes version 2 with tags for each record. loads(text) accepts version 1 (tags omitted, default empty) and version 2 (tags required), rejects unknown versions with ValueError, and returns Records using the same normalization. Keep id/text round-trips and record_count working. Do not mutate input tag lists.

Run `python -m unittest discover -s tests -q` from this directory.
