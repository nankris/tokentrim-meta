#!/usr/bin/env python3
"""Find the biggest token sinks in a saved Chat Completions request (JSON) or session (JSONL of requests).

Usage: python3 analyze.py request.json   |   python3 analyze.py session.jsonl
Prints estimated tokens (4 chars/token) by category and suggests a TokenTrim rung. Offline, no network.
"""
import json
import re
import sys

VOLATILE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
                      r"request[_ -]?id|current time", re.I)


def tok(x):
    return (len(x if isinstance(x, str) else json.dumps(x)) + 3) // 4


def analyze(req):
    msgs, tools = req.get("messages", []), req.get("tools") or []
    used = {c.get("function", {}).get("name") for m in msgs for c in m.get("tool_calls") or []}
    out = {"tool_schemas": tok(tools) if tools else 0, "tools_total": len(tools),
           "tools_never_called": sum(1 for t in tools if t.get("function", {}).get("name") not in used),
           "system": sum(tok(m.get("content") or "") for m in msgs if m.get("role") == "system"),
           "tool_outputs": sum(tok(m.get("content") or "") for m in msgs if m.get("role") == "tool"),
           "conversation": sum(tok(m.get("content") or "") for m in msgs if m.get("role") in {"user", "assistant"}),
           "largest_tool_output": max([tok(m.get("content") or "") for m in msgs if m.get("role") == "tool"] or [0]),
           "volatile_system_lines": sum(1 for m in msgs if m.get("role") == "system"
                                        for l in str(m.get("content")).splitlines() if VOLATILE.search(l))}
    tips = []
    if out["volatile_system_lines"]:
        tips.append("rung 2: remove timestamps/ids from the system prompt (cache buster)")
    if out["tools_total"] > 10 and out["tools_never_called"] > out["tools_total"] / 2:
        tips.append(f"rung 3: {out['tools_never_called']} of {out['tools_total']} tools never called -> tool selection")
    if out["largest_tool_output"] > 1000:
        tips.append("rung 4: large tool output -> compress (keep failures, file:line, counts)")
    if out["conversation"] > 20000:
        tips.append("rung 5: long history -> structured compaction with recoverable transcript")
    out["suggestions"] = tips or ["nothing large found; leave the request as is"]
    return out


def main(path):
    text = open(path, encoding="utf-8").read()
    reqs = [json.loads(l) for l in text.splitlines() if l.strip()] if path.endswith(".jsonl") else [json.loads(text)]
    for i, r in enumerate(reqs):
        print(json.dumps({"request": i, **analyze(r.get("request", r))}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
