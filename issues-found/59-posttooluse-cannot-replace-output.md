# 59 — A Claude Code PostToolUse hook cannot shrink tool output (2026-10-30)

- **Finding:** PostToolUse hooks can add `additionalContext`, but the original Bash output is still in the model's
  context. A "compression" hook there would ADD tokens.
- **Fix:** the installer (`python3 -m tokentrim.hooks.install --with-hooks`) installs only the loop guard as a hook.
  Compression is offered as a pipe filter (`cmd | python3 -m tokentrim.hooks.compress`, original recoverable with
  `--retrieve <ref>`) and inside the gateway, where it really replaces the content sent upstream.
- **Status:** fixed in `tokentrim/hooks/install.py`; uninstall also removes a legacy compress hook entry.
