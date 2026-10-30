# 56 — Cheap models are reachable only through their CLIs (2026-10-30)

- **Finding:** `gpt-6-luna` (Codex CLI) and `claude-haiku-5-5` (Claude Code CLI) work on the owner's subscriptions;
  `claude-haiku-5.5` (dotted id) is rejected. There are no API keys, and none may be added (no extra paid APIs).
- **Effect:** the cheap models cannot be the upstream behind the TokenTrim gateway. They were used as (a) quality
  probes of transforms (`benchmarks/cheap_probe.py`: raw vs compressed tool outputs, with vs without the skill),
  (b) code-writing helpers. All gateway/adapter plumbing was developed on the deterministic `MockChatUpstream`.
  The Claude Code harness adds ~15k identical prompt tokens per probe call, so probe token counts only compare arms.
- **Status:** documented; results in `results/v4_2026-10-30/cheap_probe_haiku*.jsonl`.
