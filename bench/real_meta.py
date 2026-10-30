"""REAL paired benchmark against the Meta Model API (spend-capped; secret-free output).

A scripted coding agent (list -> read -> grep -> distractor reads -> run tests -> plan -> edit/test
attempts -> summary) runs each task once per mode. Unlike bench/simulate.py:
* every call goes to https://api.meta.ai/v1 and the billed usage (prompt_tokens, cached_tokens,
  completion_tokens) comes from the API response;
* edits are the model's real JSON full-file replacements, checked by bench.checker in a
  disposable copy (real pass/fail); test logs are real unittest -v output.
Context padding (agent-sized system prompt, tool schemas, grep hits, two distractor modules) is
synthetic and labelled as such, reused from bench/simulate.py so sizes match the simulation.
Each (task, mode) run starts its system prompt with a unique session tag so provider-cache hits
cannot leak between modes. Use --dry-run to estimate tokens with the offline mock first.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import time

from tokentrim.clients.mock import MockProviderClient
from tokentrim.guard import SpendCapExceeded
from tokentrim.middleware import TokenTrim
from tokentrim.pruner import ContextItem
from tokentrim.router import HeuristicRouter, Step
from tokentrim.routing import EscalatingRouter, StepSignals
from .checker import EDIT_INSTRUCTIONS, check_edit
from .real_common import CONTRIB, STANDARD, costs, make_guard, write_json
from .runner import load_tasks, safe_path
from .simulate import SCENARIOS, _code_padding, _filler, _tools

ALL = {"trim", "prune", "cache_layout", "route"}
# mode -> (naive tool JSON?, savers or None, strong model, cheap model, extra TokenTrim kwargs)
MODES = {
    "baseline": (False, None, CONTRIB, CONTRIB, {}),
    "tokentrim": (False, ALL, CONTRIB, CONTRIB, {}),
    # Same savers, but prune drops commit immediately (no cache break-even gate).
    "tokentrim-eager": (False, ALL, CONTRIB, CONTRIB, {"prune_checkpoints": False}),
    "baseline-naive": (True, None, CONTRIB, CONTRIB, {}),
    "tokentrim-naive": (True, ALL, CONTRIB, CONTRIB, {}),
    # Optional price-tier routing: Standard Spark as "strong", Contributor as "cheap" (same weights).
    "baseline-standard": (False, None, STANDARD, STANDARD, {}),
    "tokentrim-route-standard": (False, ALL, STANDARD, CONTRIB, {}),
}
DEFAULT_TASKS = "t01_escaped_fields,t07_interval_union,t13_nested_lookup,t21_json_merge_patch,t28_sales_pipeline,t37_run_length_codec"
SYSTEM_HEAD = ("You are a coding agent working inside a scripted harness. Tool calls are executed for you and "
               "their results appear as user messages. After each tool result reply with at most two short "
               "sentences of notes. When asked to produce an edit, reply ONLY with the requested JSON.\n"
               "The text below is SYNTHETIC padding that stands in for a long production agent prompt; ignore it.\n")
MAX_TOKENS = {"read": 800, "planning": 2000, "edit": 8000, "summary": 600}


def run_task(task, mode, client, cm, guard, *, scenario, max_attempts, run_id, log):
    naive, savers, strong, cheap, extra = MODES[mode]
    if savers and strong != cheap:
        router = EscalatingRouter(HeuristicRouter(cheap, strong, long_context_tokens=64000), strong,
                                  sticky=True, allow_contributor=True)
    else:
        router = None
    pipeline = TokenTrim(client, token_budget=200_000, strong_model=strong, cost_model=cm, guard=guard,
                         router=HeuristicRouter(cheap, strong, long_context_tokens=64000),
                         escalating_router=router, savers=savers if savers is not None else set(), **extra)
    call_mode = "baseline" if savers is None else "tokentrim"
    guard.start_task(f"{task.id}:{mode}")
    session = f"Session tag: {run_id}/{task.id}/{mode}\n"
    items = [ContextItem("system", "system", session + SYSTEM_HEAD + _filler(scenario["system_tokens"], "sys"),
                         role="system"),
             ContextItem("tools", "tool_schema", _tools(scenario), role="system"),
             ContextItem("user", "message", f"Task: {task.prompt}\nRepository files: {', '.join(task.files)}",
                         turn=0, role="user")]
    state = {"turn": 0, "last_edit_model": None, "passed": False, "attempts": 0, "cap": None, "error": None,
             "malformed": 0}
    read_at = {}
    calls = []
    verbose = replace(task, check=task.check.replace(" -q", " -v"))

    def call(step, signals=None):
        state["turn"] += 1
        turn = state["turn"]
        for index, item in enumerate(items):
            if item.id in read_at and turn - read_at[item.id] > 2 and item.referenced:
                items[index] = replace(item, referenced=False)
        if naive:
            items[1] = ContextItem("tools", "tool_schema", _tools(scenario, f"{run_id}:{task.id}:{turn}"), role="system")
        t0 = time.time()
        response, record = pipeline.complete(items, step, max_tokens=MAX_TOKENS[step.kind], mode=call_mode,
                                             signals=signals)
        meta = dict(getattr(client, "last_meta", {}) or {})
        row = {"turn": turn, "step": step.kind, "model": record.decision.model, "route_reason": record.decision.reason,
               "prompt_tokens": record.usage["input"], "cached_tokens": record.usage["cached_input"],
               "completion_tokens": record.usage["output"], "reasoning_tokens": meta.get("reasoning_tokens"),
               "finish_reason": meta.get("finish_reason"), "usd": record.dollars,
               "est_tokens_sent": record.pruning.tokens_after, "est_tokens_before_savers": record.pruning.tokens_before,
               "dropped": record.pruning.dropped_ids, "compactions": len(record.compaction_ids or []),
               "prune_checkpoint": record.prune_checkpoint, "switch_check": record.switch_check,
               "fail_open": record.fail_open, "lint": record.prefix_lint_warnings,
               "latency_s": round(time.time() - t0, 2), "retries": meta.get("retries")}
        calls.append(row)
        log(f"  {task.id} {mode} #{turn} {step.kind:8s} {row['model'].split('/')[-1]:28s} in={row['prompt_tokens']:6d} "
            f"cached={row['cached_tokens']:6d} out={row['completion_tokens']:5d} ${row['usd']:.5f} "
            f"{row['finish_reason']}")
        items.append(ContextItem(f"assistant-{turn}", "message", response.text or "(empty)", turn=turn, role="assistant"))
        return response, record

    def add(item_id, kind, text, read=False, role="user"):
        items.append(ContextItem(item_id, kind, text, state["turn"], referenced=True, role=role))
        if read:
            read_at[item_id] = state["turn"]

    repo = safe_path(task.repo)
    try:
        call(Step("read"))
        listing = [f"{task.repo}/{f}" for f in task.files] + [f"{task.repo}/extra/module_{n}.py" for n in range(20)]
        add("listing", "tool_output", "Tool result (list_files):\n" + "\n".join(listing))
        call(Step("read"))
        for filename in task.files:
            text = (repo / filename).read_text(encoding="utf-8")
            add(f"file:{filename}", "file", f"Tool result (read_file {filename}):\n{text}",
                read=filename == "display.py")
        call(Step("read"))
        hits = 60
        add("grep", "tool_output", "Tool result (grep 'def helper', SYNTHETIC padding modules):\n" +
            "\n".join(f"extra/module_{n % 20}.py:{10 + n}: def helper_{n}(value, limit)" for n in range(hits)))
        for n in range(scenario["distractors"]):
            add(f"distractor:{n}", "file", f"Tool result (read_file extra/module_{n}.py, SYNTHETIC):\n" +
                _code_padding(scenario["pad_tokens"], f"{task.id}:d{n}"), read=True)
        call(Step("read"))
        before = check_edit(verbose, '{"files": {}}')
        add("tests-0", "tool_output", "Tool result (run_tests):\n" + before.output)
        call(Step("read"))
        add("plan-request", "message", "Plan the fix in at most five bullet points.")
        call(Step("planning"))
        for attempt in range(max_attempts):
            state["attempts"] = attempt + 1
            add(f"edit-request-{attempt}", "message",
                ("Now produce the edit.\n" if attempt == 0 else
                 "The tests still fail (see the latest run_tests output). Produce a corrected edit.\n") + EDIT_INSTRUCTIONS)
            signals = StepSignals(visible_test_failed=attempt > 0, malformed_output=state["malformed"] > 0,
                                  no_progress_steps=attempt, previous_model=state["last_edit_model"])
            response, record = call(Step("edit", file_count=1, failed_test_retry=attempt > 0,
                                         estimated_edit_lines=40), signals)
            state["last_edit_model"] = record.decision.model
            result = check_edit(verbose, response.text.strip())
            if result.error:
                state["malformed"] += 1
                add(f"tests-{attempt + 1}", "tool_output", f"Tool result (apply_edit): error: {result.error}")
                continue
            add(f"tests-{attempt + 1}", "tool_output", "Tool result (apply_edit + run_tests):\n" + result.output)
            if result.passed:
                state["passed"] = True
                break
        add("summary-request", "message", "Summarize what you changed in two sentences.")
        call(Step("summary"))
    except SpendCapExceeded as exc:
        state["cap"] = str(exc)
    except Exception as exc:  # record and continue; never include request bodies or headers
        state["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    totals = {k: sum(c[k] for c in calls) for k in ("prompt_tokens", "cached_tokens", "completion_tokens", "usd")}
    totals["reasoning_tokens"] = sum(c["reasoning_tokens"] or 0 for c in calls)
    return {"task_id": task.id, "mode": mode, "category": task.category, "difficulty": task.difficulty,
            "passed": state["passed"], "edit_attempts": state["attempts"], "malformed_edits": state["malformed"],
            "cap_tripped": state["cap"], "error": state["error"], "calls": len(calls), **totals,
            "cache_hit_rate": totals["cached_tokens"] / totals["prompt_tokens"] if totals["prompt_tokens"] else 0,
            "per_call": calls}


class _MockResponder:
    def __call__(self, messages, model):
        return "notes", 400


def main():
    p = argparse.ArgumentParser(description="REAL Meta API TokenTrim benchmark (spend-capped)")
    p.add_argument("--tasks-file", default="bench/tasks/tasks_40.jsonl")
    p.add_argument("--tasks", default=DEFAULT_TASKS)
    p.add_argument("--modes", default="baseline,tokentrim")
    p.add_argument("--max-attempts", type=int, default=2)
    p.add_argument("--scenario", default="realistic")
    p.add_argument("--out", default="results/real_meta_2026-10-30")
    p.add_argument("--tag", default="main")
    p.add_argument("--dry-run", action="store_true", help="offline mock client; no API calls, no ledger")
    args = p.parse_args()
    wanted = args.tasks.split(",")
    tasks = [t for t in load_tasks(args.tasks_file) if t.id in wanted]
    modes = args.modes.split(",")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cm = costs()
    if args.dry_run:
        from tokentrim.guard import SpendGuard
        client, guard = MockProviderClient(_MockResponder()), SpendGuard(per_task_usd=10, global_usd=100, max_steps=40)
    else:
        from tokentrim.clients.meta import MetaModelClient
        client, guard = MetaModelClient(), make_guard(out)
    run_id = f"{args.tag}-{int(time.time())}"
    rows = []
    start_spend = guard.global_spend
    for task in tasks:
        for mode in modes:
            row = run_task(task, mode, client, cm, guard, scenario=SCENARIOS[args.scenario],
                           max_attempts=args.max_attempts, run_id=run_id, log=print)
            rows.append(row)
            print(f"{task.id} {mode}: pass={row['passed']} in={row['prompt_tokens']} cached={row['cached_tokens']} "
                  f"out={row['completion_tokens']} ${row['usd']:.5f} (ledger ${guard.global_spend:.4f})"
                  + (f" CAP: {row['cap_tripped']}" if row["cap_tripped"] else "")
                  + (f" ERROR: {row['error']}" if row["error"] else ""))
            if row["cap_tripped"] and "global" in row["cap_tripped"]:
                break
        else:
            continue
        print("Global cap tripped; aborting.")
        break
    result = {"metadata": {"data_kind": "DRY-RUN (mock, not real)" if args.dry_run else "REAL",
                           "endpoint": None if args.dry_run else "https://api.meta.ai/v1/chat/completions",
                           "date": "2026-10-30", "run_id": run_id, "modes": modes, "tasks": [t.id for t in tasks],
                           "scenario": args.scenario, "max_attempts": args.max_attempts, "max_tokens": MAX_TOKENS,
                           "prices": {m: cm.prices[m] for m in (CONTRIB, STANDARD)},
                           "spend_this_run_usd": guard.global_spend - start_spend,
                           "ledger_total_usd": guard.global_spend, "global_cap_usd": guard.global_usd},
              "results": rows}
    name = ("dry_run_" if args.dry_run else "bench_") + args.tag + ".json"
    write_json(out / name, result)
    print(f"wrote {out / name}; spend this run ${result['metadata']['spend_this_run_usd']:.4f}")


if __name__ == "__main__":
    main()
