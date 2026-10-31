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
