# TokenTrim offline coding tasks

This set contains 40 independent Python 3.13 repo-edit tasks. All projects use only
standard-library modules and `unittest`; no network, installation, credentials,
external data, or paid services are needed. Each starting project has a behavioral
failure, and each reference overlay makes the same tests pass. Difficulty labels
are estimates based on the specification and edge cases, not measured agent scores.

## Layout and agent isolation

- `../tasks/tasks_40.jsonl`: authoritative manifest, one task per JSON line.
- `tNN_slug/`: starting project, task README, source files, and `tests/`.
- `_solutions/tNN_slug/`: reference overlay containing **only changed or added
  files**, at the same relative paths as the starting project. No tests are included.
- `validate.py`: schema, fixture, and before/after behavioral validation.
- `validation_report.md`: generated results from the latest validation.

**Stage only the selected `repo` directory in the agent's workspace.** Give the
agent its manifest `prompt` and the staged project. Never expose `_solutions`, the
full manifest's solution paths, this parent directory, or a solved copy to the
benchmark agent. `files` enumerates the project files; it is not a sandbox. A runner
must enforce the workspace boundary. Apply reference solutions only in a separate,
trusted validation workspace. Agent checks must use the original tests unchanged.

Every project has 1–5 source files, plus tests, and fewer than 300 Python lines
including tests. Adjacent presentation helpers and existing functions provide
irrelevant context as well as regression behavior. Multi-file tasks require
coordinated changes across two substantive modules. Refactor checks assert public
behavior and compatibility, without requiring a particular private architecture.

## Manifest format

Each line has exactly these fields (all paths use `/`):

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Unique `tNN_slug`, numbered 01 through 40 in this set. |
| `repo` | string | `bench/tasks_repo/<id>`, relative to the repository root. |
| `prompt` | string | User-facing request specifying behavior, edge cases, and compatibility. |
| `check` | string | Exactly `python -m unittest discover -s tests -q`. Run inside the staged project. |
| `files` | array of strings | All project files, with paths relative to the task directory. |
| `solution` | string | `bench/tasks_repo/_solutions/<id>`; trusted evaluator metadata only. |
| `category` | string | `bug_fix`, `feature`, `refactor`, `multi_file`, or `test_driven`. |
| `difficulty` | string | `easy`, `medium`, or `hard`. |

Tests exercise observable outcomes described in the prompt, including errors and
side effects where specified. They use fixed inputs, injected clocks, and injected
sleep callbacks. They do not depend on wall-clock dates, real sleeping, random
seeds, external services, or private implementation details. Features and
test-driven tasks may start with explicit `NotImplementedError` stubs; bug-fix
and refactor tasks begin with functioning but incomplete or incorrect behavior.

## Validate

From `/workspace/tokentrim`:

```sh
python3 bench/tasks_repo/validate.py
```

Use Python 3.13. The validator provides a temporary `python` alias to its own
interpreter, so the manifest command works on hosts that expose only `python3`.
It creates scratch directories **inside `bench/tasks_repo/`**, removes them on
completion, and leaves the source projects unchanged. Bytecode writing is disabled.
It does not import the surrounding TokenTrim package.

For each task it checks the exact schema, unique ids, paths, complete file list,
source count/size, Python syntax, and a nonempty overlay containing no unchanged
files or test files. It then makes two independent copies, overlays the solution
in only the second, and runs the check in both with a five-second timeout per
invocation. The baseline must execute tests and fail; the solved state must run
the same test count and pass. Test content hashes must remain unchanged. Syntax
errors, import failures, timeouts, and zero discovered tests are validation errors,
not acceptable baseline failures.

The command prints a table and summary, writes `validation_report.md`, and exits
nonzero on any error. Report timings cover both subprocess runs and vary by host;
they are not benchmark performance measurements. The report is fixture validation,
not evidence of agent pass rates or token savings.

Validator regression checks can be run separately:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s bench/tasks_repo/_validator_tests -q
```

To inspect one starting project manually, change into its directory and run the
manifest check; failure is expected. To inspect a reference state, copy the project
to a separate scratch directory and copy only its overlay files over that copy.
Never apply an overlay to the canonical starting project.

## Category and difficulty mix

| Category | Easy | Medium | Hard | Total | Share |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bug fixes | 8 | 6 | 2 | 16 | 40% |
| Small features | 4 | 4 | 2 | 10 | 25% |
| Refactors with new behavior | 1 | 4 | 1 | 6 | 15% |
| Multi-file edits | 0 | 2 | 2 | 4 | 10% |
| Test-driven implementations | 2 | 1 | 1 | 4 | 10% |
| **Total** | **15** | **17** | **8** | **40** | **100%** |

Domains include escaping and CSV, Unicode, dates and calendars, decimal money,
configuration, caching, CLI arguments, streaming iterators, priority queues,
dependency graphs, transactions, URL queries, inventory, route matching,
serialization, validation, state machines, expression parsing, binary framing,
run-length encoding, histogram bins, suggestions, and weighted paths.

## Add or replace a task

1. Choose a unique `tNN_slug` and write a concrete user request. State behavior,
   edge cases, error types, and compatibility guarantees without revealing a fix.
2. Create a small project with meaningful starting behavior and some plausible
   adjacent code. Keep it independent of other tasks and of TokenTrim itself.
3. Add deterministic `unittest` tests under `tests/`. Cover the requested change
   and existing behavior; do not assert source text, private names, or an algorithm
   unless the request explicitly makes it part of the public contract.
4. Confirm that the original tests run and fail for the intended behavioral reason.
   Do not use syntax/import failures as the benchmark challenge.
5. Implement a reference fix in a scratch copy and verify the same tests pass.
   Copy only changed or added non-test files to `_solutions/<id>/`; never leave
   the fix, answer notes, or solution links in the starting project.
6. Add/update the manifest record with the exact fields above, list every project
   file, and update this mix table. This fixed benchmark must remain exactly 40
   tasks numbered 01–40; replace an existing slot when maintaining this set. A
   larger future set needs its own manifest and explicit validator count/id changes.
7. Run validator regression checks and `validate.py`, and review the generated
   report. Record discovered problems in an authorized issues-found file.
