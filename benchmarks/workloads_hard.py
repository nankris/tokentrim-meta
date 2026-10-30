"""HARD agentic workload (v5 validation). SYNTHETIC data only: ids, logs, spans and manifests are generated
deterministically from the task index; there is no real or personal information in any task.

Each task is a 4-hop root-cause investigation designed to exercise every TokenTrim recovery path:
1. ``get_ci_log(job_id)``: a ~900-line CI log. The UNHANDLED exception (traceback with 3-4 frames) is hidden deep in
   the log (70-90% of the way down) next to 2 decoy exceptions that were retried/recovered.
2. The request id of that exception leads to a ``trace_ref`` that appears ONLY in an unremarkable INFO line far
   above the traceback, so a compressed view of the log does not show it: the model must grep/retrieve the
   original (``retrieve_original``), or read the raw log in the baseline.
3. ``inspect_spans(span_root=<trace_ref>)``: a JSON span tree; the failing span names the release and the setting.
   This tool's name and description share no words with the task prompt, and the prompt contains words of
   several distractor tools (deploy, roll back, feature flag, page, ticket), so a BM25 tool router selects the
   WRONG tools; the model has to recover the right one through ``search_tools`` (adversarial for routing).
4. ``open_artifact_manifest(build=<release>)``: key/value entries of that release, with a decoy section for the
   previous release.
Grading: 6 exact fact fields + 3 required tool executions with the correct dependent arguments + no
side-effecting tool calls. A task PASSES only if all of them hold.
"""
import json
import random

from .workloads import DISTRACTORS, RELEVANT, WORDS, _schema, _sentence, grade_json

HARD_TOOLS_EXTRA = {
    "inspect_spans": ("Return the distributed span hierarchy captured by the observability backend for one root "
                      "identifier.", {"span_root": "string"}),
    "open_artifact_manifest": ("Open the packaged artifact manifest of a build and list its key/value "
                               "configuration entries.", {"build": "string"}),
}
SIDE_EFFECT_TOOLS = {"deploy_service", "rollback_service", "feature_flag_toggle", "scale_cluster", "rotate_secret",
                     "pager_ack", "send_slack_message", "send_email", "create_jira_ticket", "update_jira_ticket",
                     "crm_update_deal", "billing_invoice", "book_travel", "expense_report", "hr_time_off"}
EXC_TYPES = ["PoolExhaustedError", "LedgerMismatchError", "SchemaVersionError", "QuotaStateError",
             "ShardRoutingError", "TokenScopeError"]
DECOY_EXC = ["TimeoutError", "ConnectionResetError", "BrokenPipeError"]
SETTINGS = ["POOL_SIZE", "MAX_INFLIGHT", "SHARD_COUNT", "LEASE_TTL_S", "BATCH_LIMIT", "RETRY_BUDGET"]
MODULES = ["auth", "billing", "cache", "queue", "search", "upload", "notify", "export"]

HARD_SYSTEM = (
    "You are an on-call engineering agent. Investigate incidents using the provided tools; tool results are "
    "real outputs from CI and observability systems. This is a read-only investigation: never call tools that "
    "change production, post messages or file tickets. Do not guess values: every answer field must be "
    "supported by a tool result. When done, reply with ONLY a JSON object with exactly the keys requested.")


def hard_tools():
    tools = [_schema(n, d, p) for n, (d, p) in RELEVANT.items()]
    tools += [_schema(n, d, p) for n, (d, p) in HARD_TOOLS_EXTRA.items()]
    tools += [_schema(n, d, {"query": "string", "options": "string", "limit": "integer"}) for n, d in DISTRACTORS]
    return sorted(tools, key=lambda t: t["function"]["name"])


def _hex(rng, n=6):
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _traceback(rng, mod, exc, msg, frames):
    lines = ["Traceback (most recent call last):"]
    for path, line, fn in frames:
        lines += [f'  File "{path}", line {line}, in {fn}', f"    {_sentence(rng, 5).lower()[:-1].replace(' ', '_')}()"]
    lines.append(f"{exc}: {msg}")
    return lines


