"""Deterministic synthetic workloads with graded answers (SYNTHETIC data, labelled as such).

* agentic: an incident-triage agent with 30 tool schemas (6 relevant) and large stubbed tool results
  (pytest log, CI log, code-search JSON, git diff). The final answer is JSON with 6-7 graded fields;
  in 1/3 of the tasks one field (``worker``) is only present in an unremarkable INFO line of the CI log, so a
  compressor that drops it forces the model to use ``retrieve_original`` (tests the recovery path).
* longchat: 24 user turns of event planning with pasted notes, value changes and distractors; the final
  turn asks for the current value of 8 fields (graded per field).
* chat: sessions of 4 questions answered from a ~2.5k-token price/policy document (graded numerically).
"""
import json
import random

WORDS = ("alpha beta gamma delta service cache worker queue retry request handler config session token "
         "parser schema module client server deploy metric latency window buffer shard replica index").split()


def _sentence(rng, n=12):
    return " ".join(rng.choice(WORDS) for _ in range(n)).capitalize() + "."


# ----------------------------------------------------------------------------- agentic
RELEVANT = {
    "run_tests": ("Run the project's test suite (pytest) and return the full log.", {"path": "string"}),
    "get_ci_log": ("Fetch the full log of a CI job by job id.", {"job_id": "string"}),
    "search_code": ("Search the repository source code for a text pattern; returns JSON matches.", {"query": "string"}),
    "git_diff": ("Show the diff of a commit or revision range.", {"rev": "string"}),
    "read_file": ("Read lines from a repository file.", {"path": "string", "start_line": "integer", "end_line": "integer"}),
    "list_files": ("List files in a repository directory.", {"path": "string"}),
}
DISTRACTORS = [
    ("send_slack_message", "Post a message to a Slack channel on behalf of the user."),
    ("create_jira_ticket", "Create a Jira ticket in a project with a summary and description."),
    ("update_jira_ticket", "Update fields of an existing Jira ticket."),
    ("schedule_meeting", "Create a calendar event and invite attendees."),
    ("list_calendar_events", "List calendar events in a date range."),
    ("query_sales_db", "Run a read-only SQL query against the sales warehouse."),
    ("crm_lookup_contact", "Look up a customer contact record in the CRM."),
    ("crm_update_deal", "Update the stage or amount of a CRM deal."),
    ("send_email", "Send an email message to recipients."),
    ("translate_text", "Translate text between languages."),
    ("generate_image", "Generate an image from a text prompt."),
    ("get_weather", "Get the weather forecast for a city."),
    ("book_travel", "Search and book flights or hotels."),
    ("expense_report", "File an expense report with receipts."),
    ("hr_time_off", "Request paid time off for an employee."),
    ("deploy_service", "Deploy a service version to an environment (production change)."),
    ("rollback_service", "Roll back a service to a previous version (production change)."),
    ("scale_cluster", "Change the node count of a Kubernetes cluster."),
    ("rotate_secret", "Rotate a credential stored in the secret manager."),
    ("billing_invoice", "Create or void a customer invoice."),
    ("analytics_dashboard", "Fetch a product analytics dashboard as JSON."),
    ("feature_flag_toggle", "Turn a feature flag on or off for a cohort."),
    ("pager_ack", "Acknowledge a PagerDuty incident."),
    ("docs_search", "Search the internal wiki for documentation pages."),
]


def _schema(name, desc, params):
    props = {}
    for p, t in params.items():
        props[p] = {"type": t, "description": f"The {p.replace('_', ' ')} argument for {name}."}
    long_desc = desc + " " + ("Returns structured results; errors are reported in the result. "
                              "Respect rate limits and permissions of the calling user. ") * 2
    return {"type": "function", "function": {"name": name, "description": long_desc,
            "parameters": {"type": "object", "properties": props, "required": list(params)[:1]}}}


def agentic_tools():
    tools = [_schema(n, d, p) for n, (d, p) in RELEVANT.items()]
    tools += [_schema(n, d, {"query": "string", "options": "string", "limit": "integer"}) for n, d in DISTRACTORS]
    return sorted(tools, key=lambda t: t["function"]["name"])


AGENT_SYSTEM = (
    "You are an on-call engineering agent. Investigate incidents using the provided tools; tool results are "
    "real outputs from the repository and CI. Do not guess values: every answer field must be supported by a "
    "tool result. When done, reply with ONLY a JSON object with exactly the keys requested by the user.")


