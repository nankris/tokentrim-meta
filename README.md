# TokenTrim

An offline-first prototype of open-source middleware for coding agents such as Claude Code, Codex, and Muse Code. TokenTrim prunes unused context and old tool output, orders stable prompt prefixes for caching, and routes routine steps to cheaper models. It optimizes estimated **dollars**, accounting for cached input separately from uncached input.

The included benchmark and dashboard use **FAKE data**. The deterministic client does not edit repositories, and the fake checker does not execute task check commands. Synthetic passing checks are not evidence of coding correctness. No credits, API calls, or network access are needed to run this prototype.

Prior measurements recorded in PREP.md (not reproduced here): stacked savers reduced estimated cost from $0.186 to $0.060 per task with 60/60 passing; front-loading context reduced tokens 45% but cost only 13.5%; local-model offloading cost about 2.1× more. These motivate measuring dollars and correctness together.

## Quickstart

Run from the repository root with Python 3.13. Standard library only at runtime and in tests; no install is necessary.

```sh
python3 -m unittest discover -s tests -v
python3 -m bench.runner --client fake --out results/results.json
python3 -m http.server 8000
```

Open `http://localhost:8000/dashboard/` in a browser. Alternatively, open `dashboard/index.html` directly and use its file picker to load `results/results.json`. The HTTP server is an optional local viewing step; it was not started during the offline build. Where `python` points to Python 3.13, the equivalent commands using `python` work. This environment provides `python3` only.

Use a different task list with:

```sh
python3 -m bench.runner --client fake --tasks bench/tasks/tasks_40.jsonl --out results/results_40_fake.json
```

Run actual offline checks, or verify the bundled reference solutions:

```sh
python3 -m bench.runner --checker real --tasks bench/tasks/tasks_40.jsonl --out results/results_40_real.json
python3 -m bench.runner --reference-self-test
```

The fake client still reports simulated usage and produces no valid edits, so its real-checker results fail. Real check results include captured output, exit code, timeout status, and errors. The checker uses the final response only, formatted as JSON with full UTF-8 file replacements: `{"files": {"core.py": "complete source contents\n"}}`. An empty `files` object runs the unmodified repo. Paths must be canonical relative POSIX paths; traversal, symlinks, duplicate keys, and edits under `tests/` are rejected. Reference solutions are read only by the explicit self-test.

Checks run without a shell in disposable copies under the project root, with a five-second timeout and local `python`/`python3` aliases. The minimal environment puts temporary files inside that workspace. This is not a security sandbox: use only trusted code and check commands; network and filesystem access are not OS-restricted. The reference unittest runs by default; set `TOKENTRIM_SKIP_REFERENCE_TEST=1` to skip its 80 subprocess checks on slow hosts.

That task corpus is managed separately. The command above still simulates results; it is not a real 40-task coding evaluation. The committed sample contains only the three toy tasks.

## Layout

- `tokentrim/`: token estimator, context pruner, cache planner, prices/costs, routing, middleware, and clients.
- `bench/`: JSON/JSONL task loader, two-mode harness, and seeded bootstrap statistics.
- `bench/tasks/example_tasks.jsonl`, `bench/examples/`: three deliberately broken toy exercises.
- `tests/`: standard-library unittest coverage, including offline end-to-end verification.
- `results/results.json`: reproducible FAKE sample with per-step usage, routing reasons, pruning reports, and task-level summaries.
- `dashboard/`: static HTML/JS viewer, no external dependencies or CDN.
- `issues-found/`: implementation issues and their status.

## Core behavior

`ContextItem` carries `id`, `kind`, `text`, `turn`, `referenced`, `reference_count`, `pinned`, and message `role`. The pruner preserves system items, pinned items, and the latest user message; it drops unreferenced files and prioritizes newer optional context. Old tool outputs keep head/tail lines and an exact trimmed-line marker. Items are returned in original order for the planner. Mandatory context exceeding the budget raises `BudgetExceededError`; callers must increase the budget or reduce mandatory content explicitly. Callers are responsible for marking task/recent references. The default estimate is rounded-up characters / 4; tokenizer callables can replace it.

The planner puts system prompts, tool schemas, repo maps, and pinned files before volatile content. It hashes the stable prefix and estimates reuse using the longest exact common segment prefix with the previous call. It warns when incoming ordering interleaves volatile content before stable content. Standalone `PromptSegment` supports tool-schema and repo-map kinds; middleware context items can pin these as system/file content. Estimates exclude provider-specific framing, minimum cache sizes, TTLs, and cache-write charges. A production client’s reported usage, not planner estimates, drives costs.

