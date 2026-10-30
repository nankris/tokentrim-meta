# 46 — Meta prompt cache hits are real but intermittent (REAL, 2026-10-30)

- **Symptom:** `usage.prompt_tokens_details.cached_tokens` is returned and is sometimes non-zero, but identical prefixes often get 0.
  - Isolated probes (`bench/meta_cache_probe.py`, one ~3.3k-token system message + short user turn): 1 hit in ~30 repeat calls,
    across immediate repeats, 3–150 s waits and 8 back-to-back repeats (`results/real_meta_2026-10-30/cache_probe*.json`).
  - Multi-turn agent traces (`bench/real_meta.py`): 78 of 255 calls (31%) had cached tokens; 26% of all prompt tokens were cached.
    Hits are not monotonic: a call can hit 10,993 tokens and the next call, with a strictly longer identical prefix, hit 0.
  - Hit sizes come in coarse steps (5,745, 6,129, 6,385, 6,641, 6,769, 10,993, 11,377 …, i.e. 128-token steps). The smallest
    benchmark hit was 5,745 tokens (system + tool-schema messages); a ~3k-token system message alone never hit in the
    benchmark (naive mode, 0 hits in 6 runs).
  - Standard `muse-spark-1.3` also returned hits (2 of 7 calls). A prefix warmed on Contributor was not observed as cached on
    Standard (and vice versa) in the cross-model probe, but with this hit rate that is weak evidence.
- **Likely cause (unverified):** per-replica caches behind a load balancer, so a hit depends on landing on the same replica.
- **Impact:**
  - Billed-dollar comparisons on a single pass are dominated by cache-hit luck. `summary.md` therefore also reports
    "$ if no cache hits", which re-prices the same billed tokens with zero cached tokens.
  - The prune break-even gate (`CostModel.breakeven_compaction`) assumes a reliable cache. Under the observed ~30% hit rate it
    deferred every drop (net −$0.0001…−$0.0004 predicted), while committing them eagerly cut prompt tokens 15.7% with 6/6 passes.
- **Status:** open. Next steps: make the cache model probabilistic (expected hit rate as a price input, default ~0.3 for Meta)
  and re-check whether caching gets more reliable with a `user`/session field or longer stable prefixes.
