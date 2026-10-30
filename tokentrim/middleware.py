"""TokenTrim middleware: savers run in a fail-open wrapper around one model call.

Cache-aware rules (see RESEARCH_2026-10-28.md):
* trim compacts tool outputs deterministically at ingest, so history stays byte-stable;
* prune is EAGER by default (``prune_checkpoints=False``): unreferenced/stale items are dropped as soon
  as the pruner selects them, and drops are latched so the prefix never oscillates. The dollar
  break-even gate (``prune_checkpoints=True``) assumed a reliable provider cache; on the real Meta API
  (hits on ~31% of calls) it deferred every drop, so it is now opt-in. Benchmarks guard eager pruning
  with a pass-rate check against the baseline (see bench/real_report.py);
* cache_layout sorts tool JSON (keys and tool lists by name) and hoists volatile lines (timestamps,
  UUIDs, request ids) out of stable segments into one trailing metadata message;
* route downgrades are checked against the cost of re-billing context on a cold model.
"""
from dataclasses import asdict, dataclass, replace

from .clients.base import ModelClient, ModelResponse
from .cost import CostModel
from .compaction import OutputStore, compact_tool_output, is_log_like
from .guard import SpendCapExceeded
from .layout import deterministic_segments, hoist_volatile_lines, lint_stable_prefix
from .planner import CacheAwarePlanner, from_context
from .pruner import ContextItem, ContextPruner, PruneReport
from .router import HeuristicRouter, Router, RoutingDecision, Step
from .routing import EscalatingRouter, StepSignals, cache_aware_switch
from .tokens import TokenEstimator, estimate_tokens

SAVERS = {"prune", "trim", "cache_layout", "route"}


