"""Visible-signal escalation; hidden-test outcomes must never feed this router."""
from dataclasses import dataclass

from .router import HeuristicRouter, RoutingDecision, Step


@dataclass(frozen=True)
class StepSignals:
    visible_test_failed: bool = False
    malformed_output: bool = False
    no_progress_steps: int = 0
    previous_model: str | None = None


@dataclass(frozen=True)
class EscalationDecision(RoutingDecision):
    escalated: bool = False
    cause: str | None = None


class CheapFirstRouter:
    """Temporal routing base: every step starts on the cheap model; EscalatingRouter upgrades
    (stickily) on visible failure signals. Avoids cold strong-model prefills on planning steps."""
    def __init__(self, cheap_model: str, strong_model: str):
        self.cheap_model = cheap_model
        self.strong_model = strong_model

    def route(self, step: Step) -> RoutingDecision:
        return RoutingDecision(self.cheap_model, "cheap-first; escalate only on visible signals")


class EscalatingRouter:
    def __init__(self, base: HeuristicRouter, strong_model: str, max_no_progress_steps=2,
                 sticky=True, allow_contributor=False):
        if "contributor" in base.cheap_model.lower() and not allow_contributor:
            raise ValueError("Contributor models require allow_contributor=True")
        self.base = base
        self.strong_model = strong_model
        self.max_no_progress_steps = max_no_progress_steps
        self.sticky = sticky
        self._escalated = False

    def reset(self):
        self._escalated = False

    def route(self, step: Step, signals: StepSignals | None = None) -> EscalationDecision:
        signals = signals or StepSignals()
        cause = None
        if self.sticky and self._escalated:
            cause = "sticky escalation"
        elif signals.malformed_output:
            cause = "malformed output"
        elif signals.visible_test_failed and signals.previous_model == self.base.cheap_model:
            cause = "visible test failure after cheap-model edit"
        elif signals.no_progress_steps >= self.max_no_progress_steps:
            cause = "no progress"
        decision = self.base.route(step)
        if cause:
            self._escalated = True
            return EscalationDecision(self.strong_model, cause, True, cause)
        # The base router's conservative strong choice covers unclassified work.
        return EscalationDecision(decision.model, decision.reason, False, None)


@dataclass(frozen=True)
class SwitchCheck:
    """Dollar comparison of staying on the warm model vs switching to a cold one."""
    stay_model: str
    candidate_model: str
    stay_usd: float
    switch_usd: float
    switch: bool
    reason: str


def cache_aware_switch(cost_model, current_model: str, candidate_model: str, context_tokens: int,
                       *, horizon_steps: int = 4, output_tokens: int = 512,
                       current_warm_tokens: int | None = None, candidate_warm_tokens: int = 0) -> SwitchCheck:
    """Provider caches are per model: a switch re-bills the non-warm context on the new model.

    Estimate the next ``horizon_steps`` calls with a constant context. Staying reads the
    current model's warm prefix at its cached rate; switching pays a prefill of whatever is
    not already warm on the candidate (plus any write premium), then cached reads. This is
    meant for downgrade decisions; correctness escalations and upgrades bypass it.
    """
    if horizon_steps < 1 or context_tokens < 0 or output_tokens < 0:
        raise ValueError("Invalid switch-check inputs")
    a, b = cost_model.prices[current_model], cost_model.prices[candidate_model]
    warm_a = context_tokens if current_warm_tokens is None else min(context_tokens, current_warm_tokens)
    warm_b = min(context_tokens, max(0, candidate_warm_tokens))

    def run(rates, warm):
        first = warm * rates["cached_input"] + (context_tokens - warm) * max(rates["input"], rates.get("cache_write", rates["input"]))
        rest = (horizon_steps - 1) * context_tokens * rates["cached_input"]
        return (first + rest + horizon_steps * output_tokens * rates["output"]) / 1_000_000

    stay, switch = run(a, warm_a), run(b, warm_b)
    do_switch = switch < stay
    reason = (f"cache-aware: switch to {candidate_model} (est ${switch:.4f} vs stay ${stay:.4f})" if do_switch
              else f"cache-aware: stay on warm {current_model} (est ${stay:.4f} vs switch ${switch:.4f})")
    return SwitchCheck(current_model, candidate_model, stay, switch, do_switch, reason)
