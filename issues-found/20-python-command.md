# Required python command absent on this host

## Symptom

The task manifest requires `python -m unittest discover -s tests -q`, but this host
provides Python 3.13.5 as `python3` and has no `python` executable on PATH.

## Reproduction

From `/workspace/tokentrim`, `python --version` fails with command not found;
`python3 --version` reports Python 3.13.5.

## Cause

The interpreter is installed under the versioned command name only. Changing the
manifest check would violate the shared benchmark format.

## Fix

Run `python3 bench/tasks_repo/validate.py`. The validator creates a temporary
`python` symlink to `sys.executable` within its local scratch directory and uses
that directory as the subprocess PATH. The manifest command stays unchanged, no
system files are modified, and scratch files are removed at completion. A benchmark
runner on this host also needs to provide `python` in its isolated task environment.

## Verification

All 40 fixtures fail before and pass after their solution overlays. The validator's
13 unittest regression checks pass using the same local interpreter alias.
