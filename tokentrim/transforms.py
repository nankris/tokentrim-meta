"""Orchestrates the opt-in optimizers for one request (each fails open, each logs an explanation line)."""
import hashlib
import json
import re

from .optimizers import cache_prefix, history
from .optimizers.schema_router import SEARCH_TOOL, SchemaRouter, schema_tokens, tool_name
from .optimizers.tool_output import ToolOutputCompressor, task_terms
from .policy import net_saving
from .tokens import estimate_tokens
from .upstream import price_name

RETRIEVE_TOOL = {"type": "function", "function": {
    "name": "retrieve_original",
    "description": ("Look up text that TokenTrim compressed, by the reference id shown in the compressed view. "
                    "Use only when a needed detail is missing. Prefer `pattern` (returns only matching lines, "
                    "with line numbers); omit it to get the full original."),
    "parameters": {"type": "object", "properties": {
        "reference_id": {"type": "string"},
        "pattern": {"type": "string", "description": "optional case-insensitive regex or substring to grep for"}},
        "required": ["reference_id"]}}}


def grep_original(text: str, pattern: str, limit: int = 200) -> str:
    try:
        rx = re.compile(pattern, re.I)
    except re.error:
        rx = re.compile(re.escape(pattern), re.I)
    hits = [f"{n}: {line}" for n, line in enumerate(text.splitlines(), 1) if rx.search(line)]
    more = f"\n[{len(hits) - limit} more matching lines not shown]" if len(hits) > limit else ""
    return (f"{len(hits)} matching lines for /{pattern}/:\n" + "\n".join(hits[:limit]) + more) if hits \
        else f"No lines match /{pattern}/ in the original."


def conversation_key(payload: dict, conversation_id: str | None) -> str:
    if conversation_id:
        return conversation_id
    msgs = payload.get("messages") or []
    head = [m for m in msgs if m.get("role") in {"system", "developer"}][:1] + \
           [m for m in msgs if m.get("role") == "user"][:1]
    return hashlib.sha256(json.dumps(head, sort_keys=True).encode()).hexdigest()[:16]


def _hit_rate(state) -> float:
    p, c = state.get("prompt_tokens", 0), state.get("cached_tokens", 0)
    return c / p if p else 0.3


