# REAL Meta Model API run (2026-10-30)

First real measurements for TokenTrim. Endpoint `https://api.meta.ai/v1/chat/completions`, model
`muse-spark-1.3-contributor` (data-sharing tier, $0.10 / $0.002 cached / $0.20 per 1M tokens), plus one small
`muse-spark-1.3` Standard check. No secrets are stored here; files hold token counts, dollars and labels only.

- **Total spend: $0.3166** (`spend_ledger.json`, SpendGuard global cap $0.50): cache probes $0.0367, benchmark $0.2800.
- `cache_probe*.json`: identical-prefix probes (min prefix, delay, repeats, cross-model, long waits).
- `bench_main.json` (baseline / tokentrim / tokentrim-eager), `bench_naive.json` (cache-busting client),
  `bench_route.json` (Standard vs routed): every call's `prompt_tokens`, `cached_tokens`, `completion_tokens`,
  reasoning tokens, finish reason, dollars and saver actions.
- `summary.md` / `summary.json`: per-task and aggregate tables (`python3 -m bench.real_report`).

Reproduce (spends real money; shares the ledger and cap):

```sh
set -a; . ~/.config/meta/env; set +a      # META_API_KEY / MODEL_API_KEY; never commit it
python3 -m bench.real_meta --dry-run --modes baseline,tokentrim --out /tmp/dry   # offline estimate first
python3 -m bench.real_meta --modes baseline,tokentrim,tokentrim-eager --tag main
python3 -m bench.real_meta --modes baseline-naive,tokentrim-naive --tag naive
python3 -m bench.real_report
```

Caveats: one pass per task/mode on 6 small tasks; pass/fail is real (model's JSON edit applied and the task's tests run)
but n is tiny. Cache hits are intermittent (issue 46), so billed-dollar deltas are noisy; the "$ if no cache hits" column
re-prices the same tokens without caching. System prompt, tool schemas, grep hits and two distractor modules are synthetic
padding (labelled in the prompt) to reach agent-sized contexts (~6–12k tokens per call).
