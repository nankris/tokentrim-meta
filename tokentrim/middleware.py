from dataclasses import asdict, dataclass, replace

from .clients.base import ModelClient, ModelResponse
from .cost import cost
from .planner import CacheAwarePlanner, from_context
from .pruner import ContextItem, ContextPruner, PruneReport
from .router import HeuristicRouter, Router, RoutingDecision, Step
from .tokens import TokenEstimator, estimate_tokens


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

    def to_dict(self) -> dict:
        return asdict(self)


class TokenTrim:
    def __init__(self, client: ModelClient, token_budget: int = 4096, router: Router | None = None,
                 strong_model: str = "fake/strong", estimator: TokenEstimator = estimate_tokens):
        self.client = client
        self.token_budget = token_budget
        self.router = router or HeuristicRouter(strong_model=strong_model)
        self.strong_model = strong_model
        self.estimator = estimator
        self.pruner = ContextPruner(estimator)
        self.planner = CacheAwarePlanner(estimator)
        self.records: list[StepRecord] = []

    def complete(self, items: list[ContextItem], step: Step, max_tokens: int = 256,
                 mode: str = "tokentrim") -> tuple[ModelResponse, StepRecord]:
        if mode not in {"baseline", "tokentrim"}:
            raise ValueError("mode must be baseline or tokentrim")
        if mode == "tokentrim":
            kept, report = self.pruner.prune(items, self.token_budget)
        else:
            kept = list(items)
            total = sum(self.estimator(i.text) for i in kept)
            report = PruneReport(total, total, [], [])
        plan = self.planner.plan([from_context(i) for i in kept], reorder=mode == "tokentrim")
        decision = (self.router.route(replace(step, context_tokens=report.tokens_after)) if mode == "tokentrim"
                    else RoutingDecision(self.strong_model, "Baseline always uses strong model"))
        # Fail before any provider call if the configured model has no known price.
        cost(decision.model, 0, 0, 0)
        if callable(getattr(self.client, "set_plan", None)):
            self.client.set_plan(plan)
        response = self.client.complete(plan.messages(), decision.model, max_tokens)
        usage = response.usage
        record = StepRecord(mode, decision, asdict(usage), cost(decision.model, usage.input, usage.cached_input, usage.output),
                            report, plan.stable_prefix_hash, plan.cacheable_tokens, plan.warnings)
        self.records.append(record)
        return response, record
