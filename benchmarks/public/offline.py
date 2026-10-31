"""$0 offline analyses on the public data (no model calls).

1. LogChunks: what the SHIPPED compressor does to 797 real CI logs, and failure-chunk retention of the opt-in
   tail-weighted CI-log compressor (text_logs=True), on the DEV split (used to choose it) and the TEST split.
2. BFCL live_multiple: how often the v5.2 router gate would route on the natural catalogues.
Usage: python3 -m benchmarks.public.offline <outdir>
"""
import collections
import hashlib
import json
import statistics as S
import sys
from pathlib import Path

from tokentrim.optimizers.schema_router import SchemaRouter
from tokentrim.optimizers.tool_output import ToolOutputCompressor
from tokentrim.tokens import estimate_tokens
from . import bfcl as B
from . import logchunks as L

TASK = "Why did this CI build fail? Quote the log lines that explain the failure."


def split(ex) -> str:
    """Deterministic split by repository (no repo in both halves)."""
    return "dev" if int(hashlib.sha256(ex["repo"].encode()).hexdigest(), 16) % 2 == 0 else "test"


def logchunks():
    rows = []
    for ex in L.examples():
        log = L.read_log(ex)
        t = estimate_tokens(log)
        shipped = ToolOutputCompressor(json_mode="auto").compress(log, task_text=TASK)
        ci = ToolOutputCompressor(json_mode="auto", text_logs=True).compress(log, task_text=TASK)
        rows.append({"id": ex["id"], "repo": ex["repo"], "split": split(ex), "tokens": t, "kind": shipped.kind,
                     "shipped_compressed": shipped.ref is not None, "ci_compressed": ci.ref is not None,
                     "ci_ratio": ci.tokens_after / t, "raw_ok": L.recall(ex["chunk"], log) >= 0.5,
                     "ci_kept": L.recall(ex["chunk"], ci.text) >= 0.5})
    out = {"n_logs": len(rows), "tokens_median": S.median(r["tokens"] for r in rows),
           "shipped_kind_counts": dict(collections.Counter(r["kind"] for r in rows)),
           "shipped_compressed": sum(r["shipped_compressed"] for r in rows)}
    for sp in ("dev", "test"):
        sub = [r for r in rows if r["split"] == sp]
        ok = [r for r in sub if r["raw_ok"]]
        out[sp] = {"logs": len(sub), "repos": len({r["repo"] for r in sub}),
                   "chunk_gradable_in_raw_log": len(ok),
                   "ci_compressed": sum(r["ci_compressed"] for r in sub),
                   "ci_mean_size_ratio": round(S.mean(r["ci_ratio"] for r in sub), 3),
                   "ci_chunk_retained": sum(r["ci_kept"] for r in ok),
                   "ci_chunk_retained_rate": round(sum(r["ci_kept"] for r in ok) / len(ok), 3)}
    return out, rows


def bfcl_gate():
    items = B.load("live_multiple")
    reasons = collections.Counter()
    sizes = collections.Counter()
    for it in items:
        tools = B.to_tools(it["function"])
        msgs = [m for turn in it["question"] for m in turn]
        ok, why, _ = SchemaRouter(6).gate(tools, msgs)
        reasons["routes" if ok else why.split(":")[0].split(" (")[0]] += 1
        n = len(tools)
        sizes["<=4" if n <= 4 else "5-8" if n <= 8 else "9-16" if n <= 16 else ">16"] += 1
    return {"items": len(items), "tool_count_buckets": dict(sizes), "gate_decisions": dict(reasons)}


def main(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    lc, rows = logchunks()
    (out / "offline_logchunks.json").write_text(json.dumps(lc, indent=1) + "\n")
    (out / "offline_logchunks_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    g = bfcl_gate()
    (out / "offline_bfcl_gate.json").write_text(json.dumps(g, indent=1) + "\n")
    print(json.dumps({"logchunks": lc, "bfcl_gate": g}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
