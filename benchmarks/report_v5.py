"""v5 report: pools rows of several run directories of one workload, pairs every arm with Baseline on the tasks
both completed without harness error, and applies the pre-registered analysis (benchmarks/PREREGISTRATION_v5.md):
paired Newcombe 95% CI of the success difference (non-inferiority margin 5 pp for Full), paired bootstrap of cost.
Nothing is projected; every number comes from recorded usage."""
import collections
import json
import sys
from pathlib import Path
from statistics import fmean, median

from bench.stats import cost_per_pass, noninferiority_paired, paired_comparison

TOK = ("prompt_tokens", "uncached_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")


def load(dirs):
    rows, metas = [], []
    for d in dirs:
        rows += [json.loads(l) for l in (Path(d) / "rows.jsonl").read_text().splitlines() if l.strip()]
        m = Path(d) / "meta.json"
        metas.append(json.loads(m.read_text()) if m.exists() else {"dir": str(d)})
    return rows, metas


def analyze(dirs, margin=0.05):
    rows, metas = load(dirs)
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["task_id"]][r["arm"]] = r
    arms = sorted({r["arm"] for r in rows}, key=lambda a: (a != "baseline", a))
    out = {"workload": rows[0]["workload"] if rows else None, "runs": [m.get("run_id") for m in metas],
           "spend_usd": sum(m.get("spend_this_run_usd") or 0 for m in metas),
           "stopped_by_cap": any(m.get("stopped_by_cap") for m in metas),
           "harness_errors": sum(bool(r["error"]) for r in rows), "arms": {}}
    for a in arms:
        tasks = sorted(t for t, x in by.items() if a in x and "baseline" in x and not x[a]["error"] and not x["baseline"]["error"])
        R = [by[t][a] for t in tasks]
        B = [by[t]["baseline"] for t in tasks]
        if not R:
            continue
        calls = sum(r["calls"] for r in R)
        s = {"n": len(R), "passed": sum(r["passed"] for r in R), "pass_rate": fmean(float(r["passed"]) for r in R),
             "mean_score": fmean(r["score"] for r in R), "usd_mean": fmean(r["usd"] for r in R),
             "usd_total": sum(r["usd"] for r in R),
             "cost_per_success": cost_per_pass([r["usd"] for r in R], [r["passed"] for r in R]),
             "tokens_mean": {k: fmean(r[k] for r in R) for k in TOK},
             "usd_by_category": {k: sum(r[k] for r in R) for k in ("usd_uncached", "usd_cached", "usd_output")},
             "calls_total": calls, "truncated_calls": sum(r["truncated_calls"] for r in R),
             "cache_hit_call_rate": sum(r["calls_with_cache_hit"] for r in R) / calls if calls else None,
             "cached_share_of_prompt": sum(r["cached_tokens"] for r in R) / max(1, sum(r["prompt_tokens"] for r in R)),
             "latency_s_median_per_task": median(r["latency_s"] for r in R),
             "search_tools": sum(r.get("search_tools", 0) for r in R), "retrieve_grep": sum(r.get("retrieve_grep", 0) for r in R),
             "retrieve_original": sum(r.get("retrieve_original", 0) for r in R),
             "failed_checks": dict(collections.Counter(k for r in R for k, v in (r.get("fields") or {}).items() if not v).most_common()),
             "failed_tasks": [r["task_id"] for r in R if not r["passed"]]}
        if a != "baseline":
            s["vs_baseline_usd"] = paired_comparison([b["usd"] for b in B], [r["usd"] for r in R])
            s["vs_baseline_pass"] = noninferiority_paired([b["passed"] for b in B], [r["passed"] for r in R], margin)
            s["baseline_on_same_tasks"] = {"passed": sum(b["passed"] for b in B), "usd_mean": fmean(b["usd"] for b in B)}
        out["arms"][a] = s
    return out


def table(s):
    lines = [f"## {s['workload']}: TokenTrim system evaluation (synthetic tasks, REAL calls)", "",
             "| arm | n | pass | $/task | saving vs baseline [95% CI] | success diff vs baseline [95% CI] | NI (-5 pp) | $/success |",
             "|---|---|---|---|---|---|---|---|"]
    for a, x in s["arms"].items():
        v, p = x.get("vs_baseline_usd"), x.get("vs_baseline_pass")
        sav = f"{v['percent_saving']['mean']:+.1f}% [{v['percent_saving']['ci95'][0]:+.1f}, {v['percent_saving']['ci95'][1]:+.1f}]" if v else "-"
        pd = f"{100 * p['diff']:+.1f} pp [{100 * p['ci95'][0]:+.1f}, {100 * p['ci95'][1]:+.1f}]" if p else "-"
        ni = ("yes" if p["non_inferior"] else "not shown") if p else "-"
        cps = x["cost_per_success"]["mean"]
        lines.append(f"| {a} | {x['n']} | {x['passed']}/{x['n']} | ${x['usd_mean']:.5f} | {sav} | {pd} | {ni} | "
                     f"{'$%.5f' % cps if cps else '-'} |")
    return "\n".join(lines)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    s = analyze(sys.argv[2:])
    out.write_text(json.dumps(s, indent=1) + "\n")
    print(table(s))
