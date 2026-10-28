import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from bench.simulate import run_simulation
from tokentrim.clients.base import ModelResponse, Usage
from tokentrim.clients.mock import MockProviderClient, RecordedClient, RecordingClient
from tokentrim.compaction import OutputStore, compact_tool_output
from tokentrim.cost import CostModel
from tokentrim.guard import SpendCapExceeded, SpendGuard
from tokentrim.layout import deterministic_segments, lint_stable_prefix
from tokentrim.middleware import TokenTrim
from tokentrim.planner import PromptSegment
from tokentrim.pruner import ContextItem
from tokentrim.proxy import make_server
from tokentrim.router import HeuristicRouter, Step
from tokentrim.routing import EscalatingRouter, StepSignals

ROOT = Path(__file__).resolve().parent.parent


class CostAndLayoutTests(unittest.TestCase):
    def test_cost_override_write_and_breakeven(self):
        model = CostModel(prices={"m": {"input": 2, "cached_input": .2, "output": 4,
                                                "cache_write": 2.5}}, overrides={"m": {"output": 5}})
        total, parts = model.cost("m", Usage(1000, 200, 100, 300))
        self.assertAlmostEqual(total, sum(parts.values()))
        self.assertGreater(parts["cache_write"], 0)
        self.assertEqual(model.prices_hash(), model.prices_hash())
        self.assertTrue(model.breakeven_compaction("m", 1, 10000, 10)["should_compact"])

    def test_layout_lint_and_json(self):
        segments = [PromptSegment("t", '{"z":1,"a":2}', "tool_schema", stable=True),
                    PromptSegment("s", "Current time 2026-10-28T12:00:00Z 123e4567-e89b-12d3-a456-426614174000",
                                  "system", stable=True)]
        self.assertEqual(deterministic_segments(segments)[1].text, '{"a":2,"z":1}')
        warnings = lint_stable_prefix(segments)
        self.assertTrue(any("UUID" in warning for warning in warnings))
        self.assertTrue(any("timestamp" in warning for warning in warnings))


class CompactionAndRoutingTests(unittest.TestCase):
    def test_compaction_restores_and_keeps_errors(self):
        store = OutputStore()
        text = "\n".join(["ok"] * 60 + ['  File "x.py", line 9', "AssertionError: bad"] + ["noise"] * 60)
        compacted, report = compact_tool_output(text, max_lines=20, store=store)
        self.assertIn("AssertionError", compacted)
        self.assertIn(f"compacted from {report.lines_before} to {report.lines_after} lines", compacted)
        self.assertIn(f"full output id={report.output_id}", compacted)
        self.assertEqual(store.get(report.output_id), text)

    def test_escalation_causes_sticky_and_contributor_guard(self):
        base = HeuristicRouter("fake/cheap", "fake/strong")
        for signals in (StepSignals(True, previous_model="fake/cheap"), StepSignals(malformed_output=True),
                        StepSignals(no_progress_steps=2)):
            router = EscalatingRouter(base, "fake/strong")
            self.assertTrue(router.route(Step("read"), signals).escalated)
            self.assertTrue(router.route(Step("read"), StepSignals()).escalated)
        with self.assertRaises(ValueError):
            EscalatingRouter(HeuristicRouter("x-contributor", "strong"), "strong")


class GuardAndMiddlewareTests(unittest.TestCase):
    def test_caps_persistence_and_fail_open_does_not_swallow(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            ledger = Path(directory) / "ledger.json"
            guard = SpendGuard(.1, .2, ledger, max_steps=2)
            guard.start_task("a")
            guard.check(.1)
            guard.record(.1)
            self.assertAlmostEqual(SpendGuard(.1, .2, ledger).global_spend, .1)
            with self.assertRaises(SpendCapExceeded):
                guard.check(.01)
            tiny = SpendGuard(0, 0)
            tiny.start_task("b")
            with self.assertRaises(SpendCapExceeded):
                TokenTrim(MockProviderClient(min_cacheable_tokens=0), guard=tiny).complete(
                    [ContextItem("u", "message", "x")], Step("read"))

    def test_saver_exception_sends_original_order_to_strong(self):
        calls = []
        class Client:
            def complete(self, messages, model, max_tokens):
                calls.append((messages, model))
                return ModelResponse("ok", Usage(2, 0, 1))
        pipeline = TokenTrim(Client())
        pipeline.pruner.prune = lambda *args: (_ for _ in ()).throw(RuntimeError("secret details"))
        items = [ContextItem("u", "message", "first"), ContextItem("s", "system", "second")]
        _, record = pipeline.complete(items, Step("read"))
        self.assertEqual([m["content"] for m in calls[0][0]], ["first", "second"])
        self.assertEqual(calls[0][1], "fake/strong")
        self.assertTrue(record.fail_open)
        self.assertEqual(record.fail_open_error, "RuntimeError")


class ClientProxySimulatorTests(unittest.TestCase):
    def test_mock_cache_blocks_minimum_and_ttl(self):
        client = MockProviderClient(cache_block_tokens=4, min_cacheable_tokens=4, ttl_steps=1,
                                    estimator=len)
        messages = [{"role": "system", "content": "abcd"}, {"role": "user", "content": "x"}]
        self.assertEqual(client.complete(messages, "m", 10).usage.cached_input, 0)
        self.assertEqual(client.complete(messages, "m", 10).usage.cached_input, 4)
        client.complete([], "other", 1)
        self.assertEqual(client.complete(messages, "m", 10).usage.cached_input, 0)

    def test_recording_round_trip(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "recording.jsonl"
            original = MockProviderClient(min_cacheable_tokens=0)
            expected = RecordingClient(original, path).complete([], "m", 10)
            actual = RecordedClient(path).complete([], "m", 10)
            self.assertEqual(actual, expected)

    def test_proxy_loopback_and_refusal(self):
        client = MockProviderClient(min_cacheable_tokens=0)
        try:
            server = make_server("127.0.0.1", 0, client, lambda upstream: TokenTrim(upstream))
        except PermissionError:
            self.skipTest("managed sandbox forbids loopback socket creation")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                              data=json.dumps({"model": "ignored", "messages": [{"role": "user", "content": "hi"}]}).encode(),
                              headers={"content-type": "application/json"})
            with urlopen(request, timeout=3) as response:
                body = json.load(response)
            self.assertIn("choices", body)
            self.assertIn("cached_tokens", body["usage"]["prompt_tokens_details"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        with self.assertRaises(ValueError):
            make_server("0.0.0.0", 0, client, lambda upstream: TokenTrim(upstream))

    def test_small_simulation_is_deterministic(self):
        first = run_simulation("bench/tasks/example_tasks.jsonl", "results/_test", repeats=1, samples=10,
                               modes=("baseline", "tokentrim"), write=False)
        second = run_simulation("bench/tasks/example_tasks.jsonl", "results/_test", repeats=1, samples=10,
                                modes=("baseline", "tokentrim"), write=False)
        self.assertEqual(first["summary"], second["summary"])
        self.assertEqual(first["metadata"]["data_kind"], "SIMULATION")
        self.assertIn("ci95", first["summary"]["tokentrim"]["vs"]["dollars"]["difference"])

if __name__ == "__main__":
    unittest.main()
