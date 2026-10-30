# 64 — Plain chat: stable prefix barely hit Meta's cache; the skill cut output tokens (REAL, 2026-10-30)

- **Measured (24 sessions x 4 questions, ~2.5k-token system prompt; baseline puts a per-request timestamp and
  request id at the top):** removing the volatile lines (`cache` arm) raised calls with cached tokens only from 0% to
  3% and saved +1.8% [-1.6, +4.7] (not significant). Meta's cache is intermittent for short (~2.5k) prefixes (issue 46).
- The skill-only arm saved +3.9% [+1.4, +6.2]: output tokens -30% (4,319 -> 3,032 per session), median latency per
  session 41.8 s -> 29.6 s, while input rose ~490 tokens per call (the skill text). Full: +5.1% [+2.8, +7.4]. 24/24
  correct in every arm.
- **Status:** documented. Dollar savings in plain chat are small because the input side is already cheap.
