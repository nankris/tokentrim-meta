"""Regression checks for rejecting invalid fixtures, using only temporary copies."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('task_validator', ROOT / 'validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='_validator_test_', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ident = 't01_sample'
        self.repo = self.root / self.ident
        self.solution = self.root / '_solutions' / self.ident
        (self.repo / 'tests').mkdir(parents=True)
        self.solution.mkdir(parents=True)
        (self.repo / 'core.py').write_text('def value(): return 0\n')
        (self.repo / 'tests' / 'test_core.py').write_text(
            'import unittest\nfrom core import value\n'
            'class ValueTests(unittest.TestCase):\n'
            '    def test_value(self): self.assertEqual(value(),1)\n')
        (self.solution / 'core.py').write_text('def value(): return 1\n')
        self.task = dict(id=self.ident, repo='bench/tasks_repo/' + self.ident,
                         solution='bench/tasks_repo/_solutions/' + self.ident,
                         prompt='Return one.', check=validator.CHECK,
                         files=['core.py', 'tests/test_core.py'], category='bug_fix', difficulty='easy')
        self.workspace = self.root / 'scratch'
        self.workspace.mkdir()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'python').symlink_to(sys.executable)
        self.environment = {'PATH': str(bin_dir), 'PYTHONDONTWRITEBYTECODE': '1'}

    def validate(self, seen=None):
        with patch.object(validator, 'BASE', self.root):
            return validator.validate_task(self.task, seen if seen is not None else set(),
                                           self.workspace, self.environment)

    def test_valid_fixture_and_original_unchanged(self):
        before = validator.hashes(validator.project_files(self.repo))
        baseline, solved, _ = self.validate()
        self.assertNotEqual(baseline[0], 0)
        self.assertEqual(solved[0], 0)
        self.assertEqual(validator.hashes(validator.project_files(self.repo)), before)

    def test_duplicate_id(self):
        with self.assertRaisesRegex(ValueError, 'duplicate id'):
            self.validate({self.ident})

    def test_rejects_test_overlay(self):
        (self.solution / 'tests').mkdir()
        (self.solution / 'tests' / 'test_core.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'solution touches tests'):
            self.validate()

    def test_missing_file(self):
        self.task['files'].append('missing.py')
        with self.assertRaisesRegex(ValueError, 'enumerate every project file'):
            self.validate()

    def test_unsafe_path(self):
        for value in ('../escape.py', '/absolute.py', 'a/../b', 'a\\b'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validator.safe_relative(value)

    def test_unchanged_overlay(self):
        (self.solution / 'core.py').write_text((self.repo / 'core.py').read_text())
        with self.assertRaisesRegex(ValueError, 'unchanged file'):
            self.validate()

    def test_passing_baseline_is_rejected(self):
        (self.repo / 'core.py').write_text('def value(): return 1\n')
        (self.solution / 'core.py').write_text('def value():\n    return 1\n')
        with self.assertRaisesRegex(ValueError, 'starting project must fail'):
            self.validate()

    def test_failing_solution_is_rejected(self):
        (self.solution / 'core.py').write_text('def value(): return 2\n')
        with self.assertRaisesRegex(ValueError, 'solved project must pass'):
            self.validate()

    def test_syntax_error_is_not_behavioral_failure(self):
        (self.repo / 'core.py').write_text('def broken(\n')
        with self.assertRaises(SyntaxError):
            self.validate()

    def test_import_error_is_not_behavioral_failure(self):
        (self.repo / 'core.py').write_text('import missing_task_specific_module\n')
        with self.assertRaisesRegex(ValueError, 'test import failed'):
            self.validate()

    def test_timeout_without_waiting(self):
        with patch.object(validator.subprocess, 'run', side_effect=subprocess.TimeoutExpired('python',5)):
            with self.assertRaisesRegex(ValueError, '5 second timeout'):
                validator.run_check(self.repo, self.environment)

    def test_no_tests_is_rejected(self):
        (self.repo / 'tests' / 'test_core.py').write_text('import unittest\n')
        with self.assertRaisesRegex(ValueError, 'did not execute tests'):
            self.validate()

    def test_manifest_mix(self):
        from collections import Counter
        tasks = [json.loads(line) for line in validator.MANIFEST.read_text().splitlines()]
        self.assertEqual(len(tasks),40)
        self.assertEqual(Counter(t['category'] for t in tasks),
                         {'bug_fix':16,'feature':10,'refactor':6,'multi_file':4,'test_driven':4})
        self.assertEqual(Counter(t['difficulty'] for t in tasks),{'easy':15,'medium':17,'hard':8})


if __name__ == '__main__':
    unittest.main()
