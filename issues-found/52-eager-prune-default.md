# 52 — Prune default switched to eager, guarded by a pass-rate check (2026-10-30)

- **Why:** on the real Meta API the dollar break-even gate deferred every drop (it assumes a reliable cache; real hits
  are intermittent, issue 46), while eager pruning cut ~16% of prompt tokens with no pass loss on 6 tasks.
- **Change:** `TokenTrim(prune_checkpoints=False)` is the default; eager drops are latched so a dropped item never comes
  back (no prefix oscillation). The gate is opt-in (`prune_checkpoints=True`). `bench/simulate.py` pins the old gated
  default so the published SIMULATION tables stay reproducible.
- **Guard:** `bench/real_report_v3.py` flags every task where `tokentrim` passed fewer repeats than any baseline.
- **Risk:** eager pruning removes stale reads the model might need on harder, longer tasks; the 3-repeat, 20-task run is
  the only evidence so far.
- **Status:** done; see results/real_meta_2026-10-30_v3/summary.md for the guard output.
