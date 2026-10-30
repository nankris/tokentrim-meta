"""Cache-aware behaviour: layout order, switch cost, ingest trimming, prune checkpoints."""
import unittest

from bench.simulate import MODES, run_simulation
from tokentrim.clients.base import ModelResponse, Usage
from tokentrim.clients.mock import MockProviderClient
from tokentrim.compaction import OutputStore, compact_tool_output, is_log_like
from tokentrim.cost import CostModel
from tokentrim.layout import deterministic_segments
from tokentrim.middleware import TokenTrim
from tokentrim.planner import PromptSegment
from tokentrim.pruner import ContextItem, ContextPruner
from tokentrim.router import HeuristicRouter, RoutingDecision, Step
from tokentrim.routing import CheapFirstRouter, EscalatingRouter, StepSignals, cache_aware_switch

PRICES = {"cheap": {"input": 1.0, "cached_input": .1, "output": 2.0},
          "strong": {"input": 4.0, "cached_input": .2, "output": 20.0},
          "near": {"input": 3.0, "cached_input": .3, "output": 19.0}}
LOG = "\n".join([f"test_{i} (t.T.test_{i}) ... ok" for i in range(80)] +
                ["Traceback (most recent call last):", '  File "t.py", line 3, in test_x',
                 "AssertionError: boom", "FAILED (failures=1)"])


class FixedRouter:
    def __init__(self, model):
        self.model = model

    def route(self, step):
        return RoutingDecision(self.model, "fixed")


class LayoutTests(unittest.TestCase):
    def test_conversation_order_is_preserved(self):
        segments = [PromptSegment("u", "q", "message"), PromptSegment("t1", "out", "tool_output"),
                    PromptSegment("a", "answer", "message", role="assistant"), PromptSegment("s", "sys", "system")]
        self.assertEqual([s.id for s in deterministic_segments(segments)], ["s", "u", "t1", "a"])


class SwitchCostTests(unittest.TestCase):
    def test_switch_check_prefers_warm_model_for_large_context(self):
        costs = CostModel(prices=PRICES)
        self.assertFalse(cache_aware_switch(costs, "strong", "near", 200_000, output_tokens=10).switch)
        self.assertTrue(cache_aware_switch(costs, "strong", "cheap", 2_000, output_tokens=500).switch)
        warm = cache_aware_switch(costs, "strong", "near", 200_000, output_tokens=10, candidate_warm_tokens=200_000)
        self.assertLess(warm.switch_usd, cache_aware_switch(costs, "strong", "near", 200_000, output_tokens=10).switch_usd)
        with self.assertRaises(ValueError):
            cache_aware_switch(costs, "strong", "cheap", 10, horizon_steps=0)

    def test_middleware_blocks_costly_downgrade_but_never_upgrade(self):
        costs = CostModel(prices=PRICES)
        client = MockProviderClient(min_cacheable_tokens=0, cache_block_tokens=1)
        router = FixedRouter("strong")
        pipeline = TokenTrim(client, token_budget=10**6, router=router, strong_model="strong", cost_model=costs,
                             savers={"route"}, switch_horizon_steps=1)
        items = [ContextItem("s", "system", "x" * 400_000), ContextItem("u", "message", "go")]
        self.assertEqual(pipeline.complete(items, Step("read"), max_tokens=5)[1].decision.model, "strong")
        router.model = "near"
        _, record = pipeline.complete(items, Step("read"), max_tokens=5)
        self.assertEqual(record.decision.model, "strong")
        self.assertIn("stay on warm", record.switch_check)
        pipeline.reset_task()
        router.model = "cheap"
        pipeline.complete(items, Step("read"), max_tokens=5)
        router.model = "strong"
        self.assertEqual(pipeline.complete(items, Step("read"), max_tokens=5)[1].decision.model, "strong")

    def test_cheap_first_escalates_stickily(self):
        router = EscalatingRouter(CheapFirstRouter("cheap", "strong"), "strong")
        self.assertEqual(router.route(Step("planning")).model, "cheap")
        self.assertEqual(router.route(Step("edit"), StepSignals(True, previous_model="cheap")).model, "strong")
        self.assertEqual(router.route(Step("read")).model, "strong")
        router.reset()
        self.assertEqual(router.route(Step("read")).model, "cheap")


