# LogChunks slice diagnostics (descriptive, after the pre-registered analysis)
ci_logs, split by what the model did after seeing the compressed log (n=120; tokens are mean prompt tokens per item):

| ci_logs behaviour | items | baseline tok | ci_logs tok | baseline pass | ci_logs pass | ci calls |
|---|---|---|---|---|---|---|
| compressed, no retrieval | 17 | 19,085 | 4,022 | 10 | 12 | 2.0 |
| grep only (`retrieve_original` with pattern) | 61 | 24,837 | 18,843 | 39 | 45 | 4.2 |
| full retrieve | 36 | 22,564 | 38,903 | 29 | 33 | 4.1 |
| not compressed (log below threshold) | 6 | 43,098 | 43,342 | 6 | 6 | 2.0 |

* The accuracy gain (+10 pp) shows up in every compressed group. The likely reason is that the head/tail-plus-error
  view puts the failure lines in front of the model. Mechanism not proven.
* The token saving is cancelled out by retrieval. 97/114 compressed items retrieved or grepped. Each extra turn
  re-sends the whole conversation, and full retrieves cost about 1.7x baseline. Net prompt-token saving is 1.1%
  [-12.4, 14.6], which is not significant (see issue 74).
* There were no harness errors and no empty answers. Grader caveat: same-repo chunks pass 258/797, so pass rates are
  lenient (see the pre-registration).
