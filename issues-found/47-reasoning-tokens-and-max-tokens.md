# 47 — Reasoning tokens eat `max_tokens`; worst-case projections then trip caps (REAL, 2026-10-30)

- **Symptom:** `muse-spark-1.3(-contributor)` spends hidden reasoning tokens that count as `completion_tokens` and against
  `max_tokens`. In the benchmark 161,283 of 176,820 completion tokens (91%) were reasoning. "Reply with just: ok" used
  144–398 reasoning tokens.
- **Effect 1:** with `max_tokens=800`, 112 of 160 short "notes" calls ended `finish_reason: "length"` with empty `content`
  (recorded as "(empty)" in history). Edit calls with `max_tokens=8000` all finished `stop` (max 3,152 completion tokens).
- **Effect 2:** `SpendGuard` projects worst case = all input uncached + full `max_tokens` output. With the generous
  `max_tokens` the model needs, the projection for one Standard-tier edit (12k in + 8k out ≈ $0.049) tripped the $0.10 per-task
  cap in `baseline-standard` before its edit step, so that run is partial. The cap behaved as designed.
- **Status:** client now records `finish_reason` and `reasoning_tokens`. Open: set read/notes `max_tokens` ≥ 1,500, add an
  optional reasoning-effort parameter if Meta exposes one, and let the guard use a calibrated output estimate (e.g. p95 of
  observed completion tokens) instead of `max_tokens`.
