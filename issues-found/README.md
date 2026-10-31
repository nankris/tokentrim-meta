# Issues found

One markdown file per issue group, named `NN-short-slug.md`.
Each file: symptom, repro, root cause (if known), fix/status.

| # | File | Status |
|---|------|--------|
| 10 | [Python command availability](10-python-command.md) | Documented; verified with Python 3.13.5 via python3 |
| 11 | [Bootstrap float comparison](11-bootstrap-float-comparison.md) | Fixed test tolerance |
| 20 | [Bench tasks: `python` command absent](20-python-command.md) | Worked around: validate.py provides a temporary `python` alias for check commands |
| 30 | [Offline checker and metadata](30-real-checker.md) | Fixed; hostile-code sandboxing remains outside scope |
| 40 | [Codex sandbox blocks loopback sockets](40-codex-sandbox-loopback.md) | Environment-only; test passes on box |
| 41 | [First simulator draft: fake prices, pinning, layout reshuffle](41-sim-fake-prices-pinning.md) | Fixed; regression tests added |
| 42 | [Muse cache parameters unknown](42-meta-cache-params-unknown.md) | Partly measured 2026-10-30 (see 46) |
| 43 | [Model switches re-bill context](43-model-switch-cache-loss.md) | Partly addressed (switch check, cheap-first); default router open |
| 44 | [CodeRescue paper withdrawn](44-coderescue-withdrawn.md) | Documented; not cited |
| 45 | [Simulator cannot measure quality loss](45-sim-quality-model-weak.md) | Open by design; needs real runs |
| 46 | [Meta cache hits are intermittent](46-meta-cache-hits-intermittent.md) | Open; REAL measurement 2026-10-30 |
| 47 | [Reasoning tokens vs max_tokens and spend caps](47-reasoning-tokens-and-max-tokens.md) | Open; client records finish/reasoning |
| 48 | [Trim and route barely engaged in the real run](48-trim-route-real-run-gaps.md) | Open; trim dropped from headline, route see 54 |
| 49 | [Meta client stub did not match the real API](49-meta-client-stub.md) | Fixed |
| 50 | [v2 naive baseline was a strawman](50-strawman-naive-baseline.md) | Fixed in v3 (realistic cache-busters) |
| 51 | [Proxy scope: no tools or streaming yet](51-proxy-scope.md) | Smoke call passed; scope open |
| 52 | [Prune default switched to eager](52-eager-prune-default.md) | Done; pass-rate guard in report |
| 53 | [v3 benchmark cost, concurrency and stats notes](53-benchmark-cost-and-stats.md) | Documented |
| 54 | [Route pilot: Spark-first never escalated](54-route-pilot.md) | Open |
| 55 | [Moving volatile lines to a trailing message does not restore real Meta cache hits](55-volatile-move-breaks-real-cache.md) | Open |
| 56 | [Cheap models only reachable through CLIs](56-cheap-models-cli-only.md) | Documented; used as probes |
| 57 | [Log compression dropped the task's line (cheap probe)](57-compression-dropped-task-line.md) | Fixed (query-aware) |
| 58 | [Over-retrieval of compressed outputs on Meta](58-over-retrieval-on-meta.md) | Fixed before frozen run |
| 59 | [PostToolUse hook cannot shrink tool output](59-posttooluse-cannot-replace-output.md) | Fixed (pipe filter) |
| 60 | [Proxy log lines lost in background; buffered streaming; global lock](60-proxy-log-flush.md) | Fixed / scope noted |
| 61 | [Reserving spend ledger for concurrency and retries](61-reservation-ledger.md) | Done |
| 62 | [Agentic benchmark quality ceiling](62-agentic-ceiling-effect.md) | Open |
| 63 | [History compaction raised real cost (+25%)](63-history-compaction-costs-more.md) | Disabled by default |
| 64 | [Plain chat: cache barely hit; skill cut output 30%](64-chat-cache-and-skill.md) | Documented |
| 65 | [Internal tool rounds forgotten on the next turn](65-internal-rounds-not-replayed.md) | Fixed |
| 66 | [Long-chat failures were a trailing-period grader artifact](66-longchat-grader-trailing-period.md) | Fixed before v5 |
| 67 | [Luna probe stopped early more on compressed inputs (n.s.)](67-luna-probe-early-stop.md) | Open (watch) |
