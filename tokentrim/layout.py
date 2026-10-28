"""Deterministic cache layout; provider cache behavior remains an assumption."""
import json
import re
from dataclasses import replace

from .planner import PromptPlan, PromptSegment

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?\b")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b(?:request[_ -]?id\s*[:=]\s*)?[0-9a-f]{16,}\b", re.I)
_TMP = re.compile(r"/tmp/[A-Za-z0-9_.-]*\d[A-Za-z0-9_.-]*")


def stable_json(value) -> str:
    """Serialize JSON with byte-stable key ordering."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.rstrip().splitlines())


def deterministic_segments(segments: list[PromptSegment]) -> list[PromptSegment]:
    # Only stable kinds move forward; everything else keeps its append order. Sorting
    # conversation kinds against each other would reshuffle history and break the cache.
    rank = {"system": 0, "tool_schema": 1, "tool_schemas": 1, "repo_map": 2, "pinned_file": 3}
    normalized = []
    for segment in segments:
        text = normalize_text(segment.text)
        if segment.kind in {"tool_schema", "tool_schemas"}:
            try:
                text = stable_json(json.loads(text))
            except (ValueError, TypeError):
                pass
        normalized.append(replace(segment, text=text))
    ordered = sorted(enumerate(normalized), key=lambda pair: (rank.get(pair[1].kind, 4), pair[0]))
    return [pair[1] for pair in ordered]


def lint_stable_prefix(segments: list[PromptSegment]) -> list[str]:
    warnings = []
    for segment in segments:
        if not (segment.stable or segment.kind in {"system", "tool_schema", "tool_schemas", "repo_map", "pinned_file"}):
            continue
        checks = ((_DATE, "date or timestamp"), (_UUID, "UUID"), (_HEX, "hex request id"),
                  (re.compile(r"current time", re.I), "Current time"), (_TMP, "absolute temporary path"))
        for pattern, label in checks:
            if pattern.search(segment.text):
                warnings.append(f"{segment.id}: stable segment contains {label}")
        try:
            value = json.loads(segment.text)
            if isinstance(value, dict) and list(value) != sorted(value):
                warnings.append(f"{segment.id}: JSON keys are not sorted")
        except (ValueError, TypeError):
            pass
    return warnings


def cache_breakpoints(plan: PromptPlan, max_breakpoints: int = 4) -> list[int]:
    """Return metadata-only marker locations after stable semantic groups."""
    if max_breakpoints < 0:
        raise ValueError("max_breakpoints must be nonnegative")
    groups = ({"system", "tool_schema", "tool_schemas"}, {"repo_map", "pinned_file"}, {"message"})
    found = []
    for kinds in groups:
        positions = [i for i, s in enumerate(plan.segments) if s.kind in kinds]
        if positions:
            found.append(max(positions))
    return found[:max_breakpoints]


class CompactionCheckpoint:
    """Records an approved history rewrite after dollar breakeven analysis."""
    def __init__(self, approved: bool, analysis: dict):
        self.approved = approved
        self.analysis = analysis


class AppendOnlyHistory:
    """Conversation history that rejects rewrites without an approved checkpoint."""
    def __init__(self, segments=()):
        self._segments = list(segments)

    @property
    def segments(self):
        return list(self._segments)

    def append(self, segment: PromptSegment):
        self._segments.append(segment)

    def compact(self, segments: list[PromptSegment], checkpoint: CompactionCheckpoint):
        if not checkpoint.approved or not checkpoint.analysis.get("should_compact", False):
            raise PermissionError("History compaction requires an approved dollar-breakeven checkpoint")
        self._segments = list(segments)
