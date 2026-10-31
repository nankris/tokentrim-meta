## agentic_hard: TokenTrim system evaluation (synthetic tasks, REAL calls)

| arm | n | pass | $/task | saving vs baseline [95% CI] | success diff vs baseline [95% CI] | NI (-5 pp) | $/success |
|---|---|---|---|---|---|---|---|
| baseline | 96 | 96/96 | $0.00856 | - | - | - | $0.00856 [0.00825, 0.00886] |
| compression_only | 96 | 96/96 | $0.00362 | +57.7% [+55.0, +60.1] | +0.0 pp [-3.8, +3.8] | yes | $0.00362 [0.00345, 0.00380] |
| guarded_full | 96 | 96/96 | $0.00428 | +50.0% [+43.6, +55.2] | +0.0 pp [-3.8, +3.8] | yes | $0.00428 [0.00384, 0.00480] |
