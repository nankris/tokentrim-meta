# 55 — Moving volatile lines to a trailing message does not restore real Meta cache hits

**Found:** 2026-10-30, v3/v3b REAL runs (`results/real_meta_2026-10-30_v3/summary.md`).

**Evidence.** On the same naive client (a timestamp plus request id on system line 2, and set-ordered tools), with cache_layout alone:
- `layout-move` hit the cache on 3% of calls and was 10.4% [7.6, 13.5] dearer than the clean client.
- `layout-drop` hit on 12% of calls, the same as the clean client, and was 1.6% [−1.9, +5.0] dearer, which is not significant.

Even the clean client got 0/60 hits on the calls right after a tool-set change. A partial prefix match was never billed as cached there.

**Cause (inferred).** Meta seems to bill a cache hit only when the new request extends an earlier request. A trailing metadata message sits at the end of call N, and call N+1 puts new history in that position, so the requests never extend each other. `MockProviderClient` matches any common prefix in 128-token blocks, which is why the offline tests passed.

**Status.** The default stays `volatile_policy="move"` (lossless), and the README reports both.

**Options:**
1. Default to `drop` (lossy; the model loses the timestamp).
2. Append-only placement: keep each turn's volatile message in history and append the new one.
3. Make the mock require extension of an earlier request.

None of these combined with eager prune has been measured.
