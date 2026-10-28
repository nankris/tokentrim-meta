# Issues found

One markdown file per issue group, named `NN-short-slug.md`.
Each file: symptom, repro, root cause (if known), fix/status.

| # | File | Status |
|---|------|--------|
| 10 | [Python command availability](10-python-command.md) | Documented; verified with Python 3.13.5 via python3 |
| 11 | [Bootstrap float comparison](11-bootstrap-float-comparison.md) | Fixed test tolerance |
| 20 | [Bench tasks: `python` command absent](20-python-command.md) | Worked around: validate.py provides a temporary `python` alias for check commands |
| 30 | [Offline checker and metadata](30-real-checker.md) | Fixed; hostile-code sandboxing remains outside scope |
