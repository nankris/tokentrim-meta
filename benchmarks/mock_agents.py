"""Deterministic MOCK agents for validating the hard workload and its graders offline (zero spend).

* ``oracle``: reads only what it is shown (raw or compressed tool output), uses search_tools when a needed tool
  is not loaded and retrieve_original(pattern=...) when a needed detail was compressed away. If the task and
  the recovery paths are sound, it must score 1.0 in every arm.
* ``lazy``: same, but never uses recovery tools (answers from what is visible).
* ``guess``: answers immediately with plausible-looking invented values.
"""
import json
import re


def _tools(payload):
    return {(t.get("function") or t).get("name") for t in payload.get("tools") or []}


def _call(n, name, args):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"m{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _final(ans):
    return {"role": "assistant", "content": json.dumps(ans)}


def hard_policy(mode="oracle"):
    def respond(payload):
        msgs = payload["messages"]
        n = len(msgs)
        user = next(m["content"] for m in msgs if m.get("role") == "user")
        if mode == "guess":
            return _final({"exception_type": "TimeoutError", "exception_location": "src/app/api.py:10",
                           "request_id": "q-1000", "trace_ref": "tr-000000", "release": "rel-1000", "setting": "POOL_SIZE=8"})
        tools = _tools(payload)
        texts = [m.get("content") or "" for m in msgs if m.get("role") == "tool"]
        alltext = "\n".join(texts)
        job = re.search(r"CI job (ci-\d+)", user)[1]
        called = {(c.get("function") or {}).get("name") for m in msgs for c in m.get("tool_calls") or []}
        ans = {}
        if "get_ci_log" not in called:
            return _call(n, "get_ci_log", {"job_id": job})
        log = next((t for t in texts if "unhandled exception" in t), "")
        m = re.search(r"ERROR req=(q-\d+) unhandled exception", log)
        if not m:
            return _final({})
        rid = m[1]
        ans["request_id"] = rid
        after = log[m.end():].splitlines()
        frames = []
        for line in after[1:]:
            fm = re.search(r'File "(.+?)", line (\d+)', line)
            if fm:
                frames.append(f"{fm[1]}:{fm[2]}")
            em = re.match(r"^(\w+Error): ", line)
            if em:
                ans["exception_type"] = em[1]
                break
        ans["exception_location"] = frames[-1] if frames else ""
        tm = re.search(rf"req={rid} accepted trace_ref=(tr-[0-9a-f]+)", alltext)
        if not tm:
            ref = re.search(r"(orig_[0-9a-z]+)", log)
            if mode == "oracle" and ref and "retrieve_original" in tools:
                return _call(n, "retrieve_original", {"reference_id": ref[1], "pattern": rid})
            return _final(ans)
        ans["trace_ref"] = trace = tm[1]
        span_text = next((t for t in texts if trace in t and "spans" in t), None)
        if span_text is None:
            if "inspect_spans" not in tools:
                if mode != "oracle" or "search_tools" not in tools:
                    return _final(ans)
                return _call(n, "search_tools", {"query": "distributed span hierarchy observability"})
            return _call(n, "inspect_spans", {"span_root": trace})
        release = setting = None
        try:
            spans = json.loads(span_text)["spans"]
            bad = next(s for s in spans if s["status"] == "ERROR")
            release, setting = bad["release"], re.search(r"setting (\w+)", bad["note"])[1]
        except (ValueError, KeyError, TypeError, StopIteration):
            row = next((l for l in span_text.splitlines() if "ERROR" in l and "rel-" in l), "")
            rm, sm = re.search(r"(rel-\d+)", row), re.search(r"setting (\w+)", row)
            release, setting = (rm[1] if rm else None), (sm[1] if sm else None)
        if not release:
            return _final(ans)
        ans["release"] = release
        man = next((t for t in texts if f"manifest for build {release}" in t), None)
        if man is None:
            if "open_artifact_manifest" not in tools:
                if mode != "oracle" or "search_tools" not in tools:
                    return _final(ans)
                return _call(n, "search_tools", {"query": "artifact manifest of a build"})
            return _call(n, "open_artifact_manifest", {"build": release})
        cur = man.split("[current]", 1)[-1].split("[previous", 1)[0]
        vm = re.search(rf"^{setting} = (\d+)", cur, re.M)
        ans["setting"] = f"{setting}={vm[1]}" if vm else ""
        return _final(ans)
    return respond
