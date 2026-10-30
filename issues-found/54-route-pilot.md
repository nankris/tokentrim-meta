# 54 — Route pilot: Spark-first never escalated (REAL, 2026-10-30)

- **Run:** 3 tasks (t07 easy, t21 medium, t15 hard), one pass each. `pilot-wonder` = Wonder for every call, no savers.
  `pilot-sparkfirst` = all savers + `CheapFirstRouter` on Standard Spark with sticky escalation to Wonder.
- **Result:** Wonder $0.954, 3/3 pass; Spark-first $0.288, 3/3 pass (−70%). Spark-first **never escalated**: every
  edit passed on the first attempt with Spark.
- **Meaning:** this corpus is easy enough that Spark solves it, so the pilot says "Wonder is not needed here", not
  "routing works". The escalation path is untested on real data, and the saving mixes routing with prune/layout.
- **Decision:** routing stays out of the headline; the $30 Wonder test was not run. A useful routing test needs tasks
  where Spark fails visibly at least sometimes.
- **Status:** open.
