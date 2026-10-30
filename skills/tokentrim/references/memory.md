# Long conversations: compact stale history, keep exact recovery

Compact only when the history is long AND the saving beats the cost (the summarizing call plus the cache
prefix you invalidate). Keep the last few turns verbatim.

State shape:
{"goal": "...", "constraints": [...], "decisions": [...], "completed": [...],
 "failed_attempts": [...], "open_tasks": [...], "facts": {"key": "latest exact value"}, "references": [...]}

Rules: copy exact values verbatim; when a value changed, keep only the latest and record the change in
`decisions`; never invent; store the transcript and give a reference id so exact wording can be recovered.
Reuse the same compacted block on later calls (cache-stable) and re-compact only after the tail grows again.
