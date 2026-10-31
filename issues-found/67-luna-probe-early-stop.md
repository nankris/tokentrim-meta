# 67: gpt-6-luna probe stopped early more often on compressed inputs (not confirmed)

- **Where:** v5 cheap probe (`benchmarks/cheap_probe_hard.py`), compressed arm, gpt-6-luna. This is a CLI probe,
  not the gateway.
- **Observed:** 20/24 compressed vs 23/24 raw. Paired diff -12.5 pp, 95% CI [-32.3, +7.2].
  - Three failures answered before the dependent `inspect_spans` / `open_artifact_manifest` calls.
  - One (ah00) answered on turn 1 without any tool call.
  - No failure was caused by an unrecoverable compressed fact.
- **Check:** re-ran the 4 failing episodes with transcripts saved. All 4 passed.
- **Assessment:** consistent with stochastic early stopping, and not significant. The compressed prompt is
  shorter, and a possible cue to stop early would be the "[compressed ...]" marker. That cannot be excluded at
  n=24.
- **Action:** none in code. The Meta run measures the real gateway path, where failures are broken down by check.
- **Status:** Open (watch).
