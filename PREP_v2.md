# TokenTrim Prep v2

*Drafted with Claude Opus 5.5 (`claude-opus-5-5`) from PREP.md, the repo README and web research on Oct 28 2026. Prep only, no code. Prepared Oct 28 2026. Submissions due Nov 4, 9:00 PM ET (7:30 AM IST, Nov 5). Internal freeze: Nov 4, 6:00 PM ET (3:30 AM IST, Nov 5). Meta credits ($150) have been requested but not confirmed.*

---

## 0. TL;DR

- **Position TokenTrim as the layer that cuts dollars while checking that tasks still pass.** It should not compete with compressors. It can sit alongside Headroom, tare and similar tools, and it differs from them in four ways: billed dollars with cached input priced separately, cache-aware layout, routing with escalation, and pass rates with 95% CIs.
- **The prototype is a sound skeleton, but every number it produces is fake.** It has no real agent loop, the Meta client is untested, and nothing has been billed. Nov 1–2 goes to a real loop, a real API client and real usage accounting. Nov 3 goes to the benchmark. Nov 4 goes to the video and submission.
- **The current corpus does not honestly meet the "40 real repo-edit tasks" promise.** It is 40 toy single-file Python tasks. Either describe it accurately and add a small SWE-bench subset as a stretch real-world check, or upgrade part of the corpus. Q3 below recommends doing both, as far as time allows.
- **Budget: about $108 planned out of $150, with about $42 (28%) held back.** The main run is 40 tasks × (Wonder baseline + TokenTrim) × 3 repeats, plus a Spark-only control and ablations on 20 tasks.
- **Decisions needed now:** which model is the baseline, whether the contributor tier is allowed, how to word "real", a fallback if credits don't arrive, and whether to start the offline work on Oct 29 regardless.

---

## 1. Problem statement and differentiators

**Pitch.** Coding agents send the same large context on every step, at the price of the strongest model. Existing savers measure success in tokens, but providers bill in dollars. On Muse Spark, cached input costs about 8× less than uncached input, and on Wonder about 20× less. Output tokens cost 3.4–5× more than uncached input. So a change that saves 45% of tokens can save only 13.5% of the cost, as an earlier measurement of ours showed. TokenTrim is open-source middleware that minimizes **billed dollars per passed task**. It removes context the agent isn't using, trims old tool output, lays out prompts so the provider's cache gets hit, and sends routine steps to a cheaper model, escalating to a stronger one when a step fails. Each change is checked against hidden tests with paired 95% confidence intervals.

**Tagline:** *TokenTrim cuts what coding agents pay, not just what they send, and shows that tasks still pass.*

### Comparison

This table is based only on the Oct 28 research notes. "Not noted" means we found no claim either way, not that the feature is missing.

| | Compression | Cache-aware layout | Model routing | Dollar objective with cached pricing | Correctness-gated benchmark with CIs | Meta Muse support |
|---|---|---|---|---|---|---|
| Headroom | **Strong** (reversible, multi-source) | Not noted | No | No (tokens) | Token claims (~20% for coding) | Not noted |
| Tamp | **Strong** (multi-stage, output compression) | Partial (cache-breaking rewrite is opt-in) | No | No (tokens) | Not noted | Not noted |
| Squeezr | Yes (schema truncation, dedup) | **Yes** (byte-stable) | No | No | Not noted | Not noted |
| tare | Yes (lossless by default) | **Yes** (compresses only after the cache breakpoint) | No | No (backs off when output spikes) | Not noted | Not noted |
| Paritok | **Strong** (learned 4B model) | Yes (schema frozen per conversation) | No | No | Not noted | Not noted |
| LiteLLM Auto Router | Via hosted guardrail | Partial (injects `cache_control`) | **Yes** | Partial (cost claims) | 21-task Terminal-Bench at the same solve rate; CIs not noted | Generic OpenAI-compatible (likely) |
| RouteLLM | No | No | **Yes** (general, not built for coding) | Partial | General benchmarks, not repo edits | Not noted |
| **TokenTrim** | Basic (pruning plus head/tail trimming) | Yes (planner exists; provider behavior unverified) | Yes, with escalation on failure | **Yes, core** (cached and uncached input billed separately) | **Core deliverable** (planned) | **Yes** (native price table, Spark/Wonder routing) |