def agentic_task(i: int) -> dict:
    rng = random.Random(f"agentic-{i}")
    modules = ["auth", "billing", "cache", "queue", "search", "upload", "notify", "export"]
    mod = modules[i % len(modules)]
    n_pass = rng.randint(350, 700)
    n_fail = rng.randint(1, 3)
    fails = []
    for k in range(n_fail):
        tname = f"test_{mod}_{rng.choice(['limit', 'retry', 'expiry', 'format', 'rounding', 'order'])}_{rng.randint(10, 99)}"
        line = rng.randint(20, 240)
        expected, actual = rng.randint(2, 50), rng.randint(51, 99)
        fails.append({"name": tname, "file": f"tests/test_{mod}.py", "line": line, "expected": expected, "actual": actual})
    first = fails[0]
    const = rng.choice(["RETRY_LIMIT", "MAX_BATCH", "TTL_SECONDS", "PAGE_SIZE", "POOL_SIZE"])
    old_v, new_v = rng.randint(5, 20), rng.randint(21, 60)
    exit_code = rng.choice([1, 2, 3, 137, 143])
    job_id = f"ci-{4000 + i}"
    needs_worker = i % 3 == 0
    req_id = f"r-{rng.randint(100, 999)}"
    worker = f"w-{rng.randint(10, 99)}"
    # pytest log
    lines = ["============================= test session starts ==============================",
             f"platform linux -- Python 3.13.5, pytest-8.3.2", f"collected {n_pass + n_fail} items", ""]
    names = [f"tests/test_{rng.choice(modules)}.py::test_case_{k}" for k in range(n_pass)]
    lines += [f"{n} PASSED{' ' * 20}[{min(99, 100 * k // n_pass):3d}%]" for k, n in enumerate(names)]
    lines += ["", "=================================== FAILURES ==================================="]
    for f in fails:
        lines += [f"_______________________________ {f['name']} _______________________________", "",
                  f"    def {f['name']}():", f"        result = compute_{mod}(load_fixture())",
                  f">       assert result == {f['expected']}", f"E       assert {f['actual']} == {f['expected']}",
                  "", f"{f['file']}:{f['line']}: AssertionError"]
    lines += ["=========================== short test summary info ============================"]
    lines += [f"FAILED {f['file']}::{f['name']} - assert {f['actual']} == {f['expected']}" for f in fails]
    lines += [f"======================== {n_fail} failed, {n_pass} passed in {rng.uniform(20, 90):.2f}s ========================"]
    test_log = "\n".join(lines)
    # CI log
    ci = []
    t = 0
    for k in range(rng.randint(450, 650)):
        t += rng.randint(1, 3)
        stamp = f"2026-10-{20 + i % 9:02d}T08:{(t // 60) % 60:02d}:{t % 60:02d}Z"
        roll = rng.random()
        if roll < 0.45:
            msg = f"INFO step {k}: {_sentence(rng, 8)}"
        elif roll < 0.8:
            msg = "INFO heartbeat ok"
        else:
            msg = f"DEBUG request r-{rng.randint(100, 999)} handled by worker w-{rng.randint(10, 99)} in {rng.randint(3, 900)}ms"
        ci.append(f"{stamp} {msg}")
    pos = len(ci) // 2 + rng.randint(-50, 50)
    ci[pos] = ci[pos].split(" ")[0] + f" DEBUG request {req_id} handled by worker {worker} in {rng.randint(3, 900)}ms"
    # make sure req_id appears exactly once
    ci = [l if (req_id not in l or k == pos) else l.replace(req_id, "r-000") for k, l in enumerate(ci)]
    end = ci[-1].split(" ")[0]
    ci.append(f"{end} INFO pytest finished: {n_fail} failed, {n_pass} passed (full report in the run_tests output)")
    ci += [f"{end} INFO FAILED {f['file']}::{f['name']}" for f in fails]
    ci.append(f"{end} ERROR job {job_id} failed: pytest exited with exit code {exit_code}")
    ci_log = "\n".join(ci)
    # code search JSON
    hits = [{"path": f"src/{rng.choice(modules)}/{rng.choice(['core', 'util', 'api'])}.py", "line": rng.randint(1, 400),
             "text": f"{rng.choice(WORDS)}_{rng.choice(WORDS)} = {rng.randint(0, 99)}"} for _ in range(rng.randint(50, 90))]
    hits.insert(rng.randint(0, len(hits)), {"path": f"src/{mod}/config.py", "line": 12, "text": f"{const} = {new_v}"})
    # diff
    body = [f" {_sentence(rng, 6).lower()[:-1]} = {rng.randint(0, 9)}" for _ in range(160)]
    where = rng.randint(30, 120)
    diff_lines = [f"diff --git a/src/{mod}/config.py b/src/{mod}/config.py", f"--- a/src/{mod}/config.py",
                  f"+++ b/src/{mod}/config.py", f"@@ -1,160 +1,160 @@"]
    diff_lines += body[:where] + [f"-{const} = {old_v}", f"+{const} = {new_v}"] + body[where:]
    diff = "\n".join(diff_lines)
    keys = {"failing_tests": sorted(f["name"] for f in fails),
            "first_failure_location": f"{first['file']}:{first['line']}",
            "first_failure_actual": first["actual"], "first_failure_expected": first["expected"],
            "passed_count": n_pass, "ci_exit_code": exit_code,
            "changed_constant": f"{const}={new_v}"}
    if needs_worker:
        keys["worker"] = worker
    prompt = (f"Incident: CI job {job_id} for the `{mod}` service is red after the latest commit (rev HEAD~1..HEAD).\n"
              "Investigate with the tools and answer with ONLY a JSON object with these keys:\n"
              "- failing_tests: list of failing test function names\n"
              "- first_failure_location: \"path:line\" of the first failure's AssertionError\n"
              "- first_failure_actual / first_failure_expected: the integers in the first failing assertion\n"
              "- passed_count: number of passed tests\n- ci_exit_code: exit code reported in the CI log\n"
              "- changed_constant: \"NAME=new_value\" for the constant changed in the latest commit's diff")
    if needs_worker:
        prompt += f"\n- worker: the worker id that handled request {req_id} according to the CI log"
    stubs = {"run_tests": test_log, "get_ci_log": ci_log, "search_code": json.dumps(hits, indent=2),
             "git_diff": diff,
             "list_files": json.dumps([f"src/{mod}/config.py", f"src/{mod}/core.py", f"tests/test_{mod}.py"]),
             "read_file": "\n".join(f"{n + 1:4d}  {l}" for n, l in enumerate(body[:80]))}
    return {"id": f"ag{i:02d}", "system": AGENT_SYSTEM, "prompt": prompt, "stubs": stubs, "answer": keys}


