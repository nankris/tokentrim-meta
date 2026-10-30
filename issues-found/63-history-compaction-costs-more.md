# 63 — History compaction raised real cost on long conversations (REAL, 2026-10-30)

- **Measured (longchat, 12 conversations x 25 calls, paired):** the `history` arm cost **+25.4% more** than baseline
  (95% CI of the saving: -37.9% to -12.0%) at similar quality (10/12 fully correct vs 11/12 for baseline; mean field score 0.979 vs 0.990).
  Full (skill + cache prefix + history) was -5.7% [-28.3, +11.8], i.e. no measurable saving.
- **Why:** Meta's cache hit well in this workload (63% of baseline calls had cached tokens, 55% of prompt tokens
  were cached at 2% of the input price). Compaction rewrites the early history, so cache hits fell to 36% of calls;
  each compaction is an extra model call with reasoning output; and the model called `retrieve_original` on the
  compacted transcript in about a third of the conversations. The cost guard skipped 115 candidate compactions, but
  its hit-rate estimate (from the conversation so far) was too optimistic about the ones it allowed.
- **Decision:** history compaction stays OFF by default and is not part of the recommended Full configuration. It
  may pay only for much longer contexts (tens of thousands of tokens) or providers without a cheap cache.
