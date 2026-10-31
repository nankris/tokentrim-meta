"""Paired runner for the public-benchmark slices (pre-registered in benchmarks/PREREGISTRATION_public_slices.md).

Workloads
* ``bfcl``: BFCL v3 live_multiple items with an AUGMENTED catalogue (the item's own functions + distractor
  functions from other BFCL items, 40 tools in total). Single client turn, graded by the BFCL AST checker
  reimplementation (benchmarks/public/bfcl.py). search_tools rounds (router arms) are resolved inside the gateway.
* ``logchunks``: a REAL failed Travis CI build log (LogChunks) is the output of the client tool
  ``get_build_log``; the model must quote the lines that explain the failure. Graded by chunk-line recall >= 0.5.
Every call goes through tokentrim.Gateway (baseline = all modules off), spend is reserved in the shared ledger.
``--mock`` runs an oracle policy with zero spend (plumbing + grader validation).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.guard import SpendCapExceeded
from tokentrim.ledger import SpendLedger
from tokentrim.optimizers.schema_router import SchemaRouter
from tokentrim.upstream import ChatUpstream, MockChatUpstream
from benchmarks.run import MODEL, Totals
from . import bfcl as B
from . import logchunks as L
from .offline import split as lc_split

ARMS = {
    "bfcl": {
        "baseline": dict(cache_prefix=False),
        "compression_only": dict(cache_prefix=False, tool_output=True),  # shipped default preset
        "router_gated": dict(cache_prefix=False, schema_router=True, router_gating=True),  # guarded-full router
        "router_forced": dict(cache_prefix=False, schema_router=True, router_gating=False),  # router always on
    },
    "logchunks": {
        "baseline": dict(cache_prefix=False),
        "compression_only": dict(cache_prefix=False, tool_output=True),  # shipped default (text logs untouched)
        "ci_logs": dict(cache_prefix=False, tool_output=True, text_logs=True),  # v5.4 opt-in CI-log compressor
    },
}
N_TOOLS = 40
LC_SYSTEM = "You are a CI assistant that diagnoses failed builds."
LC_TOOL = {"type": "function", "function": {
    "name": "get_build_log", "description": "Return the full console log of a CI build.",
    "parameters": {"type": "object", "properties": {"build_id": {"type": "string"}}, "required": ["build_id"]}}}


# ---- slices (deterministic; pre-registered) ------------------------------------------------------------
def bfcl_slice(n=100, seed=20261031, offset=0):
    items = [it for it in B.load("live_multiple") if B.check(it, B.oracle_output(it))[0]]
    rng = random.Random(seed)
    order = list(range(len(items)))
    rng.shuffle(order)
    group = lambda it: it["id"].split("-")[1]
    out = []
    for k in order[offset:offset + n]:
        it = items[k]
        own = {B.oai_name(f["name"]) for f in it["function"]}
        r = random.Random(f"{seed}/{it['id']}")
        cand, seen = [], set(own)
        pool = [x for x in items if group(x) != group(it)]
        r.shuffle(pool)
        for x in pool:
            for f in x["function"]:
                nm = B.oai_name(f["name"])
                if nm not in seen:
                    seen.add(nm)
                    cand.append(f)
            if len(cand) >= N_TOOLS - len(it["function"]):
                break
        funcs = list(it["function"]) + cand[:N_TOOLS - len(it["function"])]
        r.shuffle(funcs)
        out.append(dict(it, function_aug=funcs, n_own=len(it["function"])))
    return out


def lc_slice(n=120, seed=20261031, offset=0, lo=2000, hi=40000):
    from tokentrim.tokens import estimate_tokens
    exs = [e for e in L.examples() if lc_split(e) == "test" and L.key_lines(e["chunk"])]
    exs = [e for e in exs if lo <= estimate_tokens(L.read_log(e)) <= hi]
    rng = random.Random(seed)
    rng.shuffle(exs)
    return exs[offset:offset + n]


def lc_prompt(ex):
    return (f"Build {ex['id']} of the repository {ex['repo'].replace('@', '/')} failed on Travis CI. Read its log "
            f"with get_build_log, then reply with ONLY a JSON object {{\"failure_lines\": [...]}} that quotes, "
            f"verbatim and in order, the log lines that explain why the build failed (at most 25 lines).")


# ---- episodes ----------------------------------------------------------------------------------------
def run_bfcl(item, gw, tag, max_tokens):
    msgs = [{"role": "system", "content": f"Session: {tag}"}] + [dict(m) for m in item["question"][0]]
    tools = B.to_tools(item["function_aug"])
    data, rep = gw.complete({"model": MODEL, "messages": msgs, "tools": tools, "max_tokens": max_tokens},
                            conversation_id=tag, note=f"{item['id']}")
    totals = Totals()
    totals.add(rep)
    msg = data["choices"][0]["message"]
    calls = [c for c in msg.get("tool_calls") or [] if c.get("function", {}).get("name") not in
             ("search_tools", "retrieve_original")]
    leaked = len(msg.get("tool_calls") or []) - len(calls)
    out = B.decode(calls)
    ok, why = B.check(item, out)
    counts = {"search_tools": sum(e.startswith("search_tools") for e in rep.explanations),
              "internal_leak": leaked, "routed": any(e.startswith("Removed ") for e in rep.explanations),
              "gated": next((e for e in rep.explanations if e.startswith("Tool routing skipped")), ""),
              "error_type": why, "output": json.dumps(out)[:400]}
    return float(ok), totals, rep.explanations, counts


def run_lc(ex, gw, tag, max_tokens, max_steps=6):
    msgs = [{"role": "system", "content": f"Session: {tag}\n{LC_SYSTEM}"}, {"role": "user", "content": lc_prompt(ex)}]
    totals, notes, answer = Totals(), [], ""
    counts = {"retrieve_original": 0, "retrieve_grep": 0, "tool_calls": 0, "compressed": False}
    log = L.read_log(ex)
    for _ in range(max_steps):
        data, rep = gw.complete({"model": MODEL, "messages": msgs, "tools": [LC_TOOL], "max_tokens": max_tokens},
                                conversation_id=tag, note=f"{ex['id']}")
        totals.add(rep)
        notes += rep.explanations
        for e in rep.explanations:
            counts["retrieve_original"] += e.startswith("Model retrieved original")
            counts["retrieve_grep"] += e.startswith("Model grepped original")
            counts["compressed"] |= e.startswith("Compressed ")
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = msg.get("content") or ""
            break
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            counts["tool_calls"] += 1
            name = c.get("function", {}).get("name")
            msgs.append({"role": "tool", "tool_call_id": c.get("id"),
                         "content": log if name == "get_build_log" else f"Unknown tool {name}."})
    ok, r = L.grade(answer, ex)
    counts["recall"] = round(r, 3)
    return float(ok), totals, notes, counts, answer


# ---- mock oracle (zero spend) --------------------------------------------------------------------------
def mock_policy(workload, by_tag):
    def respond(payload):
        msgs = payload["messages"]
        tag = msgs[0]["content"].split("\n")[0].removeprefix("Session: ")
        item = by_tag[tag.rsplit("/", 1)[0]]
        names = {t["function"]["name"] for t in payload.get("tools") or []}
        if workload == "bfcl":
            want = B.oracle_output(item)
            missing = [next(iter(c)) for c in want if next(iter(c)) not in names]
            if missing and "search_tools" in names and msgs[-1].get("role") != "tool":
                return {"role": "assistant", "content": "", "tool_calls": [{"id": "s1", "type": "function",
                        "function": {"name": "search_tools", "arguments": json.dumps({"query": missing[0].replace("_", " ")})}}]}
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                for i, c in enumerate(want) for n, a in c.items()]}
        tools_seen = [m for m in msgs if m.get("role") == "tool"]
        if not tools_seen:
            return {"role": "assistant", "content": "", "tool_calls": [{"id": "g1", "type": "function",
                    "function": {"name": "get_build_log", "arguments": json.dumps({"build_id": item["id"]})}}]}
        seen = L.norm("\n".join(m["content"] for m in tools_seen))
        lines = L.key_lines(item["chunk"])
        if sum(L.line_found(l, seen) for l in lines) < 0.5 * len(lines) and "retrieve_original" in names \
                and len(tools_seen) < 3:
            import re
            ref = re.findall(r'retrieve_original\("([^"]+)"\)', tools_seen[0]["content"])
            if ref:
                return {"role": "assistant", "content": "", "tool_calls": [{"id": f"r{len(tools_seen)}", "type": "function",
                        "function": {"name": "retrieve_original", "arguments": json.dumps({"reference_id": ref[0]})}}]}
        found = [l for l in lines if L.line_found(l, seen)]
        return {"role": "assistant", "content": json.dumps({"failure_lines": found})}
    return respond


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("workload", choices=list(ARMS))
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--arms", default=None)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--max-tokens", type=int, default=8000)
    p.add_argument("--run-cap-usd", type=float, default=1.0)
    p.add_argument("--job-cap-usd", type=float, required=True)
    p.add_argument("--ledger", default="/workspace/tokentrim-work/spend_ledger.json")
    p.add_argument("--mock", action="store_true")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--results-dir", default="results/public_slices_2026-10-31")
    a = p.parse_args(argv)
    arms = a.arms.split(",") if a.arms else list(ARMS[a.workload])
    n = a.n or (100 if a.workload == "bfcl" else 120)
    items = bfcl_slice(n, offset=a.offset) if a.workload == "bfcl" else lc_slice(n, offset=a.offset)
    run_id = f"pub-{a.workload}-{datetime.now().strftime('%Y%m%d-%H%M%S')}" + ("-mock" if a.mock else "")
    out = Path(a.results_dir) / f"{a.workload}{'_mock' if a.mock else ''}"
    out.mkdir(parents=True, exist_ok=True)
    by_tag = {f"{run_id}/{it['id']}": it for it in items}
    if a.mock:
        ledger = SpendLedger(out / "_mock_ledger.json", 10**6, 10**6, run_id)
        upstream = MockChatUpstream(responder=mock_policy(a.workload, by_tag), ledger=ledger)
    else:
        ledger = SpendLedger(a.ledger, a.job_cap_usd, a.run_cap_usd, run_id)
        upstream = ChatUpstream(ledger=ledger, rpm=120)
    print(f"[{run_id}] start: {ledger.status()} items={len(items)} arms={arms}", flush=True)
    rng = random.Random(a.seed)
    jobs = []
    for it in items:
        order = list(arms)
        rng.shuffle(order)
        jobs += [(it, arm, k) for k, arm in enumerate(order)]
    lock, stop, rows_path = threading.Lock(), threading.Event(), out / "rows.jsonl"
    rows = []

    def work(job):
        it, arm, pos = job
        if stop.is_set():
            return
        gw = Gateway(upstream, GatewayConfig(**ARMS[a.workload][arm]))
        tag = f"{run_id}/{it['id']}/{arm}"
        t0 = time.time()
        answer = ""
        try:
            if a.workload == "bfcl":
                score, totals, notes, counts = run_bfcl(it, gw, tag, a.max_tokens)
            else:
                score, totals, notes, counts, answer = run_lc(it, gw, tag, a.max_tokens)
            err = None
        except SpendCapExceeded as exc:
            stop.set()
            print(f"CAP: {exc}", flush=True)
            return
        except Exception as exc:
            score, totals, notes, counts, err = 0.0, Totals(), [], {}, f"{type(exc).__name__}: {str(exc)[:200]}"
        row = {"workload": a.workload, "task_id": it["id"], "arm": arm, "arm_position": pos, "score": score,
               "passed": score == 1.0, **totals.summary(), **counts, "error": err, "wall_s": round(time.time() - t0, 1),
               "explanations": sorted(set(notes))[:12], "answer_tail": (answer or "")[-300:],
               "data_kind": getattr(upstream, "data_kind", "REAL")}
        with lock:
            rows.append(row)
            with rows_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(f"{it['id']} {arm:16s} pass={row['passed']} ${row['usd']:.5f} calls={row['calls']} "
                  f"err={err} | {ledger.status()}", flush=True)

    with ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(work, jobs))
    meta = {"run_id": run_id, "workload": a.workload, "arms": arms, "items": len(items), "offset": a.offset,
            "model": MODEL, "max_tokens": a.max_tokens, "workers": a.workers, "seed": a.seed, "rows": len(rows),
            "jobs": len(jobs), "stopped_by_cap": stop.is_set(), "spend_this_run_usd": ledger.mine(),
            "ledger_total_usd": ledger.total(), "job_cap_usd": a.job_cap_usd, "run_cap_usd": a.run_cap_usd,
            "data_kind": getattr(upstream, "data_kind", "REAL"),
            "contributor_mode": "Meta may use request content for training (owner consented; public datasets)"}
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"[{run_id}] done: {len(rows)}/{len(jobs)} runs; {ledger.status()}", flush=True)


if __name__ == "__main__":
    main()
