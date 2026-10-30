# Live proxy smoke call (REAL, 2026-10-30 ~18:55 IST)

`python3 -m tokentrim.proxy --port 8787 --upstream-base-url https://api.meta.ai/v1 --default-model meta/muse-spark-1.3-contributor --ledger results/real_meta_2026-10-30_v3/spend_ledger.json --global-cap-usd 0.5`
(key loaded from the environment; never printed). The clients sent a dummy `Authorization` header, which the proxy ignores.

| Client | Request | Result |
|---|---|---|
| curl | system prompt with a `Current time:` line + "Reply with the single word: pong" | HTTP 200, `x-tokentrim-mode: tokentrim`, content `pong`, finish `stop`, usage prompt 60 / cached 0 / completion 193, $0.0000446 |
| openai-python (`OpenAI(base_url="http://127.0.0.1:8787/v1")`) call 1 | ~870-token system prompt, "What is 0+2?" | content `2`, finish `stop`, prompt 872 / cached 0 / completion 300 |
| openai-python call 2 | same prefix, "What is 1+2?" | content `3`, finish `stop`, prompt 872 / cached 0 / completion 359 (no cache hit on this pair; Meta hits are intermittent, issue 46) |
| openai-python with `tools=[...]` | | HTTP 400 `unsupported` (by design: the prototype does not forward tools yet) |
| openai-python with `stream=True` | | HTTP 400 `unsupported` (by design: no streaming yet) |

Total smoke spend: $0.00035 (recorded in the shared v3 ledger).

Verdict: a standard OpenAI client works through the proxy for plain text chat completions against the real Meta API. It is **not** a full drop-in for coding agents yet: tool calling and streaming, which Claude Code / Codex-style agents need, are rejected with HTTP 400.
