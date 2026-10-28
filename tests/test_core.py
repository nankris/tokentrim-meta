import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tokentrim.clients.fake import FakeModelClient
from tokentrim.cost import cost, load_prices
from tokentrim.middleware import TokenTrim
from tokentrim.planner import CacheAwarePlanner, PromptSegment
from tokentrim.pruner import BudgetExceededError, ContextItem, ContextPruner
from tokentrim.router import HeuristicRouter, Step
from tokentrim.tokens import estimate_tokens

ROOT = Path(__file__).resolve().parent.parent


class TokenTests(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual([estimate_tokens(s) for s in ("", "a", "abcd", "abcde")], [0, 1, 1, 2])


class PrunerTests(unittest.TestCase):
    def test_budget_and_mandatory(self):
        items = [ContextItem("system", "system", "rules"), ContextItem("pin", "file", "pinned", pinned=True),
                 ContextItem("old", "message", "old" * 200), ContextItem("new", "message", "question", turn=2),
                 ContextItem("unused", "file", "unused"), ContextItem("used", "file", "file", turn=2, referenced=True)]
        kept, report = ContextPruner().prune(items, 15)
        self.assertLessEqual(report.tokens_after, 15)
        self.assertTrue({"system", "pin", "new"}.issubset({i.id for i in kept}))
        self.assertIn("unused", report.dropped_ids)
        self.assertEqual(report.tokens_after, sum(estimate_tokens(i.text) for i in kept))
        self.assertEqual(report.tokens_before, sum(estimate_tokens(i.text) for i in items))

    def test_mandatory_overflow_is_explicit(self):
        with self.assertRaises(BudgetExceededError):
            ContextPruner().prune([ContextItem("s", "system", "must keep")], 0)

    def test_latest_user_not_latest_assistant(self):
        items = [ContextItem("u", "message", "user", turn=1),
                 ContextItem("a", "message", "assistant" * 100, turn=2, role="assistant")]
        kept, _ = ContextPruner().prune(items, 1)
        self.assertEqual([i.id for i in kept], ["u"])

    def test_head_tail_and_original_unchanged(self):
        text = "\n".join(f"line-{i}" for i in range(100))
        items = [ContextItem("tool", "tool_output", text), ContextItem("u", "message", "go", turn=1)]
        kept, report = ContextPruner().prune(items, 60)
        tool = kept[0].text
        self.assertTrue(tool.startswith("line-0\n"))
        self.assertTrue(tool.endswith("line-99"))
        self.assertIn("[... 88 lines trimmed ...]", tool)
        self.assertEqual(items[0].text, text)
        self.assertEqual(report.truncated_ids, ["tool"])

    def test_newest_priority_and_reference_count(self):
        items = [ContextItem("old", "file", "1234", turn=0, referenced=True),
                 ContextItem("new", "file", "5678", turn=2, reference_count=1)]
        kept, _ = ContextPruner().prune(items, 1)
        self.assertEqual([i.id for i in kept], ["new"])

    def test_custom_estimator(self):
        items = [ContextItem("s", "system", "abc"), ContextItem("f", "file", "1234", referenced=True)]
        kept, report = ContextPruner(estimator=len).prune(items, 6)
        self.assertEqual(report.tokens_after, 3)
        self.assertEqual(len(kept), 1)

    def test_invalid_and_empty(self):
        self.assertEqual(ContextPruner().prune([], 0)[0], [])
        with self.assertRaises(ValueError):
            ContextPruner().prune([], -1)
        with self.assertRaises(ValueError):
            ContextPruner().prune([ContextItem("x", "file", ""), ContextItem("x", "file", "")], 5)


class PlannerTests(unittest.TestCase):
    def test_order_warning_prefix_and_invalidation(self):
        planner = CacheAwarePlanner()
        stable = [PromptSegment("s", "rules", "system", "system"),
                  PromptSegment("tools", "schemas", "tool_schema"),
                  PromptSegment("map", "map", "repo_map"),
                  PromptSegment("pin", "pinned", "file", stable=True)]
        first = planner.plan([PromptSegment("u", "first"), *stable])
        self.assertEqual([s.id for s in first.segments], ["s", "tools", "map", "pin", "u"])
        self.assertTrue(first.warnings)
        self.assertEqual(first.cacheable_tokens, 0)
        second = planner.plan([*stable, PromptSegment("u", "second")])
        self.assertEqual(second.cacheable_tokens, first.stable_prefix_tokens)
        self.assertEqual(first.stable_prefix_hash, second.stable_prefix_hash)
        third = planner.plan([PromptSegment("s", "changed", "system"), *stable[1:]])
        self.assertEqual(third.cacheable_tokens, 0)
        self.assertNotEqual(third.stable_prefix_hash, second.stable_prefix_hash)

    def test_lcp_stops_at_first_changed_segment(self):
        planner = CacheAwarePlanner(estimator=len)
        planner.plan([PromptSegment("1", "abc", stable=True), PromptSegment("2", "def", stable=True)])
        plan = planner.plan([PromptSegment("1", "abc", stable=True), PromptSegment("2", "xyz", stable=True)])
        self.assertEqual(plan.cacheable_tokens, 3)

    def test_naive_order_and_empty(self):
        planner = CacheAwarePlanner()
        plan = planner.plan([PromptSegment("u", "volatile"), PromptSegment("s", "stable", "system")], reorder=False)
        self.assertEqual(plan.stable_prefix_tokens, 0)
        self.assertEqual(plan.segments[0].id, "u")
        self.assertEqual(planner.plan([]).cacheable_tokens, 0)


class CostTests(unittest.TestCase):
    def test_muse_prices_and_cached_subset(self):
        expected = {"meta/muse-spark-1.3": (1.25, .15, 4.25),
                    "meta/muse-wonder-1.0": (4, .20, 20),
                    "meta/muse-spark-1.3-contributor": (.10, .002, .20)}
        for model, (regular, cached, output) in expected.items():
            with self.subTest(model=model):
                self.assertAlmostEqual(cost(model, 1_000_000, 0, 1_000_000), regular + output)
                self.assertAlmostEqual(cost(model, 1_000_000, 1_000_000, 0), cached)
                self.assertAlmostEqual(cost(model, 1_000_000, 500_000, 1_000_000), .5 * (regular + cached) + output)

    def test_fake_and_invalid_counts(self):
        self.assertAlmostEqual(cost("fake/cheap", 1000, 500, 100), .00075)
        for counts in ((1, 2, 0), (-1, 0, 0), (1.5, 0, 0)):
            with self.assertRaises(ValueError):
                cost("fake/cheap", *counts)
        with self.assertRaises(KeyError):
            cost("unknown", 1, 0, 0)

    def test_override(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "prices.toml"
            path.write_text('[models."custom"]\ninput=2\ncached_input=1\noutput=3\n')
            with patch.dict(os.environ, {"TOKENTRIM_PRICES": str(path)}):
                self.assertEqual(cost("custom", 1_000_000, 0, 0), 2)
                self.assertIn("custom", load_prices())


class RouterTests(unittest.TestCase):
    def test_decisions(self):
        router = HeuristicRouter()
        for step in (Step("planning"), Step("edit", file_count=2), Step("read", failed_test_retry=True),
                     Step("summary", context_tokens=9000), Step("edit", estimated_edit_lines=100), Step("unknown")):
            self.assertEqual(router.route(step).model, "fake/strong")
            self.assertTrue(router.route(step).reason)
        for step in (Step("read"), Step("summary"), Step("formatting"), Step("edit")):
            self.assertEqual(router.route(step).model, "fake/cheap")


class ClientAndPipelineTests(unittest.TestCase):
    def test_fake_cache_and_model_isolation(self):
        client = FakeModelClient()
        planner = CacheAwarePlanner()
        for model, prompt, hit in [("fake/cheap", "one", False), ("fake/cheap", "two", True), ("fake/strong", "two", False)]:
            plan = planner.plan([PromptSegment("s", "stable rules", "system"), PromptSegment("u", prompt)])
            client.set_plan(plan)
            result = client.complete(plan.messages(), model, 20)
            self.assertEqual(result.usage.cached_input > 0, hit)
            self.assertLessEqual(result.usage.output, 20)
        self.assertEqual(client.complete([], "fake/cheap", 0).usage.output, 0)

    def test_pipeline_prunes_routes_records_and_caches(self):
        pipeline = TokenTrim(FakeModelClient(), token_budget=30)
        items = [ContextItem("s", "system", "stable"), ContextItem("unused", "file", "x" * 1000),
                 ContextItem("u", "message", "read", turn=1)]
        _, first = pipeline.complete(items, Step("read"))
        _, second = pipeline.complete(items, Step("read"))
        self.assertEqual(first.decision.model, "fake/cheap")
        self.assertIn("unused", first.pruning.dropped_ids)
        self.assertGreater(second.usage["cached_input"], 0)
        self.assertLess(second.dollars, first.dollars)
        self.assertEqual(len(pipeline.records), 2)
        _, baseline = TokenTrim(FakeModelClient()).complete(items, Step("read"), mode="baseline")
        self.assertEqual(baseline.decision.model, "fake/strong")
        self.assertEqual(baseline.pruning.tokens_before, baseline.pruning.tokens_after)
