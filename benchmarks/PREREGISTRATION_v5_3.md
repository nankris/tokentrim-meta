# Pre-registration: v5.3 confirmatory benchmark (TokenTrim system evaluation)

Written and committed **before any Meta call of v5.3**. Code under test: the commit that adds this file. Any
later change to the analysis is reported as a deviation.

## Question
On fresh held-out hard agentic tasks, does **compression-only** TokenTrim (risk-aware, structure-preserving
tool-output compression, router off) keep the baseline pass rate within a 5 pp non-inferiority margin, and how
much does it cost per task and per successful task? The same question is asked of **guarded full** as a separate
arm.

This is a TokenTrim system evaluation: it compares configurations of the same model through the local proxy
code path. It compares no providers or models.

## Tasks (fresh, held out)
* `benchmarks.workloads_hard.hard_task(i)` for **i = 300…443** (144 tasks, ids ah300–ah443). These are new
  generated instances (seeded by i) of the v5 hard incident family. They do not overlap v5 (ah00–ah95,
  pilot ah100–ah103): no shared task ids and no shared trace refs. Nobody has run or inspected them on any
  model.
* Same generator, tools (32, 3 dependent read tools, side-effect tools that fail the task) and grader as v5:
  10 checks, pass = all 10.
* **Batches** (the stopping rule depends on spend only, never on outcomes):
  * Batch A: i = 300…395 (96 tasks), always run.
  * Batch B: i = 396…443 (48 tasks), run only if, after A, the round's Meta spend + 1.25 × (A's cost per
    task × 48) ≤ $3.00.
  * If B is not run, n = 96. This is the pre-registered minimum, and the report says so.
* Cheap-model validation uses **disjoint** indices 500–523, never 300–443.

## Arms (benchmarks/run.py `ARMS["agentic_hard"]`)
| arm | skill | cache prefix | tool output | JSON mode | schema router |
|---|---|---|---|---|---|
| `baseline` | no | no | no | – | no |
| `compression_only` (**primary, headline**) | no | no | yes | auto (risk-aware) | no |
| `guarded_full` (secondary) | yes | yes | yes | auto | yes, with v5.2 gating + loop guard |

History compaction is off in every arm. Settings: model `muse-spark-1.3-contributor` (Contributor mode),
max_tokens 16000, workers 6, seed 7, arm order shuffled per task, temperature at the provider default.

## Outcomes and analysis (benchmarks/report_v5.py)
* **H1 (primary):** compression_only vs baseline pass rate. Paired difference with the Newcombe method-10 95%
  CI (continuity-corrected phi; `bench.stats.noninferiority_paired`, margin 0.05). Non-inferiority is shown iff
  the lower bound is > −5 pp. Reported as shown or not shown, whatever the result.
* **H2 (secondary):** the same test for guarded_full vs baseline.
* **Cost:**
  * mean $ per task and $ per successful task, from API `usage` at list price (input $0.10/M, cached
    $0.002/M, output $0.20/M);
  * the paired bootstrap 95% CI of the saving (report_v5 defaults);
  * the token-type breakdown (uncached input, cached, output, reasoning);
  * truncated calls (finish_reason = length).
* **Counted as failures:** harness/transport errors and truncations, in the primary analysis. A sensitivity
  analysis excluding harness errors is reported separately and labelled.
* **Power note (computed before running):** with baseline at 96/96, the lower bound is −3.8 pp for 0 net
  failures, −5.7 pp for 1 and −7.3 pp for 2. So at n=96, NI is shown only with essentially no net failures.
  At n=144 one net failure is tolerated. "NI not shown" does not mean "inferior".
* Mock results are reported as harness validation only, never as results.

## Budget and safety
* Round cap $3.00 on Meta: `--run-cap-usd 3`.
* Job cap $7.94 (= $4.9373 already in the ledger + $3.00, keeping the total ≤ $9): `--job-cap-usd 7.94`.
* Reserving ledger (fail-closed, v5.1). If the cap stops a run, only completed pairs are analysed and the
  stop is reported.

## Validation before any Meta call
1. Mock harness on i = 300…395, arms as above:
   * oracle: 96/96 in every arm;
   * lazy: baseline 96/96, compression arms 2/96 (they need recovery);
   * guess: 0/96 everywhere.
   This shows that the grader discriminates and that recovery is needed.
2. Cheap probe: claude-haiku-5-5 via `claude -p`, raw vs compressed (auto JSON mode), i = 500–523.
