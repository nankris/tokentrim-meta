"""Stable request prefix for provider prompt caches (request level, OpenAI Chat Completions shape).

* tool schemas: sorted by name, dict keys sorted recursively (``required`` lists keep their order);
* leading system messages: volatile lines dropped by default (timestamps, UUIDs, request ids). On the
  real Meta API moving them to a trailing message did NOT restore cache hits (issue 55); dropping did.
  ``keep_date=True`` keeps a day-level ``Current date: YYYY-MM-DD`` line instead (changes once a day);
* optional padding of the stable system text to a multiple of N estimated tokens (off by default).
Conversation messages are never reordered.
"""
import json
import re

from ..tokens import estimate_tokens

_TS = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)\b")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_VOLATILE = (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"), _UUID,
             re.compile(r"\b(request|trace|session|correlation)[_ -]?id\s*[:=]", re.I),
             re.compile(r"\bcurrent (time|timestamp)\b", re.I), re.compile(r"\bunix time\b", re.I))


def sort_keys(value):
    if isinstance(value, dict):
        return {k: sort_keys(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [sort_keys(v) for v in value]
    return value


def stable_tools(tools: list[dict]) -> list[dict]:
    return sorted((sort_keys(t) for t in tools),
                  key=lambda t: ((t.get("function") or t).get("name", ""), json.dumps(t, sort_keys=True)))


def strip_volatile(text: str, keep_date: bool = False) -> tuple[str, list[str]]:
    keep, removed, date = [], [], None
    for line in text.split("\n"):
        if any(p.search(line) for p in _VOLATILE):
            removed.append(line)
            m = _TS.search(line)
            date = date or (m.group(1) if m else None)
        else:
            keep.append(line)
    if keep_date and date:
        keep.append(f"Current date: {date}")
    return "\n".join(keep), removed


def apply(payload: dict, keep_date=False, pad_to=0) -> list[str]:
    notes = []
    if payload.get("tools"):
        before = json.dumps(payload["tools"])
        payload["tools"] = stable_tools(payload["tools"])
        if json.dumps(payload["tools"]) != before:
            notes.append(f"Canonicalized {len(payload['tools'])} tool schemas (sorted by name and keys) for a byte-stable prefix")
    msgs = payload.get("messages") or []
    for m in msgs:
        if m.get("role") not in {"system", "developer"}:
            break
        if isinstance(m.get("content"), str):
            text, removed = strip_volatile(m["content"], keep_date)
            if removed:
                m["content"] = text
                notes.append(f"Dropped {len(removed)} volatile line(s) from the system prompt "
                             f"({'kept day-level date' if keep_date else 'timestamp/request id'}) to keep the cache prefix stable")
    if pad_to and msgs and msgs[0].get("role") == "system" and isinstance(msgs[0].get("content"), str):
        stable = estimate_tokens(json.dumps(payload.get("tools") or [])) + estimate_tokens(msgs[0]["content"])
        missing = (-stable) % pad_to
        if missing:
            msgs[0]["content"] += "\n" + ("." * (4 * missing - 1))
            notes.append(f"Padded stable prefix by ~{missing} tokens to a {pad_to}-token boundary")
    return notes
