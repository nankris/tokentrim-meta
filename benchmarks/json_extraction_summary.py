"""Summarise the v5.1 JSON extraction probe (cheap CLI model; costs are ESTIMATES at Meta list price)."""
import json
import random
import sys
from collections import defaultdict

from bench.stats import newcombe_paired

ARMS = ["raw", "legacy_table", "structured", "structured_lossy"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return c - h, c + h


def main(path, out):
    rows = [json.loads(l) for l in open(path)]
    by = defaultdict(dict)
    for r in rows:
        by[r["arm"]][r["doc"]] = r
    docs = sorted(set.intersection(*(set(by[a]) for a in ARMS)))
    rng = random.Random(0)
    lines = [f"# v5.1 JSON extraction probe: {path.split('_')[-1].replace('.jsonl', '')}", "",
             "This is a TokenTrim system evaluation on a cheap CLI model, not Meta. Costs are **estimates** at Meta "
             "list price, from chars/4 (input $0.10/M, output $0.20/M), and include the RETRIEVE recovery turns.",
             f"Documents: {len(docs)} (generated, seed 9000+i; odd i have nested `meta` with decoy releases).", "",
             "| View | Correct | 95% CI | Δ vs raw (pp, paired Newcombe) | Retrieves | Mean view tokens | "
             "Est. $ per correct answer [95% bootstrap] |",
             "|---|---|---|---|---|---|---|"]
    summary = {}
    for a in ARMS:
        rs = [by[a][d] for d in docs]
        k = sum(r["correct"] for r in rs)
        lo, hi = wilson(k, len(rs))
        usd = sum(r["est_usd"] for r in rs)
        boots = []
        for _ in range(2000):
            s = [rs[rng.randrange(len(rs))] for _ in rs]
            c = sum(r["correct"] for r in s)
            boots.append(sum(r["est_usd"] for r in s) / c if c else float("inf"))
        boots.sort()
        if a == "raw":
            delta = "-"
        else:
            r = newcombe_paired([by["raw"][x]["correct"] for x in docs], [by[a][x]["correct"] for x in docs])
            d, (l, h) = r["diff"], r["ci95"]
            delta = f"{100 * d:+.1f} [{100 * l:+.1f}, {100 * h:+.1f}]"
        nested = [r for r in rs if r["nested"]]
        flat = [r for r in rs if not r["nested"]]
        summary[a] = dict(correct=k, n=len(rs), nested_correct=sum(r["correct"] for r in nested),
                          n_nested=len(nested), flat_correct=sum(r["correct"] for r in flat), n_flat=len(flat),
                          retrieves=sum(r["retrieves"] for r in rs), usd_total_est=usd,
                          usd_per_correct_est=usd / k if k else None)
        lines.append(f"| {a} | {k}/{len(rs)} | [{100 * lo:.0f}%, {100 * hi:.0f}%] | {delta} | "
                     f"{summary[a]['retrieves']} | {sum(r['view_tokens'] for r in rs) / len(rs):.0f} | "
                     f"${usd / k * 1000:.3f} [{boots[50] * 1000:.3f}, {boots[1949] * 1000:.3f}] |"
                     if k else f"| {a} | 0/{len(rs)} | | {delta} | | | n/a |")
    lines += ["", "($ per correct answer is shown per 1,000 correct answers.)", "",
              "| View | Flat docs correct | Nested docs correct |", "|---|---|---|"]
    for a in ARMS:
        s = summary[a]
        lines.append(f"| {a} | {s['flat_correct']}/{s['n_flat']} | {s['nested_correct']}/{s['n_nested']} |")
    open(out, "w").write("\n".join(lines) + "\n")
    json.dump(summary, open(out.replace(".md", ".json"), "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:3])
