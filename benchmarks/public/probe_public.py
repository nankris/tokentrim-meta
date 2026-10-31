"""Zero-Meta-spend validation probe on claude haiku (subscription CLI, `claude -p`), on items DISJOINT from the
pre-registered Meta slices (BFCL offset 100.., LogChunks offset 120..). The CLI cannot take OpenAI tools, so:
* BFCL: tool schemas are listed as JSON in the prompt; the model replies with a JSON list of calls
  [{"name": ..., "arguments": {...}}]; arms ``full`` (40 tools) vs ``routed`` (TokenTrim router selection only,
  strict: no search_tools, i.e. the worst case for the router).
* LogChunks: the log is pasted; arms ``raw`` vs ``ci`` (text_logs compressor view, strict: no retrieval).
Graded with the same graders as the Meta runs. Usage: python3 -m benchmarks.public.probe_public <outdir> [n]
"""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sys
from pathlib import Path

from tokentrim.optimizers.schema_router import SchemaRouter, tool_name
from tokentrim.optimizers.tool_output import ToolOutputCompressor
from benchmarks.cheap_probe_hard import ask
from . import bfcl as B
from . import logchunks as L
from .run_public import bfcl_slice, lc_slice, lc_prompt

MODEL = "claude-haiku-5-5"  # must start with "claude" so ask() uses the claude CLI path


def bfcl_episode(item, arm):
    tools = B.to_tools(item["function_aug"])
    msgs = [dict(m) for turn in item["question"] for m in turn]
    if arm == "routed":
        sel, _ = SchemaRouter(6).select(tools, msgs, None, None)
        tools = [t for t in tools if tool_name(t) in sel]
    q = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    prompt = ("Available functions (JSON schemas):\n" + json.dumps([t["function"] for t in tools]) +
              "\n\nConversation:\n" + q + "\n\nReply with ONLY a JSON list of the function calls to make, e.g. "
              '[{"name": "f", "arguments": {"x": 1}}]. Use only the functions listed.')
    text, tok = ask(MODEL, "You are a function-calling assistant.", prompt)
    m = re.search(r"\[.*\]", text, re.S)
    try:
        calls = [{c["name"]: c.get("arguments") or {}} for c in json.loads(m.group(0))] if m else None
    except (ValueError, KeyError, TypeError):
        calls = None
    ok, why = B.check(item, calls)
    return {"id": item["id"], "arm": arm, "passed": ok, "why": why, "tools": len(tools), "cli_tokens": tok}


def lc_episode(ex, arm):
    log = L.read_log(ex)
    if arm == "ci":
        log = ToolOutputCompressor(text_logs=True).compress(log, task_text=lc_prompt(ex)).text
    prompt = lc_prompt(ex).replace("Read its log with get_build_log, then reply", "Its log is below. Reply") + \
        "\n\n--- LOG ---\n" + log
    text, tok = ask(MODEL, "You are a CI assistant that diagnoses failed builds.", prompt)
    ok, r = L.grade(text, ex)
    return {"id": ex["id"], "arm": arm, "passed": ok, "recall": round(r, 3), "cli_tokens": tok}


def main(outdir, n=24):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(bfcl_episode, it, a) for it in bfcl_slice(n, offset=100) for a in ("full", "routed")] + \
           [(lc_episode, ex, a) for ex in lc_slice(n, offset=120) for a in ("raw", "ci")]
    with ThreadPoolExecutor(6) as pool:
        rows = list(pool.map(lambda j: j[0](j[1], j[2]), jobs))
    (out / "probe_haiku_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summ = {}
    for a in ("full", "routed", "raw", "ci"):
        rs = [r for r in rows if r["arm"] == a]
        summ[a] = {"n": len(rs), "passed": sum(r["passed"] for r in rs), "cli_tokens": sum(r["cli_tokens"] for r in rs)}
    (out / "probe_haiku_summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 24)
