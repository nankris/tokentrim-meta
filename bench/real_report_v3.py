"""Summarize the v3 REAL Meta runs (results/real_meta_2026-10-30_v3) into summary.md / summary.json.

Statistics (honest by construction):
* pass rate per mode with a Wilson 95% interval at run level (n = tasks x repeats) AND at task level
  (n = tasks, per-task mean pass), because repeats of one task are not independent;
* paired differences: repeats are averaged within each task, then a seeded paired percentile
  bootstrap over tasks (bench.stats.paired_comparison) for billed $, prompt tokens and pass rate;
* the pass-rate difference is also given as a Newcombe interval at task level (conservative);
  "non-inferior at -10 pp" is claimed only if BOTH the bootstrap and the Newcombe lower bounds
  are above -10 pp;
* pass-rate guard for eager prune: every task where tokentrim passed fewer repeats than the
  matched baseline is FLAGGED.
"""
import argparse
import json
from pathlib import Path
from statistics import fmean

from tokentrim.cost import CostModel
from .stats import newcombe_difference, paired_comparison, wilson

COMPARISONS = [("tokentrim", "baseline-ts"), ("tokentrim", "baseline-tools"), ("tokentrim", "baseline"),
               ("baseline-ts", "baseline"), ("baseline-tools", "baseline"),
               # v3b (separate invocation, same tasks/repeats, run after the main run): cache_layout alone.
               ("layout-move", "baseline-ts"), ("layout-drop", "baseline-ts"), ("layout-move", "baseline"),
               ("layout-drop", "baseline"), ("tokentrim", "layout-move")]


def nocache_usd(row, cm):
    return sum(cm.cost(c["model"], {"input": c["prompt_tokens"], "cached_input": 0, "output": c["completion_tokens"],
                                    "cache_write": 0})[0] for c in row["per_call"])


def per_task(rows, mode, field, cm=None):
    out = {}
    for r in rows:
        if r["mode"] != mode:
            continue
        value = nocache_usd(r, cm) if field == "nocache" else float(r[field])
        out.setdefault(r["task_id"], []).append(value)
    return {t: fmean(v) for t, v in out.items()}


def pct(x):
    return "n/a" if x is None else f"{x:+.1f}%"