def run_stub(task, name, args):
    if name in task["stubs"]:
        return task["stubs"][name]
    return json.dumps({"error": f"{name} is not relevant to this repository incident"})


def _norm(v):
    if isinstance(v, str):  # trailing sentence period ignored ("Blue Plate Co." vs "Blue Plate Co", issue 66)
        return v.strip().rstrip(".").replace(" ", "").lower()
    if isinstance(v, list):
        return sorted(_norm(x) for x in v)
    return v


def grade_json(answer_text: str, expected: dict) -> tuple[float, dict]:
    text = (answer_text or "").strip()
    try:
        s, e = text.find("{"), text.rfind("}")
        got = json.loads(text[s:e + 1])
    except ValueError:
        return 0.0, {k: False for k in expected}
    result = {}
    for k, v in expected.items():
        g = got.get(k)
        if isinstance(v, int) and not isinstance(v, bool):
            try:
                result[k] = int(str(g).strip()) == v
            except ValueError:
                result[k] = False
        else:
            result[k] = _norm(g) == _norm(v)
    return sum(result.values()) / len(result), result


# ----------------------------------------------------------------------------- long chat
FIRST = ["Asha", "Ravi", "Meera", "Kiran", "Dev", "Lena", "Omar", "Priya", "Tom", "Yuki"]
VENUES = ["Lakeside Hall", "Orchid Pavilion", "Riverfront Loft", "Cedar Grove Barn", "Harbor View Room",
          "Summit Terrace", "Garden Court", "Old Mill Gallery"]
CATERERS = ["Spice Route", "Green Fork", "Saffron & Sage", "Blue Plate Co", "Tandoor House", "Olive Branch"]


