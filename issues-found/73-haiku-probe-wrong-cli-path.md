# 73: Validation probe silently used the wrong CLI (0/96)

**Found:** public slices round (2026-10-31), haiku validation probe. **Status:** Fixed. No Meta spend.

`benchmarks.cheap_probe_hard.ask()` takes the `claude -p` path only when the model name starts with `claude`. The
probe passed `"haiku"`, which fell through to the `codex exec` path, returned empty answers, and scored 0/96
("undecodable"). The fix is to use `claude-haiku-5-5`. The rerun scored BFCL full 15/24 and routed 15/24, and
LogChunks raw 18/24 and ci 17/24. The 0/96 run was discarded, and the slice was not changed afterwards.
Lesson: a 0% result on a validation probe is a plumbing failure until proven otherwise.
