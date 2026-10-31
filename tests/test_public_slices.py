import os
import unittest
from pathlib import Path

from tokentrim.optimizers.tool_output import ToolOutputCompressor, compress_ci_text

BFCL = Path(os.environ.get("BFCL_DIR", "/workspace/pubdata/bfcl"))
LC = Path(os.environ.get("LOGCHUNKS_DIR", "/workspace/pubdata/logchunks/LogChunks"))


class CiTextLogs(unittest.TestCase):
    def log(self):
        return "\n".join([f"step {i}: installing dependency pkg{i} version 1.{i}" for i in range(400)] +
                         ["something odd happened here", "make: *** [all] Error 2", "Done. Your build exited with 1."])

    def test_off_by_default(self):
        r = ToolOutputCompressor().compress(self.log())
        self.assertIsNone(r.ref)  # unstructured text untouched unless text_logs=True

    def test_opt_in_keeps_tail_and_errors(self):
        r = ToolOutputCompressor(text_logs=True).compress(self.log())
        self.assertIsNotNone(r.ref)
        self.assertIn("make: *** [all] Error 2", r.text)
        self.assertIn("Done. Your build exited with 1.", r.text)
        self.assertIn("retrieve_original(", r.text)
        self.assertLess(r.tokens_after, r.tokens_before * 0.5)

    def test_short_text_unchanged(self):
        self.assertEqual(compress_ci_text("a\nb"), "a\nb")


@unittest.skipUnless(BFCL.exists(), "BFCL data not downloaded")
class BfclChecker(unittest.TestCase):
    def test_oracle_and_perturbations(self):
        from benchmarks.public import bfcl as B
        items = B.load("multiple")
        self.assertTrue(all(B.check(it, B.oracle_output(it))[0] for it in items))
        it = items[0]
        o = B.oracle_output(it)
        name = next(iter(o[0]))
        self.assertFalse(B.check(it, [])[0])
        self.assertFalse(B.check(it, [{name: dict(o[0][name], zz_extra=1)}])[0])
        self.assertFalse(B.check(it, None)[0])

    def test_string_standardisation(self):
        from benchmarks.public import bfcl as B
        self.assertEqual(B.std("April 1, 2024"), B.std("april 1 2024"))

    def test_tool_conversion(self):
        from benchmarks.public import bfcl as B
        t = B.to_tools([{"name": "a.b", "description": "d", "parameters": {"type": "dict", "properties": {
            "x": {"type": "float", "description": "x"}, "y": {"type": "tuple", "items": {"type": "integer"}}}}}])[0]
        self.assertEqual(t["function"]["name"], "a_b")
        self.assertEqual(t["function"]["parameters"]["type"], "object")
        self.assertEqual(t["function"]["parameters"]["properties"]["x"]["type"], "number")
        self.assertEqual(t["function"]["parameters"]["properties"]["y"]["type"], "array")


@unittest.skipUnless(LC.exists(), "LogChunks data not downloaded")
class LogChunksGrader(unittest.TestCase):
    def test_oracle_passes_and_wrong_chunk_fails(self):
        from benchmarks.public import logchunks as L
        exs = L.examples()[:40]
        self.assertTrue(all(L.grade(e["chunk"], e)[0] for e in exs if L.key_lines(e["chunk"])))
        wrong = sum(L.grade(exs[(i + 7) % len(exs)]["chunk"], e)[0] for i, e in enumerate(exs))
        self.assertLessEqual(wrong, 6)  # different builds of the same repo can share a failure chunk


if __name__ == "__main__":
    unittest.main()
