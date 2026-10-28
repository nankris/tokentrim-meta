"""Prune context without mutating caller-owned items."""
from dataclasses import dataclass, replace
from typing import Literal

from .tokens import TokenEstimator, estimate_tokens


@dataclass(frozen=True)
class ContextItem:
    id: str
    kind: Literal["file", "tool_output", "message", "system", "tool_schema", "repo_map"]
    text: str
    turn: int = 0
    referenced: bool = False
    reference_count: int = 0
    pinned: bool = False
    role: str = "user"

    def __post_init__(self):
        if self.kind not in {"file", "tool_output", "message", "system", "tool_schema", "repo_map"}:
            raise ValueError(f"Invalid context kind: {self.kind}")
        if self.reference_count < 0:
            raise ValueError("reference_count must be nonnegative")


@dataclass(frozen=True)
class PruneReport:
    tokens_before: int
    tokens_after: int
    dropped_ids: list[str]
    truncated_ids: list[str]


class BudgetExceededError(ValueError):
    """The budget cannot hold mandatory system, pinned, and latest user items."""


class ContextPruner:
    def __init__(self, estimator: TokenEstimator = estimate_tokens, old_tool_lines: int | None = 12):
        # None disables routine truncation of older tool outputs (the trim saver owns that);
        # outputs are then shrunk only when they would not otherwise fit the budget.
        if old_tool_lines is not None and old_tool_lines < 2:
            raise ValueError("old_tool_lines must be at least 2")
        self.estimator = estimator
        self.old_tool_lines = old_tool_lines

    def _truncate(self, text: str, line_limit: int) -> str:
        lines = text.splitlines()
        if len(lines) <= line_limit:
            return text
        head = (line_limit + 1) // 2
        tail = line_limit // 2
        return "\n".join(lines[:head] + [f"[... {len(lines) - line_limit} lines trimmed ...]"] + lines[-tail:])

    def prune(self, items: list[ContextItem], token_budget: int) -> tuple[list[ContextItem], PruneReport]:
        if token_budget < 0:
            raise ValueError("token_budget must be nonnegative")
        if len({i.id for i in items}) != len(items):
            raise ValueError("Context ids must be unique")
        before = sum(self.estimator(i.text) for i in items)
        users = [n for n, i in enumerate(items) if i.kind == "message" and i.role == "user"]
        latest_user = max(users, key=lambda n: (items[n].turn, n), default=None)
        mandatory = {n for n, i in enumerate(items)
                     if i.kind in {"system", "tool_schema"} or i.pinned or n == latest_user}
        selected = {n: items[n] for n in mandatory}
        used = sum(self.estimator(i.text) for i in selected.values())
        if used > token_budget:
            raise BudgetExceededError(f"Mandatory context needs {used} tokens; budget is {token_budget}")
        newest_turn = max((i.turn for i in items), default=0)
        truncated = []
        for n in sorted(range(len(items)), key=lambda n: (items[n].turn, n), reverse=True):
            if n in mandatory:
                continue
            item = items[n]
            if item.kind == "file" and not (item.referenced or item.reference_count):
                continue
            candidate = item
            if self.old_tool_lines is not None and item.kind == "tool_output" and item.turn < newest_turn:
                candidate = replace(item, text=self._truncate(item.text, self.old_tool_lines))
            remaining = token_budget - used
            if self.estimator(candidate.text) > remaining and item.kind == "tool_output":
                # Shrink both ends together; never cut or miscount the trim marker.
                ceiling = self.old_tool_lines or len(item.text.splitlines()) - 1
                for limit in range(min(ceiling, len(item.text.splitlines()) - 1), 1, -1):
                    shortened = self._truncate(item.text, limit)
                    if self.estimator(shortened) <= remaining:
                        candidate = replace(item, text=shortened)
                        break
            size = self.estimator(candidate.text)
            if size <= remaining:
                selected[n] = candidate
                used += size
                if candidate.text != item.text:
                    truncated.append(item.id)
        kept = [selected[n] for n in sorted(selected)]
        return kept, PruneReport(before, used, [i.id for n, i in enumerate(items) if n not in selected], truncated)
