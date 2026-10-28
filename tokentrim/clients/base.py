from dataclasses import dataclass
from typing import Protocol

from ..planner import PromptPlan


@dataclass(frozen=True)
class Usage:
    input: int
    cached_input: int
    output: int
    cache_write: int = 0

    def __post_init__(self):
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0
               for n in (self.input, self.cached_input, self.output, self.cache_write)):
            raise ValueError("Usage counts must be nonnegative integers")
        if self.cached_input > self.input:
            raise ValueError("Cached input cannot exceed total input")
        if self.cache_write > self.input - self.cached_input:
            raise ValueError("Cache writes must be a subset of uncached input")


@dataclass(frozen=True)
class ModelResponse:
    text: str
    usage: Usage


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, str]], model: str, max_tokens: int) -> ModelResponse: ...


class PlannedModelClient(ModelClient, Protocol):
    def set_plan(self, plan: PromptPlan) -> None: ...
