# 60 — Proxy explanation lines lost when run in the background (2026-10-30)

- **Symptom:** during the live adapter smoke test the proxy log contained only the start line; per-request
  `[tokentrim] ...` lines were buffered and lost on SIGTERM.
- **Fix:** the server CLI logs with `flush=True`. Re-captured on a real call (`blog-assets/proxy_explanations_terminal.png`).
- **Also noted (scope):** streaming responses are buffered (whole upstream response, then SSE), and one global lock
  serializes gateway calls in the proxy. Fine for one local agent; not a multi-tenant server.