### Honest differentiators

1. **It optimizes for dollars, not tokens.** It uses provider-reported usage, prices cached and uncached input separately, and reports cost per *passed* task.
2. **It optimizes three savers together.** Pruning, cache layout and routing are tuned as one objective, and the system won't make a change that saves tokens if that change breaks the cache.
3. **It checks correctness, not just counts.** Pass rates come from hidden tests, comparisons are paired by task with bootstrap CIs, failures are fully accounted for, and there are ablations for each saver.
4. **It's built for Muse.** It uses Spark→Wonder routing and the Muse cache pricing, which none of the surveyed tools mention.

### Claims to avoid

- Don't claim to beat Headroom, Tamp or Paritok on compression ratio. Our compressor is basic.
- Don't say "first" or "no one does X." Say "among the tools we surveyed."
- Don't headline −68% or 60/60. Those are earlier, unreproduced numbers. Use only the results this run produces.
- Don't generalize from 40 small tasks to "coding agents in general."
- Don't say "lossless." Pruning drops content.
- Don't claim plug-in support for Claude Code, Codex or Muse Code unless each was actually tested.

**Positioning line:** *"Compressors decide what to send. TokenTrim decides what it costs and checks that tasks still pass."* As a stretch goal, show TokenTrim's router and cache planner running on top of another tool's compressed output, to show they compose.

---

## 2. Architecture outline

### Components

| Component | What it does | Status |
|---|---|---|
| Adapter / proxy | A built-in agent loop (tools: list, read, write, run visible tests, finish) for the benchmark. An OpenAI-compatible proxy for external agents is a stretch goal. | **New.** The prototype only has a two-step fake loop. |
| Context pruner | Drops unreferenced files and keeps system, pinned and latest-user items. Raises `BudgetExceededError`. | **Exists.** Needs **new** reference tracking driven by the agent's real reads and edits. |
| Tool-output trimmer | Keeps the head and tail of old tool outputs and inserts an exact marker for trimmed lines. | **Exists.** Tune it on real test logs and tracebacks. |
| Cache planner | Puts stable content first and hashes the prefix. | **Exists.** **New:** check its estimates against the provider's reported cached tokens, and learn the Muse minimum prefix and TTL. |
| Router + escalation | Heuristic routing (planning, multi-file edits and retries go to the strong model). | Routing **exists.** **New:** escalate to Wonder on a failed visible test, malformed output, or N steps with no progress. |
| Cost meter | Computes cost from usage with the formula `cost()` and `prices.toml`. | **Exists.** **New:** use provider-reported usage only, and reconcile against the billing console. |
| Meta client | Stub using `urllib` and `/chat/completions`. | **Exists but unverified.** **New:** validation, retries and parsing of usage fields. |
| Benchmark harness | Paired two-mode runs, seeded bootstrap, real checker. | **Exists.** **New:** a visible/hidden test split, repeats, ablation modes, failure categories, spend caps. |
| Dashboard | Static viewer with no dependencies. | **Exists.** **New:** auto-refresh from a JSONL file, cost-per-pass and ablation views. |

### Request flow

```
 Agent loop (or external agent via proxy)
        │ messages + tool results
        ▼
 ┌─ TokenTrim.complete(mode) ──────────────────────────────┐
 │  Context pruner ─► Tool-output trimmer ─► Cache planner │──(any error)──► FAIL-OPEN: send original request
 │                                              │          │
 │                                     Router (Spark|Wonder)│
 └──────────────────────────────────────────────┼──────────┘
                                                ▼
                                   Meta Muse API (chat/completions)
                                                │ response + usage{input, cached, output}
                                                ▼
                         Cost meter ─► Step log (JSONL) ─► Dashboard (auto-refresh)
                                                │
              Agent runs VISIBLE tests ─ fail/malformed? ─► Escalate next step to Wonder
                                                │
                                   finish ─► Hidden-test checker ─► results.json + CIs
```

### Recorded for each step