def hard_task(i: int) -> dict:
    rng = random.Random(f"agentic-hard-{i}")
    mod = MODULES[i % len(MODULES)]
    job_id = f"ci-{7000 + i}"
    exc = rng.choice(EXC_TYPES)
    setting = rng.choice(SETTINGS)
    n_frames = rng.choice([3, 4])
    frames = [(f"src/{mod}/{p}.py", rng.randint(20, 400), fn) for p, fn in
              [("api", "handle"), ("service", "apply"), ("core", "execute"), ("pool", "acquire")][:n_frames]]
    location = f"{frames[-1][0]}:{frames[-1][1]}"
    # requests
    n_req = rng.randint(50, 70)
    req_ids = rng.sample(range(1000, 9999), n_req + 3)
    reqs = [{"id": f"q-{r}", "trace": f"tr-{_hex(rng)}"} for r in req_ids]
    bad, decoys = reqs[0], reqs[1:3]
    # build the CI log
    log = []
    t = 0

    def stamp():
        nonlocal t
        t += rng.randint(1, 3)
        return f"2026-10-{10 + i % 18:02d}T09:{(t // 60) % 60:02d}:{t % 60:02d}Z"

    for k in range(rng.randint(820, 960)):
        r = rng.random()
        if r < 0.40:
            log.append(f"{stamp()} INFO step {k}: {_sentence(rng, 8)}")
        elif r < 0.75:
            log.append(f"{stamp()} INFO heartbeat ok")
        else:
            log.append(f"{stamp()} DEBUG cache {rng.choice(WORDS)} hit ratio {rng.randint(40, 99)}% in {rng.randint(1, 90)}ms")
    n = len(log)
    # accepted lines for every request (bad one far above its traceback), each surrounded by plain lines
    exc_pos = int(n * rng.uniform(0.70, 0.90))
    acc_pos = rng.randint(int(n * 0.15), int(n * 0.45))
    used = {exc_pos, acc_pos}
    positions = {}
    for q in reqs[1:]:
        while True:
            p = rng.randint(10, n - 10)
            if all(abs(p - u) > 3 for u in used):
                used.add(p)
                positions[q["id"]] = p
                break
    positions[bad["id"]] = acc_pos
    route = lambda: f"/v2/{mod}/{rng.choice(['items', 'jobs', 'quotes', 'batches', 'accounts'])}"
    for q in reqs:
        log[positions[q["id"]]] = (f"{log[positions[q['id']]][:20]} INFO req={q['id']} accepted "
                                   f"trace_ref={q['trace']} route={route()} client=c-{rng.randint(10, 99)}")
    # make sure the neighbours of the bad request's accepted line are unremarkable
    for p in (acc_pos - 1, acc_pos + 1):
        log[p] = f"{log[p][:20]} INFO heartbeat ok"
    # tracebacks: 2 decoys (recovered) before/around, the real one deep down
    blocks = []
    for d, q in enumerate(decoys):
        dex = rng.choice(DECOY_EXC)
        dpos = rng.randint(int(n * 0.3), int(n * 0.65)) + d * 7
        dframes = [(f"src/{mod}/client.py", rng.randint(20, 300), "send"), (f"src/{mod}/net.py", rng.randint(20, 300), "write")]
        blocks.append((dpos, [f"WARN req={q['id']} recovered exception, request retried successfully (attempt 2):"]
                       + _traceback(rng, mod, dex, "upstream closed the connection", dframes)))
    blocks.append((exc_pos, [f"ERROR req={bad['id']} unhandled exception, request failed with HTTP 500:"]
                   + _traceback(rng, mod, exc, f"{setting.lower()} exhausted while processing batch {rng.randint(100, 999)}",
                                frames)))
    for pos, blk in sorted(blocks, key=lambda b: -b[0]):
        ts = log[pos][:20]
        log[pos + 1:pos + 1] = [f"{ts} {blk[0]}"] + blk[1:]
    end = log[-1][:20]
    log.append(f"{end} INFO requests: {n_req + 3} accepted, 2 retried, 1 failed")
    log.append(f"{end} ERROR job {job_id} failed: 1 request(s) returned HTTP 500 during the integration stage")
    ci_log = "\n".join(log)
    # span tree
    release = f"rel-{rng.randint(1000, 9999)}"
    other_release = f"rel-{rng.randint(1000, 9999)}"
    spans = []
    n_sp = rng.randint(40, 70)
    fail_at = rng.randint(10, n_sp - 5)
    for s in range(n_sp):
        sp = {"span_id": f"sp-{_hex(rng, 4)}", "parent": spans[-1]["span_id"] if spans and rng.random() < 0.6 else
              (spans[0]["span_id"] if spans else None), "service": rng.choice(MODULES),
              "op": f"{rng.choice(['read', 'write', 'call', 'encode', 'lookup'])}_{rng.choice(WORDS)}",
              "ms": rng.randint(1, 400), "status": "ok",
              "release": rng.choice([release, other_release]), "note": ""}
        spans.append(sp)
    spans[fail_at].update({"service": mod, "op": "acquire", "status": "ERROR", "release": release,
                           "note": f"{exc}; setting {setting}"})
    span_json = json.dumps({"trace_ref": bad["trace"], "root_service": mod, "spans": spans}, indent=1)
    # manifests
    value = rng.randint(2, 64)
    old_value = value + rng.randint(5, 40)

    def manifest(build, val, prev_val):
        rows = [f"# artifact manifest for build {build} (service {mod})", "[current]"]
        keys = [f"{rng.choice(WORDS).upper()}_{rng.choice(WORDS).upper()}" for _ in range(60)]
        body = [f"{k} = {rng.randint(0, 500)}" for k in keys if k != setting]
        body.insert(rng.randint(0, len(body)), f"{setting} = {val}")
        rows += body + ["", f"[previous build rel-{rng.randint(1000, 9999)}]", f"{setting} = {prev_val}"]
        rows += [f"{k} = {rng.randint(0, 500)}" for k in keys[:20] if k != setting]
        return "\n".join(rows)

    manifests = {release: manifest(release, value, old_value), other_release: manifest(other_release, old_value, value + 1)}
    answer = {"exception_type": exc, "exception_location": location, "request_id": bad["id"],
              "trace_ref": bad["trace"], "release": release, "setting": f"{setting}={value}"}
    prompt = (f"Incident: after the latest deploy of the `{mod}` service, CI job {job_id} went red and users see "
              "HTTP 500 errors. Before anyone decides to roll back, toggle a feature flag, page someone or file a "
              "ticket, find the underlying cause. Do not deploy, roll back or change anything yourself.\n"
              "Answer with ONLY a JSON object with these fields:\n"
              f"- exception_type: class name of the UNHANDLED exception in the CI log of job {job_id} (ignore "
              "exceptions that were recovered/retried)\n"
              "- exception_location: \"path:line\" of the innermost stack frame of that exception\n"
              "- request_id: id of the request that raised it\n"
              "- trace_ref: the trace_ref recorded when that request was accepted\n"
              "- release: the release that the failing step of that trace_ref ran\n"
              "- setting: \"NAME=number\" for the setting named by that failing step, as currently shipped in that release")
    return {"id": f"ah{i:02d}", "system": HARD_SYSTEM, "prompt": prompt, "answer": answer,
            "job_id": job_id, "ci_log": ci_log, "span_json": span_json, "manifests": manifests,
            "required": {"get_ci_log": job_id, "inspect_spans": bad["trace"], "open_artifact_manifest": release}}


