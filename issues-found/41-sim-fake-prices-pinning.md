# 41 — First simulator draft: fake prices, pinned files, layout reshuffle

- **Symptoms (first Codex draft of `bench/simulate.py` and `layout.py`):**
  - It used `fake/cheap` and `fake/strong` prices instead of the Muse models.
  - It pinned every file, so prune had nothing to do.
  - The spend caps were $10 per task and $10k global.
  - The CLI printed `tasks=<repeats>`.
  - Trimming compacted every tool output except the latest, so each new output caused one history rewrite and a cache break.
  - `deterministic_segments` sorted `message` ahead of `tool_output`, which reshuffled the conversation on every call.
- **Root cause:** a spec gap plus a layout ranking bug.
- **Fix:** the simulator was rewritten.
  - It now uses the Muse prices, reference tracking (stale reads become unreferenced), $1/$120/15-step caps, `realistic` and `toy` scenarios, and cache-busting comparison modes.
  - Layout now moves only stable kinds.
  - Trim compacts at ingest, deterministically.
  - Regression tests: `tests/test_v2_cache.py` (`test_conversation_order_is_preserved`, `test_ingest_trim_is_byte_stable_across_steps`).
- **Status:** fixed. The Codex draft is kept at `/workspace/tokentrim-work/simulate_codex_v1.py`, outside the repo.
