# 40 — Codex sandbox blocks loopback sockets

- **Symptom:** during the Codex build pass, `test_proxy_loopback_and_refusal` could not bind 127.0.0.1, so the test skipped itself (`PermissionError`).
- **Repro:** run the suite inside the Codex managed sandbox.
- **Root cause:** the sandbox forbids socket creation. This is not a TokenTrim bug.
- **Status:** the test runs and passes on the box. The skip guard stays so sandboxed runners don't fail falsely.
