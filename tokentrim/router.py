from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Step:
    kind: str = "edit"
    file_count: int = 1
    failed_test_retry: bool = False
    context_tokens: int = 0
    estimated_edit_lines: int = 10


@dataclass(frozen=True)
class RoutingDecision:
    model: str
    reason: str


class Router(Protocol):
    def route(self, step: Step) -> RoutingDecision: ...


class HeuristicRouter:
    def __init__(self, cheap_model: str = "fake/cheap", strong_model: str = "fake/strong",
                 long_context_tokens: int = 8000, small_edit_lines: int = 40):
        self.cheap_model = cheap_model
        self.strong_model = strong_model
        self.long_context_tokens = long_context_tokens
        self.small_edit_lines = small_edit_lines

    def route(self, step: Step) -> RoutingDecision:
        reason = None
        if step.failed_test_retry:
            reason = "Failed-test retry needs stronger reasoning"
        elif step.kind in {"plan", "planning"}:
            reason = "Planning needs stronger reasoning"
        elif step.context_tokens > self.long_context_tokens:
            reason = "Long context"
        elif step.kind == "edit" and step.file_count > 1:
            reason = "Multi-file edit"
        if reason:
            return RoutingDecision(self.strong_model, reason)
        if step.kind in {"read", "file_read", "summary", "summarize", "format", "formatting"}:
            return RoutingDecision(self.cheap_model, "Routine read, summary, or formatting")
        if step.kind == "edit" and step.file_count == 1 and step.estimated_edit_lines <= self.small_edit_lines:
            return RoutingDecision(self.cheap_model, "Single small edit")
        return RoutingDecision(self.strong_model, "Complex or unclassified step")