@dataclass(frozen=True)
class StepRecord:
    mode: str
    decision: RoutingDecision
    usage: dict[str, int]
    dollars: float
    pruning: PruneReport
    stable_prefix_hash: str
    estimated_cacheable_tokens: int
    warnings: list[str]
    fail_open: bool = False
    fail_open_error: str | None = None
    escalated: bool = False
    escalation_cause: str | None = None
    cost_breakdown: dict[str, float] | None = None
    compaction_ids: list[str] | None = None
    prefix_lint_warnings: list[str] | None = None
    projected_usd: float = 0.0
    switch_check: str | None = None
    prune_checkpoint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class TokenTrim:
    def __init__(self, client: ModelClient, token_budget: int = 4096, router: Router | None = None,
                 strong_model: str = "fake/strong", estimator: TokenEstimator = estimate_tokens,
                 cost_model: CostModel | None = None, guard=None, escalating_router=None,
                 compactor=None, output_store: OutputStore | None = None, savers=None,
                 cache_aware_routing: bool = True, switch_horizon_steps: int = 4,
                 prune_checkpoints: bool = False, expected_remaining_steps: int = 4,
                 compaction_max_lines: int = 40, trim_only_logs: bool = True,
                 hoist_volatile: bool = True, volatile_policy: str = "move"):
        self.client = client
        self.token_budget = token_budget
        self.router = router or HeuristicRouter(strong_model=strong_model)
        self.strong_model = strong_model
        self.estimator = estimator
        self.cost_model = cost_model or CostModel()
        self.guard = guard
        self.escalating_router = escalating_router
        self.compactor = compactor or compact_tool_output
        self.output_store = output_store or OutputStore()
        self.savers = set(savers) if savers is not None else set(SAVERS)
        if not self.savers <= SAVERS:
            raise ValueError("Unknown saver")
        self.cache_aware_routing = cache_aware_routing
        self.switch_horizon_steps = switch_horizon_steps
        self.prune_checkpoints = prune_checkpoints
        self.expected_remaining_steps = expected_remaining_steps
        self.compaction_max_lines = compaction_max_lines
        self.trim_only_logs = trim_only_logs
        self.hoist_volatile = hoist_volatile
        if volatile_policy not in {"move", "drop"}:
            raise ValueError("volatile_policy must be 'move' or 'drop'")
        self.volatile_policy = volatile_policy
        # Routine tool-output truncation belongs to the trim saver, not the pruner.
        self.pruner = ContextPruner(estimator, old_tool_lines=None)
        self.planner = CacheAwarePlanner(estimator)
        self.records: list[StepRecord] = []
        self.reset_task()

    def reset_task(self):
        """Forget per-task state (warm model, latched drops, compaction cache, escalation)."""
        self._last_model = None
        self._dropped: set[str] = set()
        self._compacted: dict[tuple[str, str], tuple[str, str | None]] = {}
        self._sent: dict[str, list[dict]] = {}
        if self.escalating_router is not None and hasattr(self.escalating_router, "reset"):
            self.escalating_router.reset()

    def _warm_tokens(self, model, messages):
        """Estimated provider-cache reuse: common message prefix with the last call to ``model``."""
        warm = 0
        for current, previous in zip(messages, self._sent.get(model, [])):
            if current != previous:
                break
            warm += self.estimator(current["content"])
        return warm

    def _trim(self, items):
        compaction_ids = []
        out = []
        for item in items:
            if item.kind != "tool_output" or (self.trim_only_logs and not is_log_like(item.text)):
                out.append(item)
                continue
            key = (item.id, item.text)
            if key not in self._compacted:
                text, report = self.compactor(item.text, max_lines=self.compaction_max_lines,
                                              store=self.output_store)
                self._compacted[key] = (text, report.output_id if text != item.text else None)
            text, output_id = self._compacted[key]
            if output_id:
                compaction_ids.append(output_id)
            out.append(replace(item, text=text))
        return out, compaction_ids

    def _prune(self, items, model_hint):
        kept, report = self.pruner.prune(items, self.token_budget)
        if not self.prune_checkpoints:
            # Eager: commit immediately and latch, so a dropped item never reappears.
            kept_ids = {i.id for i in kept}
            self._dropped.update(i.id for i in items if i.id not in kept_ids)
            kept = [i for i in kept if i.id not in self._dropped]
            return kept, report, None
        kept_ids = {i.id for i in kept}
        new_drops = [i for i in items if i.id not in kept_ids and i.id not in self._dropped]
        if not new_drops:
            # Latched drops stay dropped so the prefix does not oscillate.
            return kept, report, None
        restored = [i for i in items if i.id in kept_ids or i.id in {d.id for d in new_drops}]
        restored_tokens = sum(self.estimator(i.text) for i in restored)
        if restored_tokens > self.token_budget:
            self._dropped.update(d.id for d in new_drops)
            return kept, report, "forced by token budget"
        first = min(items.index(d) for d in new_drops)
        suffix_after = sum(self.estimator(i.text) for i in items[first:] if i.id in kept_ids)
        saved = sum(self.estimator(d.text) for d in new_drops)
        analysis = self.cost_model.breakeven_compaction(model_hint, suffix_after, saved,
                                                         self.expected_remaining_steps)
        if analysis["should_compact"]:
            self._dropped.update(d.id for d in new_drops)
            return kept, report, f"committed (net ${analysis['net_saving_usd']:.5f})"
        # Not worth breaking the cache yet: keep the items this step.
        kept = [i for i in items if i.id in kept_ids or i.id in {d.id for d in new_drops}]
        kept = [i for i in kept if i.id not in self._dropped]
        after = sum(self.estimator(i.text) for i in kept)
        dropped = [i.id for i in items if i.id not in {k.id for k in kept}]
        return kept, PruneReport(report.tokens_before, after, dropped, report.truncated_ids), \
            f"deferred (net ${analysis['net_saving_usd']:.5f})"

    def complete(self, items: list[ContextItem], step: Step, max_tokens: int = 256,
                 mode: str = "tokentrim", signals: StepSignals | None = None) -> tuple[ModelResponse, StepRecord]:
        if mode not in {"baseline", "tokentrim"}:
            raise ValueError("mode must be baseline or tokentrim")
        enabled = self.savers if mode == "tokentrim" else set()
        fail_open = False
        fail_error = None
        compaction_ids = []
        lint = []
        switch_note = prune_note = None
        try:
            transformed, compaction_ids = self._trim(items) if "trim" in enabled else (list(items), [])
            if "prune" in enabled:
                kept, report, prune_note = self._prune(transformed, self._last_model or self.strong_model)
            else:
                kept = transformed
                total = sum(self.estimator(i.text) for i in kept)
                report = PruneReport(total, total, [], [])
            segments = [from_context(i) for i in kept]
            if "cache_layout" in enabled:
                segments = deterministic_segments(segments)
                if self.hoist_volatile:
                    segments, hoisted = hoist_volatile_lines(segments, drop=self.volatile_policy == "drop")
                    verb = "dropped" if self.volatile_policy == "drop" else "hoisted"
                    lint = [f"{verb} volatile line(s) from {sid}" for sid in hoisted] + lint_stable_prefix(segments)
                else:
                    lint = lint_stable_prefix(segments)
            plan = self.planner.plan(segments, reorder="cache_layout" in enabled)
            if "route" in enabled:
                routed_step = replace(step, context_tokens=report.tokens_after)
                decision = (self.escalating_router.route(routed_step, signals) if self.escalating_router
                            else self.router.route(routed_step))
                escalated = bool(getattr(decision, "escalated", False))
                prices = self.cost_model.prices
                downgrade = (self._last_model in prices and decision.model in prices
                             and prices[decision.model]["output"] < prices[self._last_model]["output"])
                if self.cache_aware_routing and not escalated and decision.model != self._last_model and downgrade:
                    messages = plan.messages()
                    check = cache_aware_switch(self.cost_model, self._last_model, decision.model,
                                               report.tokens_after, horizon_steps=self.switch_horizon_steps,
                                               output_tokens=max_tokens,
                                               current_warm_tokens=self._warm_tokens(self._last_model, messages),
                                               candidate_warm_tokens=self._warm_tokens(decision.model, messages))
                    switch_note = check.reason
                    if not check.switch:
                        decision = RoutingDecision(self._last_model, check.reason)
            else:
                decision = RoutingDecision(self.strong_model, "Baseline always uses strong model")
        except SpendCapExceeded:
            raise
        except Exception as exc:
            fail_open, fail_error = True, type(exc).__name__
            kept = list(items)
            total = sum(self.estimator(i.text) for i in kept)
            report = PruneReport(total, total, [], [])
            plan = self.planner.plan([from_context(i) for i in kept], reorder=False)
            decision = RoutingDecision(self.strong_model, "Fail-open uses strong model")
            compaction_ids, lint, switch_note, prune_note = [], [], None, None
        # Worst-case projection assumes all input is uncached and full output is used.
        projected, _ = self.cost_model.cost(decision.model,
            {"input": sum(self.estimator(m["content"]) for m in plan.messages()),
             "cached_input": 0, "output": max_tokens, "cache_write": 0})
        if self.guard:
            self.guard.check(projected)
        if callable(getattr(self.client, "set_plan", None)):
            self.client.set_plan(plan)
        response = self.client.complete(plan.messages(), decision.model, max_tokens)
        usage = response.usage
        dollars, breakdown = self.cost_model.cost(decision.model, usage)
        if self.guard:
            self.guard.record(dollars)
        self._last_model = decision.model
        self._sent[decision.model] = [dict(m) for m in plan.messages()]
        record = StepRecord(mode, decision, asdict(usage), dollars, report, plan.stable_prefix_hash,
                            plan.cacheable_tokens, plan.warnings, fail_open, fail_error,
                            bool(getattr(decision, "escalated", False)), getattr(decision, "cause", None),
                            breakdown, compaction_ids, lint, projected, switch_note, prune_note)
        self.records.append(record)
        return response, record
