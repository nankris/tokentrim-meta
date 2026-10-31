# 71: Shipped tool-output compression did nothing on real CI logs

**Found:** public slices round (2026-10-31), offline on LogChunks. **Status:** Mitigated (opt-in `text_logs`, OFF by default).

## Problem
The shipped `ToolOutputCompressor` compressed **0 of 797** real Travis CI logs (LogChunks, CC-BY-4.0). Its text
path targets the structured outputs from our synthetic workloads (JSON, tables, repeated lines). Real CI console
logs are mostly unique lines (install output, compiler and test logs), so every heuristic declined to compress them.
The large tool output that matters most for coding agents was left untouched.

## Change
Added `compress_ci_text` (keep the head and tail, plus lines matching error, failure or task terms with ±2 lines of
context; keep the original in the store for `retrieve_original`). It is enabled with `GatewayConfig(text_logs=True)`.
Parameters were tuned on the dev split only (repo-hashed). Offline results: dev retention of the labelled failure
chunk was 0.934 at a 0.211 size ratio; test retention was 0.893 at 0.252, with 324/347 logs compressed.

## Remaining risk
Without retrieval, the forced compressor drops the failure chunk in about 11% of test logs. The measured Meta run
(`results/public_slices_2026-10-31/logchunks/`) shows whether the model's recovery closes that gap. Keep the option
OFF by default until that is shown.
