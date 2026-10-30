# TokenTrim

Open-source middleware that cuts what coding agents (Claude Code, Codex, Muse Code) spend. TokenTrim optimizes **billed dollars, not tokens**: cached input is a subset of input and is billed at its own (much lower) rate, so a trick that saves tokens but breaks the provider's prefix cache can cost more.

> **Status: prototype with a first small REAL run.** `results/real_meta_2026-10-30/` holds real Meta Model API measurements (6 tasks, one pass, $0.32 total; see [below](#real-meta-run-2026-10-30)). Everything else under `results/` is **FAKE or SIMULATION data**, not real measurements.

## What it does

Each saver runs inside a fail-open wrapper. If any saver raises, the original request goes to the strong model unchanged (`SpendCapExceeded` is the one exception and always propagates).

| Saver | Module | Cache-aware rule |
|---|---|---|
| **trim**: compact test/build logs (keep every error/traceback/FAILED line, collapse passing and repeated lines) | `tokentrim/compaction.py` | Compaction happens at ingest and is deterministic, so history stays byte-stable. The full output stays restorable by ID in `OutputStore`. Grep hits and source are left alone (`is_log_like`). |
| **prune**: drop unreferenced files and stale reads | `tokentrim/pruner.py`, `middleware.py` | Drops are latched (no oscillation) and committed only when `CostModel.breakeven_compaction` says the dollar saving beats the cache break. Otherwise they are deferred. Budget-forced drops always apply. |
| **cache_layout**: stable prefix first, sorted-key tool JSON, cache-buster lint (timestamps, UUIDs, request IDs, temp paths) | `tokentrim/layout.py`, `planner.py` | Only stable kinds move forward. Conversation order is never reshuffled. `AppendOnlyHistory` refuses rewrites without an approved `CompactionCheckpoint`. |
| **route**: cheap model for routine steps, sticky escalation to the strong model on visible signals (test failure after a cheap edit, malformed output, no progress) | `tokentrim/router.py`, `routing.py` | Provider caches are per model. A downgrade must pass `cache_aware_switch`, which compares staying on the warm model with re-billing the non-warm context on the new one. Upgrades and escalations are never blocked. `CheapFirstRouter` avoids cold strong-model prefills. |

Supporting pieces:
- `tokentrim/cost.py` `CostModel`: per-model input, cached input, output and optional `cache_write` prices, with overrides, a price hash and break-even maths.
- `tokentrim/guard.py` `SpendGuard`: per-task cap ($1), global cap ($120, persisted ledger) and a 15-step cap. It checks a worst-case projection before each call.
- `tokentrim/proxy.py`: a loopback-only OpenAI-compatible `/v1/chat/completions` proxy that returns `usage.prompt_tokens_details.cached_tokens`. It never logs request bodies.
- `tokentrim/clients/mock.py`:
  - `MockProviderClient` simulates a per-model exact-prefix cache with 128-token blocks, a minimum cacheable size, a TTL and optional write charges.
  - `RecordingClient` and `RecordedClient` provide secret-free JSONL record and replay.
- `tokentrim/clients/meta.py`: opt-in Meta Model API client (OpenAI-compatible, `https://api.meta.ai/v1`), key from `META_API_KEY`/`MODEL_API_KEY`, 429/5xx back-off, parses `prompt_tokens`, `cached_tokens`, `completion_tokens` (incl. reasoning). Verified against the live API on 2026-10-30. Tests never call the network.

## Quickstart (offline, standard library only, Python 3.13)

```sh
python3 -m unittest discover -s tests -v        # TOKENTRIM_SKIP_REFERENCE_TEST=1 skips the 80 slow reference checks
python3 -m bench.simulate --tasks bench/tasks/tasks_40.jsonl --repeats 3 --seed 42 --out results/sim/ --sweep
python3 -m bench.runner --client fake --out results/results.json   # older two-step FAKE harness + dashboard data
python3 -m bench.runner --reference-self-test                      # reference solutions pass the real checker
```

`bench.simulate` writes `results/sim/sim_results.json`, `sim_summary.md`, `sensitivity.json` and `sensitivity.md`.

## Simulation harness (`bench/simulate.py`) — SIMULATION, not measurements

The harness runs a scripted agent on each of the 40 tasks: list → read files → grep → read distractors → run tests → plan → edit+test attempts (up to 4) → summary. Calls go through `TokenTrim` and `MockProviderClient`.

- **Prices.** It uses the verified Meta Muse prices: `meta/muse-spark-1.3` is the cheap model and `meta/muse-wonder-1.0` the strong one. An Anthropic-style 1.25× cache-write profile is included for illustration only.
- **Pass outcomes.** These are *assumed* per-tier probabilities drawn with common random numbers, so every mode sees identical draws. No task code is executed. Trimming's effect on quality is an explicit `trim_penalty` assumption, which defaults to 0.
- **Context sizes.** The `realistic` scenario pads the system prompt, the tools and the file reads to agent-sized contexts with synthetic, labelled content. The `toy` scenario uses the corpus as-is.
- **Statistics.** Repeats are averaged within each task, then a paired percentile bootstrap runs over the 40 tasks. Non-inferiority means the lower 95% CI bound of the pass-rate difference is above −10 pp.
- **Modes.**
  - `baseline`: Wonder only, with a cache-friendly layout.
  - `tokentrim`: all savers with the heuristic router.
  - `tokentrim-cheapfirst`: all savers with cheap-first routing and escalation.
  - Ablations: `prune-only`, `prune-eager` (no break-even gate), `trim-only`, `route-only`, `route-percall` (no switch check), `route-cheapfirst`, `cheap-only`.
  - Cache-busting comparisons (tool JSON re-serialized with random key order on every call): `baseline-naive`, `cache-only-naive`, `tokentrim-naive`.

Latest run (2026-10-28, seed 42, 40 tasks × 3 repeats, `realistic`). Full table: [`results/sim/sim_summary.md`](results/sim/sim_summary.md).

| SIMULATION mode | $/task | Saving vs reference [95% CI] | Pass-rate diff pp [95% CI] | Non-inferior |
|---|---:|---:|---:|:-:|
| baseline (Wonder only) | 0.155 | — | — (98.3%) | — |
| tokentrim (heuristic router) | 0.137 | 11.9% [10.6, 13.3] | −1.7 [−4.2, 0.0] | yes |
| tokentrim-cheapfirst | 0.084 | 45.6% [40.1, 51.1] | −4.2 [−9.2, 0.0] | yes (marginal) |
| trim-only | 0.137 | 11.6% [10.9, 12.3] | 0.0 | yes |
| prune-eager (no break-even gate) | 0.176 | **−13.6%** [−14.0, −13.3] | 0.0 | yes |
| route-only (heuristic) | 0.153 | 1.7% [0.4, 3.1] | −1.7 [−4.2, 0.0] | yes |
| cheap-only (Spark only) | 0.061 | 60.8% [59.6, 61.9] | −10.8 [−17.5, −4.2] | **no** |
| cache-only-naive vs baseline-naive | 0.155 vs 0.541 | 71.3% [71.1, 71.5] | 0.0 | yes |

How to read these numbers:
- They are simulated. Prices are real list prices, but traces and pass outcomes are synthetic.
- The cache-busting comparison shows what layout hygiene is worth when a client really does bust its cache. It is not a claim about any particular agent.
- See [`RESEARCH_2026-10-28.md`](RESEARCH_2026-10-28.md) for the design rationale and [`issues-found/`](issues-found/README.md) for known gaps.

## Real Meta run (2026-10-30)

`bench/real_meta.py` drives the same scripted agent against the live API with real JSON edits checked by the task tests; `bench/meta_cache_probe.py` probes the cache. Model `muse-spark-1.3-contributor`, 6 tasks (t01, t07, t13, t21, t28, t37), one pass each, $0.3166 total under a $0.50 SpendGuard cap. Full tables: [`results/real_meta_2026-10-30/summary.md`](results/real_meta_2026-10-30/summary.md).

| REAL comparison (6 tasks, 1 pass) | Prompt tokens | Billed $ | $ if no cache hits | Pass |
|---|---:|---:|---:|:-:|
| tokentrim (all savers, default gates) vs baseline | −2.7% | −9.7% | −5.1% | 6/6 vs 6/6 |
| tokentrim-eager (prune without break-even gate) vs baseline | **−15.7%** | −13.6% | −15.7% | 6/6 vs 6/6 |
| tokentrim-naive vs baseline-naive (cache_layout fixes shuffled tool JSON) | −0.1% | **−26.9%** | +0.7% | 6/6 vs 6/6 |
| baseline-naive vs baseline (cost of busting the cache) | −2.8% | +30.1% | −4.3% | 6/6 vs 6/6 |

Real vs simulated:
- **cache_layout** is the one saver that clearly paid off: 0 cached tokens with shuffled tool JSON vs 147k cached with TokenTrim's stable layout. The real saving (27%) is well below the simulated 71% because real Meta cache hits are intermittent: only ~31% of calls hit ([issue 46](issues-found/46-meta-cache-hits-intermittent.md)).
- **prune** with the default break-even gate deferred every drop, because the gate assumes a reliable cache. Eager pruning cut 15.7% of prompt tokens with no pass-rate loss on this tiny sample; the simulation predicted eager pruning would *cost* 13.6% more.
- **trim** compacted nothing: real test logs on these repos are short. The simulated 11.6% came from synthetic long logs ([issue 48](issues-found/48-trim-route-real-run-gaps.md)).
- **route** is a no-op with one model. The one Standard-vs-routed check is not like-for-like (the Standard baseline hit the per-task cap).
- 91% of completion tokens were hidden reasoning; short `max_tokens` truncates replies ([issue 47](issues-found/47-reasoning-tokens-and-max-tokens.md)).

These are single-pass observations on six small tasks, not statistically meaningful estimates.

## Prices

USD per one million tokens, in `tokentrim/prices.toml`. The Meta rows match the public dev.meta.ai pricing page (checked 2026-10-28) but have not yet been checked against a bill.

| Model | Input | Cached input | Output |
|---|---:|---:|---:|
| meta/muse-spark-1.3 | 1.25 | 0.15 | 4.25 |
| meta/muse-wonder-1.0 | 4.00 | 0.20 | 20.00 |
| meta/muse-spark-1.3-contributor | 0.10 | 0.002 | 0.20 |
| fake/cheap (synthetic) | 1.00 | 0.10 | 2.00 |
| fake/strong (synthetic) | 4.00 | 0.20 | 20.00 |

- Contributor mode lets Meta train on content, is not offered for Wonder, and is never selected unless `allow_contributor=True` is passed.
- The page states no minimum cacheable prefix, TTL or cache-write charge. These must be measured.
- Override the price table with `TOKENTRIM_PRICES=path.toml` or `CostModel(overrides=...)`.
- Cost formula: `((input − cached − write) × input + cached × cached_input + write × cache_write + output × output) / 1e6`.

## FAKE benchmark runner and real checker (`bench/runner.py`)

The older harness uses a deterministic FAKE client that never edits repositories. Its passing checks are not evidence of coding correctness.

```sh
python3 -m bench.runner --client fake --tasks bench/tasks/tasks_40.jsonl --out results/results_40_fake.json
python3 -m bench.runner --checker real --tasks bench/tasks/tasks_40.jsonl --out results/results_40_real.json
```

The real checker:
- **Input.** It applies the final response, formatted as JSON with full-file replacements: `{"files": {"core.py": "..."}}`. Paths must be canonical relative POSIX paths. Traversal, symlinks, duplicate keys and edits under `tests/` are rejected.
- **How checks run.** They run without a shell, in disposable copies, with a 5-second timeout. This is not a security sandbox, so use only trusted code.
- **Reference solutions.** These are read only by `--reference-self-test`.

The corpus has 40 tasks across 14 category/difficulty cells (`bench/tasks/tasks_40.jsonl`, repos in `bench/tasks_repo/`), plus three toy tasks in `bench/tasks/example_tasks.jsonl`. Open `dashboard/index.html` to view runner output.

## Tasks and statistics

Task files are JSON arrays or JSONL, one object per line:

```json
{"id":"example","repo":"bench/examples/add","prompt":"Fix addition.","check":"python3 -m unittest -q","files":["main.py"],"solution":"relative/path/to/overlay","category":"bugfix","difficulty":"easy"}
```

Required: `id`, `repo`, `prompt`, `check`. Optional: `files`, `solution`, `category`, `difficulty` (`easy`, `medium`, `hard`). Extra keys are ignored. Repository and solution paths are relative to the project root; file paths are relative to the task repo. The fake runner reads only listed context files, never reference solutions, and never executes `check`. The sample task records provide concrete checks for their individual toy exercises. Paths are constrained to the repository.

In `bench.runner` (FAKE client) each task receives two simulated steps (read, then edit), identical initial context, and an isolated cold client cache for each mode. Artificial irrelevant context and diagnostic output exercise pruning. `run_benchmark` accepts a `client_factory` and a checker callable `(task, responses, mode) -> bool | CheckResult`; `real_checker` applies and checks the final response. A production benchmark still needs a sandboxed editing-agent loop. Reference solutions must remain hidden from the agent.

Summaries report mean total tokens, estimated USD, and pass rate per task. Cached input is a subset of input and is not counted twice. Seeded percentile bootstrap uses 2,000 resamples by default. Paired comparisons match task IDs and resample task pairs; differences are TokenTrim minus baseline. Percent savings use the ratio of resampled means. Zero denominators produce JSON `null` for undefined relative estimates/intervals. The dashboard displays pass-rate differences in percentage points. Tiny, constant, or fake samples can have degenerate intervals; these are descriptive, not evidence of general performance. `--seed`, `--samples`, and `--budget` configure the run.

## Roadmap

1. Model Muse cache hits as probabilistic (~30% observed on 2026-10-30) in the simulator and in the prune break-even gate, then re-run the simulation.
2. Run a real paired benchmark: a sandboxed editing-agent loop on Spark and Wonder, measured billed dollars, real pass rates and paired 95% intervals.
3. Make cheap-first routing with sticky escalation the default if the real numbers confirm the simulated gap. Add a compact hand-off on escalation.
4. Add coding-agent adapters (proxy base-URL mode), a live dashboard and real reference tracking.
