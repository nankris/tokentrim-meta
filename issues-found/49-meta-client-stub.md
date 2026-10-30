# 49 — Meta client stub did not match the real API (fixed 2026-10-30)

- **Symptoms in the old `tokentrim/clients/meta.py`:**
  - required `META_API_BASE_URL` (no default) and only read `META_API_KEY` (no `MODEL_API_KEY` fallback);
  - sent price-table names such as `meta/muse-spark-1.3-contributor` as the API model id (the API id has no `meta/` prefix);
  - no retry or back-off for 429/5xx; `content: null` (length-truncated reasoning) would have been passed through as `None`;
  - did not expose `finish_reason` or `reasoning_tokens`.
- **Fix:** default base URL `https://api.meta.ai/v1`; key from `META_API_KEY` or `MODEL_API_KEY` (never logged or written; not in
  `repr` or error messages); `meta/` prefix stripped; exponential back-off honouring `Retry-After` on 429/5xx; usage parsed
  from `prompt_tokens`, `prompt_tokens_details.cached_tokens`, `completion_tokens`; `last_meta` carries finish reason,
  reasoning tokens and request id. Unit tests in `tests/test_meta_client.py` use the real response shape.
- **Observed:** no 429s or retries in 300+ calls at the harness's sequential pace.
