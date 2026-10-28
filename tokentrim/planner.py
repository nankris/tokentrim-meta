"""Order stable segments first and estimate exact segment-prefix reuse."""
import hashlib
import json
from dataclasses import dataclass

from .pruner import ContextItem
from .tokens import TokenEstimator, estimate_tokens


@dataclass(frozen=True)
class PromptSegment:
    id: str
    text: str
    kind: str = "message"
    role: str = "user"
    stable: bool = False


@dataclass(frozen=True)
class PromptPlan:
    segments: list[PromptSegment]
    stable_prefix_hash: str
    stable_prefix_tokens: int
    cacheable_tokens: int
    warnings: list[str]

    def messages(self) -> list[dict[str, str]]:
        return [{"role": s.role, "content": s.text} for s in self.segments]


def segment_key(segment: PromptSegment) -> tuple[str, str, str]:
    # IDs are bookkeeping; role, kind, and actual bytes affect prefix equivalence.
    return segment.role, segment.kind, segment.text


def from_context(item: ContextItem) -> PromptSegment:
    return PromptSegment(item.id, item.text, item.kind,
                         "system" if item.kind == "system" else item.role,
                         item.kind in {"system", "tool_schema", "repo_map"} or item.pinned)


class CacheAwarePlanner:
    STABLE_KINDS = {"system", "tool_schema", "tool_schemas", "repo_map", "pinned_file"}

    def __init__(self, estimator: TokenEstimator = estimate_tokens):
        self.estimator = estimator
        self._previous: list[PromptSegment] = []

    def plan(self, segments: list[PromptSegment], *, reorder: bool = True) -> PromptPlan:
        def stable(s):
            return s.stable or s.kind in self.STABLE_KINDS
        seen_volatile = False
        warnings = []
        for s in segments:
            if not stable(s):
                seen_volatile = True
            elif seen_volatile:
                warnings.append(f"Volatile content precedes stable segment {s.id}; cache reuse may suffer")
        ordered = sorted(segments, key=lambda s: not stable(s)) if reorder else list(segments)
        prefix = []
        for s in ordered:
            if not stable(s):
                break
            prefix.append(s)
        cacheable = 0
        for current, previous in zip(ordered, self._previous):
            if segment_key(current) != segment_key(previous):
                break
            cacheable += self.estimator(current.text)
        digest = hashlib.sha256(json.dumps([segment_key(s) for s in prefix], ensure_ascii=False).encode()).hexdigest()
        self._previous = list(ordered)
        return PromptPlan(ordered, digest, sum(self.estimator(s.text) for s in prefix), cacheable, warnings)
