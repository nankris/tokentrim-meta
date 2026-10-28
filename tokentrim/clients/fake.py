"""Deterministic simulation, not an editing agent or a provider cache emulator."""
import hashlib
import json

from .base import ModelResponse, Usage
from ..planner import PromptPlan
from ..tokens import TokenEstimator, estimate_tokens


class FakeModelClient:
    def __init__(self, estimator: TokenEstimator = estimate_tokens):
        self.estimator = estimator
        self._prefix_cache: dict[tuple[str, str], int] = {}
        self._plan: PromptPlan | None = None

    def set_plan(self, plan: PromptPlan) -> None:
        self._plan = plan

    def complete(self, messages: list[dict[str, str]], model: str, max_tokens: int) -> ModelResponse:
        if max_tokens < 0:
            raise ValueError("max_tokens must be nonnegative")
        plan, self._plan = self._plan, None
        total = sum(self.estimator(m["content"]) for m in messages)
        cached = 0
        if plan is not None:
            if messages != plan.messages():
                raise ValueError("Messages do not match the supplied plan")
            key = (model, plan.stable_prefix_hash)
            cached = min(total, self._prefix_cache.get(key, 0))
            self._prefix_cache[key] = plan.stable_prefix_tokens
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:12]
        text = f"FAKE simulated response {digest}; no repository edits performed."
        text = text[:max_tokens * 4]
        return ModelResponse(text, Usage(total, cached, min(max_tokens, self.estimator(text))))