def run_hard_stub(task, name, args):
    blob = json.dumps(args)
    if name == "get_ci_log":
        return task["ci_log"] if task["job_id"] in blob else json.dumps({"error": "unknown job id"})
    if name == "inspect_spans":
        return task["span_json"] if task["required"]["inspect_spans"] in blob else json.dumps({"error": "no spans recorded for that root"})
    if name == "open_artifact_manifest":
        for rel, text in task["manifests"].items():
            if rel in blob:
                return text
        return json.dumps({"error": "unknown build"})
    if name in SIDE_EFFECT_TOOLS:
        return json.dumps({"error": "permission denied: read-only investigation"})
    return json.dumps({"error": f"{name} has no data for this incident"})


def grade_hard(answer_text: str, task: dict, tool_trace: list) -> tuple[float, dict]:
    """Facts (6 fields) + required tool executions (3) + no side effects. Score = fraction of the 10 checks."""
    _, fields = grade_json(answer_text, task["answer"])
    checks = {f"fact:{k}": v for k, v in fields.items()}
    for tool, needle in task["required"].items():
        checks[f"exec:{tool}"] = any(n == tool and needle in json.dumps(a) for n, a in tool_trace)
    checks["no_side_effects"] = not any(n in SIDE_EFFECT_TOOLS for n, _ in tool_trace)
    return sum(checks.values()) / len(checks), checks
