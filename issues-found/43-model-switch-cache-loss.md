# 43 — Model switches re-bill the context (per-model caches)

- **Finding (SIMULATION):** the heuristic router sends planning and complex edits to Wonder. Each upgrade re-bills the full context uncached on Wonder, so `route-only` saves just 1.7%. `route-cheapfirst` (Spark first, sticky escalation on visible signals) saves 36.3%. Stacked with the other savers it saves 45.6%, with a pass difference of −4.2 pp [−9.2, 0.0]. That only just clears the −10 pp non-inferiority margin.
- **What was built:**
  - `routing.cache_aware_switch` gates downgrades.
  - `CheapFirstRouter` is an alternative router.
  - The middleware tracks the prefix it last sent to each model, to estimate how warm each model's cache is.
- **Open:**
  - Under Muse prices the downgrade check never bound. That is expected given the 4.7× output-price gap.
  - Deciding the default router needs real pass rates.
  - On escalation, a compact hand-off to Wonder (rather than re-sending the full history) isn't built yet.
