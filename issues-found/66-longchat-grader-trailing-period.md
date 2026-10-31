# 66 — Long-chat "failures" were a grader artifact (trailing period), found 2026-10-31

- **Question (owner):** why did Skill only score 10/12 vs Baseline 11/12 on the v4 long-chat run?
- **Finding:** all 5 failed runs (baseline 1, skill 2, history 2) failed on exactly one field, `caterer`, and in every
  case the answer was `"Blue Plate Co."` vs the expected `"Blue Plate Co"`. The task text states the fact as
  "the caterer is Blue Plate Co. Please note it.", so the sentence period and the abbreviation period coincide; the
  model's answer is a correct reading. None of the failures was a memory error.
- **Re-grade (post hoc, v4 rows unchanged on disk):** with a trailing period ignored, every v4 long-chat arm is
  12/12 (baseline, skill, history, full). The published v4 numbers used the strict grader; the README now says so.
- **Fix:** `benchmarks/workloads.py::_norm` ignores a trailing period in string fields. This was changed **before**
  the v5 long-chat run and recorded as an amendment in `benchmarks/PREREGISTRATION_v5.md`.
- **Consequence:** the v4 long-chat run cannot tell the arms apart on quality at all (ceiling), and the skill's
  10/12 was not a skill effect.
