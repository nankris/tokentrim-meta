import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench.runner import DEFAULT_TASKS, ROOT, load_tasks, run_benchmark, safe_path
from bench.stats import bootstrap_mean, paired_comparison, summarize


class StatsTests(unittest.TestCase):
    def test_seed_mean_and_constant(self):
        result = bootstrap_mean([1, 2, 3, 4, 5], seed=9)
        self.assertEqual(result, bootstrap_mean([1, 2, 3, 4, 5], seed=9))
        self.assertLessEqual(result["ci95"][0], result["mean"])
        self.assertGreaterEqual(result["ci95"][1], result["mean"])
        self.assertEqual(bootstrap_mean([7] * 20)["ci95"], [7, 7])
        self.assertEqual(bootstrap_mean([1])["ci95"], [1, 1])

    def test_paired_resampling_and_zero_denominator(self):
        result = paired_comparison([2, 4, 6], [1, 2, 3])
        for bound in result["percent_saving"]["ci95"]:
            self.assertAlmostEqual(bound, 50)
        self.assertEqual(result["difference"]["mean"], -2)
        self.assertIsNone(paired_comparison([0], [0])["percent_saving"]["mean"])
        self.assertEqual(bootstrap_mean([0, 1])["mean"], .5)
        with self.assertRaises(ValueError):
            paired_comparison([1], [1, 2])
        with self.assertRaises(ValueError):
            bootstrap_mean([])

    def test_pairs_matched_by_id_not_row_order(self):
        rows = [{"task_id": i, "mode": mode, "tokens": value, "dollars": value, "passed": True}
                for i, mode, value in [("a", "baseline", 10), ("b", "baseline", 20),
                                        ("b", "tokentrim", 19), ("a", "tokentrim", 9)]]
        self.assertEqual(summarize(rows)["paired"]["tokens"]["difference"]["ci95"], [-1, -1])
        with self.assertRaises(ValueError):
            summarize(rows[:-1])


class RunnerTests(unittest.TestCase):
    def test_end_to_end_offline_and_deterministic(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "results.json"
            with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
                result = run_benchmark(out=path, samples=200)
                again = run_benchmark(out=path, samples=200)
            self.assertEqual(result, again)
            self.assertEqual(json.loads(path.read_text()), result)
            self.assertEqual(result["metadata"]["data_kind"], "FAKE")
            self.assertEqual(len(result["results"]), 6)
            self.assertEqual({r["mode"] for r in result["results"]}, {"baseline", "tokentrim"})
            self.assertLess(result["summary"]["tokentrim"]["dollars"]["mean"], result["summary"]["baseline"]["dollars"]["mean"])
            self.assertTrue(any(r["usage"]["cached_input"] for r in result["results"] if r["mode"] == "tokentrim"))

    def test_custom_checker(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result = run_benchmark(out=Path(directory) / "out.json", checker=lambda task, responses, mode: mode == "baseline", samples=50)
            self.assertEqual(result["summary"]["baseline"]["pass_rate"]["mean"], 1)
            self.assertEqual(result["summary"]["tokentrim"]["pass_rate"]["mean"], 0)

    def test_loader_optional_extra_fields_json_and_jsonl(self):
        records = [json.loads(DEFAULT_TASKS.read_text().splitlines()[0])]
        records[0]["extra"] = "ignored"
        records[0]["solution"] = "bench/examples/add"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            for suffix, content in ((".json", json.dumps(records)), (".jsonl", json.dumps(records[0]) + "\n\n")):
                path = Path(directory) / ("tasks" + suffix)
                path.write_text(content)
                self.assertEqual(load_tasks(path)[0].solution, "bench/examples/add")
            records[0].pop("files")
            path.write_text(json.dumps(records[0]))
            self.assertEqual(load_tasks(path)[0].files, [])

    def test_paths_and_protected_output(self):
        with self.assertRaises(ValueError):
            safe_path("../outside")
        with self.assertRaises(ValueError):
            run_benchmark(out=ROOT / "bench/tasks/tasks_40.jsonl", samples=1)


if __name__ == "__main__":
    unittest.main()