Run ID, git commit, task ID, mode, repeat, step index, step type, router decision and reason, model ID, estimated and reported input tokens, reported cached tokens, output tokens, computed dollars, latency, prefix hash, planner's estimated reuse, pruning report (items dropped, lines trimmed), escalation flag and cause, retries, HTTP status, and provider request ID.

For each task: pass or fail, failure category, checker output and exit code, total dollars, wall time, and number of escalations.

### Safety and fail-open rules

- If any saver raises an exception, send the unmodified request and log `fail_open=true`.
- Never prune system, pinned or latest-user items, or the *latest* tool output.
- If the router is unsure, use the strong model. The contributor tier is never chosen automatically.
- Hard limits per task: maximum steps (e.g. 15) and maximum dollars (e.g. $1.00). A global kill switch stops all runs at $120 cumulative spend.
- Hidden tests are never visible to the agent or the router. Escalation uses only signals the agent can see.
- Logs never contain keys. Run a secret scan before any push, and don't push or post without the user's OK.

---

## 3. Build plan

Coding happens through the main Codex account with `gpt-6-astra`. Stop at 78% usage and keep track of that limit each day.

### Oct 29–31: pre-work, only if credits are confirmed

- Set up the Meta Model API account and team ID, and add a card. **Set a spend limit before the first call.**
- Check the prices and model IDs on the pricing page against `prices.toml`.
- Make one smoke call per model. Confirm the usage object reports **cached tokens** and find the field name. Measure the minimum cacheable prefix, the TTL and the rate limits.
- Exit criteria: model IDs and prices confirmed, cached-token field identified, rate limits recorded.

### Daily plan

| Day | Goals | Exit criteria | Risk / fallback |
|---|---|---|---|
| **Nov 1** | Real agent loop. Split each of the 40 tasks into visible and hidden tests. Validate the Meta client. Cost meter based on reported usage. Per-step JSONL. | Reference self-test passes 40/40 with hidden tests. 3 tasks run end to end in both modes on the real API. Computed dollars match the console to within about 5%. | If usage lacks cached counts, estimate them from the planner, label them as estimates, and reconcile with console totals. If credits are missing, see Q4. |
| **Nov 2** | Pruner reference tracking, trimmer tuned on real logs, cache layout checked against reported cached tokens, escalation rules. 10-task pilot. | In the pilot, TokenTrim passes within one task of baseline and costs less. **Config frozen and tagged** before the main run. | If Spark's pass rate is low, send all edits to Wonder and use Spark only for reads and summaries. |
| **Nov 3** | Main benchmark: 40 × 2 modes × 2–3 repeats, a Spark-only control, ablations on 20 tasks. Dashboard views. | `results.json` with paired CIs. Ablation table filled in. No silently dropped runs. | Run 4–8 workers in parallel. If behind, drop to 2 repeats. |
| **Nov 4** | Third repeat or stretch goal. README rewrite (real results first, the fake mode labeled). Video. Secret scan. Submission. | **Freeze at 6 PM ET (3:30 AM IST).** Video uploaded, repo public after the user's OK. | Use the 6–9 PM ET window only for upload problems. |

### Credit budget

**Per-task assumptions for the toy corpus:**

- **Baseline:** about 6 agent turns averaging about 10k input tokens, so about 60k input and 4.8k output per task, with about 30% of input cached by chance.
  - **Wonder-only baseline:** 42k × $4/M + 18k × $0.20/M + 4.8k × $20/M = $0.168 + $0.004 + $0.096 = **$0.27**
  - **Spark-only control:** 42k × $1.25 + 18k × $0.15 + 4.8k × $4.25 (per M) = $0.053 + $0.003 + $0.020 = **$0.076**
- **TokenTrim:** about 35k input tokens after pruning, about 70% cached, roughly 5 of 6 turns on Spark, plus escalations. That comes to **about $0.06–0.07**, consistent with the earlier $0.060.
- **Safety factor:** multiply everything by 1.5 to cover longer loops and retries. That gives Wonder $0.40, Spark $0.11 and TokenTrim $0.11 per task.

