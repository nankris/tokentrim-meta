"""v5.1 JSON extraction regression set (issue 69): 100 generated synthetic JSON tool responses with similar release
names, nested objects and misleading nearby values. Compares four views of the same document:
raw, legacy (v5 column-table flattening, kept here verbatim for reference), structured (lossless), structured_lossy.
- ``structural_check``: deterministic, no model. The failing record's id, status and release must sit on ONE line
  with their keys, and the parent record (id + service) must be present.
- ``python3 -m benchmarks.json_extraction probe <model> [n] [workers]``: cheap CLI probe (claude -p); the model may
  call RETRIEVE <regex> (grep on the original, counted as a recovery call). Cost is ESTIMATED at Meta list price
  from chars/4 token estimates of every prompt and reply (recovery turns included), not billed.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import random
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from tokentrim.optimizers.tool_output import PROTECT, compress_json
from tokentrim.tokens import estimate_tokens
from tokentrim.transforms import grep_original

SERVICES = ["cache", "upload", "search", "billing", "notify", "queue", "auth", "ledger", "media", "export"]
OPS = ["encode", "write_retry", "call_metric", "fanout", "flush", "lookup", "merge", "render"]


def similar_releases(rng):
    d = [str(rng.randint(0, 9)) for _ in range(4)]
    base = "".join(d)
    perms = {base}
    while len(perms) < 4:
        x = d[:]
        i, j = rng.sample(range(4), 2)
        x[i], x[j] = x[j], x[i]
        if rng.random() < 0.5:
            x[rng.randrange(4)] = str(rng.randint(0, 9))
        perms.add("".join(x))
    return [f"rel-{p}" for p in sorted(perms, key=lambda p: (p != base, p))]


def gen_doc(i):
    rng = random.Random(9000 + i)
    rels = similar_releases(rng)
    good, decoys = rels[0], rels[1:]
    nested = i % 2 == 1
    n = rng.randint(30, 70)
    spans, ids = [], []
    for k in range(n):
        sid = f"sp-{rng.randrange(16 ** 4):04x}"
        while sid in ids:
            sid = f"sp-{rng.randrange(16 ** 4):04x}"
        ids.append(sid)
        rec = {"span_id": sid, "parent": ids[rng.randrange(k)] if k else None, "service": rng.choice(SERVICES),
               "op": rng.choice(OPS), "ms": rng.randint(5, 900), "status": "ok",
               "release": rng.choice(decoys) if rng.random() < 0.6 else good, "note": ""}
        if nested:
            rec["meta"] = {"release_hint": rng.choice(rels), "build": {"id": f"b-{rng.randint(100, 999)}",
                                                                      "release": rng.choice(decoys)}}
        spans.append(rec)
    bad = rng.randint(n // 3, n - 3)
    spans[bad]["status"] = "ERROR"
    spans[bad]["release"] = good
    spans[bad]["note"] = "unhandled exception"
    for nb in (bad - 1, bad + 1):  # misleading neighbours
        spans[nb]["release"] = decoys[0]
        spans[nb]["note"] = f"retried after error on {decoys[1]}"
        spans[nb]["status"] = "ok"
    doc = {"trace_ref": f"tr-{rng.randrange(16 ** 6):06x}", "latest_release": decoys[2],
           "deploy": {"previous_release": decoys[0], "canary": {"release": decoys[1]}}, "spans": spans}
    parent = next(s for s in spans if s["span_id"] == spans[bad]["parent"])
    answer = {"release": good, "span_id": spans[bad]["span_id"], "parent_service": parent["service"],
              "parent_span_id": parent["span_id"]}
    return json.dumps(doc, indent=1), answer


# ---- legacy v5 JSON view (column-table flattening), copied from tokentrim v5 (commit 4ec104e) for comparison ----
def _legacy_table(rows: list[dict]) -> str | None:
    keys = list(rows[0])
    if not all(isinstance(r, dict) and list(r) == keys for r in rows) or len(rows) < 4:
        return None
    if any(isinstance(v, (dict, list)) for r in rows for v in r.values()):
        return None
    body = [" | ".join(keys)] + [" | ".join(json.dumps(r[k], ensure_ascii=False) for k in keys) for r in rows]
    return f"[table: {len(rows)} rows; columns: {', '.join(keys)}]\n" + "\n".join(body)


def legacy_compress_json(text: str, budget_tokens: int = 1500, protect=None) -> str:
    value = json.loads(text)

    def walk(v):
        if isinstance(v, list) and v and isinstance(v[0], dict):
            table = _legacy_table(v)
            if table is not None:
                return {"__table__": table}
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    restructured = walk(value)
    minified = json.dumps(restructured, ensure_ascii=False, separators=(",", ":"))
    # tables are rendered as plain text blocks after the JSON skeleton
    tables = []

    def pull(v, path="$"):
        if isinstance(v, dict) and "__table__" in v and len(v) == 1:
            tables.append((path, v["__table__"]))
            return f"<table {path}>"
        if isinstance(v, dict):
            return {k: pull(x, f"{path}.{k}") for k, x in v.items()}
        if isinstance(v, list):
            return [pull(x, f"{path}[{i}]") for i, x in enumerate(v)]
        return v
    skeleton = json.dumps(pull(restructured), ensure_ascii=False, separators=(",", ":"))
    if skeleton == '"<table $>"' and len(tables) == 1:
        skeleton, tables = "JSON array rendered as a table (lossless):", [("$", tables[0][1])]
    out = skeleton + "".join(f"\n{p}:\n{t}" for p, t in tables)
    if estimate_tokens(out) <= budget_tokens or not tables:
        return out if len(out) < len(minified) else minified
    # lossy step: long tables keep header, protected rows, first/last rows
    final = [skeleton]
    for p, t in tables:
        rows = t.splitlines()
        head, body = rows[:2], rows[2:]
        keep = [k for k, r in enumerate(body) if (protect or PROTECT).search(r)] + list(range(10)) + \
               list(range(max(0, len(body) - 3), len(body)))
        final.append(f"\n{p}:\n" + "\n".join(head + _keep_with_context(body, sorted(set(k for k in keep if k < len(body))), 0)))
    return "".join(final)



def views(text):
    return {"raw": text, "legacy_table": legacy_compress_json(text, protect=PROTECT),
            "structured": compress_json(text, mode="conservative"),
            "structured_lossy": compress_json(text, mode="lossy")}


def structural_check(view, answer):
    lines = view.splitlines()
    err = [l for l in lines if '"status":"ERROR"' in l]
    ok_err = len(err) == 1 and f'"release":"{answer["release"]}"' in err[0] and f'"span_id":"{answer["span_id"]}"' in err[0]
    ok_par = any(f'"span_id":"{answer["parent_span_id"]}"' in l and f'"service":"{answer["parent_service"]}"' in l
                 for l in lines)
    return ok_err and ok_par


QUESTION = ("Below is the JSON returned by a tracing tool (possibly in a compacted view). Find the span whose status "
            "is ERROR. Reply with exactly one line, either\nANSWER {\"release\": ..., \"span_id\": ..., "
            "\"parent_service\": ...}\n(release = that span's own release; parent_service = service of its parent "
            "span)\nor, if a needed detail is missing from the view,\nRETRIEVE <regex>\nto grep the full original.")
PRICE_IN, PRICE_OUT = 0.10e-6, 0.20e-6


def ask(model, prompt):
    out = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--tools", ""], input=prompt,
                         capture_output=True, text=True, timeout=600, cwd=tempfile.gettempdir())
    return json.loads(out.stdout).get("result", "")


def episode(model, i, arm):
    text, answer = gen_doc(i)
    view = views(text)[arm]
    transcript, est_usd, retrieves, got = [], 0.0, 0, {}
    for _ in range(3):
        prompt = QUESTION + "\n\n" + view + "".join(transcript) + "\n\nYour single line:"
        reply = ask(model, prompt)
        est_usd += estimate_tokens(prompt) * PRICE_IN + estimate_tokens(reply) * PRICE_OUT
        line = next((l.strip() for l in reply.splitlines() if l.strip().startswith(("ANSWER", "RETRIEVE"))), "")
        if line.startswith("RETRIEVE") and arm != "raw":
            retrieves += 1
            transcript.append(f"\n\n> {line}\n{grep_original(text, line[8:].strip())}")
            continue
        m = re.search(r"\{.*\}", line)
        try:
            got = json.loads(m.group(0)) if m else {}
        except ValueError:
            got = {}
        break
    correct = all(str(got.get(k, "")).strip() == answer[k] for k in ("release", "span_id", "parent_service"))
    return {"doc": i, "arm": arm, "nested": i % 2 == 1, "correct": correct, "retrieves": retrieves,
            "est_usd": est_usd, "view_tokens": estimate_tokens(view), "got": got}


def main():
    if sys.argv[1] == "structural":
        res = {}
        for arm in ("raw", "legacy_table", "structured", "structured_lossy"):
            ok = toks = 0
            for i in range(100):
                text, ans = gen_doc(i)
                v = views(text)[arm]
                toks += estimate_tokens(v)
                ok += structural_check(v if arm != "raw" else compress_json(text, mode="conservative"), ans) \
                    if arm == "raw" else structural_check(v, ans)
            res[arm] = {"structural_ok": ok, "mean_view_tokens_est": toks / 100}
        print(json.dumps(res, indent=1))
        return
    model, n, workers = sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 100, int(sys.argv[4]) if len(sys.argv) > 4 else 6
    out = Path(f"results/v5_1/json_extraction_probe_{model}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {(r["doc"], r["arm"]) for r in map(json.loads, out.read_text().splitlines())} if out.exists() else set()
    jobs = [(i, a) for i in range(n) for a in ("raw", "legacy_table", "structured", "structured_lossy") if (i, a) not in done]
    lock = threading.Lock()

    def work(job):
        try:
            row = episode(model, *job)
        except Exception as exc:
            row = {"doc": job[0], "arm": job[1], "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        with lock, out.open("a") as f:
            f.write(json.dumps(row) + "\n")

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, jobs))


if __name__ == "__main__":
    main()
