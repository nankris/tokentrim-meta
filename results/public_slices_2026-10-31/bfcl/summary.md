### bfcl (TokenTrim system evaluation on a small public slice; not a leaderboard result)

run `pub-bfcl-20261031-202947`, model `muse-spark-1.3-contributor`, 100 items, 400 rows, errors 0, spend $0.3484, stopped_by_cap=False

| arm | n | pass (Wilson 95%) | diff vs baseline (paired Newcombe 95%) | NI at -5 pp | prompt tok/item | prompt-token saving (95% CI) | $/item | $ saving (95% CI) |
|---|---|---|---|---|---|---|---|---|
| baseline | 100 | 76/100 = 76% [67, 83] | - | - | 10,011 | - | 0.00107 | - |
| compression_only | 100 | 76/100 = 76% [67, 83] | +0.0 pp [-4.7, +4.7] (b_only 2, a_only 2) | yes | 10,133 | -1.2% [-1.2, -1.2] | 0.00108 | -0.6% [-1.4, 0.4] |
| router_gated | 100 | 74/100 = 74% [65, 82] | -2.0 pp [-6.7, +2.6] (b_only 3, a_only 1) | no | 9,438 | 5.7% [2.1, 9.6] | 0.00101 | 5.4% [1.9, 9.2] |
| router_forced | 100 | 72/100 = 72% [63, 80] | -4.0 pp [-9.4, +1.3] (b_only 5, a_only 1) | no | 2,532 | 74.7% [70.2, 78.0] | 0.00033 | 69.2% [64.2, 73.2] |
