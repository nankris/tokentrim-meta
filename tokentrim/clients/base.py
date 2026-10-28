from dataclasses import dataclass
from typing import Protocol

from ..planner import PromptPlan


@dataclass(frozen=True)
class Usage:
    input: int
    cached_input: int
    output: int

    def __post_init__(self):
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in (self.input, self.cached_input, self.output)):
            raise ValueError("Usage counts must be nonnegative integers")
        if self.cached_input > self.input:
            raise ValueError("Cached input cannot exceed total input")


@dataclass(frozen=True)
class ModelResponse:
    text: str
    usage: Usage


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, str]], model: str, max_tokens: int) -> ModelResponse: ...


class PlannedModelClient(ModelClient, Protocol):
    def set_plan(self, plan: PromptPlan) -> None: ...
