"""ToolOutputCompressor: deterministic, reversible compression of large tool results.

A content-type router picks one compressor (test output, log, JSON, diff, generic text). Every compressor
keeps protected lines verbatim: exceptions/tracebacks, failing assertions, error/warning lines, exit codes,
``file:line`` references and summary counts. Lossless rewrites (minified JSON, homogeneous arrays as a
column table) are tried before lossy ones. The exact original is stored and the model-visible text ends
with ``retrieve_original("<ref>")`` so nothing is unrecoverable. Same input -> same output (cache safe).
"""
from dataclasses import dataclass
import json
import re

from ..store import OriginalStore
from ..tokens import estimate_tokens

PROTECT = re.compile(
    r"Traceback|Exception|Error\b|error[:\[]|\bERROR\b|\bFATAL\b|\bCRITICAL\b|\bWARN(ING)?\b|\bFAIL(ED|URE|S)?\b|"
    r"assert|AssertionError|panic|segfault|exit(ed)? (code|status)|returned non-zero|\bcode[ =:]\d+|"
    r"^E\s|^>\s|File \".+\", line \d+|[\w./-]+\.\w+:\d+|line \d+", re.I)
TEST_SUMMARY = re.compile(r"((?<![\w.])\d+\s+(passed|failed|errors?|skipped|xfailed|deselected|warnings?))|"
                          r"^Ran \d+ tests?|^(OK|FAILED)\b|^Tests?:|^=+ .*(passed|failed|error).* =+$|"
                          r"Test Suites?:|^\s*(\d+) (passing|failing|pending)", re.I)
PASS_LINE = re.compile(r"(\.\.\.\s*ok$|\bPASS(ED)?\b|✓|\bok\b\s*$|^\s*\.+\s*$|\[\s*\d+%\])", re.I)
FAIL_START = re.compile(r"^(=+|_+|-+)?\s*(FAIL|ERROR|FAILURES|ERRORS)\b|^_{3,} .* _{3,}$|^FAIL:|^ERROR:|"
                        r"^\s*●|^Traceback", re.I)
TS_PREFIX = re.compile(r"^\[?\d{4}-\d{2}-\d{2}[T ][\d:.,]+Z?\]?\s*|^\[?\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\]?\s*")


@dataclass(frozen=True)
class Compressed:
    text: str
    kind: str
    ref: str | None
    tokens_before: int
    tokens_after: int
    explanation: str


def classify(text: str) -> str:
    head = text.lstrip()[:1]
    if head in "[{":
        try:
            json.loads(text)
            return "json"
        except ValueError:
            pass
    sample = text[:20000]
    if re.search(r"^diff --git |^@@ -\d+(,\d+)? \+\d+", sample, re.M):
        return "diff"
    if re.search(r"(^=+ test session starts|^collected \d+ items|\.\.\. ok$|^Ran \d+ tests|PASSED|FAILED|"
                 r"Test Suites:|^\s*✓|^ok \d+ |^not ok \d+ )", sample, re.M):
        return "test"
    lines = sample.splitlines()
    if lines and sum(bool(TS_PREFIX.match(l)) or bool(re.search(r"\b(INFO|DEBUG|WARN|ERROR)\b", l))
                     for l in lines) > 0.5 * len(lines):
        return "log"
    return "text"


def _note(count: int, what: str, example: str | None = None) -> str:
    ex = f" e.g. {example.strip()[:80]!r}" if example else ""
    return f"[... {count:,} {what} omitted{ex}]"


def _keep_with_context(lines, keep_idx, context=1):
    out, skipped, last = [], [], -1
    wanted = set()
    for i in keep_idx:
        wanted.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    for i, line in enumerate(lines):
        if i in wanted:
            if skipped:
                out.append(_note(len(skipped), "lines", skipped[0]))
                skipped = []
            out.append(line)
        else:
            skipped.append(line)
    if skipped:
        out.append(_note(len(skipped), "lines", skipped[0]))
    return out


def compress_test(text: str) -> str:
    lines = text.splitlines()
    out, passing, in_fail = [], [], False
    for line in lines:
        if FAIL_START.search(line):
            in_fail = True
        if TEST_SUMMARY.search(line) or PROTECT.search(line) or in_fail:
            if passing:
                out.append(_note(len(passing), "passing-test lines", passing[0]))
                passing = []
            out.append(line)
            if in_fail and (not line.strip() or re.match(r"^(=+|-{10,})\s*$", line)) and len(out) > 1:
                in_fail = False
        elif PASS_LINE.search(line) or not line.strip():
            passing.append(line)
        else:  # unknown line outside a failure block: keep (cheap insurance)
            if passing:
                out.append(_note(len(passing), "passing-test lines", passing[0]))
                passing = []
            out.append(line)
    if passing:
        out.append(_note(len(passing), "passing-test lines", passing[0]))
    return "\n".join(out)