def optimize(gw, payload: dict, conversation_id, report):
    cfg = gw.config
    conv = gw.conversations.setdefault(conversation_key(payload, conversation_id), {})
    notes, fails = [], []
    rates = gw.upstream.cost_model.prices.get(price_name(payload.get("model", "")))
    original_tools = payload.get("tools")

    def guarded(name, fn):
        try:
            fn()
        except Exception as exc:  # fail open: this transform is skipped, the request still goes out
            fails.append(f"{name} skipped ({type(exc).__name__})")

    if cfg.lean_skill:
        def lean():
            from .skill_text import LEAN_EXECUTION
            m = payload["messages"]
            if m and m[0].get("role") == "system" and isinstance(m[0].get("content"), str):
                if LEAN_EXECUTION not in m[0]["content"]:
                    m[0]["content"] += "\n\n" + LEAN_EXECUTION
            else:
                m.insert(0, {"role": "system", "content": LEAN_EXECUTION})
            notes.append("Added Lean Execution Skill instructions (opt-in) to the system prompt")
        guarded("lean_skill", lean)

    if cfg.tool_output:
        def compress():
            comp = ToolOutputCompressor(gw.store, cfg.min_tool_output_tokens)
            raw_sent = conv.setdefault("raw_tool_outputs", set())
            done = 0
            seen_user = []
            for m in payload["messages"]:
                if m.get("role") == "user":
                    seen_user.append(m.get("content") if isinstance(m.get("content"), str) else "")
                if m.get("role") != "tool" or not isinstance(m.get("content"), str):
                    continue
                h = hashlib.sha256(m["content"].encode()).hexdigest()
                if h in raw_sent:
                    continue  # already sent uncompressed earlier: changing it now would break the cache
                result = comp.compress(m["content"], keep_terms=task_terms(seen_user))
                if result.ref and result.ref in conv.get("retrieved_refs", ()):
                    result = None  # the model needed this original once: keep it raw for the rest of the run
                if result.ref and rates:
                    d = net_saving(rates, result.tokens_before - result.tokens_after, 3, 0, _hit_rate(conv))
                    if not d.apply:
                        result = None
                if result is None or not result.ref:
                    raw_sent.add(h)
                    if result is not None and result.explanation:
                        notes.append(result.explanation)
                    continue
                m["content"] = result.text
                done += 1
                if (h, "logged") not in conv.setdefault("logged", set()):
                    conv["logged"].add((h, "logged"))
                    notes.append(result.explanation)
            if done:
                conv["needs_retrieve"] = True
        guarded("tool_output", compress)

    if cfg.history:
        def compact():
            msgs = payload["messages"]
            lead = 0
            while lead < len(msgs) and msgs[lead].get("role") in {"system", "developer"}:
                lead += 1
            head, body = msgs[:lead], msgs[lead:]
            st = conv.get("history")
            if st and st["n"] <= len(body) and history.digest(body[:st["n"]]) == st["digest"]:
                tail = body[st["n"]:]
                if history.tokens_of(tail) < cfg.history_min_tokens:
                    payload["messages"] = head + st["block"] + tail
                    return
                prior, start = st["state"], st["n"]
            elif history.tokens_of(body) < cfg.history_min_tokens:
                return
            else:
                prior, start = None, 0
            cut = history.cut_index(body, cfg.history_keep_recent)
            if cut <= start + 2:
                if st and st["n"] <= len(body) and history.digest(body[:st["n"]]) == st["digest"]:
                    payload["messages"] = head + st["block"] + body[st["n"]:]
                return
            region = body[start:cut]
            region_tokens = history.tokens_of(region)
            if rates:
                extra = (region_tokens * rates["input"] + 3000 * rates["output"]) / 1e6
                d = net_saving(rates, int(region_tokens * 0.75), cfg.history_future_calls,
                               history.tokens_of(body), _hit_rate(conv), extra)
                if not d.apply:
                    notes.append(f"History compaction skipped: {d.reason}")
                    return
            req = [{"role": "system", "content": history.PROMPT},
                   {"role": "user", "content": (("Previous state:\n" + json.dumps(prior) + "\n\n") if prior else "")
                    + "Conversation to compress:\n" + history.transcript(region)}]
            data, usage = gw.upstream.create({"model": payload["model"], "messages": req,
                                              "max_tokens": cfg.history_max_tokens}, note="history compaction")
            report.calls.append(usage)
            report.compaction_calls += 1
            text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            state = history.parse_state(text)  # raises -> fail open
            ref = gw.store.put(history.transcript(body[:cut]), "hist")
            block = history.block_messages(state, ref, cut)
            conv["history"] = {"n": cut, "digest": history.digest(body[:cut]), "block": block, "state": state}
            conv["needs_retrieve"] = True
            payload["messages"] = head + block + body[cut:]
            after = history.tokens_of(block)
            notes.append(f"Compacted {cut} earlier messages ({history.tokens_of(body[:cut]):,} -> {after:,} tokens) "
                         f"into structured state; transcript recoverable as {ref}")
        guarded("history", compact)

    if cfg.schema_router and original_tools:
        def route():
            router = SchemaRouter(cfg.schema_keep, cfg.essential_tools)
            tools = payload["tools"]
            frozen = conv.get("tool_selection")
            selected, first = router.select(tools, payload["messages"], payload.get("tool_choice"), frozen)
            removed = [t for t in tools if tool_name(t) not in selected]
            if not removed:
                conv["tool_selection"] = selected
                return
            kept = [t for t in tools if tool_name(t) in selected]
            saved = schema_tokens(removed) - schema_tokens([SEARCH_TOOL])
            if first and rates:
                d = net_saving(rates, saved, 5, 0, _hit_rate(conv))
                if not d.apply or saved <= 0:
                    notes.append(f"Tool selection skipped: {d.reason}")
                    conv["tool_selection"] = {tool_name(t) for t in tools}
                    return
            conv["tool_selection"] = selected
            payload["tools"] = kept + [SEARCH_TOOL]
            conv["all_tools"] = tools
            if first:
                notes.append(f"Removed {len(removed)} unused tool schemas, kept {len(kept)} "
                             f"(~{saved:,} tokens/call saved); others recoverable via search_tools; "
                             f"selection frozen for this conversation to keep the cache prefix")
        guarded("schema_router", route)

    # retrieve_original is offered from the FIRST request whenever tool-output compression is on and the
    # client uses tools, so the tool list does not change mid-conversation (cache-stable).
    if (cfg.tool_output and payload.get("tools")) or conv.get("needs_retrieve"):
        names = {tool_name(t) for t in payload.get("tools") or []}
        if "retrieve_original" not in names:
            payload["tools"] = list(payload.get("tools") or []) + [RETRIEVE_TOOL]

    if cfg.cache_prefix:
        def prefix():
            notes.extend(cache_prefix.apply(payload, cfg.keep_date, cfg.pad_prefix_to))
        guarded("cache_prefix", prefix)

    # explanations once per conversation for repeated identical lines
    seen = conv.setdefault("explained", set())
    fresh = [n for n in notes if n not in seen]
    seen.update(fresh)
    return payload, fresh, fails


