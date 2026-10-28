# Python command availability

- Symptom: `python --version` exits 127 in this environment.
- Repro: run `python --version` from the repository root.
- Root cause: no `python` command is configured; `python3` is Python 3.13.5.
- Fix/status: use `python3` for verification and quickstart. No interpreter installation or external environment changes were made. `python -m ...` works where that alias exists.