| Line item | Math | $ |
|---|---|---:|
| Pre-work and dev/pilot (Nov 1–2) | Hard cap | 15 |
| Main run: 40 × (Wonder baseline + TokenTrim) × 3 repeats | 40 × 0.51 × 3 | 61 |
| Spark-only control × 2 repeats | 40 × 0.11 × 2 | 9 |
| Ablations, 20 tasks, 1 repeat: prune-only, trim-only, cache-only (each on Wonder) + route-only | 20 × 0.33 × 3 + 20 × 0.15 | 23 |
| **Planned total** | | **108** |
| **Reserve (28%)** | Reruns, infrastructure failures, stretch goal | **42** |

- The SWE-bench stretch is capped at $20 and comes only out of the reserve, after the main results are frozen. At least $20 of the reserve should stay unspent.
- At Spark pricing, $150 buys about 75M tokens, so token volume is not the constraint. Wonder output is the main cost.

### Cut line

If behind schedule, drop items in this order:

1. SWE-bench stretch
2. External-agent proxy demo
3. Dashboard auto-refresh (use a static snapshot)
4. Ablations from 20 tasks to 10
5. Repeats from 3 to 2
6. Spark-only control (keep it if at all possible, because judges will ask)

**Never cut:** real billed usage, the hidden-test check, paired CIs, the video.

---

## 4. Demo video and benchmark plan

### Video storyline (about 2:40)

| Time | Shot | Content |
|---|---|---|
| 0:00–0:15 | Title card, then one chart | "Tokens aren't dollars": tokens down 45% but cost down only 13.5% |
| 0:15–0:35 | Diagram | The problem, Muse cached vs uncached pricing, the positioning line |
| 0:35–1:05 | Split-screen terminal and dashboard | Same task in baseline and TokenTrim, with the step log showing routing reasons, cached tokens and dollars per step |
| 1:05–1:25 | Dashboard zoom | Escalation: Spark fails the visible test, escalates to Wonder, and the task passes on the hidden tests |
| 1:25–2:00 | Results view | Dollars per task and cost per passed task with CIs, pass-rate difference CI, the Spark-only control, ablation waterfall |
| 2:00–2:20 | Text card | Limitations: small Python repos, n=40, one provider. Composes with compressors. |
| 2:20–2:40 | Repo page | Open source, one-command reproduction, link to the raw logs |

### Metrics

| Metric | Definition |
|---|---|
| Dollars per task | Total billed dollars, all steps, from reported usage |
| Tokens | Total, uncached input, cached input, output |
| Pass rate | Share of tasks passing the hidden tests |
| Cost per passed task | Total dollars ÷ number of passed tasks (the headline metric) |
| Latency | Wall time per task, p50 and p90 |
| Escalation rate | Share of steps escalated, and share of tasks with any escalation |
| Cache hit rate | Reported cached input ÷ total input |

### Statistics

- Use the paired percentile bootstrap that already exists: 2,000 resamples, resampling tasks, with repeats averaged within each task first.
- Report 95% CIs for the dollar difference, the percentage saved, and the pass-rate difference in percentage points.
- **Be honest about precision.** With n=40, the pass-rate CI will be about ±10 pp. Claim only "no detected drop; CI lower bound X pp" and nothing stronger.

### Ablations

| Mode | Contents |
|---|---|
| Baseline | Wonder only |
| Single savers | Baseline + prune, + trim, + cache layout, and route only |
| Stacked | Full TokenTrim |
| Control | Spark only |

### Task sets

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Own 40-task corpus | Already exists, cheap, no Docker, reference self-test | Toy single-file Python tasks | **Primary** |
| SWE-bench Lite/Verified, about 10 tasks | Credible real repos | Docker, large contexts ($1–2 per Wonder run), low Spark pass rate | **Stretch** |
| Aider Polyglot subset | Cheap, tests included | Exercism exercises, not repos | Skip |
| Terminal-Bench subset | Directly comparable with LiteLLM's claim | Docker, not repo edits | Skip |

### Pass check, failure accounting and reproducibility

