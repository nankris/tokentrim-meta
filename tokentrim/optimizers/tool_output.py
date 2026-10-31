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


def compress_test(text: str, protect=None) -> str:
    lines = text.splitlines()
    out, passing, in_fail = [], [], False
    for line in lines:
        if FAIL_START.search(line):
            in_fail = True
        elif in_fail and re.match(r"^=+ .*\S.* =+\s*$", line):
            in_fail = False  # next "==== section ====" header ends the FAILURES block
        if TEST_SUMMARY.search(line) or (protect or PROTECT).search(line) or in_fail:
            if passing:
                out.append(_note(len(passing), "passing-test lines", passing[0]))
                passing = []
            out.append(line)
        elif not line.strip():
            continue  # blank separator lines outside failure blocks carry no information
        elif PASS_LINE.search(line):
            passing.append(line)
        else:  # unknown line outside a failure block: keep (cheap insurance)
            if passing:
                out.append(_note(len(passing), "passing-test lines", passing[0]))
                passing = []
            out.append(line)
    if passing:
        out.append(_note(len(passing), "passing-test lines", passing[0]))
    return "\n".join(out)


def compress_log(text: str, protect=None) -> str:
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
    keep = [k for k, l in enumerate(collapsed) if (protect or PROTECT).search(l)]
    keep += list(range(min(5, len(collapsed)))) + list(range(max(0, len(collapsed) - 5), len(collapsed)))
    body = _keep_with_context(collapsed, sorted(set(keep)), context=1)
    # Say WHAT was omitted (by log level) so the model can trust the view instead of re-fetching it.
    shown = set()
    for k in sorted(set(keep)):
        shown.update(range(max(0, k - 1), min(len(collapsed), k + 2)))
    levels = {}
    for k, l in enumerate(collapsed):
        if k not in shown:
            m = LEVEL.search(l)
            levels[m.group(1).upper() if m else "other"] = levels.get(m.group(1).upper() if m else "other", 0) + 1
    if levels:
        body.append("[omitted lines by level: " + ", ".join(f"{k} {v}" for k, v in sorted(levels.items(), key=lambda x: -x[1]))
                    + "; every WARN/ERROR/FATAL line and every line mentioning a task identifier is shown above]")
    return "\n".join(body)


LEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|FATAL|CRITICAL)\b", re.I)