def compress_log(text: str) -> str:
    lines = text.splitlines()
    # 1) collapse runs of lines identical after removing a leading timestamp (count kept)
    collapsed, i = [], 0
    while i < len(lines):
        key = TS_PREFIX.sub("", lines[i])
        j = i + 1
        while j < len(lines) and TS_PREFIX.sub("", lines[j]) == key:
            j += 1
        collapsed.append(lines[i] + (f"  [x{j - i} identical lines through {lines[j-1][:30].strip()!r}]"
                                     if j - i > 1 else ""))
        i = j
    keep = [k for k, l in enumerate(collapsed) if PROTECT.search(l)]
    keep += list(range(min(5, len(collapsed)))) + list(range(max(0, len(collapsed) - 5), len(collapsed)))
    return "\n".join(_keep_with_context(collapsed, sorted(set(keep)), context=1))


def _table(rows: list[dict]) -> str | None:
    keys = list(rows[0])
    if not all(isinstance(r, dict) and list(r) == keys for r in rows) or len(rows) < 4:
        return None
    if any(isinstance(v, (dict, list)) for r in rows for v in r.values()):
        return None
    body = [" | ".join(keys)] + [" | ".join(json.dumps(r[k], ensure_ascii=False) for k in keys) for r in rows]
    return f"[table: {len(rows)} rows; columns: {', '.join(keys)}]\n" + "\n".join(body)


def compress_json(text: str, budget_tokens: int = 1500) -> str:
    value = json.loads(text)

    def walk(v):
        if isinstance(v, list) and v and isinstance(v[0], dict):
            table = _table(v)
            if table is not None:
                return {"__table__": table}
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    restructured = walk(value)
    minified = json.dumps(restructured, ensure_ascii=False, separators=(",", ":"))
    # tables are rendered as plain text blocks after the JSON skeleton
    tables = []

    def pull(v, path="$"):
        if isinstance(v, dict) and "__table__" in v and len(v) == 1:
            tables.append((path, v["__table__"]))
            return f"<table {path}>"
        if isinstance(v, dict):
            return {k: pull(x, f"{path}.{k}") for k, x in v.items()}
        if isinstance(v, list):
            return [pull(x, f"{path}[{i}]") for i, x in enumerate(v)]
        return v
    skeleton = json.dumps(pull(restructured), ensure_ascii=False, separators=(",", ":"))
    out = skeleton + "".join(f"\n{p}:\n{t}" for p, t in tables)
    if estimate_tokens(out) <= budget_tokens or not tables:
        return out if len(out) < len(minified) else minified
    # lossy step: long tables keep header, protected rows, first/last rows
    final = [skeleton]
    for p, t in tables:
        rows = t.splitlines()
        head, body = rows[:2], rows[2:]
        keep = [k for k, r in enumerate(body) if PROTECT.search(r)] + list(range(10)) + \
               list(range(max(0, len(body) - 3), len(body)))
        final.append(f"\n{p}:\n" + "\n".join(head + _keep_with_context(body, sorted(set(k for k in keep if k < len(body))), 0)))
    return "".join(final)


def compress_diff(text: str) -> str:
    lines = text.splitlines()
    keep = [i for i, l in enumerate(lines)
            if l.startswith(("diff --git", "--- ", "+++ ", "@@", "+", "-", "new file", "deleted file", "rename "))
            or PROTECT.search(l)]
    return "\n".join(_keep_with_context(lines, keep, context=1))


def compress_text(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 30:
        return text
    keep = [i for i, l in enumerate(lines) if PROTECT.search(l)] + list(range(15)) + \
           list(range(len(lines) - 10, len(lines)))
    return "\n".join(_keep_with_context(lines, sorted(set(keep)), context=1))


COMPRESSORS = {"test": compress_test, "log": compress_log, "json": compress_json, "diff": compress_diff,
               "text": compress_text}


class ToolOutputCompressor:
    def __init__(self, store: OriginalStore | None = None, min_tokens: int = 400, max_ratio: float = 0.8):
        self.store = store or OriginalStore()
        self.min_tokens, self.max_ratio = min_tokens, max_ratio

    def compress(self, text: str) -> Compressed:
        before = estimate_tokens(text)
        if before < self.min_tokens or "retrieve_original(" in text:
            return Compressed(text, "skip", None, before, before, "")
        kind = classify(text)
        try:
            body = COMPRESSORS[kind](text)
        except Exception:  # fail open
            return Compressed(text, kind, None, before, before, f"tool output ({kind}) left unchanged: compressor error")
        ref = self.store.put(text, "orig")
        out = (f"{body}\n[TokenTrim: {kind} output compressed {before:,}->~{estimate_tokens(body):,} tokens; "
               f"protected lines kept verbatim; exact original: retrieve_original(\"{ref}\")]")
        after = estimate_tokens(out)
        if after > self.max_ratio * before:
            return Compressed(text, kind, None, before, before,
                              f"tool output ({kind}, {before:,} tok) left unchanged: saving too small")
        return Compressed(out, kind, ref, before, after,
                          f"Compressed {kind} tool output {before:,}->{after:,} tokens "
                          f"(-{100 * (before - after) / before:.0f}%), original recoverable as {ref}")
