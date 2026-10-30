# 65 — Internal tool rounds were forgotten on the next client turn (found offline, 2026-10-31)

- **Found by:** the deterministic mock "oracle" agent on the new hard agentic set (`benchmarks/mock_agents.py`),
  MOCK upstream, zero spend. The oracle grepped the same compressed CI log 69 times in 24 tasks (about 3 per task)
  although one grep per task is enough.
- **Cause:** `retrieve_original` and `search_tools` are answered inside the gateway (internal rounds). The client
  never sees those messages, so on its next request the retrieved lines were gone from the conversation. The model
  had to retrieve again, or answer without the detail. It also changed the prompt prefix at that point, which
  breaks the provider cache.
- **Fix:** `Gateway._replay_internal` stores each internal exchange (assistant tool call + tool result) with the
  client-message position and a digest of the client prefix. On later requests in the same conversation it
  re-inserts them at the same place, byte-identical, and marks them as never-compress. If the client rewrites its
  history (digest mismatch), replay stops (fail safe). Test: `tests/test_hard_workload.py`.
- **After the fix (mock):** 23 greps in 24 tasks (one task's detail was already visible), oracle 24/24 in every arm.
- **Impact on earlier results:** the v4 agentic "full" arm (17 greps) ran before this fix; its numbers stay as
  measured. The v5 hard-set runs use the fixed gateway.
