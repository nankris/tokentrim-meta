# 61 — Spend caps must hold under concurrency and retries (design, 2026-10-30)

- **Problem:** the v3 ledger checked caps after calls; with several workers/processes the sum of in-flight calls could
  overshoot a cap.
- **Fix:** `tokentrim/ledger.py` RESERVES the worst case of each call before sending it
  ((payload chars/3 + 64) x input price + max_tokens x output price), under an `fcntl` lock with atomic writes; the
  reservation is held across retries and then committed at the actual usage or released. Reservations of dead
  processes are ignored. Tested across threads and processes. All v4 Meta calls (benchmarks, smoke tests, capture)
  went through it: $5 per run, $12 for the job.
