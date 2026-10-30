# 48 — Trim and route barely engaged in the real run (REAL, 2026-10-30)

- **trim:** compacted 0 tool outputs. The real `unittest -v` logs for these task repos are 10–30 lines, below the 40-line
  compaction threshold. The simulation's 11.6% trim saving came from synthetic 60–180-test logs. Real large logs (pytest on a
  big repo, build output) are needed to measure trim.
- **route:** with Contributor as the only model, cheap and strong are the same model, so routing is a no-op in the main runs.
  The one price-tier routing run (Contributor for reads/edits, Standard for planning) cost $0.0218 and passed, but its
  `baseline-standard` reference was stopped by the per-task cap (see 47), so there is no like-for-like comparison. Routing
  between two SKUs of the same weights is a pricing choice, not a quality trade-off; the real test needs Wonder, which was
  outside this run's budget.
- **Status:** open.
