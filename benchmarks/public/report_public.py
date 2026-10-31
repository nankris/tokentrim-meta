"""Pre-registered analysis of the public slices (benchmarks/PREREGISTRATION_public_slices.md).
Errors count as failures; pairs need both arms present. Usage:
python3 -m benchmarks.public.report_public results/public_slices_2026-10-31/{bfcl|logchunks}"""
import collections
import json
import sys
from pathlib import Path
from statistics import fmean

from bench.stats import noninferiority_paired, paired_comparison, wilson


def analyze(d, margin=0.05):
    d = Path(d)
    rows = [json.loads(l) for l in (d / "rows.jsonl").open()]
    meta = json.loads((d / "meta.json").read_text())
    for r in rows:
        if r["error"]:
            r["passed"] = False
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["task_id"]][r["arm"]] = r
    out = {"workload": meta["workload"], "run_id": meta["run_id"], "model": meta["model"],
           "spend_this_run_usd": meta["spend_this_run_usd"], "ledger_total_usd": meta["ledger_total_usd"],
           "stopped_by_cap": meta["stopped_by_cap"], "rows": len(rows), "items": meta["items"],
           "errors": sum(bool(r["error"]) for r in rows), "margin": margin, "arms": {},
           "label": "TokenTrim system evaluation on a small public slice; not a leaderboard result"}
    for a in meta["arms"]:
        tasks = sorted(t for t, x in by.items() if a in x and "baseline" in x)
        R, B = [by[t][a] for t in tasks], [by[t]["baseline"] for t in tasks]
        if not R:
            continue
        k = sum(r["passed"] for r in R)
        s = {"n": len(R), "passed": k, "pass_rate": k / len(R), "pass_ci95": wilson(k, len(R)),
             "prompt_tokens_mean": fmean(r["prompt_tokens"] for r in R),
             "output_tokens_mean": fmean(r["output_tokens"] for r in R),
             "usd_mean": fmean(r["usd"] for r in R), "usd_total": sum(r["usd"] for r in R),
             "calls_mean": fmean(r["calls"] for r in R), "errors": sum(bool(r["error"]) for r in R),
             "error_types": dict(collections.Counter(r.get("error_type") for r in R if not r["passed"]).most_common())
             if out["workload"] == "bfcl" else None}
        if out["workload"] == "bfcl":
            s.update(search_tools=sum(r.get("search_tools", 0) for r in R),
                     items_with_search=sum(bool(r.get("search_tools")) for r in R),
                     internal_leak=sum(r.get("internal_leak", 0) for r in R),
                     routed=sum(bool(r.get("routed")) for r in R),
                     gated=sum(bool(r.get("gated")) for r in R))
        else:
            s.update(compressed=sum(bool(r.get("compressed")) for r in R),
                     retrieve_original=sum(r.get("retrieve_original", 0) for r in R),
                     retrieve_grep=sum(r.get("retrieve_grep", 0) for r in R),
                     recall_mean=fmean(r.get("recall", 0) or 0 for r in R),
                     no_answer=sum(not (r.get("answer_tail") or "").strip() for r in R))
        if a != "baseline":
            s["vs_baseline_pass"] = noninferiority_paired([b["passed"] for b in B], [r["passed"] for r in R], margin)
            s["vs_baseline_prompt_tokens"] = paired_comparison([b["prompt_tokens"] for b in B],
                                                               [r["prompt_tokens"] for r in R], seed=1)["percent_saving"]
            s["vs_baseline_usd"] = paired_comparison([b["usd"] for b in B], [r["usd"] for r in R], seed=1)["percent_saving"]
        out["arms"][a] = s
    return out


def table(s):
    lines = [f"### {s['workload']} ({s['label']})", "",
             f"run `{s['run_id']}`, model `{s['model']}`, {s['items']} items, {s['rows']} rows, errors {s['errors']}, "
             f"spend ${s['spend_this_run_usd']:.4f}, stopped_by_cap={s['stopped_by_cap']}", "",
             "| arm | n | pass (Wilson 95%) | diff vs baseline (paired Newcombe 95%) | NI at -5 pp | prompt tok/item | "
             "prompt-token saving (95% CI) | $/item | $ saving (95% CI) |", "|---|---|---|---|---|---|---|---|---|"]
    for a, x in s["arms"].items():
        v = x.get("vs_baseline_pass")
        pc, uc = x.get("vs_baseline_prompt_tokens"), x.get("vs_baseline_usd")
        f = lambda p: f"{p['mean']:.1f}% [{p['ci95'][0]:.1f}, {p['ci95'][1]:.1f}]" if p and p["ci95"] else "n/a"
        lines.append(f"| {a} | {x['n']} | {x['passed']}/{x['n']} = {100*x['pass_rate']:.0f}% "
                     f"[{100*x['pass_ci95'][0]:.0f}, {100*x['pass_ci95'][1]:.0f}] | "
                     + (f"{100*v['diff']:+.1f} pp [{100*v['ci95'][0]:+.1f}, {100*v['ci95'][1]:+.1f}] "
                        f"(b_only {v['base_only']}, a_only {v['other_only']})" if v else "-") + " | "
                     + ("yes" if v and v["non_inferior"] else ("no" if v else "-")) +
                     f" | {x['prompt_tokens_mean']:,.0f} | {f(pc) if v else '-'} | {x['usd_mean']:.5f} | {f(uc) if v else '-'} |")
    return "\n".join(lines)


if __name__ == "__main__":
    s = analyze(sys.argv[1])
    Path(sys.argv[1], "summary.json").write_text(json.dumps(s, indent=1) + "\n")
    Path(sys.argv[1], "summary.md").write_text(table(s) + "\n")
    print(table(s))
    print(json.dumps({a: {k: v for k, v in x.items() if k not in ("vs_baseline_pass", "vs_baseline_prompt_tokens",
                                                                  "vs_baseline_usd")} for a, x in s["arms"].items()}, indent=1))
