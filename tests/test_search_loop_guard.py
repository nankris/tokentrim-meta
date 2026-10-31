"""v5.1 regression: search_tools loop guard (issue 68, replay of the v5 ah50 failure on the mock upstream)."""
import json
import unittest

from benchmarks import workloads_hard as WH
from benchmarks.mock_agents import flail_policy
from benchmarks.run import ARMS, run_agentic_hard
from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.ledger import SpendLedger
from tokentrim.optimizers.schema_router import SEARCH_TOOL
from tokentrim.upstream import MockChatUpstream


def replay(threshold, i=50, blind=3):
    ledger = SpendLedger(f"/tmp/tt_guard_{threshold}.json", 10**6, 10**6, f"guard-{threshold}-{i}")
    up = MockChatUpstream(responder=flail_policy(), ledger=ledger)
    spec = ARMS["agentic_hard"]["full"]
    gw = Gateway(up, GatewayConfig(**{**spec["cfg"], "search_loop_threshold": threshold, "search_max_without_evidence": blind}))
    out = run_agentic_hard(WH.hard_task(i), "full", spec, gw, f"guard/{threshold}/{i}", 4000)
    return out, up, gw


class SearchLoopGuardTest(unittest.TestCase):
    def test_ah50_replay_recovers_with_guard(self):
        (score, checks, totals, notes, counts, _), up, _ = replay(2)
        self.assertEqual(score, 1.0, checks)
        self.assertLessEqual(counts["search_tools"], 4)
        self.assertNotIn(["search_tools", {"query": "log"}], counts["tool_trace"])  # never leaked to client
        self.assertTrue(any("loop guard" in n for n in notes))
        last_tools = {t["function"]["name"] for t in up.calls[-1]["tools"]}
        self.assertTrue(set(t["function"]["name"] for t in WH.hard_tools()) <= last_tools)  # full catalogue

    def test_without_guard_the_agent_loops_and_fails(self):
        (score, checks, totals, notes, counts, _), up, _ = replay(10**6, blind=10**6)
        self.assertLess(score, 1.0)
        self.assertGreaterEqual(counts["search_tools"], 8)

    def _gw(self):
        gw = Gateway(MockChatUpstream(), GatewayConfig(schema_router=True))
        return gw

    def test_legitimate_retry_after_new_evidence_is_allowed(self):
        from tokentrim import transforms
        gw = self._gw()
        tools = WH.hard_tools()
        sent = {"model": "m", "messages": [{"role": "user", "content": "x"}], "tools": tools[:3] + [SEARCH_TOOL]}
        key = transforms.conversation_key(sent, "c1")
        gw.conversations[key] = {"all_tools": tools}

        def search(q, cid):
            call = {"id": cid, "function": {"name": "search_tools", "arguments": json.dumps({"query": q})}}
            return transforms.run_internal_tool(gw, call, "c1", sent)

        search("zzz nothing", "s1")                     # unproductive 1
        sent["messages"].append({"role": "tool", "tool_call_id": "client-1", "content": "new evidence"})
        r, line = search("zzz nothing", "s2")           # same query, but state changed -> streak reset
        self.assertNotIn("loop guard", line)
        self.assertFalse(gw.conversations[key].get("router_disabled"))
        r, line = search("distributed span hierarchy", "s3")  # productive -> resets
        self.assertIn("inspect_spans", line)
        sent["messages"].append({"role": "tool", "tool_call_id": "client-2", "content": "spans"})  # tool used
        r, line = search("zzz nothing", "s4")
        self.assertNotIn("loop guard", line)
        r, line = search("zzz nothing", "s5")           # 2 unproductive in a row, no new evidence -> guard
        self.assertIn("loop guard", line)
        self.assertIn("FULL catalogue", json.loads(r)["note"])
        r, line = search("anything", "s6")
        self.assertIn("refused", line)

    def test_blind_searches_trip_guard_even_if_they_restore_tools(self):
        from tokentrim import transforms
        gw = self._gw()
        tools = WH.hard_tools()
        sent = {"model": "m", "messages": [{"role": "user", "content": "x"}], "tools": tools[:3] + [SEARCH_TOOL]}
        gw.conversations[transforms.conversation_key(sent, "c2")] = {"all_tools": tools}
        lines = [transforms.run_internal_tool(gw, {"id": f"b{k}", "function": {"name": "search_tools", "arguments":
                 json.dumps({"query": q})}}, "c2", sent)[1] for k, q in enumerate(["weather", "time off", "deploy"])]
        self.assertNotIn("loop guard", lines[1])
        self.assertIn("loop guard", lines[2])

    def test_router_stays_disabled_on_next_request(self):
        (score, *_), up, gw = replay(2)
        self.assertTrue(any(c.get("router_disabled") for c in gw.conversations.values()))


if __name__ == "__main__":
    unittest.main()