def _compact(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _record_arrays(v, ptr=""):
    """JSON Pointer paths of arrays of >= 4 objects (outermost only; nested ones stay inside their record)."""
    if isinstance(v, list) and len(v) >= 4 and all(isinstance(x, dict) for x in v):
        return [ptr]
    out = []
    if isinstance(v, dict):
        for k, x in v.items():
            out += _record_arrays(x, f"{ptr}/{str(k).replace('~', '~0').replace('/', '~1')}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            out += _record_arrays(x, f"{ptr}/{i}")
    return out


def _get(v, ptr):
    for part in [p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:]]:
        v = v[int(part)] if isinstance(v, list) else v[part]
    return v


def _ancestors(rows, keep):
    """Also keep the parent chain of kept records (``parent``/``parent_id``-style keys pointing at an id key)."""
    id_key = next((k for k in ("id", "span_id", "node_id", "uid", "key") if all(k in r for r in rows)), None)
    par_key = next((k for k in rows[0] if "parent" in k.lower()), None) if rows else None
    if not id_key or not par_key:
        return keep
    index = {r.get(id_key): i for i, r in enumerate(rows)}
    out, todo = set(keep), list(keep)
    while todo:
        p = rows[todo.pop()].get(par_key)
        j = index.get(p) if isinstance(p, (str, int)) else None
        if j is not None and j not in out:
            out.add(j)
            todo.append(j)
    return out


def compress_json(text: str, budget_tokens: int = 1500, protect=None, mode: str = "conservative") -> str:
    """Structure-preserving JSON view (v5.1, issue 69). Never flattens records into a column table: every
    record is one compact JSON object on its own line, prefixed by its JSON Pointer, so each value stays next to
    its own key and its siblings (ids, parent links, status, release). Records matching ``protect`` (errors,
    task identifiers) are indexed in a header line.

    ``mode="conservative"`` (default) is lossless: whitespace removal only. ``mode="lossy"`` may additionally
    drop unflagged records over ``budget_tokens``; flagged records, their parent chain and the first/last rows
    are always kept, and every gap is announced with its pointer range."""
    value = json.loads(text)
    pat = protect or PROTECT
    arrays = _record_arrays(value)
    if not arrays:
        return _compact(value)
    skeleton = json.loads(_compact(value))
    for ptr in arrays:
        n = len(_get(value, ptr))
        if ptr == "":
            skeleton = f"<{n} records /0../{n - 1}, one per line below>"
            break
        parent, last = _get(skeleton, ptr.rsplit("/", 1)[0] or ""), ptr.rsplit("/", 1)[1].replace("~1", "/").replace("~0", "~")
        parent[int(last) if isinstance(parent, list) else last] = f"<{n} records {ptr}/0..{ptr}/{n - 1}, one per line below>"
    sections, flagged = [], []
    for ptr in arrays:
        rows = _get(value, ptr)
        lines = [_compact(r) for r in rows]
        hit = [i for i, l in enumerate(lines) if pat.search(l)]
        flagged += [f"{ptr}/{i}" for i in hit]
        sections.append((ptr, rows, lines, hit))
    head = [_compact(skeleton)]
    if flagged:
        head.append("[records with errors/warnings or task identifiers: " + ", ".join(flagged[:40]) +
                    (f" (+{len(flagged) - 40} more)" if len(flagged) > 40 else "") + "]")
    full = head + [f"{ptr}/{i} {l}" for ptr, _, lines, _ in sections for i, l in enumerate(lines)]
    out = "\n".join(full)
    if mode != "lossy" or estimate_tokens(out) <= budget_tokens:
        return out
    body = list(head)
    for ptr, rows, lines, hit in sections:
        keep = _ancestors(rows, set(hit)) | set(range(min(3, len(lines)))) | set(range(max(0, len(lines) - 2), len(lines)))
        gap = []
        for i, l in enumerate(lines):
            if i in keep:
                if gap:
                    body.append(f"[... {len(gap)} records {ptr}/{gap[0]}..{ptr}/{gap[-1]} omitted]")
                    gap = []
                body.append(f"{ptr}/{i} {l}")
            else:
                gap.append(i)
        if gap:
            body.append(f"[... {len(gap)} records {ptr}/{gap[0]}..{ptr}/{gap[-1]} omitted]")
    return "\n".join(body)


def compress_diff(text: str, protect=None) -> str:
    lines = text.splitlines()
    keep = [i for i, l in enumerate(lines)
            if l.startswith(("diff --git", "--- ", "+++ ", "@@", "+", "-", "new file", "deleted file", "rename "))
            or (protect or PROTECT).search(l)]
    return "\n".join(_keep_with_context(lines, keep, context=1))


def compress_text(text: str, protect=None) -> str:
    lines = text.splitlines()
    if len(lines) < 30:
        return text
    keep = [i for i, l in enumerate(lines) if (protect or PROTECT).search(l)] + list(range(15)) + \
           list(range(len(lines) - 10, len(lines)))
    return "\n".join(_keep_with_context(lines, sorted(set(keep)), context=1))


COMPRESSORS = {"test": compress_test, "log": compress_log, "json": compress_json, "diff": compress_diff,
               "text": compress_text}


class ToolOutputCompressor:
    # Plain text (source files, prose) is left alone by default: the model usually asked for exactly
    # that content and pilot runs showed it then retrieves the original anyway (net cost increase).
    DEFAULT_KINDS = ("test", "log", "json", "diff")

    def __init__(self, store: OriginalStore | None = None, min_tokens: int = 400, max_ratio: float = 0.8,
                 kinds=DEFAULT_KINDS, json_mode: str = "lossy"):
        self.store = store or OriginalStore()
        self.min_tokens, self.max_ratio, self.kinds = min_tokens, max_ratio, tuple(kinds)
        self.json_mode = json_mode  # "lossy" (flagged records + parent chain kept) or "conservative" (lossless)

    def compress(self, text: str, keep_terms=()) -> Compressed:
        """``keep_terms``: identifiers from the task (e.g. "r-417", "job ci-4000"); lines containing them are
        protected too (query-aware). Callers must pass a set that is stable for a given message."""
        protect = PROTECT
        terms = sorted({t for t in keep_terms if len(t) >= 3})
        if terms:
            protect = re.compile(PROTECT.pattern + "|" + "|".join(re.escape(t) for t in terms), PROTECT.flags)
        before = estimate_tokens(text)
        if before < self.min_tokens or "retrieve_original(" in text:
            return Compressed(text, "skip", None, before, before, "")
        kind = classify(text)
        if kind not in self.kinds:
            return Compressed(text, kind, None, before, before, "")
        try:
            body = (compress_json(text, protect=protect, mode=self.json_mode) if kind == "json"
                    else COMPRESSORS[kind](text, protect=protect))
        except Exception:  # fail open
            return Compressed(text, kind, None, before, before, f"tool output ({kind}) left unchanged: compressor error")
        ref = self.store.put(text, "orig")
        out = (f"{body}\n[TokenTrim: {kind} output compressed {before:,}->~{estimate_tokens(body):,} tokens; "
               f"errors, failures, summaries and task identifiers kept verbatim; "
               f"full original only if a needed detail is missing: retrieve_original(\"{ref}\")]")
        after = estimate_tokens(out)
        if after > self.max_ratio * before:
            return Compressed(text, kind, None, before, before,
                              f"tool output ({kind}, {before:,} tok) left unchanged: saving too small")
        return Compressed(out, kind, ref, before, after,
                          f"Compressed {kind} tool output {before:,}->{after:,} tokens "
                          f"(-{100 * (before - after) / before:.0f}%), original recoverable as {ref}")


ID_TERM = re.compile(r"\b(?=[\w.-]*\d)(?=[\w.-]*[A-Za-z])[A-Za-z][\w.-]*[-_.][\w.-]*\w\b|\b[A-Za-z]+\d+[A-Za-z\d]*\b")


def task_terms(texts) -> set[str]:
    """Identifier-like tokens (contain a letter and a digit, e.g. r-417, ci-4000, w-12) from task text."""
    out = set()
    for t in texts:
        if isinstance(t, str):
            out |= {m.group(0) for m in ID_TERM.finditer(t)}
    return out
