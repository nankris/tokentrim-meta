import json
import unittest

from benchmarks import workloads_hard as WH
from benchmarks.mock_agents import hard_policy
from benchmarks.run import ARMS, HISTORY_CFG, run_agentic_hard
from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.ledger import SpendLedger
from tokentrim.optimizers.schema_router import SchemaRouter
from tokentrim.upstream import MockChatUpstream


def run(policy, arm, i=0, tmp="/tmp/tt_hard_test_ledger.json"):
    ledger = SpendLedger(tmp, 10**6, 10**6, f"test-{policy}-{arm}-{i}")
    up = MockChatUpstream(responder=hard_policy(policy), ledger=ledger)
    spec = ARMS["agentic_hard"][arm]
    gw = Gateway(up, GatewayConfig(**spec["cfg"]))
    return run_agentic_hard(WH.hard_task(i), arm, spec, gw, f"t/{policy}/{arm}/{i}", 4000), up


class HardWorkloadTest(unittest.TestCase):
    def test_deterministic_and_synthetic(self):
        a, b = WH.hard_task(3), WH.hard_task(3)
        self.assertEqual(a["answer"], b["answer"])
        self.assertNotEqual(WH.hard_task(4)["answer"], a["answer"])
        self.assertNotIn("@", a["ci_log"] + a["span_json"])  # no e-mail-like personal data

    def test_router_selection_is_wrong_by_design(self):
        for i in range(24):
            t = WH.hard_task(i)
            sel, _ = SchemaRouter().select(WH.hard_tools(), [{"role": "user", "content": t["prompt"]}], None, None)
            self.assertNotIn("inspect_spans", sel)
            self.assertNotIn("open_artifact_manifest", sel)

    def test_oracle_passes_every_arm_and_guess_fails(self):
        for arm in ARMS["agentic_hard"]:
            (score, checks, *_), _ = run("oracle", arm)
            self.assertEqual(score, 1.0, (arm, checks))
        (score, checks, *_), _ = run("guess", "baseline")
        self.assertFalse(all(checks.values()))

    def test_lazy_agent_fails_when_recovery_is_needed(self):
        (score, checks, *_), _ = run("lazy", "full")
        self.assertFalse(checks["exec:inspect_spans"])
        (score, checks, *_), _ = run("lazy", "baseline")
        self.assertEqual(score, 1.0)

    def test_side_effect_tool_fails_task(self):
        t = WH.hard_task(1)
        _, checks = WH.grade_hard(json.dumps(t["answer"]), t, [("deploy_service", {})] +
                                  [(k, {"x": v}) for k, v in t["required"].items()])
        self.assertFalse(checks["no_side_effects"])
        _, checks = WH.grade_hard(json.dumps(t["answer"]), t, [(k, {"x": v}) for k, v in t["required"].items()])
        self.assertTrue(all(checks.values()))

    def test_internal_exchange_replayed_on_next_turn(self):
        (score, checks, totals, notes, counts, _), up = run("oracle", "full", i=2)
        self.assertEqual(score, 1.0)
        self.assertEqual(counts["retrieve_grep"], 1)  # retrieved once, then remembered (issue 65)
        last = up.calls[-1]["messages"]
        self.assertTrue(any(m.get("role") == "tool" and "matching lines" in (m.get("content") or "") for m in last))


if __name__ == "__main__":
    unittest.main()


class PairedNewcombeTest(unittest.TestCase):
    def test_known_values(self):
        from bench.stats import newcombe_paired, noninferiority_paired
        r = newcombe_paired([True] * 24, [True] * 24)
        self.assertAlmostEqual(r["ci95"][0], -(1 - 24 / (24 + 1.959964 ** 2)), places=3)
        self.assertFalse(noninferiority_paired([True] * 24, [True] * 24)["non_inferior"])
        self.assertTrue(noninferiority_paired([True] * 90, [True] * 90)["non_inferior"])
        # StatsDirect worked example: both 20, first only 12, second only 2, n 50 -> p1-p2 CI 0.056156..0.329207
        base = [True] * 20 + [True] * 12 + [False] * 2 + [False] * 16
        oth = [True] * 20 + [False] * 12 + [True] * 2 + [False] * 16
        r = newcombe_paired(base, oth)
        self.assertAlmostEqual(r["ci95"][0], -0.329207, places=5)
        self.assertAlmostEqual(r["ci95"][1], -0.056156, places=5)
        # statsmodels example [[10, 5], [2, 20]] -> p1-p2 CI (-0.0643926, 0.2211160)
        base = [True] * 15 + [False] * 22
        oth = [True] * 10 + [False] * 5 + [True] * 2 + [False] * 20
        r = newcombe_paired(base, oth)
        self.assertAlmostEqual(-r["ci95"][1], -0.0643926, places=5)
        self.assertAlmostEqual(-r["ci95"][0], 0.2211160, places=5)
