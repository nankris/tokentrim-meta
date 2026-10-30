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
| 48 | [Trim and route barely engaged in the real run](48-trim-route-real-run-gaps.md) | Open |
| 49 | [Meta client stub did not match the real API](49-meta-client-stub.md) | Fixed |
