# SIMULATION — not real measurements

Scripted synthetic agent traces through a mock per-model prefix cache. No model was called.
Prices: `meta-verified` (meta/muse-spark-1.3 cheap, meta/muse-wonder-1.0 strong). Scenario: `realistic`. Tasks: 40 x 3 repeats (averaged per task). Seed 42. 95% percentile bootstrap over tasks, 2000 samples.
Pass outcomes are assumed probabilities, not test runs: {"strong": {"easy": 0.92, "medium": 0.85, "hard": 0.75}, "cheap": {"easy": 0.8, "medium": 0.62, "hard": 0.45}}; trim_penalty=0.0. min_cacheable_tokens=1024, cache writes charged: False.

| Mode | vs | $/task [95% CI] | $ saving % [95% CI] | Pass % | Pass diff pp [95% CI] | NI (-10pp) | $/pass | Cache hit | Cheap calls | Switches | Escalated |
|---|---|---:|---:|---:|---:|:-:|---:|---:|---:|---:|---:|
| baseline | — | 0.1552 [0.1523, 0.1585] | — | 98.3 | — | — | 0.1578 | 84.4% | 0.0/10.2 | 0.00 | 0% |
| tokentrim | baseline | 0.1368 [0.1337, 0.1403] | 11.9 [10.6, 13.3] | 96.7 | -1.7 [-4.2, 0.0] | yes | 0.1415 | 74.1% | 8.3/10.2 | 2.03 | 10% |
| tokentrim-cheapfirst | baseline | 0.0844 [0.0754, 0.0939] | 45.6 [40.1, 51.1] | 94.2 | -4.2 [-9.2, 0.0] | yes | 0.0896 | 82.7% | 9.6/10.4 | 0.37 | 37% |
| prune-only | baseline | 0.1552 [0.1523, 0.1585] | 0.0 [0.0, 0.0] | 98.3 | 0.0 [0.0, 0.0] | yes | 0.1578 | 84.4% | 0.0/10.2 | 0.00 | 0% |
| prune-eager | baseline | 0.1763 [0.1729, 0.1802] | -13.6 [-14.0, -13.3] | 98.3 | 0.0 [0.0, 0.0] | yes | 0.1793 | 78.0% | 0.0/10.2 | 0.00 | 0% |
| trim-only | baseline | 0.1372 [0.1352, 0.1396] | 11.6 [10.9, 12.3] | 98.3 | 0.0 [0.0, 0.0] | yes | 0.1395 | 86.4% | 0.0/10.2 | 0.00 | 0% |
| route-only | baseline | 0.1526 [0.1487, 0.1569] | 1.7 [0.4, 3.1] | 96.7 | -1.7 [-4.2, 0.0] | yes | 0.1579 | 71.5% | 8.3/10.2 | 2.03 | 10% |
| route-percall | baseline | 0.1526 [0.1487, 0.1569] | 1.7 [0.4, 3.1] | 96.7 | -1.7 [-4.2, 0.0] | yes | 0.1579 | 71.5% | 8.3/10.2 | 2.03 | 10% |
| route-cheapfirst | baseline | 0.0988 [0.0875, 0.1106] | 36.3 [29.4, 43.2] | 94.2 | -4.2 [-9.2, 0.0] | yes | 0.1049 | 80.5% | 9.6/10.4 | 0.37 | 37% |
| cheap-only | baseline | 0.0609 [0.0589, 0.0631] | 60.8 [59.6, 61.9] | 87.5 | -10.8 [-17.5, -4.2] | no | 0.0696 | 84.8% | 10.6/10.6 | 0.00 | 0% |
| baseline-naive | — | 0.5411 [0.5288, 0.5556] | — | 98.3 | — | — | 0.5503 | 17.8% | 0.0/10.2 | 0.00 | 0% |
| cache-only-naive | baseline-naive | 0.1552 [0.1522, 0.1585] | 71.3 [71.1, 71.5] | 98.3 | 0.0 [0.0, 0.0] | yes | 0.1578 | 84.4% | 0.0/10.2 | 0.00 | 0% |
| tokentrim-naive | baseline-naive | 0.1368 [0.1337, 0.1403] | 74.7 [74.4, 75.1] | 96.7 | -1.7 [-4.2, 0.0] | yes | 0.1415 | 74.1% | 8.3/10.2 | 2.03 | 10% |

Token means per task (uncached / cached / output):

- baseline: 23624 / 128551 / 1749; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- tokentrim: 37215 / 107238 / 1788; compacted outputs 2.2, prune commits 0.00, deferrals 5.28, cache-aware stays 0.00, cap trips 0.00
- tokentrim-cheapfirst: 26205 / 122217 / 1904; compacted outputs 2.4, prune commits 0.00, deferrals 5.48, cache-aware stays 0.00, cap trips 0.00
- prune-only: 23624 / 128551 / 1749; compacted outputs 0.0, prune commits 0.00, deferrals 5.22, cache-aware stays 0.00, cap trips 0.00
- prune-eager: 30013 / 106481 / 1749; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- trim-only: 19358 / 123812 / 1749; compacted outputs 2.1, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- route-only: 43647 / 110233 / 1788; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- route-percall: 43647 / 110233 / 1788; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- route-cheapfirst: 31777 / 127302 / 1904; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- cheap-only: 25016 / 140238 / 2025; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- baseline-naive: 125189 / 26987 / 1749; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- cache-only-naive: 23621 / 128543 / 1749; compacted outputs 0.0, prune commits 0.00, deferrals 0.00, cache-aware stays 0.00, cap trips 0.00
- tokentrim-naive: 37215 / 107238 / 1788; compacted outputs 2.2, prune commits 0.00, deferrals 5.28, cache-aware stays 0.00, cap trips 0.00
