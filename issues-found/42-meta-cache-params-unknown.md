# 42 — Muse cache parameters are unknown

- **Symptom:** dev.meta.ai lists cached-input prices and a `cached_tokens` usage field. It does not state a minimum cacheable prefix, block size, TTL, whether caches are shared across model versions, or any write charge.
- **Impact:** the simulator assumes OpenAI-like values (1024-token minimum, 128-token blocks, a TTL of 10 calls, no write charge). The sweep shows the minimum doesn't matter for agent-sized prefixes. A write premium would cut savings by about 2 pp.
- **Status:** open. This needs credits and approval. Measure it with a few identical-prefix calls per model before the real benchmark.
