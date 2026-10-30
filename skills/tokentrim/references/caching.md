# Prompt-cache rules (provider prefix caches)

Providers bill cached input at a fraction of the normal input price (Meta Muse Spark Contributor: 2%;
Standard: 12%). A cache hit needs the new request to start with exactly the same bytes as an earlier one.

- Put stable content first: system instructions, then tool schemas, then pinned files, then the conversation.
- Serialize tool schemas deterministically (sorted by name, sorted keys). Do not rebuild them from a set.
- Keep timestamps, request ids, UUIDs and random session tags OUT of the system prompt. If the date matters,
  use a day-level date. On the Meta API, moving such lines to a trailing message did not restore hits;
  removing them did (TokenTrim issue 55).
- Append; do not rewrite. Editing or deleting an early message invalidates everything after it.
- Measured hit rates on Meta were intermittent (about 12% of calls in our runs), so do not count on hits:
  removing tokens still pays when hits are rare.
