# 74: CI-log compression improved accuracy, but retrieval cancelled the token saving

**Found:** public slices round, measured LogChunks run (2026-10-31). **Status:** Open. `text_logs` stays OFF by default.

With `text_logs=True` on 120 real failed Travis CI logs (muse-spark-1.3-contributor), the pass rate was 80% vs 70%
for baseline (+10.0 pp, paired Newcombe 95% [+3.5, +16.6]; NI holds). But mean prompt tokens were 23,986 vs 24,253
(1.1% saving, 95% [-12.4, 14.6]). The model called `retrieve_original` on 97 of the 114 compressed logs (168 greps,
36 full retrieves; 3.8 calls per item vs 2.0). Each extra turn re-sends the conversation, and full retrieves cost
about 1.7x baseline. On the 17 items with no retrieval, tokens fell 79%.

Next steps (not done; need a decision): make retrieved greps replace the compressed message instead of appending
turns, steer away from full retrieves (as in issue 58), or return grep hits inline at compression time. Re-measure on
a fresh slice: the remaining test-split logs (offset 144 and up) or the dev split. Keep this slice for confirmation only.
