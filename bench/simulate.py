"""Offline synthetic-trace harness. EVERYTHING produced here is a SIMULATION.

No model is called and no task code is executed. A deterministic scripted agent walks each
task (list -> read -> grep -> read -> run tests -> plan -> edit/test attempts -> summary).
MockProviderClient emulates a per-model exact-prefix cache. Outcomes (visible/hidden test
passes) are drawn from assumed per-tier success probabilities with common random numbers,
so modes are compared on identical draws. Dollar figures use the bundled price table
(Meta Muse prices verified on dev.meta.ai, 2026-10-28) unless an illustrative profile is
selected. The simulation can NOT measure quality loss from trimming; that is an explicit
``trim_penalty`` assumption (default 0) that the sweep varies.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess

from tokentrim.clients.mock import MockProviderClient
from tokentrim.cost import CostModel
from tokentrim.guard import SpendCapExceeded, SpendGuard
from tokentrim.middleware import TokenTrim
from tokentrim.pruner import ContextItem
from tokentrim.router import HeuristicRouter, Step
from tokentrim.routing import CheapFirstRouter, EscalatingRouter, StepSignals
from .runner import ROOT, load_tasks, safe_path
from .stats import average_repeats, bootstrap_mean, cost_per_pass, noninferiority, paired_comparison

CHEAP = "meta/muse-spark-1.3"
STRONG = "meta/muse-wonder-1.0"
ALL = {"prune", "trim", "cache_layout", "route"}
# mode -> (input variant, savers or None for pass-through, model for pass-through, extra kwargs, reference mode)
MODES = {
    "baseline": ("friendly", None, STRONG, {}, None),
    "tokentrim": ("friendly", ALL, None, {}, "baseline"),
    "tokentrim-cheapfirst": ("friendly", ALL, None, {"router": "cheap-first"}, "baseline"),
    "prune-only": ("friendly", {"prune"}, None, {}, "baseline"),
    "prune-eager": ("friendly", {"prune"}, None, {"prune_checkpoints": False}, "baseline"),
    "trim-only": ("friendly", {"trim"}, None, {}, "baseline"),
    "route-only": ("friendly", {"route"}, None, {}, "baseline"),
    "route-percall": ("friendly", {"route"}, None, {"cache_aware_routing": False}, "baseline"),
    "route-cheapfirst": ("friendly", {"route"}, None, {"router": "cheap-first"}, "baseline"),
    "cheap-only": ("friendly", None, CHEAP, {}, "baseline"),
    "baseline-naive": ("naive", None, STRONG, {}, None),
    "cache-only-naive": ("naive", {"cache_layout"}, None, {}, "baseline-naive"),
    "tokentrim-naive": ("naive", ALL, None, {}, "baseline-naive"),
}
DEFAULT_MODES = tuple(MODES)
DEFAULT_SUCCESS = {"strong": {"easy": .92, "medium": .85, "hard": .75},
                   "cheap": {"easy": .80, "medium": .62, "hard": .45}}
HIDDEN_PASS = {"strong": .97, "cheap": .93}
MALFORMED = {"strong": .01, "cheap": .04}
SCENARIOS = {
    # "realistic": agent-sized prefix and reads (synthetic padding, labelled in the text).
    "realistic": {"system_tokens": 3000, "tool_count": 12, "tool_desc_chars": 1200, "pad_tokens": 1400,
                  "distractors": 2, "grep": True, "log_tests": (60, 180)},
    # "toy": the corpus files as-is with a small prompt; contexts are tiny.
    "toy": {"system_tokens": 200, "tool_count": 5, "tool_desc_chars": 300, "pad_tokens": 0,
            "distractors": 0, "grep": False, "log_tests": (15, 40)},
}
MAX_ATTEMPTS = 4
WORDS = ("agent must keep edits minimal run the visible tests read files before editing never print secrets "
         "prefer small diffs explain failures cite paths respect repository style avoid network access").split()


def _uniform(seed, *parts):
    """Common random number keyed by task/repeat/event, independent of mode."""
    digest = hashlib.sha256((str(seed) + "|" + "|".join(map(str, parts))).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big")).random()


def _filler(tokens, tag):
    rng = random.Random(tag)
    out, size = [], 0
    while size < tokens * 4:
        line = f"{len(out) + 1}. " + " ".join(rng.choice(WORDS) for _ in range(12)) + "."
        out.append(line)
        size += len(line) + 1
    return "\n".join(out)


def _code_padding(tokens, tag):
    rng = random.Random(tag)
    out, size, n = ["# --- SIMULATION padding to a realistic module size ---"], 0, 0
    while size < tokens * 4:
        n += 1
        block = (f"def helper_{n}(value, limit={rng.randint(1, 99)}):\n"
                 f"    \"\"\"Synthetic helper {n}; not part of the task.\"\"\"\n"
                 f"    if value is None:\n        return {rng.randint(0, 9)}\n"
                 f"    return min(limit, len(str(value)) * {rng.randint(2, 7)})\n")
        out.append(block)
        size += len(block)
    return "\n".join(out)


def _tools(scenario, shuffle_seed=None):
    rng = random.Random(shuffle_seed)
    tools = []
    for n in range(scenario["tool_count"]):
        tool = {"name": f"tool_{n}", "description": _filler(scenario["tool_desc_chars"] // 4, f"tool{n}"),
                "parameters": {"type": "object", "additionalProperties": False,
                               "properties": {"path": {"type": "string"}, "content": {"type": "string"},
                                              "reason": {"type": "string"}}}}
        tools.append(tool)
    if shuffle_seed is None:
        return json.dumps(tools, sort_keys=True, separators=(",", ":"))

    def shuffled(value):
        if isinstance(value, dict):
            keys = list(value)
            rng.shuffle(keys)
            return {k: shuffled(value[k]) for k in keys}
        if isinstance(value, list):
            return [shuffled(v) for v in value]
        return value
    # Naive client: re-serializes tools with nondeterministic key order every call.
    return json.dumps(shuffled(tools), separators=(",", ":"))


def _test_log(task_id, tests, failures, attempt):
    lines = [f"collecting tests ... {n}" for n in range(1, 6)]
    failed = set(range(failures))
    for i in range(tests):
        status = "FAIL" if i in failed else "ok"
        lines.append(f"test_case_{i} (tests.test_behavior.BehaviorTests.test_case_{i}) ... {status}")
    for i in sorted(failed):
        lines += ["=" * 70, f"FAIL: test_case_{i} (tests.test_behavior.BehaviorTests.test_case_{i})", "-" * 70,
                  "Traceback (most recent call last):",
                  f'  File "tests/test_behavior.py", line {20 + 3 * i + attempt}, in test_case_{i}',
                  "    self.assertEqual(actual, expected)",
                  f"AssertionError: simulated mismatch in {task_id} case {i}"]
    lines += ["-" * 70, f"Ran {tests} tests in 0.0{attempt + 1}s", "",
              f"FAILED (failures={failures})" if failures else "OK"]
    return "\n".join(lines)


def _read_file(task, filename, scenario):
    text = safe_path(filename, safe_path(task.repo)).read_text(encoding="utf-8")
    pad = scenario["pad_tokens"] if filename.endswith(".py") else scenario["pad_tokens"] // 4
    if pad:
        text += "\n" + _code_padding(pad, f"{task.id}:{filename}")
    return f"File: {filename}\n{text}"


class _Responder:
    def __init__(self):
        self.tokens = 50

    def __call__(self, messages, model):
        return "x" * (self.tokens * 4), self.tokens


def _tier(model):
    return "cheap" if model == CHEAP else "strong"


def _run_task(task, repeat, mode, *, seed, costs, success, scenario, min_cacheable_tokens, charges_write,
              trim_penalty, max_steps, global_guard):
    variant, savers, fixed_model, extra, _ = MODES[mode]
    responder = _Responder()
    client = MockProviderClient(responder, min_cacheable_tokens=min_cacheable_tokens,
                                charges_cache_write=charges_write)
    global_guard.start_task(f"{task.id}:{repeat}")
    extra = dict(extra)
    # The published SIMULATION tables used the v2 gated prune default; keep them reproducible.
    extra.setdefault("prune_checkpoints", True)
    base = (CheapFirstRouter(CHEAP, STRONG) if extra.pop("router", None) == "cheap-first"
            else HeuristicRouter(CHEAP, STRONG, long_context_tokens=64000))
    escalating = EscalatingRouter(base, STRONG, sticky=True)
    pipeline = TokenTrim(client, token_budget=200_000, strong_model=fixed_model or STRONG, cost_model=costs,
                         guard=global_guard, escalating_router=escalating,
                         savers=savers if savers is not None else set(), **extra)
    call_mode = "baseline" if savers is None else "tokentrim"
    naive = variant == "naive"
    items = [ContextItem("system", "system", "SIMULATION coding agent.\n" + _filler(scenario["system_tokens"], "sys"),
                         role="system"),
             ContextItem("tools", "tool_schema", _tools(scenario), role="system"),
             ContextItem("user", "message", task.prompt, turn=0, role="user")]
    source = [f for f in task.files if f.endswith(".py") and not f.startswith("tests/") and f != "display.py"]
    edit_file = source[0] if source else task.files[0]
    state = {"turn": 0, "last_edit_model": None, "failed_attempts": 0, "malformed": False, "visible_pass": False,
             "cap": None, "switches": 0, "stays": 0, "prune_commits": 0, "prune_defers": 0}
    read_at = {}

    def call(step, out_tokens, signals=None):
        state["turn"] += 1
        turn = state["turn"]
        # Reference tracking: reads never cited after two calls become unreferenced.
        for index, item in enumerate(items):
            if item.id in read_at and turn - read_at[item.id] > 2 and item.referenced:
                items[index] = ContextItem(item.id, item.kind, item.text, item.turn, referenced=False, role=item.role)
        if naive:
            items[1] = ContextItem("tools", "tool_schema", _tools(scenario, f"{task.id}:{repeat}:{turn}"), role="system")
        responder.tokens = out_tokens
        previous = pipeline._last_model
        response, record = pipeline.complete(items, step, max_tokens=out_tokens, mode=call_mode, signals=signals)
        if previous and record.decision.model != previous:
            state["switches"] += 1
        state["stays"] += bool(record.switch_check and "stay on warm" in record.switch_check)
        note = record.prune_checkpoint or ""
        state["prune_commits"] += note.startswith("committed")
        state["prune_defers"] += note.startswith("deferred")
        items.append(ContextItem(f"assistant-{turn}", "message", response.text, turn=turn, role="assistant"))
        return record

    def add(item_id, kind, text, referenced=True, read=False):
        items.append(ContextItem(item_id, kind, text, state["turn"], referenced=referenced, role="user"))
        if read:
            read_at[item_id] = state["turn"]

    def draw(*parts):
        return _uniform(seed, task.id, repeat, *parts)

    try:
        call(Step("read"), 60)
        listing = [f"{task.repo}/{f}" for f in task.files] + [f"{task.repo}/extra/module_{n}.py" for n in range(20)]
        add("listing", "tool_output", "\n".join(listing))
        half = max(1, len(task.files) // 2)
        for batch, files in enumerate((task.files[:half], task.files[half:])):
            call(Step("read"), 70)
            for filename in files:
                add(f"file:{filename}", "file", _read_file(task, filename, scenario), read=filename == "display.py")
        if scenario["grep"]:
            call(Step("read"), 60)
            hits = int(30 + draw("grep") * 50)
            add("grep", "tool_output", "\n".join(f"extra/module_{n % 20}.py:{10 + n}: def helper_{n}(value, limit)"
                                                 for n in range(hits)))
        for n in range(scenario["distractors"]):
            call(Step("read"), 60)
            add(f"distractor:{n}", "file", f"File: extra/module_{n}.py\n" + _code_padding(scenario["pad_tokens"], f"{task.id}:d{n}"),
                read=True)
        low, high = scenario["log_tests"]
        tests = int(low + draw("tests") * (high - low))
        call(Step("read"), 50)
        add("tests-0", "tool_output", _test_log(task.id, tests, 1 + int(draw("fails") * 3), 0))
        call(Step("planning"), int(300 + draw("plan") * 400))
        edit_tokens = max(150, len(_read_file(task, edit_file, scenario)) // 4 // 3) + 80
        lines = {"easy": 15, "medium": 50, "hard": 120}[task.difficulty]
        file_count = 2 if task.category == "multi_file" else 1
        for attempt in range(MAX_ATTEMPTS):
            signals = StepSignals(
                visible_test_failed=attempt > 0,
                malformed_output=state["malformed"],
                no_progress_steps=state["failed_attempts"],
                previous_model=state["last_edit_model"])
            record = call(Step("edit", file_count=file_count, failed_test_retry=attempt > 0,
                               estimated_edit_lines=lines), edit_tokens, signals)
            tier = _tier(record.decision.model)
            state["last_edit_model"] = record.decision.model
            state["malformed"] = draw("malformed", attempt) < MALFORMED[tier]
            if state["malformed"]:
                state["failed_attempts"] += 1
                add(f"tool-{attempt}", "tool_output", "error: malformed tool call; could not apply edit")
                continue
            p = success[tier][task.difficulty] - (trim_penalty if savers and "trim" in savers else 0)
            passed = draw("attempt", attempt, tier) < p
            add(f"tool-{attempt}", "tool_output", f"Wrote {edit_file}\n" +
                _test_log(task.id, tests, 0 if passed else 1 + int(draw("refail", attempt) * 2), attempt + 1))
            if passed:
                state["visible_pass"] = True
                break
            state["failed_attempts"] += 1
        call(Step("summary"), 150)
    except SpendCapExceeded as exc:
        state["cap"] = str(exc)
    final_tier = _tier(state["last_edit_model"]) if state["last_edit_model"] else "strong"
    hidden = state["visible_pass"] and not state["cap"] and draw("hidden", final_tier) < HIDDEN_PASS[final_tier]
    records = pipeline.records
    usage = {key: sum(r.usage.get(key, 0) for r in records) for key in ("input", "cached_input", "output", "cache_write")}
    return {"task_id": task.id, "repeat": repeat, "mode": mode, "difficulty": task.difficulty,
            "category": task.category, "passed": hidden, "visible_passed": state["visible_pass"],
            "dollars": sum(r.dollars for r in records), "tokens": usage["input"] + usage["output"],
            "uncached_input": usage["input"] - usage["cached_input"], **usage,
            "cache_hit_rate": usage["cached_input"] / usage["input"] if usage["input"] else 0,
            "escalated": any(r.escalated for r in records), "model_switches": state["switches"],
            "cache_aware_stays": state["stays"], "prune_commits": state["prune_commits"],
            "prune_defers": state["prune_defers"], "compacted_outputs": len({i for r in records for i in r.compaction_ids or []}),
            "cheap_calls": sum(r.decision.model == CHEAP for r in records),
            "fail_open_count": sum(r.fail_open for r in records), "steps": len(records),
            "cap_tripped": bool(state["cap"])}


def _git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True,
                              timeout=2, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def illustrative_cache_write_prices():
    """ILLUSTRATIVE ONLY: Meta prices plus an Anthropic-style 1.25x cache-write premium."""
    base = CostModel()
    return CostModel(overrides={m: {"cache_write": base.prices[m]["input"] * 1.25} for m in (CHEAP, STRONG)})


def run_simulation(tasks_path=ROOT / "bench/tasks/tasks_40.jsonl", out=ROOT / "results/sim", *, repeats=3,
                   seed=42, samples=2000, modes=DEFAULT_MODES, max_steps=15, success=None,
                   min_cacheable_tokens=1024, cost_model=None, price_profile="meta-verified",
                   scenario="realistic", trim_penalty=0.0, per_task_usd=1.0, global_usd=120.0, write=True):
    """Run deterministic synthetic agent traces; no task code is executed or modified."""
    tasks = load_tasks(tasks_path)
    out = safe_path(out)
    if out.is_relative_to(ROOT / "bench/tasks_repo"):
        raise ValueError("Output may not be inside the task corpus")
    unknown = set(modes) - set(MODES)
    if unknown:
        raise ValueError(f"Unknown modes: {sorted(unknown)}")
    modes = tuple(modes)
    for mode in modes:
        reference = MODES[mode][4]
        if reference and reference not in modes:
            raise ValueError(f"Mode {mode} needs its reference mode {reference}")
    success = success or DEFAULT_SUCCESS
    costs = cost_model or CostModel()
    profile = SCENARIOS[scenario]
    charges_write = any(r.get("cache_write", r["input"]) != r["input"] for m, r in costs.prices.items()
                        if m in (CHEAP, STRONG))
    rows = []
    for mode in modes:
        # Spend caps as in PREP_v2: $1/task, $120 global ledger (one per mode), 15 calls/task.
        guard = SpendGuard(per_task_usd=per_task_usd, global_usd=global_usd * repeats, max_steps=max_steps)
        for task in tasks:
            for repeat in range(repeats):
                rows.append(_run_task(task, repeat, mode, seed=seed, costs=costs, success=success,
                                      scenario=profile, min_cacheable_tokens=min_cacheable_tokens,
                                      charges_write=charges_write, trim_penalty=trim_penalty,
                                      max_steps=max_steps, global_guard=guard))
    averaged = average_repeats(rows)
    by_mode = {mode: sorted((r for r in averaged if r["mode"] == mode), key=lambda r: r["task_id"]) for mode in modes}
    summary = {}
    for mode in modes:
        values = by_mode[mode]
        s = {"dollars": bootstrap_mean([r["dollars"] for r in values], seed=seed, samples=samples),
             "pass_rate": bootstrap_mean([r["passed"] for r in values], seed=seed, samples=samples),
             "cost_per_pass": cost_per_pass([r["dollars"] for r in values], [r["passed"] for r in values],
                                            seed=seed, samples=samples)}
        for field in ("uncached_input", "cached_input", "output", "tokens", "cache_hit_rate", "escalated",
                      "model_switches", "cache_aware_stays", "prune_commits", "prune_defers", "compacted_outputs",
                      "cheap_calls", "steps", "fail_open_count", "cap_tripped"):
            s[field + "_mean"] = sum(r[field] for r in values) / len(values)
        reference = MODES[mode][4]
        if reference:
            ref = by_mode[reference]
            dollars = paired_comparison([r["dollars"] for r in ref], [r["dollars"] for r in values],
                                        seed=seed, samples=samples)
            passes = paired_comparison([100 * r["passed"] for r in ref], [100 * r["passed"] for r in values],
                                       seed=seed, samples=samples)
            s["vs"] = {"reference": reference, "dollars": dollars, "pass_rate_diff_pp": passes["difference"],
                       "noninferiority": noninferiority(passes["difference"]["ci95"])}
        summary[mode] = s
    task_bytes = safe_path(tasks_path).read_bytes()
    result = {"metadata": {
        "data_kind": "SIMULATION", "notice": "SIMULATION — not real measurements",
        "assumptions": {"success_probabilities": success, "hidden_pass": HIDDEN_PASS, "malformed": MALFORMED,
                        "trim_penalty": trim_penalty, "scenario": scenario, "scenario_sizes": profile,
                        "min_cacheable_tokens": min_cacheable_tokens, "cache_block_tokens": 128,
                        "cache_write_charged": charges_write,
                        "cache_model": "per-model exact message-prefix cache; 128-token blocks; TTL 10 calls",
                        "caps": {"per_task_usd": per_task_usd, "global_usd_per_mode_per_repeat": global_usd,
                                 "max_steps": max_steps}},
        "models": {"cheap": CHEAP, "strong": STRONG}, "prices": {m: costs.prices[m] for m in (CHEAP, STRONG)},
        "prices_hash": costs.prices_hash(), "price_profile": price_profile,
        "task_list_hash": hashlib.sha256(task_bytes).hexdigest(), "tasks": len(tasks),
        "seed": seed, "repeats": repeats, "bootstrap_samples": samples, "git_commit": _git_commit()},
        "results": rows, "averaged_results": averaged, "summary": summary}
    if write:
        out.mkdir(parents=True, exist_ok=True)
        (out / "sim_results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (out / "sim_summary.md").write_text(render_summary(result), encoding="utf-8")
    return result


def _ci(value, fmt="{:.1f}"):
    if not value or value.get("ci95") is None:
        return "n/a"
    lo, hi = value["ci95"]
    return f"{fmt.format(value['mean'])} [{fmt.format(lo)}, {fmt.format(hi)}]"


def render_summary(result):
    meta, summary = result["metadata"], result["summary"]
    a = meta["assumptions"]
    lines = ["# SIMULATION — not real measurements", "",
             "Scripted synthetic agent traces through a mock per-model prefix cache. No model was called.",
             f"Prices: `{meta['price_profile']}` ({meta['models']['cheap']} cheap, {meta['models']['strong']} strong). "
             f"Scenario: `{a['scenario']}`. Tasks: {meta['tasks']} x {meta['repeats']} repeats (averaged per task). "
             f"Seed {meta['seed']}. 95% percentile bootstrap over tasks, {meta['bootstrap_samples']} samples.",
             f"Pass outcomes are assumed probabilities, not test runs: {json.dumps(a['success_probabilities'])}; "
             f"trim_penalty={a['trim_penalty']}. min_cacheable_tokens={a['min_cacheable_tokens']}, "
             f"cache writes charged: {a['cache_write_charged']}.", "",
             "| Mode | vs | $/task [95% CI] | $ saving % [95% CI] | Pass % | Pass diff pp [95% CI] | NI (-10pp) | "
             "$/pass | Cache hit | Cheap calls | Switches | Escalated |",
             "|---|---|---:|---:|---:|---:|:-:|---:|---:|---:|---:|---:|"]
    for mode, s in summary.items():
        vs = s.get("vs")
        saving = _ci(vs["dollars"]["percent_saving"]) if vs else "—"
        diff = _ci(vs["pass_rate_diff_pp"]) if vs else "—"
        ni = ("yes" if vs["noninferiority"]["verdict"] else "no") if vs else "—"
        cpp = s["cost_per_pass"]["mean"]
        lines.append(f"| {mode} | {vs['reference'] if vs else '—'} | {_ci(s['dollars'], '{:.4f}')} | {saving} | "
                     f"{100 * s['pass_rate']['mean']:.1f} | {diff} | {ni} | "
                     f"{cpp:.4f} | {100 * s['cache_hit_rate_mean']:.1f}% | {s['cheap_calls_mean']:.1f}/{s['steps_mean']:.1f} | "
                     f"{s['model_switches_mean']:.2f} | {100 * s['escalated_mean']:.0f}% |" if cpp is not None else
                     f"| {mode} | — | {_ci(s['dollars'], '{:.4f}')} | {saving} | 0 | {diff} | {ni} | n/a | | | | |")
    lines += ["", "Token means per task (uncached / cached / output):", ""]
    for mode, s in summary.items():
        lines.append(f"- {mode}: {s['uncached_input_mean']:.0f} / {s['cached_input_mean']:.0f} / {s['output_mean']:.0f}; "
                     f"compacted outputs {s['compacted_outputs_mean']:.1f}, prune commits {s['prune_commits_mean']:.2f}, "
                     f"deferrals {s['prune_defers_mean']:.2f}, cache-aware stays {s['cache_aware_stays_mean']:.2f}, "
                     f"cap trips {s['cap_tripped_mean']:.2f}")
    return "\n".join(lines) + "\n"


def run_sweep(tasks, out, *, seed=42, samples=500):
    """One-factor-at-a-time sensitivity around the default SIMULATION (repeats=1)."""
    modes = ("baseline", "tokentrim", "tokentrim-cheapfirst", "route-percall", "cheap-only")
    cheap = lambda m: {t: {d: (v * m if t == "cheap" else v) for d, v in table.items()}
                       for t, table in DEFAULT_SUCCESS.items()}
    configs = [("default", {}),
               ("cheap_success_x0.70", {"success": cheap(.70)}), ("cheap_success_x0.85", {"success": cheap(.85)}),
               ("min_cacheable_0", {"min_cacheable_tokens": 0}), ("min_cacheable_4096", {"min_cacheable_tokens": 4096}),
               ("cache_write_1.25x_ILLUSTRATIVE", {"cost_model": illustrative_cache_write_prices(),
                                                   "price_profile": "illustrative-cache-write"}),
               ("trim_penalty_3pp", {"trim_penalty": .03}), ("trim_penalty_8pp", {"trim_penalty": .08}),
               ("scenario_toy", {"scenario": "toy"})]
    rows = []
    for name, kwargs in configs:
        result = run_simulation(tasks, out, repeats=1, seed=seed, samples=samples, modes=modes, write=False, **kwargs)
        row = {"config": name}
        for mode in modes[1:]:
            vs = result["summary"][mode]["vs"]
            row[mode] = {"saving_pct": vs["dollars"]["percent_saving"]["mean"],
                         "saving_ci95": vs["dollars"]["percent_saving"]["ci95"],
                         "pass_diff_pp": vs["pass_rate_diff_pp"]["mean"],
                         "pass_diff_ci95": vs["pass_rate_diff_pp"]["ci95"],
                         "noninferior": vs["noninferiority"]["verdict"]}
        row["baseline_usd_per_task"] = result["summary"]["baseline"]["dollars"]["mean"]
        rows.append(row)
    out = safe_path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "sensitivity.json").write_text(json.dumps({"data_kind": "SIMULATION", "repeats": 1, "rows": rows},
                                                     indent=2) + "\n", encoding="utf-8")
    md = ["# SIMULATION sensitivity (one factor at a time, repeats=1) — not real measurements", "",
          "| Config | baseline $/task | TokenTrim saving % [CI] | TokenTrim pass diff pp [CI] | NI | "
          "cheap-first stack saving % [CI] | cheap-first pass diff pp [CI] | NI | route-percall saving % | "
          "cheap-only saving % | cheap-only pass diff pp |", "|---|---:|---:|---:|:-:|---:|---:|:-:|---:|---:|---:|"]
    for r in rows:
        t, f, p, c = r["tokentrim"], r["tokentrim-cheapfirst"], r["route-percall"], r["cheap-only"]
        fmt = lambda v, ci: f"{v:.1f} [{ci[0]:.1f}, {ci[1]:.1f}]" if ci else f"{v:.1f}"
        md.append(f"| {r['config']} | {r['baseline_usd_per_task']:.4f} | {fmt(t['saving_pct'], t['saving_ci95'])} | "
                  f"{fmt(t['pass_diff_pp'], t['pass_diff_ci95'])} | {'yes' if t['noninferior'] else 'no'} | "
                  f"{fmt(f['saving_pct'], f['saving_ci95'])} | {fmt(f['pass_diff_pp'], f['pass_diff_ci95'])} | "
                  f"{'yes' if f['noninferior'] else 'no'} | "
                  f"{p['saving_pct']:.1f} | {c['saving_pct']:.1f} | {c['pass_diff_pp']:.1f} |")
    (out / "sensitivity.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser(description="SIMULATION — offline synthetic TokenTrim trace harness")
    parser.add_argument("--tasks", default="bench/tasks/tasks_40.jsonl")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="results/sim/")
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="realistic")
    parser.add_argument("--min-cacheable", type=int, default=1024)
    parser.add_argument("--trim-penalty", type=float, default=0.0)
    parser.add_argument("--sweep", action="store_true", help="Also run one-factor sensitivity configurations")
    args = parser.parse_args()
    print("SIMULATION — not real measurements")
    result = run_simulation(args.tasks, args.out, repeats=args.repeats, seed=args.seed, samples=args.samples,
                            scenario=args.scenario, min_cacheable_tokens=args.min_cacheable,
                            trim_penalty=args.trim_penalty)
    print(render_summary(result))
    if args.sweep:
        run_sweep(args.tasks, args.out, seed=args.seed)
        print(Path(safe_path(args.out), "sensitivity.md").read_text(encoding="utf-8"))
    meta = result["metadata"]
    print(f"SIMULATION results written to {args.out} ({meta['tasks']} tasks x {meta['repeats']} repeats)")


if __name__ == "__main__":
    main()
