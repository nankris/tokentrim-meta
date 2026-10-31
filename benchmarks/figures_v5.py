"""v5 figures, built only from recorded v5 summaries (benchmarks/report_v5.py output). No projections."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path(sys.argv[1] if len(sys.argv) > 1 else "results/v5_2026-10-31")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/workspace/tokentrim-work/blog-assets")
OUT.mkdir(parents=True, exist_ok=True)
NOTE = "TokenTrim system evaluation: REAL calls to muse-spark-1.3-contributor, synthetic graded tasks, 2026-10-31"
C = {"baseline": "#8a8f98", "skill": "#6aa9ff", "tool_output": "#f5a623", "schema_router": "#b48cff",
     "full_no_router": "#4cd1a5", "full": "#1f6feb", "full_no_history": "#4cd1a5"}


def save(fig, name):
    fig.text(0.01, -0.02, NOTE, fontsize=7, color="#555")
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUT / name)


def forest(s, name, title):
    arms = [a for a in s["arms"] if a != "baseline"]
    fig, ax = plt.subplots(figsize=(7.5, 0.6 * len(arms) + 1.6))
    for i, a in enumerate(arms):
        p = s["arms"][a]["vs_baseline_pass"]
        lo, hi, d = 100 * p["ci95"][0], 100 * p["ci95"][1], 100 * p["diff"]
        ax.plot([lo, hi], [i, i], color=C.get(a, "k"), lw=3)
        ax.plot([d], [i], "o", color=C.get(a, "k"))
        ax.text(hi + 0.8, i, f"{s['arms'][a]['passed']}/{p['n']} vs {s['arms'][a]['baseline_on_same_tasks']['passed']}/{p['n']}"
                f"  [{lo:+.1f}, {hi:+.1f}]", va="center", fontsize=8)
    ax.axvline(-5, color="#d1242f", ls="--", lw=1)
    ax.text(-5, -0.45, " -5 pp margin", color="#d1242f", fontsize=8)
    ax.axvline(0, color="#999", lw=0.8)
    ax.set_yticks(range(len(arms)), arms)
    ax.set_xlabel("task success, arm minus baseline (pp), paired Newcombe 95% CI")
    ax.set_xlim(-30, 40)
    ax.set_title(title, fontsize=10)
    save(fig, name)


def cost(s, name, title):
    arms = list(s["arms"])
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    cats = [("usd_uncached", "uncached input", "#d29922"), ("usd_cached", "cached input", "#4cd1a5"), ("usd_output", "output", "#6aa9ff")]
    bottom = [0.0] * len(arms)
    for k, lab, col in cats:
        v = [1000 * s["arms"][a]["usd_by_category"][k] / s["arms"][a]["n"] for a in arms]
        ax.bar(arms, v, bottom=bottom, color=col, label=lab)
        bottom = [b + x for b, x in zip(bottom, v)]
    for i, a in enumerate(arms):
        v = s["arms"][a].get("vs_baseline_usd")
        lab = f"{v['percent_saving']['mean']:+.0f}%\n[{v['percent_saving']['ci95'][0]:+.0f}, {v['percent_saving']['ci95'][1]:+.0f}]" if v else "ref"
        ax.text(i, bottom[i], lab, ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("$ per task x 1000 (billed categories)")
    ax.set_ylim(0, max(bottom) * 1.35)
    ax.legend(fontsize=7, loc="upper left")
    ax.set_title(title + "  (labels: saving vs baseline, 95% CI)", fontsize=10)
    plt.xticks(fontsize=8, rotation=15)
    save(fig, name)


if __name__ == "__main__":
    for f, w in (("summary_agentic_hard_primary.json", "agentic_hard_primary"), ("summary_agentic_hard_ablation.json", "agentic_hard_ablation"),
                 ("summary_longchat.json", "longchat")):
        p = R / f
        if not p.exists():
            continue
        s = json.loads(p.read_text())
        forest(s, f"v5_success_{w}.png", f"v5 {w}: success difference vs baseline (n={s['arms']['baseline']['n']})")
        cost(s, f"v5_cost_{w}.png", f"v5 {w}: billed $ per task")
