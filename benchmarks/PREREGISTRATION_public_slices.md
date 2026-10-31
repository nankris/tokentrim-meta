# Pre-registration: public benchmark slices (2026-10-31)

Written and committed BEFORE any Meta call of this round. These are **TokenTrim system evaluations on a small
slice of public datasets, not leaderboard results**. They use muse-spark-1.3-contributor (Contributor mode: Meta may
use request content for training; the owner consented; the inputs are public datasets with no personal data).
Data sources, licenses and pinned versions are in `benchmarks/public/DATA_SOURCES.md`. Runner:
`benchmarks/public/run_public.py`. Validation already done at $0 Meta spend: grader-vs-official agreement
(BFCL 11,268/11,268), oracle/mock runs (all arms 100%), and a disjoint-item haiku probe
(`results/public_slices_2026-10-31/validation/`).

## Common
* Model `muse-spark-1.3-contributor`, max_tokens 8000, 6 workers, arm order shuffled per item (seed 7).
  Every call goes through `tokentrim.Gateway`; baseline = all modules off. `cache_prefix` is OFF in every arm, so
  arms differ only in the module under test.
* A run that errors (API error, timeout, malformed output) scores as a FAILURE in its arm. It is not dropped.
* Non-inferiority (NI): paired difference in pass rate (arm minus baseline) with a paired Newcombe 95% CI
  (`benchmarks/report_v5.newcombe_paired`). NI holds if the CI lower bound is > -5 pp. Superiority is not claimed.
* Efficiency: mean prompt tokens sent upstream per item (primary; cache-independent), and billed $ from the ledger
  pricing (input $0.10/M, cached $0.002/M, output $0.20/M). Both are reported as paired ratios vs baseline, with
  a bootstrap 95% CI (2,000 resamples over items, seed 1).
* Pairs are kept only where both arms have a row. If the cap stops a run, the partial result is reported as partial.

## Study 1: BFCL v3 `live_multiple`, tool routing
* Slice: `bfcl_slice(n=100, seed=20261031, offset=0)`, which is 100 items whose official ground truth passes the
  checker, shuffled. Each item's catalogue is AUGMENTED to 40 tools with distractor functions from other BFCL
  groups. Natural BFCL catalogues are small (1,051/1,053 items have 16 tools or fewer), so routing could not be
  tested on them. The augmented catalogue is a TokenTrim construction and is not the BFCL leaderboard setting.
* Metric: BFCL AST accuracy, using a faithful reimplementation of the official `ast_checker` (pinned gorilla commit;
  100% agreement on all ground truths and on the perturbation set; see `bfcl_checker_vs_official.json`). Internal
  calls (`search_tools`, `retrieve_original`) are dropped from the answer before grading. Any that leak are counted.
* Arms: `baseline`; `compression_only` (shipped tool_output preset; expected to do nothing, since there is no tool
  output); `router_gated` (schema_router plus the shipped confidence gate); `router_forced` (schema_router with the
  gate off, keep 6, plus search_tools recovery).
* H1 (key hypothesis): `router_forced` is NI vs baseline at -5 pp. H2: `router_gated` is NI. `compression_only` is
  reported descriptively.
* Also reported: offline router recall (gold function in the top 6 for 96/100 items, computed before the run),
  how often the gate routed, the search_tools count, internal leaks, and an error-type breakdown.

## Study 2: real CI logs, tool-output compression (substitute for SWE-bench Lite / Terminal-Bench)
* Why a substitute: the box has no Docker or Podman, so the SWE-bench and Terminal-Bench harnesses cannot run.
  Their main tool outputs are source files, which TokenTrim does not compress by design. LogChunks (Brandt et al.,
  MSR 2020; CC-BY-4.0) gives REAL failed Travis CI logs with human-labelled failure chunks. That is the kind of large
  tool output TokenTrim targets.
* Slice: `lc_slice(n=120, seed=20261031, offset=0)`, from the test split (repos hashed out of the dev split used to
  tune `text_logs`), with logs of 2k to 40k estimated tokens.
* Task: the model calls `get_build_log`, which returns the real cleaned log, then replies with JSON
  `{"failure_lines": [...]}` (at most 25 verbatim lines). There are at most 6 steps.
* Metric: pass if at least 50% of the labelled chunk's key lines appear in the answer (`logchunks.grade`).
  Grader caveat: a chunk from another build of the same repo would pass 258/797 times, because CI logs repeat
  boilerplate. So the metric is lenient toward answers that are plausible but not read from the log.
* Arms: `baseline`; `compression_only` (shipped default; text logs untouched, offline 0/797 compressed);
  `ci_logs` (opt-in `text_logs=True`, OFF by default; offline test-split retention 0.893 without retrieval;
  `retrieve_original` is available).
* H: `ci_logs` is NI vs baseline at -5 pp. `compression_only` is reported descriptively.
* Also reported: the compressed fraction, retrieve_original/grep counts, mean recall, and an exact-line metric.

## Spend rule
* Ledger at start: $6.5166 (job cap $7.94). The job cap passed to the runs is $9.01. That is ledger + $2.5 for this
  round at most, enforced by the fail-closed reserving ledger. Per-run caps: BFCL $0.80, LogChunks $1.50, and a
  2-item smoke test $0.05.
* Smoke test first: BFCL `--n 2 --offset 300` and LogChunks `--n 2 --offset 200`. Both are disjoint from the slices
  and the probe, and both are excluded from analysis. (Amended before any Meta call: the LogChunks pool has only
  214 logs, so offset 300 would be empty.) It is written to `results/public_slices_2026-10-31/smoke/`.
* On a cap stop or another blocker: stop, report the partial result, and do not raise the cap further.
