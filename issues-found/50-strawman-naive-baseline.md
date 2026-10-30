# 50 — v2 naive baseline was a strawman (fixed in v3, 2026-10-30)

- **Symptom:** the v2 headline (`tokentrim-naive` −26.9% $ vs `baseline-naive`) compared against a client that
  re-serialized the tool JSON with random key order on *every* call. Few real clients do that, so the number overstated
  what cache_layout is worth.
- **Fix (v3):** `bench/real_meta.py` now has realistic, separately reported cache-busters:
  `baseline-ts` (fresh `Current time: <ISO> request_id: <uuid4>` on line 2 of the system prompt every call) and
  `baseline-tools` (tool list in hash-set order with per-tool dict-order nondeterminism, re-drawn only when the agent adds
  or removes a tool; all modes share the same add/remove schedule). `tokentrim` receives the naive client with both
  cache-busters. cache_layout gained `hoist_volatile_lines` (moves timestamp/UUID/request-id lines out of stable segments
  into one trailing metadata message) and name-sorted tool lists in `stable_json`.
- **Not measured:** the split of the tokentrim saving between cache_layout and eager prune (no layout-only mode in v3).
- **Status:** fixed; v2 strawman modes kept as `legacy-*` for reproducibility only.
