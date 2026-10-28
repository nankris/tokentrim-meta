"""Restorable tool-output compaction; token counts use the local estimator."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from .tokens import estimate_tokens

ERROR = re.compile(r'Traceback|Error|Exception|FAILED|FAIL:|assert|error:|^E\s+|File ".+", line \d+', re.I)
PASS = re.compile(r"^(?:\.*|.*\b(?:ok|PASSED)\b.*)$", re.I)


class OutputStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else None
        self._values = {}
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, text: str) -> str:
        output_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        self._values[output_id] = text
        if self.directory:
            (self.directory / output_id).write_text(text, encoding="utf-8")
        return output_id

    def get(self, output_id: str) -> str:
        if output_id in self._values:
            return self._values[output_id]
        if self.directory:
            return (self.directory / output_id).read_text(encoding="utf-8")
        raise KeyError(output_id)

    load = get


@dataclass(frozen=True)
class CompactionReport:
    lines_before: int
    lines_after: int
    tokens_before: int
    tokens_after: int
    kept_error_lines: int
    output_id: str


def compact_tool_output(text: str, *, kind="auto", max_lines=40, store: OutputStore | None = None):
    if kind not in {"auto", "test_log", "traceback", "build_log", "generic"} or max_lines < 3:
        raise ValueError("Invalid compaction options")
    store = store or OutputStore()
    output_id = store.save(text)
    lines = text.splitlines()
    if len(lines) <= max_lines:
        report = CompactionReport(len(lines), len(lines), estimate_tokens(text), estimate_tokens(text),
                                  sum(bool(ERROR.search(x)) for x in lines), output_id)
        return text, report
    # Collapse identical consecutive lines, preserving an explicit count.
    collapsed = []
    i = 0
    def signature(line):
        # Treat changing counters/addresses as near-identical build noise.
        return re.sub(r"(?:0x)?[0-9a-f]{4,}|\d+", "#", line.strip(), flags=re.I)
    while i < len(lines):
        j = i + 1
        while j < len(lines) and signature(lines[j]) == signature(lines[i]) and not ERROR.search(lines[i]):
            j += 1
        collapsed.append(lines[i])
        if j - i > 1:
            collapsed.append(f"[repeated {j - i} times]")
        i = j
    errors = [(i, line) for i, line in enumerate(collapsed) if ERROR.search(line)]
    pass_count = sum(bool(PASS.match(line.strip())) for line in collapsed)
    budget = max(2, max_lines - len(errors) - 2)
    head = budget // 2
    tail = budget - head
    indices = set(range(min(head, len(collapsed)))) | set(range(max(0, len(collapsed) - tail), len(collapsed)))
    indices.update(i for i, _ in errors)
    kept = [collapsed[i] for i in sorted(indices)]
    if pass_count > 3:
        kept = [line for line in kept if not PASS.match(line.strip())]
        kept.append(f"[{pass_count} passing test lines collapsed]")
    # Exact, verifiable marker: original vs compacted line counts (collapse markers included).
    marker = (f"[... tool output compacted from {len(lines)} to {len(kept) + 1} lines; "
              f"errors kept; full output id={output_id} ...]")
    kept.insert(min(head, len(kept)), marker)
    result = "\n".join(kept)
    report = CompactionReport(len(lines), len(result.splitlines()), estimate_tokens(text), estimate_tokens(result),
                              len(errors), output_id)
    return result, report


def is_log_like(text: str, *, min_lines: int = 20, min_fraction: float = .2) -> bool:
    """True for test/build logs (pass/error lines or repeated noise), not grep hits or source."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < min_lines:
        return False
    signature = lambda line: re.sub(r"(?:0x)?[0-9a-f]{4,}|\d+", "#", line.strip(), flags=re.I)
    hit = re.compile(r"^\S+:\d+:")  # grep/compiler-style "path:line:" hits are content, not noise
    repeated = sum(1 for a, b in zip(lines, lines[1:]) if signature(a) == signature(b) and not hit.match(b))
    marked = sum(bool(PASS.match(line.strip()) or ERROR.search(line)) for line in lines)
    return (marked + repeated) / len(lines) >= min_fraction
