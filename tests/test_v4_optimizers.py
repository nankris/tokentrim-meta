import json
import multiprocessing
import os
import tempfile
import threading
import unittest

from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.guard import SpendCapExceeded
from tokentrim.ledger import SpendLedger
from tokentrim.optimizers import cache_prefix
from tokentrim.optimizers.schema_router import SchemaRouter, tool_name
from tokentrim.optimizers.tool_output import ToolOutputCompressor, classify
from tokentrim.store import OriginalStore
from tokentrim.upstream import MockChatUpstream

MODEL = "muse-spark-1.3-contributor"


def tool(name, desc):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}


TOOLS = [tool("read_file", "Read a source file from the repository"),
         tool("run_tests", "Run the project's unit tests and return the log"),
         tool("search_code", "Search code in the repository for a pattern"),
         tool("edit_file", "Replace text in a file")] + \
        [tool(f"crm_{i}", f"Customer relationship management record operation number {i} for sales leads " * 3)
         for i in range(16)] + [tool("send_slack_message", "Post a message to a Slack channel " * 3)]


def test_log(n_pass=400):
    lines = ["============================= test session starts =============================",
             f"collected {n_pass + 2} items"]
    lines += [f"tests/test_mod{i % 9}.py::test_case_{i} PASSED" for i in range(n_pass)]
    lines += ["=================================== FAILURES ===================================",
              "______________________________ test_jwt_signature ______________________________",
              "tests/test_auth.py:42: in test_jwt_signature",
              "E       AssertionError: Invalid JWT signature: expected 'HS256' got 'none'",
              "",
              "______________________________ test_db_timeout ______________________________",
              "tests/test_db.py:81: in test_db_timeout",
              "E       TimeoutError: Connection timeout after 30.0s (host=db-7)",
              "",
              f"========================= 2 failed, {n_pass} passed in 12.34s ========================="]
    return "\n".join(lines)


def _proc_reserve(path, n, out):
    led = SpendLedger(path, job_cap_usd=1.0, run_cap_usd=1.0, run_id="p")
    ok = 0
    for _ in range(n):
        try:
            t = led.reserve(0.05)
            led.commit(t, 0.05)
            ok += 1
        except SpendCapExceeded:
            pass
    out.put(ok)


