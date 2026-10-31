"""v5.1 regression: structure-preserving JSON compression (issue 69, ah43 misassociated release)."""
import json
import unittest

from benchmarks import json_extraction as JX
from benchmarks import workloads_hard as WH
from tokentrim.optimizers.tool_output import ToolOutputCompressor, compress_json, task_terms


class JsonStructureTests(unittest.TestCase):
    def test_100_generated_documents_keep_associations(self):
        for i in range(100):
            text, ans = JX.gen_doc(i)
            for mode in ("conservative", "lossy"):
                self.assertTrue(JX.structural_check(compress_json(text, mode=mode), ans), (i, mode))

    def test_legacy_table_was_ambiguous(self):  # documents the v5 failure mode the fix removes
        bad = sum(not JX.structural_check(JX.legacy_compress_json(t, protect=None), a)
                  for t, a in map(JX.gen_doc, range(100)))
        self.assertGreaterEqual(bad, 50)

    def test_conservative_is_lossless(self):
        for i in range(20):
            text, _ = JX.gen_doc(i)
            view = compress_json(text, mode="conservative")
            doc = json.loads(text)
            for k, rec in enumerate(doc["spans"]):
                self.assertIn(f"/spans/{k} " + json.dumps(rec, separators=(",", ":")), view)

    def test_ah43_error_record_carries_its_release(self):
        t = WH.hard_task(43)
        spans = WH.run_hard_stub(t, "inspect_spans", {"span_root": "tr-bf93f2"})
        r = ToolOutputCompressor(min_tokens=400).compress(spans, keep_terms=task_terms([t["prompt"]]))
        err = [l for l in r.text.splitlines() if '"status":"ERROR"' in l]
        self.assertEqual(len(err), 1)
        self.assertIn('"release":"rel-1309"', err[0])
        self.assertNotIn(" | ", r.text)
        self.assertIn("records", r.text)
        self.assertIn("omitted]", r.text)  # gaps announced with pointer ranges

    def test_lossy_keeps_parent_chain_and_is_deterministic(self):
        text, ans = JX.gen_doc(3)
        a, b = compress_json(text, mode="lossy"), compress_json(text, mode="lossy")
        self.assertEqual(a, b)
        doc = json.loads(text)
        by = {s["span_id"]: s for s in doc["spans"]}
        sid = ans["span_id"]
        while by[sid]["parent"]:
            sid = by[sid]["parent"]
            self.assertIn(f'"span_id":"{sid}"', a)


if __name__ == "__main__":
    unittest.main()
