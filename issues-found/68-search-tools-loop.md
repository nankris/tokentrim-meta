# 68: Full arm looped on search_tools after a wrong dependent argument (ah50)

- **Where:** v5 Meta run B, agentic_hard task ah50, arm `full`. This is a REAL run.
- **Observed:** the run scored 0.40, with 52 calls, $0.0429 (about 4x the baseline's $0.0101), 1,452 s wall time
  and 7 retries. All three dependent tool calls were eventually right, but there was no final answer, so all 6 fact
  checks failed.
- **Sequence:**
  1. get_ci_log returned compressed output (15,235 -> 854 tokens).
  2. `retrieve_original(pattern="q-1067")` returned the correct line `... accepted trace_ref=tr-498a8e ...`.
  3. The model then called `inspect_spans(span_root="q-1067")`, using the request id instead of the trace ref, and
     got "no spans recorded".
  4. It then made 37 `search_tools` calls. Every one returned "restored 0 tool(s): none new", because the needed
     tools were already visible after the first search.
  5. Interleaved were list_files and a full retrieve_original. It finally made the correct calls, but the 14-turn
     budget ran out before an answer.
- **Cause:** the model's wrong argument choice is outside TokenTrim. TokenTrim made it worse in two ways:
  - "none new" search results do not tell the model to stop searching, and internal rounds do not count against
    any loop budget.
  - The tool list kept changing (8 -> 11 ... 18 schemas), which broke the cache prefix.
- **Proposed fix (NOT applied in v5, which is a validation round with frozen code):**
  - After 2 consecutive "none new" results, answer search_tools with an explicit "all tools matching your need are
    already available: <names>; do not search again".
  - Count internal rounds toward the loop guard.
- **Status:** Open (fix proposed).

## Fix (v5.1, offline, zero spend)

`tokentrim/transforms.py::_search_tools` now has a per-conversation loop guard:

* A search is *unproductive* when it restores no new tool or repeats an earlier (normalised) query.
* The guard trips after `search_loop_threshold=2` unproductive searches in a row, **or** after
  `search_max_without_evidence=3` searches with no client tool result between them. The second rule matters because
  in ah50 several searches "restored" irrelevant tools (hr_time_off, get_weather), so they never counted as empty.
* When it trips, the full catalogue is restored in the same round, the router is disabled for the rest of the
  conversation (`router_disabled`; later requests send every client tool), and the model gets an actionable note.
  The note lists every tool, says not to search again, and suggests the earlier failure was an argument problem
  ("reuse identifiers exactly as they appear in earlier tool results"). Any later search_tools call is refused
  cheaply, without searching.
* Legitimate retries still work. A new client tool result resets both counters, so the same query after a state
  change, or a search after using a restored tool, goes through normally.

Regression: `tests/test_search_loop_guard.py` (5 tests). The mock `flail_policy` replays ah50: it passes the
request id to inspect_spans, gets "no spans recorded", then cycles the v5 queries.

| | search_tools calls | score |
|---|---|---|
| guard on (defaults) | 3 | 1.0 |
| guard off | 49 | 0.2 |

These are mock-upstream results, not model results.

Residual (noted, not fixed): when `max_internal_rounds` is exhausted, an internal tool call can pass through to the
client harness ("search_tools has no data for this incident"). With the guard, at most 3 searches run before
recovery, so this path is now hard to reach.

Status: **Fixed (v5.1)**; to be confirmed on the fresh v5.3 benchmark.