The heuristic router uses stronger models for planning, multi-file edits, failed-test retries, long context, and complex/unclassified edits. Reads, summaries, formatting, and small single-file edits use the cheap model. Defaults are synthetic models. Configure `HeuristicRouter` explicitly for other models; contributor mode is never selected by default.

`TokenTrim.complete(items, step, mode="tokentrim")` runs pruning → planning → routing → client and returns `(ModelResponse, StepRecord)`. Baseline mode preserves all context and its original ordering and always selects the strong model. Keep separate middleware/client instances for independent conversations and competing modes. Clients implement `complete(messages, model, max_tokens)`; an optional `set_plan(plan)` hook supplies prefix metadata to the fake client. Its cache is keyed by model and stable-prefix hash and simulates full stable-prefix hits only. A changed stable prefix is a miss, even if the planner estimates partial reuse.

`MetaModelClient` is an opt-in, unverified transport stub using `urllib` and an OpenAI-compatible `/chat/completions` payload. It requires `META_API_BASE_URL` (API root, HTTPS) and `META_API_KEY` environment variables. No real URL or credential is embedded. The offline CLI accepts only `--client fake`; the Meta stub is never called by tests.

## Prices

USD per one million tokens, copied from PREP.md / hackathon documentation:

| Model | Input | Cached input | Output |
|---|---:|---:|---:|
| meta/muse-spark-1.3 | 1.25 | 0.15 | 4.25 |
| meta/muse-wonder-1.0 | 4.00 | 0.20 | 20.00 |
| meta/muse-spark-1.3-contributor | 0.10 | 0.002 | 0.20 |
| fake/cheap (synthetic) | 1.00 | 0.10 | 2.00 |
| fake/strong (synthetic) | 4.00 | 0.20 | 20.00 |

**Meta credits have not yet been claimed. Verify against dev.meta.ai pricing before real use.** No online verification was performed. Contributor mode permits Meta to train on content and requires an explicit model choice.

`cost(model, input_tokens, cached_tokens, output_tokens)` treats input as the total including its cached subset: `((input - cached) × input_price + cached × cached_price + output × output_price) / 1,000,000`. Override the bundled `tokentrim/prices.toml` with the `TOKENTRIM_PRICES` environment variable, using the same `[models."model-name"]` table format.

## Tasks and statistics

Task files are JSON arrays or JSONL, one object per line:

```json
{"id":"example","repo":"bench/examples/add","prompt":"Fix addition.","check":"python3 -m unittest -q","files":["main.py"],"solution":"relative/path/to/overlay","category":"bugfix","difficulty":"easy"}
```

Required: `id`, `repo`, `prompt`, `check`. Optional: `files`, `solution`, `category`, `difficulty` (`easy`, `medium`, `hard`). Extra keys are ignored. Repository and solution paths are relative to the project root; file paths are relative to the task repo. The fake runner reads only listed context files, never reference solutions, and never executes `check`. The sample task records provide concrete checks for their individual toy exercises. Paths are constrained to the repository.

Each task receives two simulated steps (read, then edit), identical initial context, and an isolated cold client cache for each mode. Artificial irrelevant context and diagnostic output exercise pruning. `run_benchmark` accepts a `client_factory` and a checker callable `(task, responses, mode) -> bool | CheckResult`; `real_checker` applies and checks the final response. A production benchmark still needs a sandboxed editing-agent loop. Reference solutions must remain hidden from the agent.

Summaries report mean total tokens, estimated USD, and pass rate per task. Cached input is a subset of input and is not counted twice. Seeded percentile bootstrap uses 2,000 resamples by default. Paired comparisons match task IDs and resample task pairs; differences are TokenTrim minus baseline. Percent savings use the ratio of resampled means. Zero denominators produce JSON `null` for undefined relative estimates/intervals. The dashboard displays pass-rate differences in percentage points. Tiny, constant, or fake samples can have degenerate intervals; these are descriptive, not evidence of general performance. `--seed`, `--samples`, and `--budget` configure the run.

## Roadmap

1. Integrate a sandboxed real editing-agent loop with the offline checker.
2. Validate Meta transport, model identifiers, pricing, and provider cache behavior after explicit API authorization.
3. Compare measured tokens, billed dollars, and real pass rates with paired 95% intervals; add cost/quality ablations and failed-run accounting.
4. Add coding-agent adapters, reference tracking, richer cache planning, and live dashboard refresh.
