"""Offline tests for the v3 changes: volatile-line hoisting, name-sorted tools, proxy upstream config."""
import json
import os
import threading
import unittest
from unittest import mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from bench.real_meta import naive_system, tool_json, tool_names
from tokentrim.clients.meta import MetaModelClient
from tokentrim.clients.mock import MockProviderClient
from tokentrim.layout import VOLATILE_SEGMENT_ID, deterministic_segments, hoist_volatile_lines, stable_json
from tokentrim.middleware import TokenTrim
from tokentrim.planner import PromptSegment
from tokentrim.proxy import make_server
from tokentrim.pruner import ContextItem
from tokentrim.router import Step


class HoistTests(unittest.TestCase):
    def test_hoists_timestamp_and_request_id_lines(self):
        segs = [PromptSegment("system", "Rules\nCurrent time: 2026-10-30T12:00:00Z\nrequest_id: abc\nMore", "system", "system", True),
                PromptSegment("u", "hello", "message")]
        out, changed = hoist_volatile_lines(segs)
        self.assertEqual(changed, ["system"])
        self.assertEqual(out[0].text, "Rules\nMore")
        self.assertEqual(out[-1].id, VOLATILE_SEGMENT_ID)
        self.assertIn("2026-10-30T12:00:00Z", out[-1].text)
        self.assertIn("request_id: abc", out[-1].text)

    def test_drop_policy_removes_lines_without_trailing_message(self):
        segs = [PromptSegment("system", "Rules\nCurrent time: 2026-10-30T12:00:00Z\nMore", "system", "system", True),
                PromptSegment("u", "hello", "message")]
        out, changed = hoist_volatile_lines(segs, drop=True)
        self.assertEqual(changed, ["system"])
        self.assertEqual([s.text for s in out], ["Rules\nMore", "hello"])

    def test_volatile_policy_is_validated(self):
        with self.assertRaises(ValueError):
            TokenTrim(MockProviderClient(), token_budget=1000, strong_model="fake/strong", volatile_policy="hide")

    def test_no_volatile_lines_is_identity(self):
        segs = [PromptSegment("system", "Rules only", "system", "system", True)]
        self.assertEqual(hoist_volatile_lines(segs), (segs, []))

    def test_middleware_makes_prefix_byte_stable_under_timestamp(self):
        client = MockProviderClient(min_cacheable_tokens=0, cache_block_tokens=1)
        pipeline = TokenTrim(client, token_budget=10**6, strong_model="fake/strong", savers={"cache_layout"})
        cached = []
        for n in range(3):
            items = [ContextItem("system", "system", f"Rules\nCurrent time: 2026-10-30T12:00:0{n}Z\n" + "r" * 400),
                     ContextItem("u", "message", "task " * 50, turn=0)]
            cached.append(pipeline.complete(items, Step("read"))[0].usage.cached_input)
        self.assertEqual(cached[0], 0)
        self.assertGreater(cached[2], 0)

    def test_tool_lists_sorted_by_name(self):
        a = [{"name": "b", "parameters": {"y": 1, "x": 2}}, {"name": "a"}]
        b = [{"name": "a"}, {"parameters": {"x": 2, "y": 1}, "name": "b"}]
        self.assertEqual(stable_json(a), stable_json(b))
        segs = [PromptSegment("tools", json.dumps(a), "tool_schema", "system", True)]
        self.assertEqual(deterministic_segments(segs)[0].text, stable_json(b))


class NaiveClientTests(unittest.TestCase):
    def test_set_order_changes_only_when_tool_set_changes(self):
        scenario = {"tool_count": 4, "tool_desc_chars": 40}
        same = [tool_json(scenario, tool_names(t), "setorder", "s") for t in (1, 2, 3)]
        self.assertEqual(len(set(same)), 1)
        self.assertNotEqual(tool_names(1), tool_names(5))
        setorder = json.loads(tool_json(scenario, tool_names(5), "setorder", "s"))
        clean = json.loads(tool_json(scenario, tool_names(5), "sorted", "s"))
        self.assertEqual(sorted(setorder, key=lambda t: t["name"]), clean)
        self.assertNotEqual(tool_json(scenario, tool_names(5), "setorder", "s"),
                            tool_json(scenario, tool_names(5), "sorted", "s"))
        self.assertEqual(stable_json(setorder), tool_json(scenario, tool_names(5), "sorted", "s"))

    def test_naive_system_has_volatile_second_line(self):
        first, second = naive_system("HEAD\n", "body", True), naive_system("HEAD\n", "body", True)
        self.assertNotEqual(first, second)
        self.assertEqual(naive_system("HEAD\n", "body", False), "HEAD\nbody")


class UpstreamConfigTests(unittest.TestCase):
    def test_base_url_configurable_and_validated(self):
        with mock.patch.dict(os.environ, {"META_API_KEY": "k", "TOKENTRIM_UPSTREAM_BASE_URL": "https://example.test/v1"}, clear=True):
            self.assertEqual(MetaModelClient().base_url, "https://example.test/v1")
            self.assertEqual(MetaModelClient(base_url="http://127.0.0.1:9/v1").base_url, "http://127.0.0.1:9/v1")
            with self.assertRaises(ValueError):
                MetaModelClient(base_url="http://localhost.evil.test/v1")
            self.assertNotIn("k", repr(MetaModelClient()))

    def test_proxy_passes_model_and_rejects_tools(self):
        client = MockProviderClient(min_cacheable_tokens=0)
        seen = []

        def factory(upstream, model):
            seen.append(model)
            return TokenTrim(upstream, strong_model="fake/strong")
        try:
            server = make_server("127.0.0.1", 0, client, factory)
        except PermissionError:
            self.skipTest("loopback sockets unavailable")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        try:
            body = {"model": "fake/strong", "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]}
            with urlopen(Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"}), timeout=3) as r:
                self.assertIn("choices", json.load(r))
            self.assertEqual(seen, ["fake/strong"])
            body["tools"] = [{"type": "function", "function": {"name": "x"}}]
            with self.assertRaises(HTTPError) as ctx:
                urlopen(Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"}), timeout=3)
            self.assertEqual(ctx.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()


class ReplayTests(unittest.TestCase):
    def test_record_then_replay_reproduces_usage_and_outcome(self):
        import tempfile
        from pathlib import Path
        from bench.real_meta import RecordingMeta, ReplayMeta, run_task, _MockResponder
        from bench.real_common import SharedLedger, TaskGuard
        from bench.runner import ROOT, load_tasks
        from bench.simulate import SCENARIOS
        from tokentrim.cost import CostModel
        task = load_tasks("bench/tasks/tasks_40.jsonl")[0]
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "rec.jsonl"
            ledger = SharedLedger(Path(directory) / "ledger.json", 10**6)
            kwargs = dict(scenario=SCENARIOS["toy"], max_attempts=1, run_id="t", log=lambda m: None)
            first = run_task(task, "tokentrim", RecordingMeta(MockProviderClient(_MockResponder()), path), CostModel(),
                             TaskGuard(ledger, 10), **kwargs)
            second = run_task(task, "tokentrim", ReplayMeta(path), CostModel(), TaskGuard(ledger, 10), **kwargs)
            for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "passed", "calls"):
                self.assertEqual(first[key], second[key])
            self.assertGreater(ledger.mine, 0)
