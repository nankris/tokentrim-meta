"""Zero-Meta-spend quality probe of the HARD agentic set on cheap CLI models (subscription auth, no API keys):
claude-haiku-5-5 via `claude -p` and gpt-6-luna via `codex exec`. These CLIs cannot be the gateway upstream, so
the agent loop is emulated with a text protocol: the model replies `CALL <tool> <json>` or `ANSWER <json>`; the
harness runs the synthetic tool stubs and re-prompts with the transcript.
Arms: ``raw`` = tool outputs as-is; ``compressed`` = TokenTrim ToolOutputCompressor (query-aware) with
``retrieve_original`` (full or grep) available. Same tasks, same tools, same grader (benchmarks.workloads_hard).
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from tokentrim.optimizers.tool_output import ToolOutputCompressor, task_terms
from tokentrim.store import OriginalStore
from tokentrim.transforms import grep_original
from . import workloads_hard as WH

PROTOCOL = ("\n\nYou act through a text protocol. Reply with exactly ONE line and nothing else, either\n"
            "CALL <tool_name> <JSON arguments>\nor, when finished,\nANSWER <JSON object>\n"
            "Do not run shell commands or read files; only the tools listed below exist.")
EMPTY = Path(tempfile.mkdtemp(prefix="tt_probe_"))


def ask(model, system, prompt):
    if model.startswith("claude"):
        out = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--tools", "",
                              "--system-prompt", system, prompt], capture_output=True, text=True, timeout=600,
                             cwd=EMPTY)
        d = json.loads(out.stdout)
        u = d.get("usage", {})
        return d.get("result", ""), u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + \
            u.get("cache_read_input_tokens", 0)
    last = Path(tempfile.mktemp(dir=EMPTY, suffix=".txt"))
    out = subprocess.run(["codex", "exec", "-m", model, "-s", "read-only", "--skip-git-repo-check", "-C", str(EMPTY),
                          "--output-last-message", str(last), "-"], input=system + "\n\n" + prompt,
                         capture_output=True, text=True, timeout=900)
    m = re.search(r"tokens used\s*\n?\s*([\d,]+)", out.stdout + out.stderr)
    return (last.read_text() if last.exists() else ""), int(m[1].replace(",", "")) if m else 0


def tool_listing(extra_retrieve):
    lines = []
    for t in WH.hard_tools():
        f = t["function"]
        lines.append(f"- {f['name']}({', '.join(f['parameters']['properties'])}): {f['description'].split('. ')[0]}.")
    if extra_retrieve:
        lines.append("- retrieve_original(reference_id, pattern): look up text that was compressed, by its reference "
                     "id; prefer `pattern` (returns only matching lines); omit it for the full original.")
    return "\n".join(lines)


def episode(model, task, arm, max_turns=9):
    store = OriginalStore(Path(tempfile.mkdtemp(dir=EMPTY)))
    comp = ToolOutputCompressor(store, min_tokens=400)
    terms = task_terms([task["prompt"]])
    system = task["system"] + PROTOCOL
    head = task["prompt"] + "\n\nAvailable tools:\n" + tool_listing(arm == "compressed")
    transcript, trace, tokens, retrieves, answer, retrieved = [], [], 0, 0, "", set()
    for turn in range(max_turns):
        prompt = head + "\n\nTranscript so far:\n" + ("\n\n".join(transcript) or "(nothing yet)") + \
            "\n\nYour next single line:"
        reply, tok = ask(model, system, prompt)
        tokens += tok
        line = next((l.strip() for l in reply.splitlines() if l.strip().startswith(("CALL", "ANSWER"))), reply.strip())
        if line.startswith("ANSWER"):
            answer = line[6:].strip() or reply
            break
        m = re.match(r"CALL\s+(\w+)\s*(\{.*\})?\s*$", line)
        if not m:
            transcript.append(f"> {line[:200]}\n(protocol error: reply with one CALL or ANSWER line)")
            continue
        name = m[1]
        try:
            args = json.loads(m[2] or "{}")
        except ValueError:
            args = {}
        if name == "retrieve_original" and arm == "compressed":
            retrieves += 1
            ref, pat = str(args.get("reference_id", "")), args.get("pattern")
            try:
                text = store.get(ref)
                result = grep_original(text, pat) if isinstance(pat, str) and pat.strip() else text
                if not pat:
                    retrieved.add(ref)
            except KeyError:
                result = f"No original stored under {ref!r}."
        else:
            trace.append((name, args))
            result = WH.run_hard_stub(task, name, args)
            if arm == "compressed":
                r = comp.compress(result, keep_terms=terms)
                if r.ref and r.ref not in retrieved:
                    result = r.text
        transcript.append(f"> CALL {name} {json.dumps(args)}\nRESULT:\n{result}")
    score, checks = WH.grade_hard(answer, task, trace)
    if os.environ.get("TT_PROBE_TRANSCRIPTS"):  # diagnostics only (synthetic data)
        d = Path(os.environ["TT_PROBE_TRANSCRIPTS"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{model}_{task['id']}_{arm}.txt").write_text("\n\n".join(transcript) + f"\n\n> ANSWER {answer}\n")
    return {"probe": "hard_agentic", "model": model, "task": task["id"], "arm": arm, "score": score,
            "passed": score == 1.0, "turns": turn + 1, "retrieves": retrieves, "tokens_cli": tokens,
            "fails": [k for k, v in checks.items() if not v], "tool_trace": [n for n, _ in trace]}


def main():
    model = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    only = [x for x in os.environ.get("TT_PROBE_ONLY", "").split(",") if x]  # e.g. "ah00:compressed,ah09:raw"
    out = Path(os.environ.get("TT_PROBE_OUT", f"results/v5_2026-10-31/cheap_probe_hard_{model}.jsonl"))
    out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    jobs = [(WH.hard_task(i), arm) for i in range(n) for arm in ("raw", "compressed")]
    if only:
        jobs = [j for j in jobs if f"{j[0]['id']}:{j[1]}" in only]

    def work(job):
        try:
            row = episode(model, *job)
        except Exception as exc:
            row = {"probe": "hard_agentic", "model": model, "task": job[0]["id"], "arm": job[1],
                   "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        with lock:
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(row, flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, jobs))


if __name__ == "__main__":
    main()
