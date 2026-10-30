"""Zero-Meta-spend probe on a cheap model via the Claude Code CLI (subscription auth, no API key).

(a) compression quality: the same agentic task answered from RAW vs TokenTrim-COMPRESSED tool outputs;
    the model may answer `RETRIEVE <ref>` once to get an original back (mirrors retrieve_original).
(b) skill-only: chat questions answered with vs without the TokenTrim SKILL.md appended to the system prompt.
Usage numbers come from the CLI's JSON (its ~15k-token harness prompt is identical across arms).
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from tokentrim.optimizers.tool_output import ToolOutputCompressor
from tokentrim.store import OriginalStore
from . import workloads as W
from .run import skill_text, CHAT_BASE, ITEMS

MODEL = "claude-haiku-5-5"


def ask(system, prompt):
    out = subprocess.run(["claude", "-p", "--model", MODEL, "--output-format", "json", "--tools", "",
                          "--system-prompt", system, prompt], capture_output=True, text=True, timeout=300)
    d = json.loads(out.stdout)
    u = d.get("usage", {})
    return d.get("result", ""), {"input": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                                 + u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}


def probe_compression(n):
    rows = []
    store = OriginalStore(Path(tempfile.mkdtemp()))
    comp = ToolOutputCompressor(store, min_tokens=400)
    for i in range(n):
        t = W.agentic_task(i)
        for arm in ("raw", "compressed"):
            parts = []
            for name in ("run_tests", "get_ci_log", "git_diff"):
                text = t["stubs"][name]
                if arm == "compressed":
                    text = comp.compress(text).text
                parts.append(f"### tool result: {name}\n{text}")
            prompt = (t["prompt"] + "\n\nTool results so far:\n\n" + "\n\n".join(parts) +
                      "\n\nIf a value you need was elided, reply with ONLY `RETRIEVE <orig_ref>` instead.")
            ans, use = ask(W.AGENT_SYSTEM, prompt)
            retrieved = 0
            m = re.search(r"RETRIEVE\s+(orig_[0-9a-f]+)", ans)
            if m:
                retrieved = 1
                ans, use2 = ask(W.AGENT_SYSTEM, prompt + f"\n\nOriginal {m[1]}:\n{store.get(m[1])}")
                use = {k: use[k] + use2[k] for k in use}
            score, fields = W.grade_json(ans, t["answer"])
            rows.append({"probe": "compression", "task": t["id"], "arm": arm, "score": score,
                         "retrieved": retrieved, **use, "fails": [k for k, v in fields.items() if not v]})
            print(rows[-1], flush=True)
    return rows


def probe_skill(n):
    rows = []
    for i in range(n):
        q = W.chat_task(i, ITEMS)["questions"][0]
        for arm in ("baseline", "skill"):
            system = CHAT_BASE + ("\n\n# Loaded skill: tokentrim\n" + skill_text() if arm == "skill" else "")
            ans, use = ask(system, q["q"])
            rows.append({"probe": "skill", "task": f"ch{i:02d}", "arm": arm, "ok": W.grade_total(ans, q["answer"]),
                         **use, "answer_chars": len(ans)})
            print(rows[-1], flush=True)
    return rows


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    rows = probe_compression(n) + probe_skill(n)
    out = Path("results/v4_2026-10-30/cheap_probe_haiku.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
