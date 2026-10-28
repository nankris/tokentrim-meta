# Offline checker and honest result metadata

- Symptom: the default checker accepted FAKE response prefixes without applying edits or executing checks. The metadata notice always claimed checks were simulated, even for custom checkers.
- Repro: run the old benchmark with the fake client; every synthetic response passes regardless of task correctness.
- Root cause: only a synthetic checker was wired into the CLI, and the notice was hard-coded.
- Fix: added an opt-in real checker, strict JSON full-file replacements, disposable repository copies, captured check output, a five-second process-group timeout, and temporary Python command aliases. Metadata distinguishes simulated usage from simulated checks. Reference self-tests exercise the same parser and execution path and verify original corpus hashes.
- Status: fixed; fake remains the compatibility default. The fake client intentionally fails the real edit parser.

## Remaining execution boundary

The temporary workspace and minimal environment are not an OS security sandbox. Executed Python can access the host filesystem or network if instructed to do so. Use trusted offline tasks/edits only; hostile generated code requires an external sandbox. This change makes no network/model calls and does not add a remote client.