- **Pass check:** each task's tests are split. Visible tests are shown to the agent and used for escalation. Hidden tests are used only by the checker and run in a disposable copy with a timeout.
- **Failure accounting:** timeouts, exceeded step or dollar caps, and malformed output count as **failures in that mode, and the money spent still counts.** API errors that persist after retries are labeled infrastructure failures, rerun once, and reported separately. Nothing is excluded silently.
- **Reproducibility:** pin model IDs, temperature 0 if supported, seeds, a hash of `prices.toml`, a hash of the task list and the commit. Publish the cleaned per-step JSONL. Provide a one-command rerun, and keep fake mode so people without credits can reproduce the pipeline.

### Does the corpus count as "real"?

The promise was **"40 real repo-edit tasks."** The current corpus in `bench/tasks_repo` is toy single-file Python. Most judges would not call that "real," and it doesn't exercise pruning or multi-file routing much.

Verified Oct 28: `bench/tasks/tasks_40.jsonl` exists with 40 tasks (t01–t40 under `bench/tasks_repo`, plus `_solutions` and `_validator_tests`). The README line saying the committed sample has only 3 tasks is stale and should be fixed.

Options are in Q3.

---

## 5. Open questions for the user

1. **Baseline and strong model.**
   - (a) Wonder-only baseline vs TokenTrim with Spark by default and Wonder for escalation
   - (b) Spark-only baseline
   - **Default: (a), plus a Spark-only control.**
2. **Contributor tier (Meta may train on what we send).**
   - (a) Never
   - (b) Dev and smoke runs on synthetic tasks only
   - (c) Headline runs too
   - **Default: (b), with all headline numbers at standard pricing.**
3. **Wording for "real".**
   - (a) Describe the corpus as "40 small Python repo-edit tasks" and add a SWE-bench stretch
   - (b) Upgrade about 10 tasks to multi-file repos
   - (c) Mine real bugfix commits
   - **Default: (a), plus (b) if Nov 2 goes well.** Also post a correction note on Substack, only with the user's OK.
4. **Credits not confirmed by Nov 1, 12:00 IST.**
   - (a) Use your own card with a $40 cap and run 1 repeat
   - (b) Contributor tier only
   - (c) Submit in fake mode
   - **Default: (a).**
5. **Start offline coding on Oct 29 regardless of credits?** The agent loop and the test split don't need the API. **Default: yes.**
6. **How to integrate with agents.**
   - (a) Built-in loop only
   - (b) Plus an OpenAI-compatible proxy demo
   - **Default: (a), with (b) as a stretch.** We don't know whether Muse Code accepts a custom base URL.
7. **Earlier numbers ($0.186→$0.060, 60/60).**
   - **Default: mention them only as "earlier exploratory" results, not as headlines.**
8. **Margin for "no quality loss."**
   - (a) Report CIs only
   - (b) Pre-register a −10 pp non-inferiority margin
   - **Default: (b).**
9. **"Live" dashboard.**
   - (a) Local auto-refresh
   - (b) Hosted static snapshot
   - **Default: both.** Hosting it counts as publishing, so it needs the user's OK.
10. **License and when to go public.**
    - **Default: Apache-2.0, repo goes public Nov 4 after the secret scan and the user's OK.**

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Credits arrive late or not at all | Q4 fallback. Offline work starts Oct 29. Set a spend limit on the card. |
| Usage doesn't report cached tokens | Reconcile against console totals and label cache savings as estimated |
| Muse cache behavior differs from planner assumptions (minimum prefix, TTL) | Measure it during pre-work. Ablations show what each saver actually contributes. |
| Spark pass rate drops | Escalation, routing edits to Wonder, a frozen config, and honest CIs |
| Rate limits slow the main run | Parallel workers with backoff. Start Nov 3 early. Fall back to 2 repeats. |
| Leakage from hidden tests | Strict visible/hidden split. Router and escalation use only signals the agent can see. |
| Overspending | Per-task cap, $120 kill switch, $42 reserve |
| "Real tasks" credibility gap | Accurate wording, SWE-bench stretch, plain limitations card in the video |
| Codex usage hits the 78% stop | Do the heavy coding Nov 1–2, keep prompts small, and do manual fixes after that |
| Leaking a key or secret | Load keys from environment only, secret scan, no push without the user's OK |
| Missing the deadline across time zones | Freeze at 6 PM ET (3:30 AM IST). Upload the video by Nov 4 afternoon ET. |