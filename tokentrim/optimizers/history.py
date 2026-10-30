"""Structured history compaction with exact recovery (opt-in; P3 — kept out of defaults until it passes quality tests).

Older turns are replaced by ONE compact JSON state (goal, constraints, decisions, completed,
failed_attempts, open_tasks, facts, references) produced by a model call whose cost is counted. The exact
transcript of the compacted range is stored and retrievable. The compacted block is reused unchanged on
later calls of the same conversation (cache-stable) and only re-compacted after the uncompacted tail
grows past the threshold again.
"""
import hashlib
import json

from ..tokens import estimate_tokens

STATE_KEYS = ["goal", "constraints", "decisions", "completed", "failed_attempts", "open_tasks", "facts", "references"]

PROMPT = (
    "You compress a conversation into a JSON state object so the conversation can continue without the "
    "transcript. Output ONLY one JSON object with keys: goal (string), constraints (list), decisions (list), "
    "completed (list), failed_attempts (list), open_tasks (list), facts (object: every concrete value the user "
    "or assistant stated - names, numbers, amounts, dates, times, ids, file paths, settings - as key: value; "
    "when a value was changed later keep ONLY the latest value and note the change in decisions), references "
    "(list). Copy exact values verbatim. Do not invent anything. If a previous state is given, merge it.")


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        body = _text(m)
        if m.get("tool_calls"):
            body += " [tool calls: " + json.dumps([c.get("function") for c in m["tool_calls"]]) + "]"
        lines.append(f"{m.get('role', '?').upper()}: {body}")
    return "\n".join(lines)


def tokens_of(messages) -> int:
    return sum(estimate_tokens(json.dumps(m)) for m in messages)


def digest(messages) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()


def cut_index(body: list[dict], keep_recent: int) -> int:
    """Largest index c <= len(body)-keep_recent such that body[c] is a user message (clean boundary)."""
    c = max(0, len(body) - keep_recent)
    while c > 0 and body[c].get("role") != "user":
        c -= 1
    return c


def parse_state(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    state = json.loads(text[start:end + 1])
    if not isinstance(state, dict) or "facts" not in state:
        raise ValueError("compaction state missing required keys")
    return {k: state.get(k, [] if k != "facts" else {}) for k in STATE_KEYS}


def block_messages(state: dict, ref: str, n: int) -> list[dict]:
    body = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return [{"role": "user", "content": (
                f"[TokenTrim: the first {n} messages of this conversation were compacted into the structured "
                f"state below. Latest values win. Exact transcript: retrieve_original(\"{ref}\")]\n{body}")},
            {"role": "assistant", "content": "Understood. I will continue from this state."}]
