#!/usr/bin/env python3
"""Validate offline task fixtures without modifying the original projects."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parent
MANIFEST = BASE.parent / 'tasks' / 'tasks_40.jsonl'
REPORT = BASE / 'validation_report.md'
CHECK = 'python -m unittest discover -s tests -q'
FIELDS = {'id', 'repo', 'prompt', 'check', 'files', 'solution', 'category', 'difficulty'}
CATEGORIES = {'bug_fix', 'feature', 'refactor', 'multi_file', 'test_driven'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_relative(value):
    require(isinstance(value, str) and value, 'path must be a nonempty string')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in value,
            f'unsafe relative path: {value}')
    require(path.as_posix() == value and value != '.', f'noncanonical path: {value}')
    for part in path.parts:
        require(not (part in {'.local', '.ssh'} or part.startswith(('.env', 'colab_key', 'colab_rsa', '.codex'))
                     or part.endswith('.pem')), 'prohibited path')
    return path


def project_files(root):
    require(root.is_dir() and not root.is_symlink(), f'missing or symlinked directory: {root.name}')
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != '__pycache__')
        for name in dirs:
            path = Path(directory) / name
            safe_relative(path.relative_to(root).as_posix())
            require(not path.is_symlink(), f'symlink directory: {name}')
        for name in sorted(files):
            if name.endswith('.pyc'):
                continue
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            safe_relative(rel)
            require(not path.is_symlink(), f'symlink file: {rel}')
            result[rel] = path
    return result


def hashes(files):
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def compile_sources(files):
    for name, path in files.items():
        if name.endswith('.py'):
            compile(path.read_bytes(), name, 'exec')


def run_check(repo, environment):
    start = time.monotonic()
    try:
        result = subprocess.run(shlex.split(CHECK), cwd=repo, env=environment,
                                capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired as error:
        raise ValueError('check exceeded the 5 second timeout') from error
    output = result.stdout + result.stderr
    matches = re.findall(r'Ran (\d+) tests? in ', output)
    require(matches and int(matches[-1]) > 0, 'unittest did not execute tests:\n' + output)
    require('unittest.loader._FailedTest' not in output, 'test import failed:\n' + output)
    return result.returncode, int(matches[-1]), time.monotonic() - start, output


def validate_task(task, seen, workspace, environment):
    require(isinstance(task, dict) and set(task) == FIELDS, 'manifest fields do not match the shared schema')
    ident = task['id']
    require(isinstance(ident, str) and re.fullmatch(r't\d{2}_[a-z0-9_]+', ident), 'invalid task id')
    require(ident not in seen, f'duplicate id: {ident}')
    seen.add(ident)
    require(task['repo'] == f'bench/tasks_repo/{ident}', 'repo must point to this task directory')
    require(task['solution'] == f'bench/tasks_repo/_solutions/{ident}', 'incorrect solution path')
    require(isinstance(task['prompt'], str) and task['prompt'].strip(), 'empty prompt')
    require(task['check'] == CHECK, 'unexpected check command')
    require(task['category'] in CATEGORIES, 'invalid category')
    require(task['difficulty'] in {'easy', 'medium', 'hard'}, 'invalid difficulty')
    require(isinstance(task['files'], list) and task['files'], 'files must be a nonempty list')
    for rel in task['files']:
        safe_relative(rel)
    require(len(task['files']) == len(set(task['files'])), 'duplicate files entry')
    repo, solution = BASE / ident, BASE / '_solutions' / ident
    original, overlay = project_files(repo), project_files(solution)
    require(set(task['files']) == set(original), 'files must enumerate every project file')
    tests = {name: path for name, path in original.items() if name.startswith('tests/')}
    require(any(name.endswith('.py') for name in tests), 'no test files')
    sources = [name for name in original if name.endswith('.py') and not name.startswith('tests/')]
    require(1 <= len(sources) <= 5, 'expected 1 to 5 source files')
    lines = sum(len(path.read_text().splitlines()) for name, path in original.items() if name.endswith('.py'))
    require(lines < 300, f'project has {lines} Python lines (limit <300)')
    require(overlay, 'empty solution overlay')
    for name, path in overlay.items():
        require(name != 'tests' and not name.startswith('tests/'), 'solution touches tests: ' + name)
        require(name not in original or path.read_bytes() != original[name].read_bytes(),
                'solution includes an unchanged file: ' + name)
    compile_sources(original)
    compile_sources(overlay)
    before = workspace / 'before'
    after = workspace / 'after'
    shutil.copytree(repo, before, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(repo, after, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    initial_hashes = hashes(tests)
    for name, path in overlay.items():
        target = after / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    after_tests = {name: path for name, path in project_files(after).items() if name.startswith('tests/')}
    require(hashes(after_tests) == initial_hashes, 'overlay changed the tests')
    baseline = run_check(before, environment)
    solved = run_check(after, environment)
    require(baseline[0] != 0 and 'FAILED (' in baseline[3],
            'starting project must fail its tests:\n' + baseline[3])
    require(solved[0] == 0, 'solved project must pass:\n' + solved[3])
    require(baseline[1] == solved[1], 'test count changed after overlay')
    for copy in (before, after):
        final_tests = {name: path for name, path in project_files(copy).items() if name.startswith('tests/')}
        require(hashes(final_tests) == initial_hashes, 'check modified test files')
    return baseline, solved, lines


def main():
    records, errors = [], []
    try:
        for number, line in enumerate(MANIFEST.read_text().splitlines(), 1):
            try:
                require(bool(line.strip()), 'blank manifest line')
                records.append(json.loads(line))
            except (ValueError, TypeError) as error:
                errors.append(f'Line {number}: {error}')
    except OSError as error:
        errors.append(f'Cannot read manifest: {error}')
    if len(records) != 40:
        errors.append(f'Expected exactly 40 tasks, found {len(records)}')
    rows, seen, passed = [], set(), 0
    # The required command uses "python"; provide it locally even on python3-only hosts.
    # All scratch files live below the permitted tasks_repo directory and are removed.
    with tempfile.TemporaryDirectory(prefix='_validation_', dir=BASE) as scratch:
        workspace = Path(scratch)
        bin_dir = workspace / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'python').symlink_to(sys.executable)
        environment = {'PATH': str(bin_dir), 'PYTHONDONTWRITEBYTECODE': '1',
                       'PYTHONHASHSEED': '0', 'PYTHONIOENCODING': 'utf-8',
                       'HOME': str(workspace), 'TMPDIR': str(workspace)}
        print(f"{'Task':32} {'Before':8} {'After':8} {'Tests':5} {'Seconds':8} Result")
        for index, task in enumerate(records):
            ident = task.get('id', f'line_{index+1}') if isinstance(task, dict) else f'line_{index+1}'
            category = task.get('category', '?') if isinstance(task, dict) else '?'
            difficulty = task.get('difficulty', '?') if isinstance(task, dict) else '?'
            task_workspace = workspace / str(index)
            task_workspace.mkdir()
            try:
                before, after, lines = validate_task(task, seen, task_workspace, environment)
                elapsed = before[2] + after[2]
                rows.append((ident, category, difficulty, 'FAIL', 'PASS', str(after[1]), f'{elapsed:.3f}', 'PASS'))
                passed += 1
                print(f'{ident:32} {"FAIL":8} {"PASS":8} {after[1]:5} {elapsed:8.3f} PASS')
            except Exception as error:
                errors.append(f'{ident}: {type(error).__name__}: {error}')
                rows.append((str(ident), str(category), str(difficulty), '?', '?', '?', '?', 'FAIL'))
                print(f'{str(ident):32} {"?":8} {"?":8} {"?":5} {"?":8} FAIL')
            finally:
                shutil.rmtree(task_workspace)
    expected_ids = set(range(1,41))
    actual_ids = {int(ident[1:3]) for ident in seen}
    if actual_ids != expected_ids:
        errors.append('Task ids must cover t01 through t40 exactly once')
    summary = f'Validation: {passed}/40 tasks fail-before and pass-after; {len(errors)} errors.'
    table = ['| Task | Category | Difficulty | Before | After | Tests | Seconds (both) | Result |',
             '| --- | --- | --- | --- | --- | ---: | ---: | --- |']
    table.extend('| ' + ' | '.join(row) + ' |' for row in rows)
    report = ['# Task validation report', '', f'Python: {sys.version.split()[0]}', '',
              'Command: `python -m unittest discover -s tests -q`', '',
              'Each state ran in a fresh isolated copy. Solution overlays and test hashes were checked.', '',
              *table, '', summary, '']
    if errors:
        report += ['## Errors', '', '```text', '\n\n'.join(errors), '```', '']
    REPORT.write_text('\n'.join(report))
    print(summary)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