class TrimAndPruneTests(unittest.TestCase):
    def test_log_detection_and_restorable_errors(self):
        grep = "\n".join(f"pkg/m{i}.py:{i}: def helper_{i}(x)" for i in range(60))
        self.assertTrue(is_log_like(LOG))
        self.assertFalse(is_log_like(grep))
        store = OutputStore()
        text, report = compact_tool_output(LOG, store=store)
        self.assertIn("AssertionError: boom", text)
        self.assertLess(report.tokens_after, report.tokens_before)
        self.assertEqual(store.get(report.output_id), LOG)

    def test_ingest_trim_is_byte_stable_across_steps(self):
        client = MockProviderClient(min_cacheable_tokens=0, cache_block_tokens=1)
        pipeline = TokenTrim(client, token_budget=10**6, savers={"trim"})
        items = [ContextItem("s", "system", "rules " * 50), ContextItem("log", "tool_output", LOG, turn=1)]
        _, first = pipeline.complete(items, Step("read"))
        items.append(ContextItem("a", "message", "next", turn=2, role="assistant"))
        items.append(ContextItem("log2", "tool_output", "short", turn=3))
        _, second = pipeline.complete(items, Step("read"))
        self.assertEqual(second.usage["cached_input"], first.usage["input"])
        self.assertTrue(first.compaction_ids)

    def test_pruner_none_disables_routine_truncation(self):
        items = [ContextItem("t", "tool_output", "\n".join(map(str, range(100))), turn=0),
                 ContextItem("u", "message", "q", turn=1)]
        kept, report = ContextPruner(old_tool_lines=None).prune(items, 10**6)
        self.assertEqual(kept[0].text, items[0].text)
        self.assertEqual(report.truncated_ids, [])

    def test_prune_is_eager_by_default_and_latched(self):
        costs = CostModel(prices=PRICES)
        client = MockProviderClient(min_cacheable_tokens=0, cache_block_tokens=1)
        items = [ContextItem("s", "system", "rules"), ContextItem("f", "file", "y" * 4000, referenced=False),
                 ContextItem("u", "message", "q" * 40000, turn=1)]
        eager = TokenTrim(client, token_budget=10**6, strong_model="strong", cost_model=costs,
                          savers={"prune"}, expected_remaining_steps=1)
        self.assertFalse(eager.prune_checkpoints)
        _, record = eager.complete(items, Step("read"))
        self.assertIn("f", record.pruning.dropped_ids)
        self.assertIsNone(record.prune_checkpoint)
        # Latched: even if the item is referenced again it stays dropped (no prefix oscillation).
        again = [items[0], ContextItem("f", "file", "y" * 4000, referenced=True), items[2]]
        eager.complete(again, Step("read"))
        self.assertNotIn("y" * 4000, [m["content"] for m in client._cache["strong"][0]])

    def test_prune_checkpoint_defers_commits_latches_and_forces(self):
        costs = CostModel(prices=PRICES)
        client = MockProviderClient(min_cacheable_tokens=0, cache_block_tokens=1)
        big = "y" * 4000
        items = [ContextItem("s", "system", "rules"), ContextItem("f", "file", big, referenced=False),
                 ContextItem("u", "message", "q" * 40000, turn=1)]
        deferring = TokenTrim(client, token_budget=10**6, strong_model="strong", cost_model=costs,
                              savers={"prune"}, expected_remaining_steps=1, prune_checkpoints=True)
        _, record = deferring.complete(items, Step("read"))
        self.assertTrue(record.prune_checkpoint.startswith("deferred"))
        self.assertNotIn("f", record.pruning.dropped_ids)
        committing = TokenTrim(client, token_budget=10**6, strong_model="strong", cost_model=costs,
                               savers={"prune"}, expected_remaining_steps=10**4, prune_checkpoints=True)
        _, record = committing.complete(items, Step("read"))
        self.assertTrue(record.prune_checkpoint.startswith("committed"))
        _, again = committing.complete(items, Step("read"))
        self.assertIn("f", again.pruning.dropped_ids)
        self.assertIsNone(again.prune_checkpoint)
        forced = TokenTrim(client, token_budget=10_100, strong_model="strong", cost_model=costs,
                           savers={"prune"}, expected_remaining_steps=1, prune_checkpoints=True)
        self.assertEqual(forced.complete(items, Step("read"))[1].prune_checkpoint, "forced by token budget")

    def test_compactor_failure_fails_open(self):
        calls = []

        class Client:
            def complete(self, messages, model, max_tokens):
                calls.append(messages)
                return ModelResponse("ok", Usage(1, 0, 1))
        pipeline = TokenTrim(Client(), compactor=lambda *a, **k: 1 / 0)
        _, record = pipeline.complete([ContextItem("t", "tool_output", LOG)], Step("read"))
        self.assertTrue(record.fail_open)
        self.assertEqual(calls[0][0]["content"], LOG)


class SimulationPropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modes = ("baseline", "tokentrim", "prune-eager", "baseline-naive", "cache-only-naive", "cheap-only")
        cls.result = run_simulation("bench/tasks/example_tasks.jsonl", "results/_test", repeats=1, samples=20,
                                    modes=modes, write=False)

    def test_labels_and_meta_prices(self):
        meta = self.result["metadata"]
        self.assertEqual(meta["data_kind"], "SIMULATION")
        self.assertEqual(meta["prices"]["meta/muse-wonder-1.0"]["cached_input"], .2)
        self.assertEqual(meta["prices"]["meta/muse-spark-1.3"]["input"], 1.25)

    def test_structural_effects(self):
        s = self.result["summary"]
        self.assertLess(s["baseline-naive"]["cache_hit_rate_mean"], s["baseline"]["cache_hit_rate_mean"])
        self.assertGreater(s["cache-only-naive"]["cache_hit_rate_mean"], s["baseline-naive"]["cache_hit_rate_mean"])
        self.assertGreater(s["prune-eager"]["dollars"]["mean"], s["baseline"]["dollars"]["mean"])
        self.assertLess(s["cheap-only"]["dollars"]["mean"], s["baseline"]["dollars"]["mean"])
        self.assertEqual(s["tokentrim"]["vs"]["reference"], "baseline")
        self.assertEqual(s["cache-only-naive"]["vs"]["reference"], "baseline-naive")

    def test_spend_cap_trips_fail_the_task(self):
        result = run_simulation("bench/tasks/example_tasks.jsonl", "results/_test", repeats=1, samples=5,
                                modes=("baseline",), per_task_usd=.001, write=False)
        self.assertTrue(all(r["cap_tripped"] and not r["passed"] for r in result["results"]))

    def test_unknown_or_unpaired_modes_rejected(self):
        with self.assertRaises(ValueError):
            run_simulation("bench/tasks/example_tasks.jsonl", "results/_test", modes=("nope",), write=False)
        with self.assertRaises(ValueError):
            run_simulation("bench/tasks/example_tasks.jsonl", "results/_test", modes=("tokentrim",), write=False)
        self.assertTrue(all(len(spec) == 5 for spec in MODES.values()))


if __name__ == "__main__":
    unittest.main()
