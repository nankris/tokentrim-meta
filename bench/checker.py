"""Offline checks in disposable copies (process isolation, not a security sandbox)."""
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

from .tasks_repo.validate import project_files, safe_relative

ROOT = Path(__file__).resolve().parent.parent
EDIT_INSTRUCTIONS = '''Return your final edit as a JSON object only: {"files": {"relative/path.py": "complete file contents\\n"}}.
Each entry replaces a whole UTF-8 file. Use canonical relative POSIX paths; no parent traversal,
absolute paths, symlinks, or changes under tests/. Include every intended edit in the final response.
Do not wrap the JSON in Markdown. An empty files object means no edits.'''


def parse_edits(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    data = json.loads(text, object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {'files'} or not isinstance(data['files'], dict):
        raise ValueError('Expected a JSON object containing only a files object')
    for name, content in data['files'].items():
        safe_relative(name)
        if name == 'tests' or name.startswith('tests/'):
            raise ValueError('Edits may not replace task tests')
        if not isinstance(content, str):
            raise ValueError('File contents must be strings')
    return data['files']


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    output: str
    returncode: int | None = None
    timed_out: bool = False
    error: str | None = None

    def __bool__(self):
        return self.passed


def check_edit(task, text, *, timeout=5):
    """Apply one final response and execute argv from task.check without a shell."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Timeout must be finite and positive')
    try:
        edits = parse_edits(text)
        safe_relative(task.repo)
        source = ROOT / task.repo
        if not source.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in [source, *source.parents] if p.is_relative_to(ROOT)):
            raise ValueError('Unsafe repository path')
        project_files(source)  # Reject symlinks before copying or following any file.
        with tempfile.TemporaryDirectory(prefix='.checker-', dir=ROOT) as directory:
            workspace = Path(directory)
            repo = workspace / 'repo'
            shutil.copytree(source, repo, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            for name, content in edits.items():
                target = repo / name
                if not target.resolve().is_relative_to(repo):
                    raise ValueError('Edit escapes temporary repository')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')
            bin_dir = workspace / 'bin'
            bin_dir.mkdir()
            for name in ('python', 'python3'):
                (bin_dir / name).symlink_to(sys.executable)
            env = {'PATH': str(bin_dir), 'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTHONHASHSEED': '0', 'PYTHONIOENCODING': 'utf-8',
                   'HOME': str(workspace), 'TMPDIR': str(workspace)}
            with subprocess.Popen(shlex.split(task.check), cwd=repo, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  start_new_session=True) as process:
                timed_out = False
                try:
                    output, _ = process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    output, _ = process.communicate()
                finally:
                    # Also stop any children left behind by a completed command.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                return CheckResult(process.returncode == 0 and not timed_out,
                                   output.decode('utf-8', errors='replace'), process.returncode,
                                   timed_out, 'Check timed out' if timed_out else None)
    except (ValueError, OSError) as error:
        return CheckResult(False, '', error=f'{type(error).__name__}: {error}')


def real_checker(task, responses, mode):
    return check_edit(task, responses[-1].text if responses else '')


def reference_self_test(tasks_path=None, *, timeout=5):
    from .runner import load_tasks, safe_path
    tasks = load_tasks(tasks_path or ROOT / 'bench/tasks/tasks_40.jsonl')
    rows = []
    for task in tasks:
        if not task.solution:
            raise ValueError(f'{task.id}: missing reference solution')
        solution = safe_path(task.solution)
        files = project_files(solution)
        edit = json.dumps({'files': {name: path.read_text(encoding='utf-8') for name, path in files.items()}})
        before = check_edit(task, '{"files": {}}', timeout=timeout)
        after = check_edit(task, edit, timeout=timeout)
        # Infrastructure errors/timeouts are not evidence that a broken repo fails its tests.
        failed = before.returncode is not None and before.returncode > 0 and not before.error and 'FAILED (' in before.output
        rows.append({'task_id': task.id, 'unmodified_failed': bool(failed),
                     'before': asdict(before), 'reference': asdict(after)})
    return {'task_count': len(tasks), 'reference_passed': sum(r['reference']['passed'] for r in rows),
            'unmodified_failed': sum(r['unmodified_failed'] for r in rows), 'results': rows}
