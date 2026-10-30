# 53 — v3 benchmark budget, concurrency and statistics notes (2026-10-30)

- **Cost estimate was 5x too high:** the brief assumed ~$0.053 per task-mode (~$12 for 240 runs); Contributor runs
  actually cost ~$0.006–0.010 each. The harness pre-estimates at $0.012/run and reduces the task count to fit the cap
  (`--est-usd-per-run`, `--cap-usd`, `--run-cap-usd`), and never drops runs silently: cap-stopped runs are listed under
  `skipped` and excluded tasks are named in the report.
- **Concurrency:** runs execute in 8 threads. `SharedLedger` reserves each call's worst-case cost before sending
  (thread-safe, `flock`-protected file), so concurrent runs cannot overshoot the cap; the route pilot ran as a second
  process on the same ledger with its own $3 sub-cap.
- **Mock artifact:** `MockProviderClient` keeps one cache slot per model, so `--dry-run --workers >1` shows near-zero
  mock cache hits. Use `--workers 1` for dry runs. Real runs are unaffected.
- **Statistics:** repeats of one task are correlated, so pass rates are reported at run level and at task level
  (Wilson), and the paired pass difference both as a task-level paired bootstrap and a (conservative) Newcombe
  interval; non-inferiority at −10 pp is claimed only if both lower bounds clear it. A 100% pass rate gives a degenerate
  bootstrap interval [0, 0], which is why the Newcombe interval is shown.
- **Status:** documented.