def ci(c, scale=1.0, suffix=""):
    return "n/a" if c is None else f"[{c[0] * scale:+.1f}, {c[1] * scale:+.1f}]{suffix}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/real_meta_2026-10-30_v3")
    p.add_argument("--main", default="bench_main.json")
    p.add_argument("--pilot", default="bench_route_pilot.json")
    p.add_argument("--extra", default="bench_v3b.json", help="optional second run merged in (v3b layout-only modes)")
    args = p.parse_args()
    out = Path(args.out)
    cm = CostModel()
    data = json.loads((out / args.main).read_text())
    rows, meta = data["results"], data["metadata"]
    extra_spend = 0.0
    if (out / args.extra).exists():
        ex = json.loads((out / args.extra).read_text())
        assert ex["metadata"]["tasks"] == meta["tasks"] and ex["metadata"]["repeats"] == meta["repeats"]
        rows = rows + ex["results"]
        meta = dict(meta, modes=meta["modes"] + ex["metadata"]["modes"])
        data = dict(data, skipped=data.get("skipped", []) + ex.get("skipped", []))
        extra_spend = ex["metadata"]["spend_this_run_usd"]
    complete = [r for r in rows if not r["cap_tripped"] and not r["error"]]
    incomplete = [r for r in rows if r["cap_tripped"] or r["error"]]
    modes = meta["modes"]
    # Only tasks where every mode x repeat completed enter the paired comparisons (listed if not).
    counts = {}
    for r in complete:
        counts.setdefault(r["task_id"], set()).add((r["mode"], r["repeat"]))
    need = {(m, k) for m in modes for k in range(meta["repeats"])}
    tasks = sorted(t for t, have in counts.items() if have >= need)
    excluded = sorted(set(meta["tasks"]) - set(tasks))
    use = [r for r in complete if r["task_id"] in tasks]
    lines = ["# REAL Meta Model API run v3 — 2026-10-30", "",
             f"Model `muse-spark-1.3-contributor` on https://api.meta.ai/v1 (**Contributor tier: Meta may use the "
             f"request content for training; the user consented**). {len(tasks)} tasks x {len(modes)} modes x "
             f"{meta['repeats']} repeats = {len(use)} complete runs; spend ${meta['spend_this_run_usd']:.4f} (main) + "
             f"${extra_spend:.4f} (v3b layout-only modes, a second invocation run right after the main one). "
             "Usage and dollars come from the API `usage` fields priced with `tokentrim/prices.toml`.", ""]
    if excluded or incomplete or data.get("skipped"):
        lines += [f"**Not like-for-like / excluded:** tasks excluded from paired stats: {excluded or 'none'}; "
                  f"incomplete runs: {[(r['task_id'], r['mode'], r['repeat'], r['cap_tripped'] or r['error']) for r in incomplete] or 'none'}; "
                  f"skipped (cap): {len(data.get('skipped', []))}.", ""]
    calls = [c for r in use for c in r["per_call"]]
    lines += ["## Per mode", "",
              "| Mode | Client input | Runs | Pass (run-level) [Wilson 95%] | Pass (task-level, n=tasks) [Wilson 95%] | "
              "Mean $/run | Mean prompt tok/run | Cached share of prompt | Calls with any cache hit | Mean $/run if no cache hits |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    describe = {"baseline": "well-behaved (sorted tools, no volatile text)",
                "baseline-ts": "volatile timestamp + request id on system line 2",
                "baseline-tools": "set-ordered tools + dict-order nondeterminism (re-drawn when tool set changes)",
                "tokentrim": "naive (timestamp + set-ordered tools) -> TokenTrim v3 defaults",
                "layout-move": "naive -> cache_layout only; volatile lines moved to a trailing message (v3b)",
                "layout-drop": "naive -> cache_layout only; volatile lines dropped (v3b)"}
    summary = {"modes": {}, "comparisons": {}, "tasks": tasks, "excluded_tasks": excluded}
    for m in modes:
        mr = [r for r in use if r["mode"] == m]
        passes = sum(r["passed"] for r in mr)
        tp = per_task(use, m, "passed")
        task_level = sum(tp.values())
        w_run, w_task = wilson(passes, len(mr)), wilson(task_level, len(tp))
        mc = [c for r in mr for c in r["per_call"]]
        prompt = sum(c["prompt_tokens"] for c in mc)
        cached = sum(c["cached_tokens"] for c in mc)
        hits = sum(c["cached_tokens"] > 0 for c in mc)
        usd = fmean(r["usd"] for r in mr)
        nc = fmean(nocache_usd(r, cm) for r in mr)
        summary["modes"][m] = {"runs": len(mr), "passes": passes, "pass_rate": passes / len(mr), "wilson_run": w_run,
                               "task_level_pass": task_level / len(tp), "wilson_task": w_task, "mean_usd": usd,
                               "mean_prompt_tokens": prompt / len(mr), "cached_share": cached / prompt,
                               "calls_with_hit": hits / len(mc), "mean_usd_nocache": nc}
        lines.append(f"| {m} | {describe.get(m, '')} | {len(mr)} | {100 * passes / len(mr):.1f}% "
                     f"[{100 * w_run[0]:.1f}, {100 * w_run[1]:.1f}] | {100 * task_level / len(tp):.1f}% "
                     f"[{100 * w_task[0]:.1f}, {100 * w_task[1]:.1f}] | {usd:.5f} | {prompt / len(mr):,.0f} | "
                     f"{100 * cached / prompt:.1f}% | {100 * hits / len(mc):.0f}% | {nc:.5f} |")
    lines += ["", "## Paired comparisons (repeats averaged per task, paired bootstrap over tasks, 2,000 resamples, seed 42)", "",
              "Saving = (reference - new) / reference, so positive means `new` is cheaper. Pass diff = new - reference.", "",
              "| New vs reference | Billed $ saving [95% CI] | Prompt-token saving [95% CI] | $ saving if no cache hits [95% CI] | "
              "Pass diff pp, bootstrap [95% CI] | Pass diff pp, Newcombe task-level [95% CI] | Non-inferior at -10 pp? |",
              "|---|---:|---:|---:|---:|---:|:-:|"]
    for new, ref in COMPARISONS:
        if new not in modes or ref not in modes:
            continue
        res = {}
        for label, field in (("usd", "usd"), ("prompt", "prompt_tokens"), ("nocache", "nocache"), ("pass", "passed")):
            a, b = per_task(use, ref, field, cm), per_task(use, new, field, cm)
            res[label] = paired_comparison([a[t] for t in tasks], [b[t] for t in tasks])
        pa, pb = per_task(use, ref, "passed"), per_task(use, new, "passed")
        nd = newcombe_difference(sum(pa.values()), len(tasks), sum(pb.values()), len(tasks))
        boot = res["pass"]["difference"]["ci95"]
        noninf = boot[0] * 100 > -10 and nd[0] * 100 > -10
        summary["comparisons"][f"{new} vs {ref}"] = {
            "usd_saving_pct": res["usd"]["percent_saving"], "prompt_saving_pct": res["prompt"]["percent_saving"],
            "nocache_saving_pct": res["nocache"]["percent_saving"], "pass_diff": res["pass"]["difference"],
            "pass_diff_newcombe": nd, "noninferior_minus10pp": noninf}
        s = res["usd"]["percent_saving"]
        lines.append(f"| {new} vs {ref} | {pct(s['mean'])} {ci(s['ci95'])} | {pct(res['prompt']['percent_saving']['mean'])} "
                     f"{ci(res['prompt']['percent_saving']['ci95'])} | {pct(res['nocache']['percent_saving']['mean'])} "
                     f"{ci(res['nocache']['percent_saving']['ci95'])} | {100 * res['pass']['difference']['mean']:+.1f} "
                     f"{ci(boot, 100)} | {100 * (sum(pb.values()) - sum(pa.values())) / len(tasks):+.1f} {ci(nd, 100)} | "
                     f"{'yes' if noninf else 'no (interval too wide or below margin)'} |")
    # Pass-rate guard for eager prune.
    flags = []
    for ref in ("baseline", "baseline-ts", "baseline-tools"):
        a, b = per_task(use, ref, "passed"), per_task(use, "tokentrim", "passed")
        flags += [f"{t}: tokentrim passed {b[t] * meta['repeats']:.0f}/{meta['repeats']} vs {ref} {a[t] * meta['repeats']:.0f}/{meta['repeats']}"
                  for t in tasks if b.get(t, 1) < a.get(t, 0)]
    summary["pass_rate_guard_flags"] = flags
    lines += ["", "## Pass-rate guard (eager prune is the default; any task where tokentrim passed fewer repeats than a baseline is flagged)", ""]
    lines += [f"- FLAG {f}" for f in flags] or ["- No task where tokentrim passed fewer repeats than any baseline."]
    lines += ["", "## Per task (passes out of repeats; mean billed $ per run)", "",
              "| Task | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for t in tasks:
        cells = []
        for m in modes:
            mr = [r for r in use if r["task_id"] == t and r["mode"] == m]
            cells.append(f"{sum(r['passed'] for r in mr)}/{len(mr)} ${fmean(r['usd'] for r in mr):.5f}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    reasoning = sum(c["reasoning_tokens"] or 0 for c in calls)
    completion = sum(c["completion_tokens"] for c in calls)
    lines += ["", f"Calls: {len(calls)}; reasoning tokens {reasoning:,} of {completion:,} completion tokens; "
              f"calls ending `length`: {sum(c['finish_reason'] == 'length' for c in calls)}; retries: {sum(c['retries'] or 0 for c in calls)}.",
              "", "What these numbers do NOT measure: the split of TokenTrim's saving between cache_layout and eager prune "
              "in the main run; the v3b layout-only modes were run separately and no prune-only mode was run, so "
              "`tokentrim vs layout-move` is an approximate prune+trim effect); other models; real agents (the agent is scripted).", ""]
    pilot_path = out / args.pilot
    if pilot_path.exists():
        pdata = json.loads(pilot_path.read_text())
        prow = pdata["results"]
        lines += ["## Route pilot (3 tasks, 1 pass): Wonder only vs Spark-first with sticky escalation to Wonder", "",
                  "`pilot-wonder`: `muse-wonder-1.0` for every call, no savers. `pilot-sparkfirst`: all savers, "
                  "`CheapFirstRouter` on Standard `muse-spark-1.3` (not Contributor), sticky escalation to Wonder on "
                  "visible test failure / malformed output / no progress.", "",
                  "| Task | Wonder $ | Wonder pass | Spark-first $ | Spark-first pass | Spark-first escalated? | Models used (Spark-first) |",
                  "|---|---:|:-:|---:|:-:|:-:|---|"]
        by = {(r["task_id"], r["mode"]): r for r in prow}
        tw = ts = 0.0
        for t in pdata["metadata"]["tasks"]:
            w, s = by.get((t, "pilot-wonder")), by.get((t, "pilot-sparkfirst"))
            if not w or not s:
                lines.append(f"| {t} | missing run | | | | | |")
                continue
            tw += w["usd"]
            ts += s["usd"]
            models = sorted({c["model"].split("/")[-1] for c in s["per_call"]})
            mark = lambda r: "cap" if r["cap_tripped"] else ("err" if r["error"] else ("✓" if r["passed"] else "✗"))
            lines.append(f"| {t} | {w['usd']:.4f} | {mark(w)} | {s['usd']:.4f} | {mark(s)} | "
                         f"{'yes' if any(c.get('escalated') for c in s['per_call']) else 'no'} | {', '.join(models)} |")
        lines += [f"| **total** | **{tw:.4f}** | {sum(r['passed'] for r in prow if r['mode'] == 'pilot-wonder')}/3 | "
                  f"**{ts:.4f}** | {sum(r['passed'] for r in prow if r['mode'] == 'pilot-sparkfirst')}/3 | | |", "",
                  f"Pilot spend ${pdata['metadata']['spend_this_run_usd']:.4f} (sub-cap $3). Three tasks, one pass: "
                  "a direction check, not an estimate.", ""]
        summary["route_pilot"] = {"wonder_usd": tw, "sparkfirst_usd": ts,
                                  "rows": [{k: r[k] for k in ("task_id", "mode", "passed", "usd", "cap_tripped", "error")} for r in prow]}
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
