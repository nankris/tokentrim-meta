# v5.1 JSON extraction probe: claude-haiku-5-5

This is a TokenTrim system evaluation on a cheap CLI model, not Meta. Costs are **estimates** at Meta list price, from chars/4 (input $0.10/M, output $0.20/M), and include the RETRIEVE recovery turns.
Documents: 100 (generated, seed 9000+i; odd i have nested `meta` with decoy releases).

| View | Correct | 95% CI | Δ vs raw (pp, paired Newcombe) | Retrieves | Mean view tokens | Est. $ per correct answer [95% bootstrap] |
|---|---|---|---|---|---|---|
| raw | 99/100 | [95%, 100%] | - | 0 | 2991 | $0.316 [0.295, 0.338] |
| legacy_table | 100/100 | [96%, 100%] | +1.0 [-2.8, +5.4] | 0 | 1850 | $0.199 [0.181, 0.219] |
| structured | 100/100 | [96%, 100%] | +1.0 [-2.8, +5.4] | 0 | 2312 | $0.245 [0.230, 0.261] |
| structured_lossy | 100/100 | [96%, 100%] | +1.0 [-2.8, +5.4] | 0 | 839 | $0.098 [0.094, 0.103] |

($ per correct answer is shown per 1,000 correct answers.)

| View | Flat docs correct | Nested docs correct |
|---|---|---|
| raw | 49/50 | 50/50 |
| legacy_table | 50/50 | 50/50 |
| structured | 50/50 | 50/50 |
| structured_lossy | 50/50 | 50/50 |

## Reading this honestly
* On this probe, haiku answered correctly from **every** view, including the legacy table (100/100). It never
  needed RETRIEVE. So the model probe does **not** show an accuracy gain from the new format. Every Δ CI includes
  0, and raw's single miss (doc 50) is model noise.
* The reason for the change is the **structural** check: in 50/100 documents the legacy table lost or mixed key
  paths, so the answer could not be determined from the view. That is what broke ah43 on Muse Spark (issue 69).
  The structured views are 100/100 structurally sound.
* The cost case is clear. The structured lossy view cut the estimated cost per correct answer by 69% vs raw
  ($0.098 vs $0.316 per 1,000 correct answers) and by 51% vs the legacy table, with no measured accuracy loss.
  The conservative (lossless) view saves only about 23%, which is below the compressor's 0.8 max-ratio gate, so
  by default it is sent raw.
* These are estimated costs at Meta list price for a cheap CLI model, not measured Meta spend.