def observe(gw, payload, conversation_id, usage):
    conv = gw.conversations.setdefault(conversation_key(payload, conversation_id), {})
    conv["prompt_tokens"] = conv.get("prompt_tokens", 0) + usage.prompt_tokens
    conv["cached_tokens"] = conv.get("cached_tokens", 0) + usage.cached_tokens


def run_internal_tool(gw, call, conversation_id, sent):
    fn = call.get("function") or {}
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except ValueError:
        args = {}
    name = fn.get("name")
    if name == "retrieve_original":
        ref = str(args.get("reference_id") or args.get("id") or "")
        pattern = args.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            try:
                return grep_original(gw.store.get(ref), pattern.strip()), \
                    f"Model grepped original {ref} for /{pattern.strip()[:40]}/ (TokenTrim recovery path used)"
            except KeyError:
                return f"No original stored under {ref!r}.", f"retrieve_original: unknown reference {ref!r}"
        try:
            original = gw.store.get(ref)
            # from now on this tool result is sent uncompressed, so the model never has to retrieve it again
            conv = gw.conversations.setdefault(conversation_key(sent, conversation_id), {})
            conv.setdefault("retrieved_refs", set()).add(ref)
            return original, f"Model retrieved original {ref} (TokenTrim recovery path used)"
        except KeyError:
            return f"No original stored under {ref!r}.", f"retrieve_original: unknown reference {ref!r}"
    if name == "search_tools":
        conv = gw.conversations.setdefault(conversation_key(sent, conversation_id), {})
        all_tools = conv.get("all_tools") or []
        found = SchemaRouter().search(str(args.get("query", "")), all_tools)
        have = {tool_name(t) for t in sent.get("tools") or []}
        new = [t for t in found if tool_name(t) not in have]
        if new:
            conv.setdefault("tool_selection", set()).update(tool_name(t) for t in new)
            sent["tools"] = sorted(list(sent.get("tools") or []) + new, key=tool_name)
        listing = [{"name": tool_name(t), "description": (t.get("function") or t).get("description", "")[:200]}
                   for t in found]
        return (json.dumps({"tools": listing, "note": "These tools are now callable."}),
                f"search_tools({args.get('query', '')!r}) restored {len(new)} tool(s): "
                f"{', '.join(tool_name(t) for t in new) or 'none new'}")
    return "unknown internal tool", None
