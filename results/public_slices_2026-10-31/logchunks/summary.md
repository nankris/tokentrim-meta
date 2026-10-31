### logchunks (TokenTrim system evaluation on a small public slice; not a leaderboard result)

run `pub-logchunks-20261031-203612`, model `muse-spark-1.3-contributor`, 120 items, 360 rows, errors 0, spend $1.0016, stopped_by_cap=False

| arm | n | pass (Wilson 95%) | diff vs baseline (paired Newcombe 95%) | NI at -5 pp | prompt tok/item | prompt-token saving (95% CI) | $/item | $ saving (95% CI) |
|---|---|---|---|---|---|---|---|---|
| baseline | 120 | 84/120 = 70% [61, 77] | - | - | 24,253 | - | 0.00280 | - |
| compression_only | 120 | 87/120 = 72% [64, 80] | +2.5 pp [-2.7, +7.8] (b_only 3, a_only 6) | yes | 24,498 | -1.0% [-1.1, -0.9] | 0.00280 | -0.2% [-0.9, 0.5] |
| ci_logs | 120 | 96/120 = 80% [72, 86] | +10.0 pp [+3.5, +16.6] (b_only 2, a_only 14) | yes | 23,986 | 1.1% [-12.4, 14.6] | 0.00275 | 1.7% [-9.5, 12.9] |
