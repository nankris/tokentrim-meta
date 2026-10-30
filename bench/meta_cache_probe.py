"""REAL Meta API cache probe: minimum cacheable prefix, warm reuse, cross-model sharing.

Spend-capped through the shared SpendGuard ledger. Prompts are synthetic filler; no secrets.
"""
import argparse
import json
from pathlib import Path
import random
import time

from tokentrim.clients.meta import MetaModelClient
from .real_common import CONTRIB, STANDARD, costs, make_guard, write_json

WORDS = "cache probe filler text alpha beta gamma delta river stone cloud lamp paper window".split()


def filler(tokens, tag):
    rng = random.Random(tag)
    return " ".join(rng.choice(WORDS) for _ in range(int(tokens * 0.8)))  # ~1.25 tokens/word guess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/real_meta_2026-10-30")
    p.add_argument("--sizes", default="256,512,1024,2048,4096")
    p.add_argument("--ttl-wait", type=int, default=90)
    p.add_argument("--phase", choices=["basic", "latency", "repeat", "crossmodel", "longwait"], default="basic")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client, cm, guard = MetaModelClient(), costs(), make_guard(out, per_task_usd=0.05)
    rows = []
    run_tag = f"probe-{int(time.time())}"

    def call(model, prefix, question, label):
        msgs = [{"role": "system", "content": prefix}, {"role": "user", "content": question}]
        projected, _ = cm.cost(model, {"input": 2 * sum(len(m["content"]) // 3 for m in msgs), "cached_input": 0,
                                       "output": 400, "cache_write": 0})
        guard.check(projected)
        t = time.time()
        r = client.complete(msgs, model, 400)
        usd, _ = cm.cost(model, r.usage)
        guard.record(usd)
        row = {"label": label, "model": model, "prompt_tokens": r.usage.input, "cached_tokens": r.usage.cached_input,
               "completion_tokens": r.usage.output, "reasoning_tokens": client.last_meta.get("reasoning_tokens"),
               "finish_reason": client.last_meta.get("finish_reason"), "usd": usd,
               "latency_s": round(time.time() - t, 2)}
        rows.append(row)
        print(json.dumps(row))
        return row

    guard.start_task("cache-probe-" + args.phase)
    if args.phase == "longwait":
        return longwait_phase(args, out, call, run_tag, rows)
    if args.phase == "crossmodel":
        return crossmodel_phase(args, out, call, run_tag, rows)
    if args.phase == "repeat":
        return repeat_phase(args, out, call, run_tag, rows)
    if args.phase == "latency":
        return latency_phase(args, out, call, run_tag, rows)
    sizes = [int(s) for s in args.sizes.split(",")]
    prefixes = {n: f"[{run_tag}-{n}] " + filler(n, f"{run_tag}-{n}") for n in sizes}
    for n in sizes:
        call(CONTRIB, prefixes[n], "Reply with just: ok", f"min-prefix {n} cold")
        call(CONTRIB, prefixes[n], "Reply with just: yes", f"min-prefix {n} warm (different suffix)")
    big = prefixes[max(sizes)]
    call(STANDARD, big, "Reply with just: ok", "cross-model: contributor-warm prefix sent to standard")
    call(STANDARD, big, "Reply with just: yes", "standard warm")
    if args.ttl_wait:
        time.sleep(args.ttl_wait)
        call(CONTRIB, big, "Reply with just: sure", f"contributor after {args.ttl_wait}s idle")
    write_json(out / "cache_probe.json", {"data_kind": "REAL", "endpoint": "https://api.meta.ai/v1/chat/completions",
                                          "date": "2026-10-30", "rows": rows,
                                          "total_usd": sum(r["usd"] for r in rows)})


def longwait_phase(args, out, call, run_tag, rows):
    """Re-test the single hit seen in the basic phase: warm call after 90 s and 150 s idle."""
    for wait in (90, 150):
        prefix = f"[{run_tag}-w{wait}] " + filler(4096, f"{run_tag}-w{wait}")
        call(CONTRIB, prefix, "Reply with just: ok", f"wait {wait}s: cold")
        time.sleep(wait)
        call(CONTRIB, prefix, "Reply with just: yes", f"wait {wait}s: after {wait}s")
        call(CONTRIB, prefix, "Reply with just: no", f"wait {wait}s: immediately after that")
    write_json(out / "cache_probe_longwait.json", {"data_kind": "REAL", "date": "2026-10-30", "rows": rows,
                                                   "total_usd": sum(r["usd"] for r in rows)})


def crossmodel_phase(args, out, call, run_tag, rows):
    """Is a prefix first sent to Standard Spark readable from cache by Contributor (and vice versa)?"""
    prefix = f"[{run_tag}-x] " + filler(4096, f"{run_tag}-x")
    call(STANDARD, prefix, "Reply with just: ok", "standard cold")
    time.sleep(30)
    call(CONTRIB, prefix, "Reply with just: yes", "contributor 30s after standard")
    time.sleep(5)
    call(STANDARD, prefix, "Reply with just: no", "standard again")
    time.sleep(5)
    call(CONTRIB, prefix, "Reply with just: maybe", "contributor again")
    write_json(out / "cache_probe_crossmodel.json", {"data_kind": "REAL", "date": "2026-10-30", "rows": rows,
                                                     "total_usd": sum(r["usd"] for r in rows)})


def repeat_phase(args, out, call, run_tag, rows):
    """Does a prefix need several sightings before cached_tokens appears? 8 sends, 5 s apart."""
    prefix = f"[{run_tag}-rep] " + filler(4096, f"{run_tag}-rep")
    for n in range(8):
        call(CONTRIB, prefix, f"Reply with just the number {n}", f"repeat #{n + 1}")
        time.sleep(5)
    write_json(out / "cache_probe_repeat.json", {"data_kind": "REAL", "date": "2026-10-30", "rows": rows,
                                                 "total_usd": sum(r["usd"] for r in rows)})


def latency_phase(args, out, call, run_tag, rows):
    """Cache population delay (warm call after d seconds) and min prefix after a long wait."""
    for delay in (3, 10, 20, 40):
        prefix = f"[{run_tag}-d{delay}] " + filler(4096, f"{run_tag}-d{delay}")
        call(CONTRIB, prefix, "Reply with just: ok", f"delay {delay}s: cold")
        time.sleep(delay)
        call(CONTRIB, prefix, "Reply with just: yes", f"delay {delay}s: after {delay}s")
    small = {n: f"[{run_tag}-s{n}] " + filler(n, f"{run_tag}-s{n}") for n in (512, 1024, 1536, 2048)}
    for n, prefix in small.items():
        call(CONTRIB, prefix, "Reply with just: ok", f"min-prefix {n}: cold")
    time.sleep(60)
    for n, prefix in small.items():
        call(CONTRIB, prefix, "Reply with just: yes", f"min-prefix {n}: after >=60s")
    write_json(out / "cache_probe_latency.json", {"data_kind": "REAL", "date": "2026-10-30", "rows": rows,
                                                  "total_usd": sum(r["usd"] for r in rows)})


if __name__ == "__main__":
    main()
