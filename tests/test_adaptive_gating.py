"""v5.2: deterministic router gating and risk-aware JSON compression mode."""
import json
import unittest

from benchmarks import workloads_hard as WH
from benchmarks.json_extraction import gen_doc
from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.optimizers.schema_router import SchemaRouter
from tokentrim.optimizers.tool_output import ToolOutputCompressor, json_risk
from tokentrim.upstream import MockChatUpstream


def tool(name, desc, params=("query",)):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": {p: {"type": "string"} for p in params}}}}


DISTINCT = [tool(f"svc_{w}", f"Operate the {w} subsystem: {w} {w} operations only.") for w in
            ["billing", "payroll", "weather", "travel", "calendar", "slack", "email", "image", "translate", "crm",
             "jira", "pager", "secrets", "cluster", "dns", "cdn", "kafka", "redis", "vault", "ldap"]]


class GatingTest(unittest.TestCase):
    def test_router_off_by_default(self):
        self.assertFalse(GatewayConfig().schema_router)

    def test_few_tools_keep_all(self):
        ok, why, _ = SchemaRouter().gate(DISTINCT[:10], [{"role": "user", "content": "weather"}])
        self.assertFalse(ok)
        self.assertIn("only 10 tools", why)

    def test_low_confidence_keeps_all_on_hard_tasks(self):
        for i in range(0, 96, 7):
            ok, why, _ = SchemaRouter().gate(WH.hard_tools(), [{"role": "user", "content": WH.hard_task(i)["prompt"]}])
            self.assertFalse(ok)
            self.assertIn("low confidence", why)

    def test_clear_cut_routes_and_keeps_chain_tools(self):
        tools = DISTINCT + [tool("open_manifest", "Open a packaged manifest.", ("build",))]
        msgs = [{"role": "user", "content": "check billing billing payroll weather travel calendar slack "
                 "invoices; the build rel-12 is involved"}]
        ok, why, chain = SchemaRouter(keep=6).gate(tools, msgs)
        self.assertTrue(ok, why)
        self.assertIn("open_manifest", chain)

    def test_gated_conversation_sends_all_tools(self):
        up = MockChatUpstream()
        gw = Gateway(up, GatewayConfig(schema_router=True))
        t = WH.hard_task(3)
        _, rep = gw.complete({"model": "muse-spark-1.3-contributor", "tools": WH.hard_tools(),
                              "messages": [{"role": "user", "content": t["prompt"]}]}, "g1")
        self.assertTrue(any("Tool routing skipped" in e for e in rep.explanations))
        self.assertEqual(len(up.calls[0]["tools"]), len(WH.hard_tools()))


class RiskModeTest(unittest.TestCase):
    def test_exact_extraction_over_linked_records_is_conservative(self):
        text = gen_doc(1)[0]
        mode, why = json_risk(text, "Report the exact release and parent span id of the failing span.")
        self.assertEqual(mode, "conservative", why)
        mode, _ = json_risk(text, "Summarise overall health.")
        self.assertEqual(mode, "lossy")
        flat = json.dumps({"rows": [{"n": i, "v": i * 2} for i in range(50)]})
        self.assertEqual(json_risk(flat, "exact value")[0], "lossy")

    def test_auto_mode_lossless_on_hard_spans(self):
        t = WH.hard_task(5)
        comp = ToolOutputCompressor(json_mode="auto")
        r = comp.compress(t["span_json"], task_text=t["prompt"])
        if r.ref:  # compressed: must be lossless (every span present)
            self.assertIn("losslessly", r.explanation)
            n = len(json.loads(t["span_json"])["spans"])
            self.assertEqual(sum(1 for l in r.text.splitlines() if l.startswith("/spans/")), n)
            self.assertNotIn("omitted]", r.text)


if __name__ == "__main__":
    unittest.main()
