### bfcl (TokenTrim system evaluation on a small public slice; not a leaderboard result)

run `pub-bfcl-20261031-202911`, model `muse-spark-1.3-contributor`, 2 items, 8 rows, errors 0, spend $0.0072, stopped_by_cap=False

| arm | n | pass (Wilson 95%) | diff vs baseline (paired Newcombe 95%) | NI at -5 pp | prompt tok/item | prompt-token saving (95% CI) | $/item | $ saving (95% CI) |
|---|---|---|---|---|---|---|---|---|
| baseline | 2 | 1/2 = 50% [9, 91] | - | - | 10,469 | - | 0.00109 | - |
| compression_only | 2 | 1/2 = 50% [9, 91] | +0.0 pp [-57.3, +57.3] (b_only 0, a_only 0) | no | 10,591 | -1.2% [-1.2, -1.1] | 0.00110 | -0.6% [-0.8, -0.4] |
| router_gated | 2 | 1/2 = 50% [9, 91] | +0.0 pp [-57.3, +57.3] (b_only 0, a_only 0) | no | 10,470 | -0.0% [-0.0, -0.0] | 0.00109 | 0.2% [0.1, 0.4] |
| router_forced | 2 | 1/2 = 50% [9, 91] | +0.0 pp [-57.3, +57.3] (b_only 0, a_only 0) | no | 3,026 | 71.1% [69.4, 72.7] | 0.00033 | 69.4% [67.0, 71.5] |
