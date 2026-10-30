# 62 — Agentic benchmark has a quality ceiling (REAL, 2026-10-30)

- **Finding:** all 5 arms passed 24/24 agentic tasks. That shows no observed quality loss, but it cannot prove
  non-inferiority at a 10-point margin: with 24/24 vs 24/24 the Newcombe 95% interval of the pass-rate difference is
  about +-14 points. The tasks are graded on exact fields, but they are easy for this model.
- **Status:** open. Report "no observed loss (24/24 in every arm)", not "non-inferior". Harder tasks (more
  distractors, multi-hop lookups, values only in omitted regions) are the next step.
