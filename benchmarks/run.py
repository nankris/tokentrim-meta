"""v4 paired benchmark: Baseline vs TokenTrim Skill only vs TokenTrim Full (+ single-module ablations).

Every call goes through tokentrim.Gateway (baseline = all modules off = pure passthrough), so all arms share
one code path and one accounting path. Spend is enforced by tokentrim.ledger.SpendLedger: each call RESERVES
its worst case before it is sent (job cap + per-run cap), so concurrency cannot overshoot.
Arms of a task run interleaved in a per-task random order; each (task, arm) has a unique session tag at the
top of the system prompt so provider-cache hits cannot leak between arms. ``--mock`` = offline, zero spend.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import re
import threading
import time
from datetime import datetime, timezone
import uuid

from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.guard import SpendCapExceeded
from tokentrim.ledger import SpendLedger
from tokentrim.upstream import ChatUpstream, MockChatUpstream
from . import workloads as W
from . import workloads_hard as WH

MODEL = "muse-spark-1.3-contributor"
SKILL = Path(__file__).resolve().parent.parent / "skills" / "tokentrim" / "SKILL.md"


def skill_text() -> str:
    text = SKILL.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text


ARMS = {
    "agentic": {
        "baseline": dict(skill=False, cfg=dict(cache_prefix=False)),
        "skill": dict(skill=True, cfg=dict(cache_prefix=False)),
        "tool_output": dict(skill=False, cfg=dict(cache_prefix=False, tool_output=True)),
        "schema_router": dict(skill=False, cfg=dict(cache_prefix=False, schema_router=True)),
        "full": dict(skill=True, cfg=dict(cache_prefix=True, tool_output=True, schema_router=True)),
    },
    "agentic_hard": {
        "baseline": dict(skill=False, cfg=dict(cache_prefix=False)),
        "skill": dict(skill=True, cfg=dict(cache_prefix=False)),
        "tool_output": dict(skill=False, cfg=dict(cache_prefix=False, tool_output=True)),
        "schema_router": dict(skill=False, cfg=dict(cache_prefix=False, schema_router=True)),
        "full_no_router": dict(skill=True, cfg=dict(cache_prefix=True, tool_output=True)),
        "full": dict(skill=True, cfg=dict(cache_prefix=True, tool_output=True, schema_router=True)),
    },
    "longchat": {
        "baseline": dict(skill=False, cfg=dict(cache_prefix=False)),
        "skill": dict(skill=True, cfg=dict(cache_prefix=False)),
        "history": dict(skill=False, cfg=dict(cache_prefix=False, history=True)),
        "full": dict(skill=True, cfg=dict(cache_prefix=True, history=True)),
        "full_no_history": dict(skill=True, cfg=dict(cache_prefix=True)),  # recommended Full (compaction off)
    },
    "chat": {  # the chat client puts a per-request timestamp + request id in its system prompt (common pattern)
        "baseline": dict(skill=False, cfg=dict(cache_prefix=False)),
        "skill": dict(skill=True, cfg=dict(cache_prefix=False)),
        "cache": dict(skill=False, cfg=dict(cache_prefix=True)),
        "full": dict(skill=True, cfg=dict(cache_prefix=True)),
    },
}
HISTORY_CFG = dict(history_min_tokens=3000, history_keep_recent=6, history_future_calls=8)


def system_for(base: str, tag: str, use_skill: bool, timestamp: bool = False) -> str:
    text = f"Session: {tag}\n"
    if timestamp:
        text += (f"Current time: {datetime.now(timezone.utc).isoformat(timespec='milliseconds')} "
                 f"request_id: {uuid.uuid4()}\n")
    text += base
    if use_skill:
        text += "\n\n# Loaded skill: tokentrim\n" + skill_text()
    return text


class Totals:
    def __init__(self):
        self.calls = []

    def add(self, report):
        self.calls += report.calls

    def summary(self):
        c = self.calls
        return {"calls": len(c), "usd": sum(x.usd for x in c), "prompt_tokens": sum(x.prompt_tokens for x in c),
                "uncached_tokens": sum(x.uncached_tokens for x in c), "cached_tokens": sum(x.cached_tokens for x in c),
                "cache_write_tokens": sum(x.cache_write_tokens for x in c),
                "output_tokens": sum(x.completion_tokens for x in c), "reasoning_tokens": sum(x.reasoning_tokens for x in c),
                "usd_uncached": sum(x.usd_uncached for x in c), "usd_cached": sum(x.usd_cached for x in c),
                "usd_output": sum(x.usd_output for x in c), "latency_s": round(sum(x.latency_s for x in c), 2),
                "truncated_calls": sum(x.truncated for x in c), "calls_with_cache_hit": sum(x.cached_tokens > 0 for x in c),
                "over_reservation": sum(x.over_reservation for x in c), "retries": sum(x.retries for x in c)}


def run_agentic(task, arm, spec, gw, tag, max_tokens, max_steps=10):
    msgs = [{"role": "system", "content": system_for(task["system"], tag, spec["skill"])},
            {"role": "user", "content": task["prompt"]}]
    tools, totals, notes, answer = W.agentic_tools(), Totals(), [], ""
    counts = {"retrieve_original": 0, "retrieve_grep": 0, "search_tools": 0, "tool_calls": 0}
    for step in range(max_steps):
        data, rep = gw.complete({"model": MODEL, "messages": msgs, "tools": tools, "max_tokens": max_tokens},
                                conversation_id=tag, note=f"{task['id']}/{arm}")
        totals.add(rep)
        notes += rep.explanations
        for e in rep.explanations:
            if e.startswith("Model retrieved original"):
                counts["retrieve_original"] += 1
            if e.startswith("Model grepped original"):
                counts["retrieve_grep"] = counts.get("retrieve_grep", 0) + 1
            if e.startswith("search_tools("):
                counts["search_tools"] += 1
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = msg.get("content") or ""
            break
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            counts["tool_calls"] += 1
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            msgs.append({"role": "tool", "tool_call_id": c.get("id"), "content": W.run_stub(task, c["function"]["name"], args)})
    score, fields = W.grade_json(answer, task["answer"])
    return score, fields, totals, notes, counts, answer


def run_agentic_hard(task, arm, spec, gw, tag, max_tokens, max_steps=14):
    msgs = [{"role": "system", "content": system_for(task["system"], tag, spec["skill"])},
            {"role": "user", "content": task["prompt"]}]
    tools, totals, notes, answer, trace = WH.hard_tools(), Totals(), [], "", []
    counts = {"retrieve_original": 0, "retrieve_grep": 0, "search_tools": 0, "tool_calls": 0}
    for step in range(max_steps):
        data, rep = gw.complete({"model": MODEL, "messages": msgs, "tools": tools, "max_tokens": max_tokens},
                                conversation_id=tag, note=f"{task['id']}/{arm}")
        totals.add(rep)
        notes += rep.explanations
        for e in rep.explanations:
            if e.startswith("Model retrieved original"):
                counts["retrieve_original"] += 1
            if e.startswith("Model grepped original"):
                counts["retrieve_grep"] += 1
            if e.startswith("search_tools("):
                counts["search_tools"] += 1
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = msg.get("content") or ""
            break
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            counts["tool_calls"] += 1
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            trace.append((c["function"]["name"], args))
            msgs.append({"role": "tool", "tool_call_id": c.get("id"),
                         "content": WH.run_hard_stub(task, c["function"]["name"], args)})
    score, checks = WH.grade_hard(answer, task, trace)
    counts["tool_trace"] = [[n, a] for n, a in trace]
    return score, checks, totals, notes, counts, answer


def run_longchat(task, arm, spec, gw, tag, max_tokens):
    msgs = [{"role": "system", "content": system_for(W.LONGCHAT_SYSTEM, tag, spec["skill"])}]
    totals, notes = Totals(), []
    answer = ""
    for turn in task["turns"] + [task["question"]]:
        msgs.append({"role": "user", "content": turn})
        data, rep = gw.complete({"model": MODEL, "messages": msgs, "max_tokens": max_tokens},
                                conversation_id=tag, note=f"{task['id']}/{arm}")
        totals.add(rep)
        notes += rep.explanations
        answer = data["choices"][0]["message"].get("content") or ""
        msgs.append({"role": "assistant", "content": answer})
    score, fields = W.grade_json(answer, task["answer"])
    return score, fields, totals, notes, {}, answer


DOC, ITEMS = W.chat_doc()
CHAT_BASE = ("You are a support assistant for ACME Hardware. Answer from the reference document below; show the "
             "computation briefly.\n\n" + DOC)


def run_chat(task, arm, spec, gw, tag, max_tokens):
    totals, notes, oks, answers = Totals(), [], [], []
    for q in task["questions"]:
        msgs = [{"role": "system", "content": system_for(CHAT_BASE, tag, spec["skill"], timestamp=True)},
                {"role": "user", "content": q["q"]}]
        data, rep = gw.complete({"model": MODEL, "messages": msgs, "max_tokens": max_tokens},
                                conversation_id=None, note=f"{task['id']}/{arm}")
        totals.add(rep)
        notes += rep.explanations
        text = data["choices"][0]["message"].get("content") or ""
        oks.append(W.grade_total(text, q["answer"]))
        answers.append(text[-80:])
    return sum(oks) / len(oks), {f"q{i}": ok for i, ok in enumerate(oks)}, totals, notes, {}, answers


RUNNERS = {"agentic": run_agentic, "agentic_hard": run_agentic_hard, "longchat": run_longchat, "chat": run_chat}


def mock_responder(workload, policy="oracle"):
    """Deterministic offline policy so the harness can be exercised end to end with zero spend."""
    if workload == "agentic_hard":
        from .mock_agents import hard_policy
        return hard_policy(policy)

    def respond(payload):
        msgs = payload["messages"]
        if msgs[0]["content"].startswith("You compress a conversation"):
            return {"role": "assistant", "content": json.dumps({"goal": "mock", "facts": {}})}
        if workload == "agentic":
            done = {m.get("tool_call_id") for m in msgs if m.get("role") == "tool"}
            order = ["run_tests", "get_ci_log", "git_diff"]
            n = len(done)
            if n < len(order):
                return {"role": "assistant", "content": "", "tool_calls": [{"id": f"c{n}", "type": "function",
                        "function": {"name": order[n], "arguments": "{}"}}]}
            return {"role": "assistant", "content": '{"failing_tests": []}'}
        return {"role": "assistant", "content": "Noted. TOTAL: 0"}
    return respond


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("workload", choices=list(ARMS))
    p.add_argument("--tasks", type=int, default=24)
    p.add_argument("--arms", default=None, help="comma list (default: all arms of the workload)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--max-tokens", type=int, default=16000)
    p.add_argument("--run-cap-usd", type=float, default=5.0)
    p.add_argument("--job-cap-usd", type=float, default=12.0)
    p.add_argument("--ledger", default="/workspace/tokentrim-work/spend_ledger.json")
    p.add_argument("--out", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--offset", type=int, default=0, help="first task index (pilots use indices >= 100)")
    p.add_argument("--mock-policy", default="oracle", choices=("oracle", "lazy", "guess"))
    p.add_argument("--results-dir", default="results/v4_2026-10-30")
    a = p.parse_args(argv)
    arms = a.arms.split(",") if a.arms else list(ARMS[a.workload])
    run_id = f"v4-{a.workload}-{datetime.now().strftime('%Y%m%d-%H%M%S')}" + ("-mock" if a.mock else "")
    out = Path(a.out or f"{a.results_dir}/{a.workload}{'_mock' if a.mock else ''}")
    out.mkdir(parents=True, exist_ok=True)
    if a.mock:
        ledger = SpendLedger(out / "_mock_ledger.json", 10**6, 10**6, run_id)
        upstream = MockChatUpstream(responder=mock_responder(a.workload, a.mock_policy), ledger=ledger)
    else:
        ledger = SpendLedger(a.ledger, a.job_cap_usd, a.run_cap_usd, run_id)
        upstream = ChatUpstream(ledger=ledger, rpm=120)
    print(f"[{run_id}] start: {ledger.status()}", flush=True)
    idx = range(a.offset, a.offset + a.tasks)
    if a.workload == "agentic":
        tasks = [W.agentic_task(i) for i in idx]
    elif a.workload == "agentic_hard":
        tasks = [WH.hard_task(i) for i in idx]
    elif a.workload == "longchat":
        tasks = [W.longchat_task(i) for i in idx]
    else:
        tasks = [W.chat_task(i, ITEMS) for i in idx]
    rng = random.Random(a.seed)
    jobs = []
    for t in tasks:
        order = list(arms)
        rng.shuffle(order)
        jobs += [(t, arm, k) for k, arm in enumerate(order)]
    # warm-up (excluded from results): connection + model warm, unique tags so nothing is shared with arms
    if not a.mock:
        for w in range(2):
            Gateway(upstream, GatewayConfig(cache_prefix=False)).complete(
                {"model": MODEL, "messages": [{"role": "user", "content": f"warm-up {run_id} {w}: reply OK"}],
                 "max_tokens": 2000}, note="warm-up")
    lock = threading.Lock()
    rows, stop = [], threading.Event()
    rows_path = out / "rows.jsonl"

    def work(job):
        task, arm, pos = job
        if stop.is_set():
            return
        spec = ARMS[a.workload][arm]
        cfg = dict(spec["cfg"], **(HISTORY_CFG if spec["cfg"].get("history") else {}))
        gw = Gateway(upstream, GatewayConfig(**cfg))
        tag = f"{run_id}/{task['id']}/{arm}"
        t0 = time.time()
        try:
            score, fields, totals, notes, counts, answer = RUNNERS[a.workload](task, arm, spec, gw, tag, a.max_tokens)
            err = None
        except SpendCapExceeded as exc:
            stop.set()
            print(f"CAP: {exc}", flush=True)
            return
        except Exception as exc:
            score, fields, totals, notes, counts, answer, err = 0.0, {}, Totals(), [], {}, "", f"{type(exc).__name__}: {str(exc)[:200]}"
        row = {"workload": a.workload, "task_id": task["id"], "arm": arm, "arm_position": pos, "score": score,
               "passed": score == 1.0, "fields": fields, **totals.summary(), **counts, "error": err,
               "wall_s": round(time.time() - t0, 1), "explanations": sorted(set(notes))[:20],
               "answer_tail": answer if isinstance(answer, list) else (answer or "")[-300:],
               "data_kind": getattr(upstream, "data_kind", "REAL")}
        with lock:
            rows.append(row)
            with rows_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(f"{task['id']} {arm:13s} score={score:.2f} ${row['usd']:.5f} calls={row['calls']} "
                  f"trunc={row['truncated_calls']} err={err} | {ledger.status()}", flush=True)

    with ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(work, jobs))
    meta = {"run_id": run_id, "workload": a.workload, "arms": arms, "tasks": len(tasks), "offset": a.offset, "model": MODEL,
            "max_tokens": a.max_tokens, "workers": a.workers, "seed": a.seed, "rows": len(rows),
            "jobs": len(jobs), "stopped_by_cap": stop.is_set(), "spend_this_run_usd": ledger.mine(),
            "ledger_total_usd": ledger.total(), "job_cap_usd": a.job_cap_usd, "run_cap_usd": a.run_cap_usd,
            "data_kind": getattr(upstream, "data_kind", "REAL"),
            "contributor_mode": "Meta may use request content for training (owner consented; synthetic tasks)"}
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"[{run_id}] done: {len(rows)}/{len(jobs)} runs; {ledger.status()}", flush=True)


if __name__ == "__main__":
    main()