class LedgerTests(unittest.TestCase):
    def test_threads_cannot_overshoot(self):
        with tempfile.TemporaryDirectory() as d:
            led = SpendLedger(os.path.join(d, "l.json"), job_cap_usd=0.30, run_cap_usd=5, run_id="r")
            tokens, errs = [], []

            def worker():
                try:
                    tokens.append(led.reserve(0.1))
                except SpendCapExceeded:
                    errs.append(1)
            ts = [threading.Thread(target=worker) for _ in range(10)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(len(tokens), 3)
            for t in tokens:
                led.commit(t, 0.08)
            self.assertAlmostEqual(led.total(), 0.24)
            with self.assertRaises(SpendCapExceeded):
                led.reserve(0.07)

    def test_processes_share_reservations(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "l.json")
            q = multiprocessing.Queue()
            ps = [multiprocessing.Process(target=_proc_reserve, args=(path, 10, q)) for _ in range(4)]
            [p.start() for p in ps]
            [p.join() for p in ps]
            total_ok = sum(q.get() for _ in ps)
            self.assertEqual(total_ok, 20)
            self.assertLessEqual(SpendLedger(path, 1, 1, "x").total(), 1.0 + 1e-9)

    def test_run_cap_and_release(self):
        with tempfile.TemporaryDirectory() as d:
            led = SpendLedger(os.path.join(d, "l.json"), job_cap_usd=12, run_cap_usd=0.1, run_id="r")
            t = led.reserve(0.09)
            with self.assertRaises(SpendCapExceeded):
                led.reserve(0.02)
            led.release(t)
            led.reserve(0.02)

    def test_upstream_reserves_before_call(self):
        with tempfile.TemporaryDirectory() as d:
            led = SpendLedger(os.path.join(d, "l.json"), job_cap_usd=0.001, run_cap_usd=1, run_id="r")
            up = MockChatUpstream(ledger=led)
            with self.assertRaises(SpendCapExceeded):  # 16000 max_tokens * $0.20/M > $0.001
                up.create({"model": MODEL, "messages": [{"role": "user", "content": "hi"}]})
            self.assertEqual(up.calls, [])
            data, usage = up.create({"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100})
            self.assertGreater(led.total(), 0)


class ToolOutputTests(unittest.TestCase):
    def test_test_log_keeps_failures_and_counts(self):
        store = OriginalStore()
        log = test_log()
        self.assertEqual(classify(log), "test")
        r = ToolOutputCompressor(store).compress(log)
        self.assertLess(r.tokens_after, 0.2 * r.tokens_before)
        for needle in ["tests/test_auth.py:42", "Invalid JWT signature: expected 'HS256' got 'none'",
                       "tests/test_db.py:81", "30.0s (host=db-7)", "2 failed, 400 passed in 12.34s"]:
            self.assertIn(needle, r.text)
        self.assertEqual(store.get(r.ref), log)
        self.assertIn(f'retrieve_original("{r.ref}")', r.text)
        self.assertEqual(ToolOutputCompressor(store).compress(log).text, r.text)  # deterministic

    def test_json_records_keep_keys_for_small_rows(self):
        rows = [{"id": i, "status": "open" if i % 7 else "error", "amount": i * 1.5} for i in range(60)]
        text = json.dumps({"items": rows, "page": 1}, indent=2)
        r = ToolOutputCompressor(min_tokens=100).compress(text)
        self.assertEqual(r.kind, "json")
        for i, row in enumerate(rows):  # every record intact, keyed, with its JSON Pointer (issue 69)
            self.assertIn(f"/items/{i} " + json.dumps(row, separators=(",", ":")), r.text)
        self.assertNotIn(" | ", r.text)
        self.assertLess(r.tokens_after, r.tokens_before)

    def test_log_and_diff(self):
        log = "\n".join([f"2026-10-30T10:00:{i:02d}Z INFO heartbeat ok" for i in range(50)] +
                        ["2026-10-30T10:01:00Z ERROR worker crashed: exit code 137 in job_17"] +
                        [f"2026-10-30T10:02:{i:02d}Z INFO request {i} served" for i in range(60)])
        r = ToolOutputCompressor(min_tokens=100).compress(log)
        self.assertEqual(r.kind, "log")
        self.assertIn("exit code 137 in job_17", r.text)
        diff = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,80 +1,80 @@\n" + \
            "\n".join(f" ctx line {i}" for i in range(40)) + "\n-old = 1\n+new = 2\n" + \
            "\n".join(f" ctx line {i}" for i in range(40, 200))
        r = ToolOutputCompressor(min_tokens=100).compress(diff)
        self.assertEqual(r.kind, "diff")
        self.assertIn("+new = 2", r.text)
        self.assertIn("-old = 1", r.text)

    def test_small_output_untouched(self):
        r = ToolOutputCompressor().compress("ok")
        self.assertIsNone(r.ref)


class SchemaRouterTests(unittest.TestCase):
    def test_selects_relevant_and_keeps_used(self):
        msgs = [{"role": "user", "content": "The unit tests fail; read the source file and fix it"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function",
                 "function": {"name": "send_slack_message", "arguments": "{}"}}]}]
        sel, first = SchemaRouter(keep=4).select(TOOLS, msgs, None, None)
        self.assertIn("run_tests", sel)
        self.assertIn("read_file", sel)
        self.assertIn("send_slack_message", sel)
        self.assertLessEqual(len(sel), 5)


def responder_factory():
    def responder(payload):
        msgs = payload["messages"]
        last = msgs[-1]
        names = {tool_name(t) for t in payload.get("tools") or []}
        if msgs[0]["content"].startswith("You compress a conversation"):
            return {"role": "assistant", "content": json.dumps({"goal": "plan trip", "facts": {"budget": "4500"}})}
        if last["role"] == "user" and "search_tools" in names and "edit_file" not in names:
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": "s1", "type": "function", "function": {"name": "search_tools", "arguments": '{"query": "edit replace text in a file"}'}}]}
        if last["role"] == "tool" and "edit_file" in names and "retrieve" not in json.dumps(msgs[-3:]):
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": "e1", "type": "function", "function": {"name": "edit_file", "arguments": '{"path": "a.py"}'}}]}
        return {"role": "assistant", "content": "done"}
    return responder


class GatewayTests(unittest.TestCase):
    def test_cache_prefix_drops_timestamp_and_sorts_tools(self):
        p = {"model": MODEL, "tools": list(reversed(TOOLS[:3])), "messages": [
            {"role": "system", "content": "You are helpful.\nCurrent time: 2026-10-30T12:00:01.123Z request_id: 8f1d2c3a-1b2c-4d5e-8f90-123456789abc\nBe brief."},
            {"role": "user", "content": "hi"}]}
        notes = cache_prefix.apply(p)
        self.assertEqual(p["messages"][0]["content"], "You are helpful.\nBe brief.")
        self.assertEqual([tool_name(t) for t in p["tools"]], ["read_file", "run_tests", "search_code"])
        self.assertTrue(notes)
        q = json.loads(json.dumps(p))
        q["messages"][0]["content"] = "You are helpful.\nCurrent time: 2026-10-30T12:00:01Z\nBe brief."
        cache_prefix.apply(q, keep_date=True)
        self.assertIn("Current date: 2026-10-30", q["messages"][0]["content"])

    def test_schema_router_with_search_tools_recovery(self):
        up = MockChatUpstream(responder=responder_factory())
        gw = Gateway(up, GatewayConfig(schema_router=True, schema_keep=2))
        p = {"model": MODEL, "tools": TOOLS, "messages": [{"role": "user", "content": "run the unit tests"}]}
        data, rep = gw.complete(p, "c1")
        self.assertTrue(any("Removed" in e and "unused tool schemas" in e for e in rep.explanations))
        self.assertTrue(any("search_tools" in e and "edit_file" in e for e in rep.explanations))
        self.assertEqual(data["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "edit_file")
        self.assertLess(len(up.calls[0]["tools"]), len(TOOLS))
        # second request in the same conversation: frozen selection (+ recovered tool) unchanged order
        p2 = json.loads(json.dumps(p))
        p2["messages"] += [data["choices"][0]["message"], {"role": "tool", "tool_call_id": "e1", "content": "ok"}]
        gw.complete(p2, "c1")
        names = [tool_name(t) for t in up.calls[-1]["tools"]]
        self.assertIn("edit_file", names)

    def test_tool_output_compressed_in_request_and_retrievable(self):
        up = MockChatUpstream()
        gw = Gateway(up, GatewayConfig(tool_output=True))
        p = {"model": MODEL, "tools": TOOLS[:2], "messages": [
            {"role": "user", "content": "why do tests fail"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "run_tests", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "t1", "content": test_log()}]}
        data, rep = gw.complete(p)
        sent = up.calls[0]["messages"][-1]["content"]
        self.assertIn("tests/test_auth.py:42", sent)
        self.assertLess(len(sent), len(test_log()) / 4)
        self.assertIn("retrieve_original", [tool_name(t) for t in up.calls[0]["tools"]])
        ref = sent.split('retrieve_original("')[1].split('"')[0]
        self.assertEqual(gw.store.get(ref), test_log())

    def test_history_compaction_and_reuse(self):
        up = MockChatUpstream(responder=responder_factory())
        gw = Gateway(up, GatewayConfig(history=True, history_min_tokens=500, history_keep_recent=4,
                                       cost_guard=True))
        msgs = [{"role": "system", "content": "assistant"}]
        for i in range(30):
            msgs += [{"role": "user", "content": f"note {i}: " + "detail " * 40}, {"role": "assistant", "content": "ok"}]
        msgs.append({"role": "user", "content": "what's the budget?"})
        data, rep = gw.complete({"model": MODEL, "messages": msgs}, "h1")
        self.assertEqual(rep.compaction_calls, 1)
        self.assertTrue(any("Compacted" in e for e in rep.explanations))
        sent = up.calls[-1]["messages"]
        self.assertLess(len(sent), len(msgs))
        self.assertIn('"budget":"4500"', json.dumps(sent).replace('\\"', '"'))
        msgs += [{"role": "assistant", "content": "4500"}, {"role": "user", "content": "thanks"}]
        data, rep2 = gw.complete({"model": MODEL, "messages": msgs}, "h1")
        self.assertEqual(rep2.compaction_calls, 0)  # block reused, cache stable

    def test_fail_open(self):
        up = MockChatUpstream()
        gw = Gateway(up, GatewayConfig(schema_router=True, tool_output=True))
        bad = {"model": MODEL, "tools": [{"weird": 1}], "messages": [{"role": "user", "content": "x"}]}
        data, rep = gw.complete(bad)
        self.assertEqual(data["choices"][0]["message"]["content"], "MOCK reply")


if __name__ == "__main__":
    unittest.main()


class QueryAwareAndGrepTest(unittest.TestCase):
    def test_task_identifier_lines_survive_log_compression(self):
        from tokentrim.optimizers.tool_output import ToolOutputCompressor, task_terms
        lines = [f"2026-10-01T00:00:{i % 60:02d}Z DEBUG request r-{100 + i} handled by worker w-{i % 90}" for i in range(600)]
        text = "\n".join(lines)
        out = ToolOutputCompressor(min_tokens=100).compress(text, task_terms(["Which worker handled request r-417?"]))
        self.assertIsNotNone(out.ref)
        self.assertIn("r-417 handled by worker w-47", out.text)
        self.assertIn("omitted lines by level: DEBUG", out.text)

    def test_grep_original(self):
        from tokentrim.transforms import grep_original
        text = "a\nfoo 1\nb\nFOO 2"
        self.assertEqual(grep_original(text, "foo"), "2 matching lines for /foo/:\n2: foo 1\n4: FOO 2")
        self.assertIn("No lines match", grep_original(text, "zzz"))
        self.assertIn("1 matching", grep_original("x(\ny", "x("))  # invalid regex -> substring
