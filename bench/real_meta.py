"""REAL paired benchmark against the Meta Model API (spend-capped; secret-free output).

A scripted coding agent (list -> read -> grep -> distractor reads -> run tests -> plan -> edit/test
attempts -> summary) runs each task once per mode and repeat. Unlike bench/simulate.py:
* every call goes to https://api.meta.ai/v1 and the billed usage (prompt_tokens, cached_tokens,
  completion_tokens) comes from the API response;
* edits are the model's real JSON full-file replacements, checked by bench.checker in a
  disposable copy (real pass/fail); test logs are real unittest -v output.
Context padding (agent-sized system prompt, tool schemas, grep hits, two distractor modules) is
synthetic and labelled as such, reused from bench/simulate.py so sizes match the simulation.
Each (task, mode, repeat) run starts its system prompt with a unique session tag so provider-cache
hits cannot leak between runs.

v3 baselines (realistic naive-client cache-busters instead of the v2 per-call JSON reshuffle):
* ``baseline``       well-behaved client: name-sorted tools with sorted keys, no volatile text;
* ``baseline-ts``    same, plus "Current time: <ISO timestamp> request_id: <uuid4>" as the 2nd
                     line of the system prompt, fresh on every call (a common naive pattern);
* ``baseline-tools`` tool list serialized in set order with per-tool dict-order nondeterminism.
                     The order is stable while the tool set is unchanged and is re-drawn only when
                     the agent adds or removes a tool (all modes share the same schedule:
                     ``mcp_search`` added from call 4, ``tool_3`` removed from call 7);
* ``tokentrim``      the naive client with BOTH cache-busters, sent through TokenTrim with the v3
                     defaults (cache_layout, eager prune, trim; route is a no-op with one model).
Use --dry-run to exercise everything with the offline mock first.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import threading
import time
import uuid

from tokentrim.clients.mock import MockProviderClient
from tokentrim.guard import SpendCapExceeded
from tokentrim.middleware import TokenTrim
from tokentrim.pruner import ContextItem
from tokentrim.router import HeuristicRouter, Step
from tokentrim.routing import CheapFirstRouter, EscalatingRouter, StepSignals
from .checker import EDIT_INSTRUCTIONS, check_edit
from .real_common import CONTRIB, STANDARD, WONDER, SharedLedger, TaskGuard, costs, write_json
from .runner import load_tasks, safe_path
from .simulate import SCENARIOS, _code_padding, _filler, _tools

ALL = {"trim", "prune", "cache_layout", "route"}


@dataclass(frozen=True)
class Mode:
    tools: str = "sorted"          # sorted | setorder | shuffle (v2 strawman: random key order every call)
    timestamp: bool = False        # volatile timestamp + request id on line 2 of the system prompt
    savers: frozenset | None = None  # None = pass-through baseline
    strong: str = CONTRIB
    cheap: str = CONTRIB
    router: str = "heuristic"      # heuristic | cheapfirst (only used when strong != cheap)
    extra: dict = field(default_factory=dict)


MODES = {
    # v3 (2026-10-30 second run)
    "baseline": Mode(),
    "baseline-ts": Mode(timestamp=True),
    "baseline-tools": Mode(tools="setorder"),
    "tokentrim": Mode(tools="setorder", timestamp=True, savers=frozenset(ALL)),
    # v3b: cache_layout alone (no prune/trim/route) on the same naive client, to measure layout by itself.
    "layout-move": Mode(tools="setorder", timestamp=True, savers=frozenset({"cache_layout"})),
    "layout-drop": Mode(tools="setorder", timestamp=True, savers=frozenset({"cache_layout"}),
                        extra={"volatile_policy": "drop"}),
    # Route pilot: Wonder only vs Spark (Standard, not Contributor) first with sticky escalation.
    "pilot-wonder": Mode(strong=WONDER, cheap=WONDER),
    "pilot-sparkfirst": Mode(savers=frozenset(ALL), strong=WONDER, cheap=STANDARD, router="cheapfirst"),
    # v2 legacy modes (first run), kept so that run stays reproducible.
    "legacy-tokentrim-gated": Mode(savers=frozenset(ALL), extra={"prune_checkpoints": True}),
    "legacy-baseline-naive": Mode(tools="shuffle"),
    "legacy-tokentrim-naive": Mode(tools="shuffle", savers=frozenset(ALL), extra={"prune_checkpoints": True}),
}
V3_MODES = "baseline,baseline-ts,baseline-tools,tokentrim"


def tool_names(turn: int, count: int = 12) -> list[str]:
    """Tool set the scripted agent has at a call: ``mcp_search`` loaded from call 4, ``tool_3`` unloaded from call 7."""
    names = [f"tool_{n}" for n in range(count)]
    if turn >= 4:
        names.append("mcp_search")
    if turn >= 7:
        names.remove("tool_3")
    return names


def tool_json(scenario, names, style, salt, turn=0):
    by_name = {}
    for n, name in enumerate(names):
        by_name[name] = {"name": name, "description": _filler(scenario["tool_desc_chars"] // 4, name),
                         "parameters": {"type": "object", "additionalProperties": False,
                                        "properties": {"path": {"type": "string"}, "content": {"type": "string"},
                                                       "reason": {"type": "string"}}}}
    if style == "sorted":
        return json.dumps([by_name[k] for k in sorted(by_name)], sort_keys=True, separators=(",", ":"))
    if style == "shuffle":
        rng = random.Random(f"{salt}:{turn}")
    elif style == "setorder":
        # Like iterating a hash set / hash map: arbitrary but fixed for a given set content.
        rng = random.Random(hashlib.sha256((salt + "|" + ",".join(sorted(names))).encode()).hexdigest())
    else:
        raise ValueError(style)

    def scramble(value):
        if isinstance(value, dict):
            keys = list(value)
            rng.shuffle(keys)
            return {k: scramble(value[k]) for k in keys}
        if isinstance(value, list):
            return [scramble(v) for v in value]
        return value
    order = list(by_name)
    rng.shuffle(order)
    return json.dumps([scramble(by_name[k]) for k in order], separators=(",", ":"))


def naive_system(head: str, body: str, timestamp: bool) -> str:
    if not timestamp:
        return head + body
    first, _, rest = head.partition("\n")
    stamp = (f"Current time: {datetime.now(timezone.utc).isoformat(timespec='milliseconds')} "
             f"request_id: {uuid.uuid4()}")
    return f"{first}\n{stamp}\n{rest}{body}"


DEFAULT_TASKS = "t01_escaped_fields,t07_interval_union,t13_nested_lookup,t21_json_merge_patch,t28_sales_pipeline,t37_run_length_codec"
SYSTEM_HEAD = ("You are a coding agent working inside a scripted harness. Tool calls are executed for you and "
               "their results appear as user messages. After each tool result reply with at most two short "
               "sentences of notes. When asked to produce an edit, reply ONLY with the requested JSON.\n"
               "The text below is SYNTHETIC padding that stands in for a long production agent prompt; ignore it.\n")
MAX_TOKENS = {"read": 800, "planning": 2000, "edit": 8000, "summary": 600}


def run_task(task, mode, client, cm, guard, *, scenario, max_attempts, run_id, log, repeat=0):
    spec = MODES[mode]
    savers, strong, cheap = spec.savers, spec.strong, spec.cheap
    router = None
    if savers and strong != cheap:
        base = (CheapFirstRouter(cheap, strong) if spec.router == "cheapfirst"
                else HeuristicRouter(cheap, strong, long_context_tokens=64000))
        router = EscalatingRouter(base, strong, sticky=True, allow_contributor=True)
    pipeline = TokenTrim(client, token_budget=200_000, strong_model=strong, cost_model=cm, guard=guard,
                         router=HeuristicRouter(cheap, strong, long_context_tokens=64000),
                         escalating_router=router, savers=set(savers) if savers is not None else set(), **spec.extra)
    call_mode = "baseline" if savers is None else "tokentrim"
    guard.start_task(f"{task.id}:{mode}:{repeat}")
    session = f"Session tag: {run_id}/{task.id}/{mode}/r{repeat}\n"
    salt = f"{run_id}:{task.id}:{mode}:{repeat}"
    sys_body = SYSTEM_HEAD + _filler(scenario["system_tokens"], "sys")

    def system_text():
        return naive_system(session, sys_body, spec.timestamp)

    def tools_text(turn):
        return tool_json(scenario, tool_names(turn, scenario["tool_count"]), spec.tools, salt, turn)
    items = [ContextItem("system", "system", system_text(), role="system"),
             ContextItem("tools", "tool_schema", tools_text(1), role="system"),
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
        items[0] = ContextItem("system", "system", system_text(), role="system")
        items[1] = ContextItem("tools", "tool_schema", tools_text(turn), role="system")
        t0 = time.time()
        if hasattr(client, "key"):
            client.key = f"{task.id}|{mode}|{repeat}|{turn}"
        try:
            response, record = pipeline.complete(items, step, max_tokens=MAX_TOKENS[step.kind], mode=call_mode,
                                                 signals=signals)
        except BaseException:
            if hasattr(guard, "release"):
                guard.release()
            raise
        if hasattr(client, "record_key"):
            client.record_key(f"{task.id}|{mode}|{repeat}|{turn}")
        meta = dict(getattr(client, "last_meta", {}) or {})
        row = {"turn": turn, "step": step.kind, "model": record.decision.model, "route_reason": record.decision.reason,
               "prompt_tokens": record.usage["input"], "cached_tokens": record.usage["cached_input"],
               "completion_tokens": record.usage["output"], "reasoning_tokens": meta.get("reasoning_tokens"),
               "finish_reason": meta.get("finish_reason"), "usd": record.dollars,
               "est_tokens_sent": record.pruning.tokens_after, "est_tokens_before_savers": record.pruning.tokens_before,
               "dropped": record.pruning.dropped_ids, "compactions": len(record.compaction_ids or []),
               "prune_checkpoint": record.prune_checkpoint, "switch_check": record.switch_check,
               "fail_open": record.fail_open, "lint": record.prefix_lint_warnings,
               "latency_s": round(time.time() - t0, 2), "retries": meta.get("retries"),
               "escalated": record.escalated}
        calls.append(row)
        log(f"  {task.id} {mode} r{repeat} #{turn} {step.kind:8s} {row['model'].split('/')[-1]:28s} in={row['prompt_tokens']:6d} "
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
    return {"task_id": task.id, "mode": mode, "repeat": repeat, "category": task.category, "difficulty": task.difficulty,
            "passed": state["passed"], "edit_attempts": state["attempts"], "malformed_edits": state["malformed"],
            "cap_tripped": state["cap"], "error": state["error"], "calls": len(calls), **totals,
            "cache_hit_rate": totals["cached_tokens"] / totals["prompt_tokens"] if totals["prompt_tokens"] else 0,
            "per_call": calls}


class _MockResponder:
    def __call__(self, messages, model):
        return "notes", 400


class RecordingMeta:
    """Wraps the real client and appends one secret-free JSONL row per call (key, model, text, usage)."""
    def __init__(self, inner, path):
        self.inner, self.path, self.lock = inner, Path(path), threading.Lock()
        self.local = threading.local()

    @property
    def last_meta(self):
        return getattr(self.local, "meta", {})

    def complete(self, messages, model, max_tokens):
        response = self.inner.complete(messages, model, max_tokens)
        self.local.meta = dict(getattr(self.inner, "last_meta", {}) or {})
        self.local.pending = (model, response)
        return response

    def record_key(self, key):
        model, response = self.local.pending
        meta = self.local.meta
        row = {"key": key, "model": model, "text": response.text,
               "usage": {"input": response.usage.input, "cached_input": response.usage.cached_input,
                         "output": response.usage.output, "cache_write": response.usage.cache_write},
               "finish_reason": meta.get("finish_reason"), "reasoning_tokens": meta.get("reasoning_tokens")}
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")


class ReplayMeta:
    """REPLAY of a recorded REAL run: returns the recorded text and billed usage for each call key.
    No network. Edits are re-checked locally by the real checker, so pass/fail is reproduced."""
    data_kind = "REPLAY of recorded REAL run"

    def __init__(self, path):
        self.rows = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                self.rows[row["key"]] = row
        self.local = threading.local()

    @property
    def key(self):
        return getattr(self.local, "key", None)

    @key.setter
    def key(self, value):
        self.local.key = value

    @property
    def last_meta(self):
        return getattr(self.local, "meta", {})

    def complete(self, messages, model, max_tokens):
        from tokentrim.clients.base import ModelResponse, Usage
        row = self.rows.get(self.key)
        if row is None:
            raise KeyError(f"no recorded call for {self.key}")
        self.local.meta = {"finish_reason": row.get("finish_reason"), "reasoning_tokens": row.get("reasoning_tokens"),
                           "retries": 0}
        return ModelResponse(row["text"], Usage(**row["usage"]))


class _ThreadMeta:
    """Per-thread last_meta view over one shared MetaModelClient (urllib calls are thread-safe)."""
    def __init__(self, inner):
        self.inner, self.local = inner, threading.local()

    @property
    def last_meta(self):
        return getattr(self.local, "meta", {})

    def complete(self, messages, model, max_tokens):
        from tokentrim.clients.meta import MetaModelClient
        client = getattr(self.local, "client", None)
        if client is None:
            client = self.local.client = MetaModelClient(base_url=self.inner.base_url)
        response = client.complete(messages, model, max_tokens)
        self.local.meta = dict(client.last_meta)
        return response


def main():
    p = argparse.ArgumentParser(description="REAL Meta API TokenTrim benchmark (spend-capped)")
    p.add_argument("--tasks-file", default="bench/tasks/tasks_40.jsonl")
    p.add_argument("--tasks", default=DEFAULT_TASKS, help="comma list, 'first:N' or 'stride:N' (every Nth task; v3 used stride:2)")
    p.add_argument("--modes", default=V3_MODES)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-attempts", type=int, default=2)
    p.add_argument("--scenario", default="realistic")
    p.add_argument("--out", default="results/real_meta_2026-10-30_v3")
    p.add_argument("--tag", default="main")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--cap-usd", type=float, default=15.0, help="hard cap on the shared ledger total")
    p.add_argument("--run-cap-usd", type=float, default=None, help="max this invocation may add to the ledger")
    p.add_argument("--per-task-usd", type=float, default=0.10)
    p.add_argument("--est-usd-per-run", type=float, default=0.012,
                   help="pre-estimate per (task, mode, repeat) run; tasks are reduced to fit the budget")
    p.add_argument("--record", default=None, help="append a JSONL recording of every call (for --replay)")
    p.add_argument("--replay", default=None, help="REPLAY a recording: no API calls, no ledger")
    p.add_argument("--dry-run", action="store_true", help="offline mock client; no API calls, no ledger")
    args = p.parse_args()
    all_tasks = load_tasks(args.tasks_file)
    if args.tasks.startswith("first:"):
        tasks = all_tasks[:int(args.tasks.split(":")[1])]
    elif args.tasks.startswith("stride:"):  # every Nth task: spreads categories/difficulties
        tasks = all_tasks[::int(args.tasks.split(":")[1])]
    else:
        wanted = args.tasks.split(",")
        tasks = [t for t in all_tasks if t.id in wanted]
    modes = args.modes.split(",")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cm = costs()
    offline = args.dry_run or args.replay
    if args.dry_run:
        client, data_kind = MockProviderClient(_MockResponder()), "DRY-RUN (mock, not real)"
    elif args.replay:
        client, data_kind = ReplayMeta(args.replay), ReplayMeta.data_kind
    else:
        from tokentrim.clients.meta import MetaModelClient
        client, data_kind = _ThreadMeta(MetaModelClient()), "REAL"
        if args.record:
            client = RecordingMeta(client, args.record)
    ledger = SharedLedger(out / ("_offline_ledger.json" if offline else "spend_ledger.json"),
                          10**6 if offline else args.cap_usd, None if offline else args.run_cap_usd)
    if offline and ledger.path.exists():
        ledger.path.unlink()
        ledger.total = ledger.start = 0.0
    # Pre-estimate and reduce the task count to fit the remaining budget (never silently).
    budget = ledger.cap - ledger.total
    if ledger.run_cap is not None:
        budget = min(budget, ledger.run_cap)
    per_task = args.est_usd_per_run * len(modes) * args.repeats
    fit = int(budget // per_task) if per_task else len(tasks)
    estimate = {"requested_tasks": len(tasks), "est_usd_per_run": args.est_usd_per_run,
                "est_usd_requested": per_task * len(tasks), "budget_remaining_usd": budget}
    if not offline and fit < len(tasks):
        print(f"Pre-estimate ${per_task * len(tasks):.2f} exceeds remaining ${budget:.2f}; reducing to {fit} tasks.")
        tasks = tasks[:fit]
    estimate["tasks_run"] = len(tasks)
    print(f"Pre-estimate: {len(tasks)} tasks x {len(modes)} modes x {args.repeats} repeats ~ "
          f"${per_task * len(tasks):.2f}; ledger ${ledger.total:.4f} / cap ${ledger.cap:.2f}"
          + (f"; this run may add at most ${ledger.run_cap:.2f}" if ledger.run_cap is not None else ""))
    run_id = f"{args.tag}-{int(time.time())}" if not args.replay else f"{args.tag}-replay"
    jobs = []
    for repeat in range(args.repeats):
        for index, task in enumerate(tasks):
            rotated = modes[(index + repeat) % len(modes):] + modes[:(index + repeat) % len(modes)]
            jobs.extend((task, mode, repeat) for mode in rotated)
    rows, skipped, stop = [], [], threading.Event()
    lock = threading.Lock()
    partial = out / f"partial_{args.tag}.jsonl"

    def work(job):
        task, mode, repeat = job
        if stop.is_set():
            with lock:
                skipped.append({"task_id": task.id, "mode": mode, "repeat": repeat, "reason": "global cap reached"})
            return
        guard = TaskGuard(ledger, per_task_usd=args.per_task_usd)
        row = run_task(task, mode, client, cm, guard, scenario=SCENARIOS[args.scenario],
                       max_attempts=args.max_attempts, run_id=run_id, log=lambda m: None, repeat=repeat)
        with lock:
            rows.append(row)
            if not offline:
                with partial.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({k: v for k, v in row.items() if k != "per_call"}) + "\n")
            print(f"[{len(rows)}/{len(jobs)}] {task.id} {mode} r{repeat}: pass={row['passed']} in={row['prompt_tokens']} "
                  f"cached={row['cached_tokens']} out={row['completion_tokens']} ${row['usd']:.5f} "
                  f"(ledger ${ledger.total:.4f})" + (f" CAP: {row['cap_tripped']}" if row["cap_tripped"] else "")
                  + (f" ERROR: {row['error']}" if row["error"] else ""), flush=True)
        if row["cap_tripped"] and "global" in row["cap_tripped"]:
            stop.set()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(work, jobs))
    if stop.is_set():
        print("Global cap reached: remaining runs were NOT executed and are listed under 'skipped'.")
    key = {m: i for i, m in enumerate(modes)}
    rows.sort(key=lambda r: (r["repeat"], r["task_id"], key[r["mode"]]))
    result = {"metadata": {"data_kind": data_kind,
                           "endpoint": None if offline else "https://api.meta.ai/v1/chat/completions",
                           "date": "2026-10-30", "run_id": run_id, "modes": modes, "tasks": [t.id for t in tasks],
                           "repeats": args.repeats, "scenario": args.scenario, "max_attempts": args.max_attempts,
                           "max_tokens": MAX_TOKENS, "workers": args.workers, "pre_estimate": estimate,
                           "mode_specs": {m: {"tools": MODES[m].tools, "timestamp": MODES[m].timestamp,
                                              "savers": sorted(MODES[m].savers) if MODES[m].savers else None,
                                              "strong": MODES[m].strong, "cheap": MODES[m].cheap,
                                              "router": MODES[m].router, "extra": MODES[m].extra} for m in modes},
                           "prices": {m: cm.prices[m] for m in (CONTRIB, STANDARD, WONDER)},
                           "spend_this_run_usd": ledger.mine, "run_cap_usd": ledger.run_cap,
                           "ledger_total_usd": ledger.total, "cap_usd": ledger.cap,
                           "global_cap_reached": stop.is_set()},
              "results": rows, "skipped": skipped}
    name = ("dry_run_" if args.dry_run else "replay_" if args.replay else "bench_") + args.tag + ".json"
    write_json(out / name, result)
    if offline:
        print(f"wrote {out / name}; recorded/simulated cost ${result['metadata']['spend_this_run_usd']:.4f} "
              "(NOT billed: no API calls were made)")
    else:
        print(f"wrote {out / name}; spend this run ${result['metadata']['spend_this_run_usd']:.4f}")


if __name__ == "__main__":
    main()
