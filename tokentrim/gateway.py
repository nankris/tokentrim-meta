"""TokenTrim gateway: optimize one OpenAI Chat Completions request, call the upstream, resolve internal tools.

Interface (used by the proxy adapters):
    gw = Gateway(upstream, GatewayConfig(...))
    response_json, report = gw.complete(payload, conversation_id=None)
``response_json`` is an OpenAI chat.completion object (usage summed over any internal tool rounds);
``report.explanations`` is a list of human-readable lines, ``report.calls`` the per-call CallUsage list.
Every transform fails open: on any exception the original payload is sent unchanged.
"""
from dataclasses import dataclass, field
import copy
import json

from .guard import SpendCapExceeded
from .store import OriginalStore

INTERNAL_TOOLS = {"retrieve_original", "search_tools"}


@dataclass
class GatewayConfig:
    cache_prefix: bool = True          # stable prefix: system first, tools sorted, volatile lines dropped
    keep_date: bool = False            # keep a day-level date line instead of dropping timestamps entirely
    pad_prefix_to: int = 0             # optional: pad stable system prefix to a multiple of N tokens (e.g. 128)
    tool_output: bool = False          # ToolOutputCompressor on role=tool messages
    compression_mode: str = "auto"     # JSON: "auto" (risk-aware), "conservative" (lossless) or "lossy"
    schema_router: bool = False        # Tool Schema Router (keep essentials + relevant, search_tools); OFF by default
    router_gating: bool = True         # v5.2 deterministic gating (False = v5 behaviour, router always applied)
    router_min_tools: int = 16         # gating: with this many client tools or fewer, keep them all
    router_margin: float = 0.8         # gating: keep all if the first excluded tool scores >= margin x last kept
    router_chain: bool = True          # gating: keep tools whose parameters name entities from the task/results
    history: bool = False              # structured history compaction
    lean_skill: bool = False           # prepend the opt-in Lean Execution Skill text
    cost_guard: bool = True            # skip transforms with non-positive estimated net saving
    max_internal_rounds: int = 4
    search_loop_threshold: int = 2     # unproductive search_tools calls before the router is disabled
    search_max_without_evidence: int = 3  # search_tools calls with no client tool result in between
    schema_keep: int = 6
    essential_tools: tuple = ()
    min_tool_output_tokens: int = 400
    history_keep_recent: int = 8
    history_min_tokens: int = 6000
    history_future_calls: int = 8
    history_max_tokens: int = 12000


@dataclass
class GatewayReport:
    explanations: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    internal_calls: int = 0
    fail_open: list = field(default_factory=list)
    compaction_calls: int = 0

    def usd(self):
        return sum(c.usd for c in self.calls)


