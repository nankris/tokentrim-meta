# 57 — Log compression dropped the one line the task asked about (cheap probe, 2026-10-30)

- **Symptom:** haiku probe, task ag00 asks "which worker handled request r-649". The CI-log compressor kept errors and
  edges but dropped that DEBUG line; the model guessed instead of calling `retrieve_original` (score 0.875 vs 1.0 raw).
  On ag03 the model did retrieve and was correct.
- **Fix:** query-aware protection. `task_terms()` extracts identifier-like tokens (letters + digits, e.g. `r-649`,
  `ci-4000`) from the user messages BEFORE each tool message (stable per message, so the compressed text, and the cache
  prefix, do not change later). Lines containing them are kept verbatim. Re-probe: 4/4 tasks correct, no retrieval.
- **Status:** fixed; unit test `QueryAwareAndGrepTest`.
