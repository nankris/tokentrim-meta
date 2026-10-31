# Validation probe (zero Meta spend)
claude-haiku-5-5 via `claude -p` (subscription CLI), on items DISJOINT from the pre-registered Meta slices
(BFCL `bfcl_slice(24, offset=100)`, LogChunks `lc_slice(24, offset=120)`). Purpose: check plumbing and graders on a
real model, NOT a measured result. The CLI cannot take OpenAI tools, so schemas/logs are pasted into the prompt.

| arm | passed /24 | CLI input tokens (incl. CLI system prompt) |
|---|---|---|
| BFCL full (40 tools) | 15 | 667,103 |
| BFCL routed (router top-6 only, strict, no search) | 15 | 402,844 |
| LogChunks raw log | 18 | 946,733 |
| LogChunks ci view (text_logs, strict, no retrieval) | 17 | 474,681 |

Notes
* A first run scored 0/96 because `MODEL="haiku"` did not start with `claude` and `ask()` fell through to the
  codex path (all answers empty -> "undecodable"). Fixed (`claude-haiku-5-5`); the 0/96 run was discarded.
* BFCL failures inspected: `wrong_func_name` cases are ambiguities between an item's OWN functions
  (e.g. `finish` vs `get_translation_nllb`), not caused by the added distractors; the router kept the gold function
  in all 24 probe items.
* Offline router recall on the pre-registered Meta slice (offset 0, n=100): gold function(s) in the top-6 for
  96/100 items; the other 4 need the `search_tools` recovery path.
