# BFCL slice diagnostics (descriptive, after the pre-registered analysis)
* **Noise floor.** `compression_only` and `router_gated` (on 91/100 items) send the same request as baseline, apart
  from one extra internal tool and the session tag. Even so, each has 4 items that disagree with baseline
  (compression_only 2 vs 2; gated 3 vs 1). All of router_gated's disagreements are on items that were NOT routed.
  So about 4/100 discordant items is run-to-run nondeterminism at this n.
* **Router recall.** The gold function was outside the top 6 for 4/100 items (17-4-9, 22-4-14, 263-126-0,
  444-144-4). router_forced called `search_tools` on each, found the function, and **passed all 4**.
* **router_forced losses (5, vs 1 win):**
  * 948-198-0: also lost by compression_only and gated (noise).
  * 272-127-7 and 57-22-4: `wrong_count`. The model called two related tools where the gold answer has one.
  * 559-154-5: `missing_required`.
  * 748-169-3: value error after 2 searches.
  None of these is a case where the gold function was missing. The router-specific effect is at most about
  -3 to -4 pp and cannot be told apart from noise at n=100.
* Internal-tool leaks: 0 in every arm. search_tools: 15 calls on 11 items, forced arm only.