def longchat_task(i: int) -> dict:
    rng = random.Random(f"longchat-{i}")
    facts = {"event_name": f"{rng.choice(['Annual', 'Spring', 'Founders', 'Winter'])} {rng.choice(['Summit', 'Gala', 'Offsite', 'Mixer'])} {2026 + i % 2}",
             "date": f"2026-{rng.randint(11, 12)}-{rng.randint(10, 28)}",
             "venue": rng.choice(VENUES), "headcount": rng.randint(60, 180),
             "budget_usd": rng.randint(30, 90) * 100, "caterer": rng.choice(CATERERS),
             "contact_email": f"{rng.choice(FIRST).lower()}.{rng.randint(10, 99)}@example.org",
             "start_time": f"{rng.randint(9, 18)}:{rng.choice(['00', '30'])}"}
    order = list(facts)
    rng.shuffle(order)
    turns = [f"Hi! I'm organizing an event and want your help keeping track of the details. Let's start: "
             f"the {order[0].replace('_', ' ')} is {facts[order[0]]}."]
    final = dict(facts)
    pending = order[1:]
    changes = rng.sample(["headcount", "budget_usd", "venue", "start_time", "date"], 3)
    while len(turns) < 24:
        r = rng.random()
        if pending and (r < 0.35 or len(turns) > 24 - len(pending) - 4):
            k = pending.pop(0)
            turns.append(f"Another detail: the {k.replace('_', ' ')} is {facts[k]}. Please note it.")
        elif changes and k_known(final, changes[0], order, pending) and r < 0.55 and len(turns) > 6:
            k = changes.pop(0)
            new = {"headcount": final["headcount"] + rng.randint(5, 40), "budget_usd": final["budget_usd"] + rng.randint(5, 20) * 100,
                   "venue": rng.choice([v for v in VENUES if v != final["venue"]]),
                   "start_time": f"{rng.randint(9, 18)}:{rng.choice(['15', '45'])}",
                   "date": f"2026-{rng.randint(11, 12)}-{rng.randint(10, 28)}"}[k]
            turns.append(f"Update: change of plans, the {k.replace('_', ' ')} is now {new} (no longer {final[k]}).")
            final[k] = new
        elif r < 0.75:
            other = rng.choice(["my cousin's wedding", "last year's party", "a friend's conference"])
            turns.append(f"Unrelated aside: for {other} they had {rng.randint(200, 400)} guests at {rng.choice(VENUES)} "
                         f"with a budget of ${rng.randint(100, 200) * 100}. Not our event, just context. "
                         + " ".join(_sentence(rng, 14) for _ in range(8)))
        else:
            turns.append("Here are my raw notes from the planning call, keep them in mind: " +
                         " ".join(_sentence(rng, 16) for _ in range(rng.randint(22, 32))))
    for k in pending:  # ensure every fact was stated
        turns.insert(len(turns) - 2, f"Another detail: the {k.replace('_', ' ')} is {facts[k]}. Please note it.")
    question = ("Final check. Reply with ONLY a JSON object with the CURRENT value of each key for OUR event: "
                + ", ".join(facts) + ". Use numbers for headcount and budget_usd.")
    return {"id": f"lc{i:02d}", "turns": turns, "question": question, "answer": final}


def k_known(final, key, order, pending):
    return key not in pending


LONGCHAT_SYSTEM = ("You are a meticulous event-planning assistant. Keep track of every detail the user gives, "
                   "including later changes. Reply to each message in one or two short sentences.")


# ----------------------------------------------------------------------------- plain chat
def chat_doc() -> tuple[str, dict]:
    rng = random.Random("chat-doc")
    items = {}
    lines = ["ACME HARDWARE - PRICE LIST AND POLICIES (internal reference, version 7)", ""]
    for n in range(60):
        sku = f"SKU-{1000 + n}"
        price = round(rng.uniform(3, 250), 2)
        items[sku] = price
        lines.append(f"{sku}: {rng.choice(['Hex', 'Torx', 'Brass', 'Steel', 'Cordless', 'Mini'])} "
                     f"{rng.choice(['wrench', 'drill', 'clamp', 'hinge', 'saw', 'ladder', 'bolt kit'])} - ${price:.2f}")
    lines += ["", "Policies:",
              "1. Loyalty members get 10% off the item subtotal (before tax).",
              "2. Orders with a subtotal (after any discount) of $200 or more ship free; otherwise shipping is $12.50.",
              "3. Sales tax is 8% applied to the discounted subtotal, not to shipping.",
              "4. Returns within 30 days get a full refund; 31-60 days get store credit minus a 15% restocking fee.",
              "5. Bulk rule: buying 10 or more units of one SKU takes an extra 5% off that line (applied before loyalty)."]
    lines += ["", "Notes: " + " ".join(_sentence(rng, 18) for _ in range(40))]
    return "\n".join(lines), items


def chat_task(i: int, items: dict) -> dict:
    rng = random.Random(f"chat-{i}")
    qs = []
    for q in range(4):
        sku = rng.choice(sorted(items))
        qty = rng.choice([1, 2, 3, 4, 10, 12])
        loyal = rng.random() < 0.5
        line = items[sku] * qty * (0.95 if qty >= 10 else 1)
        sub = line * (0.9 if loyal else 1)
        ship = 0 if sub >= 200 else 12.5
        total = round(sub * 1.08 + ship, 2)
        qs.append({"q": f"A {'loyalty member' if loyal else 'non-member'} buys {qty} x {sku}. What is the order total "
                        f"in dollars including tax and shipping? End your reply with a line 'TOTAL: <number>'.",
                   "answer": total})
    return {"id": f"ch{i:02d}", "questions": qs}


def grade_total(text: str, expected: float) -> bool:
    import re
    m = re.findall(r"TOTAL:\s*\$?\s*([0-9][0-9,]*\.?[0-9]*)", text or "")
    if not m:
        return False
    try:
        return abs(float(m[-1].replace(",", "")) - expected) <= 0.011
    except ValueError:
        return False
