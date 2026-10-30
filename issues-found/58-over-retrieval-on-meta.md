# 58 — Meta's model re-fetched compressed outputs it did not need (pilots, 2026-10-30)

- **Symptom (REAL, pilot n=2-3):** with tool-output compression on, the model called `retrieve_original` on the CI log
  in almost every task, sometimes 2-4 times per task (the internal retrieval is invisible to the client, so the next
  call showed the compressed view again). The tool_output arm cost MORE than baseline in 2 of 3 pilot tasks.
- **Causes and fixes:**
  1. A footer saying "if a value is missing, retrieve instead of guessing" invited retrieval -> neutral wording.
  2. After one full retrieval the same output was compressed again -> the ref is remembered per conversation and that
     tool result is sent raw from then on.
  3. Full retrieval is expensive -> `retrieve_original` gained an optional `pattern` (grep: matching lines with line
     numbers, max 200).
  4. The compressed log did not say what was removed -> it now ends with "omitted lines by level: INFO n, DEBUG m;
     every WARN/ERROR/FATAL line and every task-identifier line is shown above".
  5. Plain text (source files the model asked for) is no longer compressed by default.
  6. Workload artifact: the synthetic CI log said "pytest exited with code N" but contained no pytest summary, so the
     model went looking for one. Real CI logs contain the summary; the generator now adds it (same for all arms).
- **Status:** fixed before the frozen benchmark. In the final agentic run (n=24): 8 full retrievals in the
  tool_output arm, 17 greps and 0 full retrievals in the full arm, no quality loss.
