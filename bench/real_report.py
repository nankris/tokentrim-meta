"""Summarize REAL Meta benchmark JSON files into results/real_meta_<date>/summary.md."""
import argparse
import json
from pathlib import Path

from tokentrim.cost import CostModel


def load(out):
    rows = []
    for path in sorted(Path(out).glob("bench_*.json")):
        data = json.loads(path.read_text())
        for r in data["results"]:
            r["file"] = path.name
            rows.append(r)
    return rows


def uncached_usd(r, cm):
    """What the same billed tokens would cost with zero cache hits (removes cache-hit lottery noise)."""
    return sum(cm.cost(c["model"], {"input": c["prompt_tokens"], "cached_input": 0, "output": c["completion_tokens"],
                                    "cache_write": 0})[0] for c in r["per_call"])


def mark(r):
    return "cap" if r.get("cap_tripped") else ("✓" if r["passed"] else "✗")


def pair_table(rows, ref, other, cm):
    by = {(r["task_id"], r["mode"]): r for r in rows}
    tasks = [t for t in dict.fromkeys(r["task_id"] for r in rows) if (t, ref) in by and (t, other) in by]
    if not tasks:
        return [], None
    lines = [f"### {other} vs {ref}", "",
             "| Task | prompt tok (ref → new) | Δ prompt | cached tok (ref → new) | completion tok (ref → new) | "
             "$ billed (ref → new) | Δ $ billed | $ if no cache hits (ref → new) | pass (ref/new) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|:-:|"]
    agg = {k: [0, 0] for k in ("prompt_tokens", "cached_tokens", "completion_tokens", "usd", "nocache")}
    for t in tasks:
        a, b = by[(t, ref)], by[(t, other)]
        na, nb = uncached_usd(a, cm), uncached_usd(b, cm)
        for k in ("prompt_tokens", "cached_tokens", "completion_tokens", "usd"):
            agg[k][0] += a[k]
            agg[k][1] += b[k]
        agg["nocache"][0] += na
        agg["nocache"][1] += nb
        dp = 100 * (b["prompt_tokens"] - a["prompt_tokens"]) / a["prompt_tokens"]
        dd = 100 * (b["usd"] - a["usd"]) / a["usd"]
        lines.append(f"| {t} | {a['prompt_tokens']:,} → {b['prompt_tokens']:,} | {dp:+.1f}% | "
                     f"{a['cached_tokens']:,} → {b['cached_tokens']:,} | {a['completion_tokens']:,} → {b['completion_tokens']:,} | "
                     f"{a['usd']:.5f} → {b['usd']:.5f} | {dd:+.1f}% | {na:.5f} → {nb:.5f} | "
                     f"{mark(a)}/{mark(b)} |")
    pct = lambda k: 100 * (agg[k][1] - agg[k][0]) / agg[k][0] if agg[k][0] else 0
    lines.append(f"| **total ({len(tasks)})** | {agg['prompt_tokens'][0]:,} → {agg['prompt_tokens'][1]:,} | "
                 f"**{pct('prompt_tokens'):+.1f}%** | {agg['cached_tokens'][0]:,} → {agg['cached_tokens'][1]:,} | "
                 f"{agg['completion_tokens'][0]:,} → {agg['completion_tokens'][1]:,} | "
                 f"{agg['usd'][0]:.5f} → {agg['usd'][1]:.5f} | **{pct('usd'):+.1f}%** | "
                 f"{agg['nocache'][0]:.5f} → {agg['nocache'][1]:.5f} ({pct('nocache'):+.1f}%) | "
                 f"{sum(by[(t, ref)]['passed'] for t in tasks)}/{sum(by[(t, other)]['passed'] for t in tasks)} |")
    if any(by[(t, m)].get("cap_tripped") for t in tasks for m in (ref, other)):
        lines.append("")
        lines.append("`cap` = the SpendGuard per-task cap ($0.10) stopped that run before its edit step, so its "
                     "totals are partial and this comparison is NOT like-for-like.")
    return lines + [""], {"tasks": len(tasks), **{k: v for k, v in agg.items()},
                          "prompt_pct": pct("prompt_tokens"), "usd_pct": pct("usd"), "nocache_pct": pct("nocache")}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/real_meta_2026-10-30")
    args = p.parse_args()
    cm = CostModel()
    rows = load(args.out)
    out = Path(args.out)
    calls = [c for r in rows for c in r["per_call"]]
    hits = [c for c in calls if c["cached_tokens"]]
    lines = ["# REAL Meta Model API run — 2026-10-30", "",
             "Measured on https://api.meta.ai/v1 (`muse-spark-1.3-contributor`, plus a small `muse-spark-1.3` "
             "routing check). Usage and dollars come from the API's `usage` fields priced with `tokentrim/prices.toml`. "
             "One pass per task/mode: these are small-sample observations, not statistically significant results.", "",
             f"- Benchmark calls: {len(calls)}; calls with any cached tokens: {len(hits)} "
             f"({100 * len(hits) / max(1, len(calls)):.0f}%); cached share of all prompt tokens: "
             f"{100 * sum(c['cached_tokens'] for c in calls) / max(1, sum(c['prompt_tokens'] for c in calls)):.1f}%.",
             f"- Reasoning tokens: {sum(c['reasoning_tokens'] or 0 for c in calls):,} of "
             f"{sum(c['completion_tokens'] for c in calls):,} completion tokens; calls ending `length`: "
             f"{sum(c['finish_reason'] == 'length' for c in calls)}.",
             f"- Benchmark spend (sum of runs): ${sum(r['usd'] for r in rows):.4f}.", ""]
    summary = {}
    for ref, other in (("baseline", "tokentrim"), ("baseline", "tokentrim-eager"),
                       ("baseline-naive", "tokentrim-naive"), ("baseline", "baseline-naive"),
                       ("baseline-standard", "tokentrim-route-standard")):
        table, agg = pair_table(rows, ref, other, cm)
        lines += table
        if agg:
            summary[f"{other}_vs_{ref}"] = agg
    lines += ["## Per-call cache observations", "",
              "| Task | Mode | per-call cached/prompt tokens |", "|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['task_id']} | {r['mode']} | " +
                     ", ".join(f"{c['cached_tokens']}/{c['prompt_tokens']}" for c in r["per_call"]) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
