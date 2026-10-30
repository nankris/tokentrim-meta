# 51 — Proxy: works for plain chat completions; tools and streaming not supported (REAL smoke call, 2026-10-30)

- **Result:** `python3 -m tokentrim.proxy --upstream-base-url https://api.meta.ai/v1` served real completions to curl and
  to the official `openai` Python client (`base_url=http://127.0.0.1:8787/v1`); see
  `results/real_meta_2026-10-30_v3/proxy_smoke.md`.
- **Gaps:** `tools`/`tool_choice`, `stream: true`, images and sampling parameters are not forwarded. Requests with
  `tools` or `stream` now get HTTP 400 instead of being silently changed. Coding agents (Codex, Claude Code) need tool
  calling and streaming, so the README no longer calls the proxy a "drop-in" for them.
- **Earlier bugs fixed while testing:** the proxy ignored the request `model`, always reported `finish_reason: stop`, and
  labelled every real response `data_kind: SIMULATION`. The upstream base URL is now configurable
  (`--upstream-base-url`, `TOKENTRIM_UPSTREAM_BASE_URL`; HTTPS, or plain HTTP only for loopback).
- **Planned:** Anthropic Messages (`/v1/messages`) and OpenAI Responses (`/v1/responses`) front-ends; tool/stream pass-through.
- **Status:** open (scope), smoke call passed.
