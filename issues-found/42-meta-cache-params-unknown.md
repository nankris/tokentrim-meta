# 42 — Muse cache parameters are unknown

- **Symptom:** dev.meta.ai lists cached-input prices and a `cached_tokens` usage field. It does not state a minimum cacheable prefix, block size, TTL, whether caches are shared across model versions, or any write charge.
- **Impact:** the simulator assumes OpenAI-like values (1024-token minimum, 128-token blocks, a TTL of 10 calls, no write charge). The sweep shows the minimum doesn't matter for agent-sized prefixes. A write premium would cut savings by about 2 pp.
- **Status:** partly measured on 2026-10-30 (REAL). Hits come in 128-token steps, the smallest observed hit was 5,745 tokens in agent traces (one 3,185-token hit in probes), no TTL could be pinned down because hits are intermittent (~31% of agent calls), and no cache-write charge is visible in `usage`. See [46](46-meta-cache-hits-intermittent.md).
