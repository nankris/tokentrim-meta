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

    GENERIC_PARAMS = {"query", "options", "limit", "path", "id", "name", "text", "start", "end", "line", "value",
                      "page", "size", "offset", "format", "type", "mode", "data", "input", "args", "key"}

    def gate(self, tools, messages, min_tools=16, margin=0.8, chain=True):
        """Deterministic gating (v5.2). Returns (route, reason, chain_tools). ``route=False`` means keep every
        tool (the router is not trusted for this conversation):
        * few tools: ``len(tools) <= min_tools``, so the saving is small and the risk is not worth it;
        * low confidence: the BM25 cut is not separated (first excluded score >= margin x last kept score),
          or the task matches fewer tools than would be kept.
        When routing, ``chain_tools`` are tools whose parameter names refer to an entity that appears in the task
        or in tool results seen so far (e.g. ``build`` when a build/release id is in play). They are the next
        links of a dependency chain, so they are kept as well."""
        names = [tool_name(t) for t in tools]
        if len(tools) <= min_tools:
            return False, f"only {len(tools)} tools (<= {min_tools}): all kept", set()
        must = (self.essential | used_tool_names(messages)) & set(names)
        ranked = [(sc, n) for sc, n in bm25_rank(task_text(messages), tools) if n not in must]
        positive = [p for p in ranked if p[0] > 0]
        if len(positive) <= self.keep:
            return False, f"low confidence: task matches only {len(positive)} tools", set()
        last, nxt = positive[self.keep - 1][0], positive[self.keep][0]
        if nxt >= margin * last:
            return False, (f"low confidence: no clear cut between kept and dropped tools "
                           f"(score {nxt:.1f} vs {last:.1f}); all kept"), set()
        found = set()
        if chain:
            seen = set(_tokens(" ".join(
                (m.get("content") if isinstance(m.get("content"), str) else "") for m in messages)))
            for t in tools:
                props = ((t.get("function") or t).get("parameters") or {}).get("properties") or {}
                words = {w for p in props for w in _tokens(p.replace("_", " "))} - self.GENERIC_PARAMS
                if words and words & seen:
                    found.add(tool_name(t))
        return True, "", found

    def search(self, query: str, tools: list[dict], limit: int = 5) -> list[dict]:
        ranked = [n for s, n in bm25_rank(query, tools) if s > 0][:limit]
        by = {tool_name(t): t for t in tools}
        return [by[n] for n in ranked]


def schema_tokens(tools: list[dict]) -> int:
    return estimate_tokens(json.dumps(tools, separators=(",", ":")))
