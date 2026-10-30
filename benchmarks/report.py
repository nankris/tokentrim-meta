"""Summarize a v4 benchmark run: per-arm cost/quality/token categories + paired bootstrap CIs vs baseline.

Only tasks for which EVERY arm has a row (no harness error) are paired. Nothing here is projected: every
number is computed from the recorded per-call usage of the run."""
import json
import sys
from pathlib import Path
from statistics import fmean, median

from bench.stats import bootstrap_mean, cost_per_pass, paired_comparison, percentile


def load(d):
    rows = [json.loads(l) for l in (Path(d) / "rows.jsonl").read_text().splitlines() if l.strip()]
    meta = json.loads((Path(d) / "meta.json").read_text()) if (Path(d) / "meta.json").exists() else {}
    return rows, meta


def paired_score(base, other, seed=42, samples=2000):
    return bootstrap_mean([o - b for b, o in zip(base, other)], seed=seed, samples=samples)


def summarize(d):
    rows, meta = load(d)
    arms = meta.get("arms") or sorted({r["arm"] for r in rows})
    by = {}
    for r in rows:
        by.setdefault(r["task_id"], {})[r["arm"]] = r
    complete = sorted(t for t, a in by.items() if all(x in a and not a[x]["error"] for x in arms))
    out = {"run_id": meta.get("run_id"), "workload": meta.get("workload"), "model": meta.get("model"),
           "tasks_paired": len(complete), "tasks_total": len(by), "harness_errors": sum(bool(r["error"]) for r in rows),
           "spend_this_run_usd": meta.get("spend_this_run_usd"), "ledger_total_usd": meta.get("ledger_total_usd"),
           "data_kind": meta.get("data_kind"), "arms": {}}
    base_usd = [by[t]["baseline"]["usd"] for t in complete]
    base_score = [by[t]["baseline"]["score"] for t in complete]
    base_pass = [float(by[t]["baseline"]["passed"]) for t in complete]
    no_trunc = [t for t in complete if all(by[t][a]["truncated_calls"] == 0 for a in arms)]
    for a in arms:
        R = [by[t][a] for t in complete]
        calls = sum(r["calls"] for r in R)
        s = {"n": len(R), "pass_rate": fmean(float(r["passed"]) for r in R), "mean_score": fmean(r["score"] for r in R),
             "usd_total": sum(r["usd"] for r in R), "usd_mean": fmean(r["usd"] for r in R),
             "cost_per_success": cost_per_pass([r["usd"] for r in R], [r["passed"] for r in R]),
             "tokens_mean": {k: fmean(r[k] for r in R) for k in ("prompt_tokens", "uncached_tokens", "cached_tokens",
                             "output_tokens", "reasoning_tokens")},
             "usd_by_category": {k: sum(r[k] for r in R) for k in ("usd_uncached", "usd_cached", "usd_output")},
             "calls_total": calls, "cache_hit_call_rate": sum(r["calls_with_cache_hit"] for r in R) / calls if calls else None,
             "cached_share_of_prompt": sum(r["cached_tokens"] for r in R) / max(1, sum(r["prompt_tokens"] for r in R)),
             "truncated_calls": sum(r["truncated_calls"] for r in R), "truncation_rate": sum(r["truncated_calls"] for r in R) / calls if calls else None,
             "latency_s_median_per_task": median(r["latency_s"] for r in R),
             "retrieve_original": sum(r.get("retrieve_original", 0) for r in R),
             "retrieve_grep": sum(r.get("retrieve_grep", 0) for r in R),
             "search_tools": sum(r.get("search_tools", 0) for r in R)}
        if a != "baseline":
            s["vs_baseline_usd"] = paired_comparison(base_usd, [r["usd"] for r in R])
            s["vs_baseline_score_diff"] = paired_score(base_score, [r["score"] for r in R])
            s["vs_baseline_pass_diff"] = paired_score(base_pass, [float(r["passed"]) for r in R])
            if no_trunc and len(no_trunc) < len(complete):
                s["vs_baseline_usd_non_truncated"] = paired_comparison([by[t]["baseline"]["usd"] for t in no_trunc],
                                                                       [by[t][a]["usd"] for t in no_trunc])
        out["arms"][a] = s
    return out


def table(summary):
    lines = [f"## {summary['workload']} ({summary['model']}, {summary['tasks_paired']} paired tasks, REAL Meta calls)",
             "", "| arm | pass | score | $/task | saving vs baseline (95% CI) | score diff (95% CI) | $/success | uncached | cached | output | trunc |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a, s in summary["arms"].items():
        v = s.get("vs_baseline_usd")
        sav = f"{v['percent_saving']['mean']:+.1f}% [{v['percent_saving']['ci95'][0]:+.1f}, {v['percent_saving']['ci95'][1]:+.1f}]" if v else "-"
        d = s.get("vs_baseline_score_diff")
        sd = f"{d['mean']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]" if d else "-"
        cps = s["cost_per_success"]["mean"]
        t = s["tokens_mean"]
        lines.append(f"| {a} | {s['pass_rate']:.0%} | {s['mean_score']:.3f} | ${s['usd_mean']:.5f} | {sav} | {sd} | "
                     f"{'$%.5f' % cps if cps else '-'} | {t['uncached_tokens']:,.0f} | {t['cached_tokens']:,.0f} | "
                     f"{t['output_tokens']:,.0f} | {s['truncated_calls']}/{s['calls_total']} |")
    return "\n".join(lines)


if __name__ == "__main__":
    for d in sys.argv[1:]:
        s = summarize(d)
        (Path(d) / "summary.json").write_text(json.dumps(s, indent=1) + "\n")
        print(table(s))
        print()
