"""v5.3 figures from the recorded confirmatory summary (report_v5 output). No projections."""
import json
import sys
from pathlib import Path

from benchmarks import figures_v5 as F

if __name__ == "__main__":
    src, outs = Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]
    s = json.loads(src.read_text())
    F.NOTE = ("TokenTrim system evaluation: REAL calls to muse-spark-1.3-contributor via the local proxy code path, "
              "fresh held-out synthetic tasks, 2026-10-31")
    F.C.update({"compression_only": "#f5a623", "guarded_full": "#1f6feb"})
    n = s["arms"]["baseline"]["n"]

    def save(fig, name):  # footer lower than v5 so it does not overlap the x label
        fig.supxlabel(F.NOTE, fontsize=7, color="#555", x=0.01, ha="left", y=-0.22)
        fig.savefig(F.OUT / name, dpi=160, bbox_inches="tight", facecolor="white")
        F.plt.close(fig)
        print(F.OUT / name)
    F.save = save
    for out in outs:
        out.mkdir(parents=True, exist_ok=True)
        F.OUT = out
        F.forest(s, "v53_success.png", f"v5.3 confirmatory (fresh tasks, n={n}): success vs baseline")
        F.cost(s, "v53_cost.png", f"v5.3 confirmatory (n={n}): billed $ per task")
