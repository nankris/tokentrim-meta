"""Blog/README figures built ONLY from recorded v4 results (summary.json files) + captured logs."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path("results/v4_2026-10-30")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/tokentrim-work/blog-assets")
OUT.mkdir(parents=True, exist_ok=True)
NOTE = "REAL calls to muse-spark-1.3-contributor (Meta API), synthetic graded tasks, 2026-10-30"
C = {"baseline": "#8a8f98", "skill": "#6aa9ff", "tool_output": "#f5a623", "schema_router": "#b48cff",
     "history": "#ff7a7a", "cache": "#4cd1a5", "full": "#1f6feb"}


def load(w):
    p = R / w / "summary.json"
    return json.loads(p.read_text()) if p.exists() else None


def savefig(fig, name):
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUT / name)


def ablation_table(sums):
    rows = [["workload", "arm", "n", "pass", "$ / task", "saving [95% CI]", "$ / success", "truncated"]]
    for s in sums:
        for a, v in s["arms"].items():
            sv = v.get("vs_baseline_usd")
            sav = "-" if not sv else f"{sv['percent_saving']['mean']:+.1f}% [{sv['percent_saving']['ci95'][0]:+.1f}, {sv['percent_saving']['ci95'][1]:+.1f}]"
            cps = v["cost_per_success"]["mean"]
            rows.append([s["workload"], a, str(v["n"]), f"{v['pass_rate']:.0%}", f"${v['usd_mean']:.5f}", sav,
                         f"${cps:.5f}" if cps else "-", f"{v['truncated_calls']}/{v['calls_total']}"])
    fig, ax = plt.subplots(figsize=(14, 0.42 * len(rows) + 0.8))
    ax.axis("off")
    t = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center",
                 colWidths=[0.1, 0.13, 0.05, 0.07, 0.1, 0.25, 0.11, 0.1])
    t.auto_set_font_size(False)
    t.set_fontsize(9.5)
    t.scale(1, 1.35)
    for (r, c), cell in t.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1f2328"); cell.set_text_props(color="white", weight="bold")
        elif rows[r][1] == "full":
            cell.set_facecolor("#e8f0fe")
    ax.set_title("TokenTrim v4 ablations: cost and quality per task (paired, same tasks per arm)\n" + NOTE, fontsize=10.5)
    savefig(fig, "ablation_table.png")


def attribution(s):
    arms = [a for a in s["arms"] if a != "baseline"]
    vals = [s["arms"][a]["vs_baseline_usd"]["percent_saving"] for a in arms]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    m = [v["mean"] for v in vals]
    err = [[v["mean"] - v["ci95"][0] for v in vals], [v["ci95"][1] - v["mean"] for v in vals]]
    ax.bar(arms, m, yerr=err, capsize=5, color=[C.get(a, "#999") for a in arms])
    for i, v in enumerate(m):
        ax.text(i, v + (3 if v >= 0 else -6), f"{v:+.1f}%", ha="center", fontsize=10)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("cost saving vs baseline (% of $/task)")
    ax.set_title(f"Savings attribution - {s['workload']} workload (n={s['tasks_paired']} paired tasks, 95% bootstrap CI)\n{NOTE}", fontsize=9.5)
    savefig(fig, f"savings_attribution_{s['workload']}.png")


def token_breakdown(s):
    arms = list(s["arms"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.3))
    unc = [s["arms"][a]["tokens_mean"]["uncached_tokens"] for a in arms]
    cac = [s["arms"][a]["tokens_mean"]["cached_tokens"] for a in arms]
    out = [s["arms"][a]["tokens_mean"]["output_tokens"] for a in arms]
    a1.bar(arms, unc, label="uncached input", color="#f5a623")
    a1.bar(arms, cac, bottom=unc, label="cached input", color="#4cd1a5")
    a1.bar(arms, out, bottom=[u + c for u, c in zip(unc, cac)], label="output (incl. reasoning)", color="#1f6feb")
    a1.set_ylabel("tokens per task (mean)"); a1.legend(fontsize=8); a1.set_title("Tokens by type", fontsize=10)
    n = s["tasks_paired"]
    usd = {k: [s["arms"][a]["usd_by_category"][k] / n * 1000 for a in arms] for k in ("usd_uncached", "usd_cached", "usd_output")}
    a2.bar(arms, usd["usd_uncached"], label="uncached input", color="#f5a623")
    a2.bar(arms, usd["usd_cached"], bottom=usd["usd_uncached"], label="cached input", color="#4cd1a5")
    a2.bar(arms, usd["usd_output"], bottom=[u + c for u, c in zip(usd["usd_uncached"], usd["usd_cached"])], label="output", color="#1f6feb")
    a2.set_ylabel("$ per 1,000 tasks (mean)"); a2.legend(fontsize=8); a2.set_title("Dollars by type", fontsize=10)
    for a in (a1, a2):
        a.tick_params(axis="x", rotation=20)
    fig.suptitle(f"Token-type breakdown - {s['workload']} (n={n} tasks per arm). {NOTE}", fontsize=9.5)
    savefig(fig, f"token_breakdown_{s['workload']}.png")


def cache_hits(sums):
    fig, ax = plt.subplots(figsize=(10, 4))
    labels, hit, share = [], [], []
    for s in sums:
        for a, v in s["arms"].items():
            labels.append(f"{s['workload']}\n{a}"); hit.append(100 * v["cache_hit_call_rate"]); share.append(100 * v["cached_share_of_prompt"])
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], hit, 0.4, label="calls with any cached tokens (%)", color="#4cd1a5")
    ax.bar([i + 0.2 for i in x], share, 0.4, label="cached share of prompt tokens (%)", color="#1f6feb")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=7.5); ax.legend(fontsize=8)
    ax.set_title("Provider cache hits per arm (Meta caching is intermittent; measured, not assumed)\n" + NOTE, fontsize=9.5)
    savefig(fig, "cache_hit_rate.png")


def truncation(sums):
    calls = sum(v["calls_total"] for s in sums for v in s["arms"].values())
    trunc = sum(v["truncated_calls"] for s in sums for v in s["arms"].values())
    fig, ax = plt.subplots(figsize=(6.5, 4))
    before, after = 100 * 114 / 255, 100 * trunc / calls
    ax.bar(["v2 benchmark\nmax_tokens 800-8000\n(114 / 255 calls)", f"v4 benchmarks\nmax_tokens 16000\n({trunc} / {calls:,} calls)"],
           [before, after], color=["#ff7a7a", "#1f6feb"])
    for i, v in enumerate([before, after]):
        ax.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=11)
    ax.set_ylabel("calls ending finish_reason=length (%)")
    ax.set_title("Truncation before/after the max_tokens fix\n(reasoning tokens count against max_tokens on Meta)", fontsize=10)
    savefig(fig, "truncation_before_after.png")


def terminal(path, name, title):
    import textwrap
    text = [w for line in Path(path).read_text().rstrip().splitlines()
            for w in (textwrap.wrap(line, 140, subsequent_indent="[tokentrim]     ") or [""])]
    fig, ax = plt.subplots(figsize=(13, 0.32 * len(text) + 0.9))
    fig.patch.set_facecolor("#0d1117"); ax.set_facecolor("#0d1117"); ax.axis("off")
    for i, line in enumerate(text):
        color = "#7ee787" if line.startswith("$") else ("#79c0ff" if "[tokentrim]   " in line else "#c9d1d9")
        ax.text(0.0, 1 - (i + 0.5) / len(text), line[:150], family="monospace", fontsize=9, color=color,
                transform=ax.transAxes, va="center")
    ax.set_title(title, color="#c9d1d9", fontsize=10, loc="left")
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print(OUT / name)


def compression_example():
    sys.path.insert(0, ".")
    from benchmarks import workloads as W
    from tokentrim.optimizers.tool_output import ToolOutputCompressor, task_terms
    from tokentrim.store import OriginalStore
    import tempfile
    t = W.agentic_task(1)
    raw = t["stubs"]["run_tests"]
    c = ToolOutputCompressor(OriginalStore(Path(tempfile.mkdtemp())), 400).compress(raw, task_terms([t["prompt"]]))
    rl = raw.splitlines()
    left = rl[:14] + [f"   ... ({len(rl) - 28:,} more lines) ..."] + rl[-14:]
    import textwrap
    right = [w for line in c.text.splitlines() for w in (textwrap.wrap(line, 95, subsequent_indent="  ") or [""])]
    fig, (a, b) = plt.subplots(1, 2, figsize=(16, 9))
    for ax, lines, title in ((a, left, f"BEFORE: raw pytest output, {c.tokens_before:,} tokens ({len(rl):,} lines)"),
                             (b, right, f"AFTER: TokenTrim view, {c.tokens_after:,} tokens (-{100 * (1 - c.tokens_after / c.tokens_before):.0f}%), original kept as {c.ref}")):
        ax.axis("off"); ax.set_facecolor("#0d1117")
        for i, line in enumerate(lines):
            ax.text(0, 1 - (i + 0.5) / max(len(lines), 30), line[:95], family="monospace", fontsize=7.2,
                    color="#ffa198" if line.startswith(("E ", "FAILED", ">")) else "#c9d1d9", transform=ax.transAxes, va="center")
        ax.set_title(title, color="#c9d1d9", fontsize=10, loc="left")
    fig.patch.set_facecolor("#0d1117")
    fig.suptitle("Reversible tool-output compression (deterministic; failures, assertions and summaries kept verbatim; "
                 "synthetic test log from the benchmark)", color="#c9d1d9", fontsize=10)
    fig.savefig(OUT / "tool_output_before_after.png", dpi=160, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print(OUT / "tool_output_before_after.png")


if __name__ == "__main__":
    sums = [s for s in (load(w) for w in ("agentic", "longchat", "chat")) if s]
    ablation_table(sums)
    for s in sums:
        attribution(s)
        token_breakdown(s)
    cache_hits(sums)
    truncation(sums)
    cap = Path("/workspace/tokentrim-work/capture_terminal.txt")
    if cap.exists():
        terminal(cap, "proxy_explanations_terminal.png",
                 "TokenTrim proxy (real Meta call): every optimization prints an explanation line")
    compression_example()