class Gateway:
    def __init__(self, upstream, config: GatewayConfig | None = None, store: OriginalStore | None = None,
                 log=None):
        self.upstream = upstream
        self.config = config or GatewayConfig()
        self.store = store or OriginalStore()
        self.log = log  # optional callable(str) for explanation lines
        self.conversations: dict[str, dict] = {}

    # -- optimization -----------------------------------------------------------------
    def optimize(self, payload: dict, conversation_id: str | None = None, report=None):
        """Return (optimized payload, explanations, fail-open notes). Any unexpected error -> original payload."""
        from . import transforms
        report = report if report is not None else GatewayReport()
        try:
            return transforms.optimize(self, copy.deepcopy(payload), conversation_id, report)
        except SpendCapExceeded:  # budget/ledger errors are never swallowed by fail-open
            raise
        except Exception as exc:
            return copy.deepcopy(payload), [], [f"all transforms skipped ({type(exc).__name__})"]

    def _replay_internal(self, payload: dict, conversation_id):
        """Re-insert earlier internal tool exchanges (retrieve_original / search_tools) at the positions where
        they happened. Without this, a retrieved detail disappears from the conversation on the next client
        turn (the client never sees internal rounds), and the cached prefix breaks at that point (issue 65)."""
        from . import transforms
        conv = self.conversations.get(transforms.conversation_key(payload, conversation_id)) or {}
        inserts = conv.get("internal_inserts")
        if not inserts:
            return payload
        msgs = list(payload.get("messages") or [])
        out, done = [], 0
        for pos in sorted(inserts):
            if pos > len(msgs):
                break
            if transforms.history.digest(msgs[:pos]) != inserts[pos]["digest"]:
                break  # client rewrote its history: stop replaying (fail safe)
            out += msgs[done:pos] + copy.deepcopy(inserts[pos]["messages"])
            done = pos
        if not out:
            return payload
        payload = dict(payload)
        payload["messages"] = out + msgs[done:]
        return payload

    def complete(self, payload: dict, conversation_id: str | None = None, note: str = ""):
        report = GatewayReport()
        client_len = len(payload.get("messages") or [])
        client_digest = None
        try:
            from . import transforms
            client_digest = transforms.history.digest(payload.get("messages") or [])
            key = transforms.conversation_key(payload, conversation_id)
            payload = self._replay_internal(payload, conversation_id)
        except Exception:  # fail open
            key = None
        internal_msgs = []
        sent, explanations, fails = self.optimize(payload, conversation_id, report)
        report.explanations += explanations
        report.fail_open += fails
        for line in explanations + [f"fail-open: {f}" for f in fails]:
            if self.log:
                self.log(line)
        client_tools = {t.get("function", {}).get("name") for t in payload.get("tools") or []}
        for round_ in range(self.config.max_internal_rounds + 1):
            data, usage = self.upstream.create(sent, note=note)
            report.calls.append(usage)
            from . import transforms
            transforms.observe(self, payload, conversation_id, usage)
            message = (data.get("choices") or [{}])[0].get("message") or {}
            calls = message.get("tool_calls") or []
            internal = [c for c in calls if c.get("function", {}).get("name") in INTERNAL_TOOLS
                        and c["function"]["name"] not in client_tools]
            if not internal or round_ == self.config.max_internal_rounds:
                break
            from . import transforms
            sent = copy.deepcopy(sent)
            asst = {k: v for k, v in message.items() if k in {"role", "content", "tool_calls"}}
            sent["messages"].append(asst)
            internal_msgs.append(copy.deepcopy(asst))
            for call in calls:
                if call in internal:
                    result, line = transforms.run_internal_tool(self, call, conversation_id, sent)
                else:  # mixed internal + client calls: client calls are not executed here
                    result, line = "Not executed by gateway; call again if still needed.", None
                sent["messages"].append({"role": "tool", "tool_call_id": call.get("id"), "content": result})
                internal_msgs.append({"role": "tool", "tool_call_id": call.get("id"), "content": result})
                report.internal_calls += 1
                if line:
                    report.explanations.append(line)
                    if self.log:
                        self.log(line)
        if internal_msgs and key is not None and client_digest is not None:
            conv = self.conversations.setdefault(key, {})
            conv.setdefault("internal_inserts", {})[client_len] = {"digest": client_digest, "messages": internal_msgs}
            import hashlib
            raw = conv.setdefault("raw_tool_outputs", set())  # replayed exactly as first sent: never compressed
            raw.update(hashlib.sha256(m["content"].encode()).hexdigest() for m in internal_msgs
                       if m.get("role") == "tool" and isinstance(m.get("content"), str))
        data = copy.deepcopy(data)
        total = {"prompt_tokens": sum(c.prompt_tokens for c in report.calls),
                 "completion_tokens": sum(c.completion_tokens for c in report.calls)}
        total["total_tokens"] = total["prompt_tokens"] + total["completion_tokens"]
        total["prompt_tokens_details"] = {"cached_tokens": sum(c.cached_tokens for c in report.calls)}
        total["completion_tokens_details"] = {"reasoning_tokens": sum(c.reasoning_tokens for c in report.calls)}
        data["usage"] = total
        data["x_tokentrim"] = {"explanations": report.explanations, "internal_tool_calls": report.internal_calls,
                               "usd": report.usd(), "fail_open": report.fail_open,
                               "compaction_calls": report.compaction_calls,
                               "calls": [c.to_dict() for c in report.calls],
                               "data_kind": getattr(self.upstream, "data_kind", "REAL")}
        return data, report
