"""Tool Schema Router: send only the tool schemas a conversation needs, with recovery.

Rules: (1) essential tools (configured names, tools already called in the history, a forced tool_choice)
are always kept; (2) the remaining slots go to the most relevant tools by BM25 over name + description +
parameter names against the task text; (3) a ``search_tools(query)`` tool lets the model recover any tool
that was not selected. The selection is frozen per conversation (only ever grows) so the tool prefix
stays byte-stable for the provider cache.
"""
import json
import math
import re

from ..tokens import estimate_tokens

SEARCH_TOOL = {"type": "function", "function": {
    "name": "search_tools",
    "description": ("Find additional tools that are available but not loaded. Call with a short description "
                    "of the capability you need; matching tools become callable on your next turn."),
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}

_WORD = re.compile(r"[a-z0-9]+")


def tool_name(tool: dict) -> str:
    return (tool.get("function") or tool).get("name", "")


def _tool_text(tool: dict) -> str:
    fn = tool.get("function") or tool
    params = fn.get("parameters") or {}
    props = " ".join((params.get("properties") or {}).keys())
    name = fn.get("name", "")
    return f"{name} {name.replace('_', ' ')} {fn.get('description', '')} {props}"


def _tokens(text: str) -> list[str]:
    words = _WORD.findall(text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]


def bm25_rank(query: str, tools: list[dict], k1=1.2, b=0.75) -> list[tuple[float, str]]:
    docs = [_tokens(_tool_text(t)) for t in tools]
    n = len(docs)
    avg = sum(map(len, docs)) / max(1, n)
    df = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    q = set(_tokens(query))
    scored = []
    for tool, d in zip(tools, docs):
        s = 0.0
        for w in q:
            tf = d.count(w)
            if tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg))
        scored.append((s, tool_name(tool)))
    return sorted(scored, key=lambda p: (-p[0], p[1]))


def used_tool_names(messages: list[dict]) -> set[str]:
    names = set()
    for m in messages:
        for c in m.get("tool_calls") or []:
            names.add((c.get("function") or {}).get("name", ""))
    return names


def task_text(messages: list[dict]) -> str:
    users = [m for m in messages if m.get("role") == "user"]
    def text(m):
        c = m.get("content")
        return c if isinstance(c, str) else " ".join(p.get("text", "") for p in c or [] if isinstance(p, dict))
    parts = [text(users[0])] if users else []
    if len(users) > 1:
        parts.append(text(users[-1]))
    return " ".join(parts)


class SchemaRouter:
    def __init__(self, keep: int = 6, essential=()):
        self.keep, self.essential = keep, set(essential)

    def select(self, tools: list[dict], messages: list[dict], tool_choice, frozen: set[str] | None):
        """Return (selected names, explanation or None). ``frozen`` is the conversation's earlier selection."""
        names = [tool_name(t) for t in tools]
        must = (self.essential | used_tool_names(messages)) & set(names)
        if isinstance(tool_choice, dict):
            must.add((tool_choice.get("function") or {}).get("name", ""))
        if frozen is not None:
            selected = (frozen | must) & set(names)
            return selected, None
        selected = set(must)
        for score, name in bm25_rank(task_text(messages), tools):
            if len(selected) >= self.keep + len(must):
                break
            if score > 0:
                selected.add(name)
        return selected, "initial"

    def search(self, query: str, tools: list[dict], limit: int = 5) -> list[dict]:
        ranked = [n for s, n in bm25_rank(query, tools) if s > 0][:limit]
        by = {tool_name(t): t for t in tools}
        return [by[n] for n in ranked]


def schema_tokens(tools: list[dict]) -> int:
    return estimate_tokens(json.dumps(tools, separators=(",", ":")))
