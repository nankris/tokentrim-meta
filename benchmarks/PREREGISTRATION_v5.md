# v5 pre-registration: hard agentic set + long chat without compaction

Written and committed **before any Meta API call of round v5** (2026-10-31, Asia/Calcutta). Commit hash and time are
in git history. Anything added after the runs start is marked "AMENDMENT" with its time and reason.

These are evaluations of the **TokenTrim system** (skill, hooks, gateway) on synthetic tasks. They are not
evaluations or rankings of any model, and no comparison with other providers' models is made or implied.
Model: `muse-spark-1.3-contributor` (Contributor tier: Meta may use request content for training; every task is
synthetic and contains no real or personal data).

## Primary hypothesis (H1, non-inferiority of task success)
- **Workload:** `agentic_hard` (`benchmarks/workloads_hard.py`): 4-hop root-cause tasks with a deep unhandled
  exception among decoys, a detail that compression hides (needs `retrieve_original`), two needed tools that the
  BM25 router deliberately does not select (needs `search_tools`), dependent tool arguments, and a read-only rule.
- **Endpoint:** task success = all 10 checks pass (6 exact facts, 3 required tool executions with the correct
  dependent argument, no side-effecting tool call). Grader: `grade_hard`, validated offline with mock agents
  (oracle 24/24 in every arm, lazy 0-1/24 when recovery is needed, guess 0/24).
- **Comparison:** TokenTrim **Full** (skill + cache prefix + tool-output compression + schema router) vs
  **Baseline** (pure pass-through), paired on identical tasks.
- **Margin:** **5 percentage points.** Full is called non-inferior on task success only if the **lower bound of the
  two-sided 95% CI** of (success_Full - success_Baseline) is **greater than -5 pp**. Method: Newcombe (1998) method 10
  for paired proportions with continuity-corrected phi (`bench.stats.noninferiority_paired`, checked against
  published worked examples).
- **Known limit, stated in advance:** even with zero failures in both arms, this lower bound is -13.8 pp at n = 24,
  -7.4 pp at n = 48, -5.1 pp at n = 72 and -3.8 pp at n = 96. Non-inferiority at a 5 pp margin therefore needs
  n >= 80 paired tasks and very few Full-only failures.
- **Sample size:** n = 96 paired tasks (indices 0-95), unless the cost pilot below projects that the whole round
  would exceed the $5 round cap; then n = the largest multiple of 24 that fits, fixed before the main run and
  recorded as an AMENDMENT. If n < 80, H1 cannot be confirmed, and the report will say so.

## Secondary analyses (reported with CIs, no confirmatory claim)
- On tasks 0-47 (or 0-23 if the budget is short): Skill only, Full without router (`full_no_router`),
  tool_output only, schema_router only, each vs Baseline. Cost per task and per successful task (paired bootstrap
  95% CI, 2,000 resamples), pass rate with the paired Newcombe CI, token categories, truncation.
- **Long chat** (`longchat`, tasks 0-23): Baseline, Skill only, and **Full without history compaction**
  (`full_no_history` = skill + cache prefix), the configuration recommended after issue 63. Same statistics. With
  24 tasks no non-inferiority claim is possible (see limit above).
- **Skill 10/12 vs baseline 11/12 (v4 long chat):** inspect the failing fields and answers of those runs and of the
  new runs, and report what failed and whether it is consistent with the skill.

## Procedure
- Cheap first: graders and tasks validated on the deterministic mock upstream; quality probes with
  `claude-haiku-5-5` (`claude -p`) and `gpt-6-luna` (`codex exec`), raw vs compressed tool outputs, before any Meta call.
  These CLI models are probes only; they cannot be the gateway upstream.
- Cost pilot: tasks 100-103 of `agentic_hard`, all 6 arms; excluded from every analysis.
- Arms run interleaved in random order per task (seed 7), unique session tag per (task, arm), 2 warm-up calls
  excluded, `max_tokens` 16,000, at most 14 model turns per task.
- Spend: reserving ledger, per-run cap $5, job cap = $1.3456 already spent + $5 round cap = **$6.35**. A run
  that hits a cap stops; partial results are reported as partial.
- Every number reported comes from recorded API usage; nothing is projected.

## AMENDMENT 1 (2026-10-31 ~05:40 IST, before any v5 Meta call)
The v4 long-chat failures were all `"Blue Plate Co."` vs `"Blue Plate Co"` (issue 66). The string grader now
ignores a trailing period. This applies to every v5 run; the v4 published numbers are left as measured, and a
post-hoc re-grade is reported separately and labelled as such.
