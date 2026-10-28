import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace

from bench.checker import check_edit, parse_edits, real_checker, reference_self_test
from bench.runner import ROOT, load_tasks, run_benchmark


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.task = load_tasks('bench/tasks/tasks_40.jsonl')[0]

    def test_parser_rejects_unsafe_and_malformed_edits(self):
        for name in ('../escape', '/absolute', 'a/../../escape', 'a\\b', './core.py', 'tests/test_behavior.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_edits(json.dumps({'files': {name: ''}}))
        for text in ('FAKE', '{}', '{"files": []}', '{"files":{"core.py":1}}',
                     '{"files":{"core.py":"a","core.py":"b"}}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_edits(text)

    def test_failure_output_and_invalid_response(self):
        result = check_edit(self.task, '{"files":{}}')
        self.assertFalse(result)
        self.assertIn('FAILED (', result.output)
        self.assertIsNotNone(result.returncode)
        result = check_edit(self.task, 'FAKE response')
        self.assertFalse(result)
        self.assertIsNotNone(result.error)

    def test_timeout_captures_output(self):
        task = replace(self.task, check='python -c "import time; print(123, flush=True); time.sleep(10)"')
        result = check_edit(task, '{"files":{}}', timeout=.2)
        self.assertFalse(result)
        self.assertTrue(result.timed_out)
        self.assertIn('123', result.output)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            repo = Path(directory)
            (repo / 'link').symlink_to(ROOT / 'README.md')
            task = replace(self.task, repo=str(repo.relative_to(ROOT)))
            result = check_edit(task, '{"files":{"link":"changed"}}')
            self.assertFalse(result)
            self.assertIn('symlink', result.error)

    def test_real_checker_metadata_with_fake_client(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result = run_benchmark(out=Path(directory) / 'result.json', checker=real_checker, samples=10)
        self.assertTrue(result['metadata']['usage_simulated'])
        self.assertFalse(result['metadata']['checks_simulated'])
        self.assertTrue(all(not row['passed'] and row['check']['error'] for row in result['results']))

    @unittest.skipIf(os.environ.get('TOKENTRIM_SKIP_REFERENCE_TEST') == '1', 'Reference subprocess suite disabled')
    def test_all_references_and_unmodified_repositories(self):
        corpus = ROOT / 'bench/tasks_repo'
        def snapshot():
            return {str(p.relative_to(corpus)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in corpus.rglob('*') if p.is_file()}
        before = snapshot()
        result = reference_self_test()
        self.assertEqual(result['task_count'], 40)
        self.assertEqual(result['reference_passed'], 40, result)
        self.assertEqual(result['unmodified_failed'], 40, result)
        self.assertEqual(snapshot(), before)


if __name__ == '__main__':
    unittest.main()
