# v5 cheap-model probe on the hard agentic set (zero Meta spend)

These are probes, not gateway runs. The CLIs (`claude -p`, `codex exec`) cannot be the gateway upstream, so
`benchmarks/cheap_probe_hard.py` emulates the agent loop with a one-line `CALL` / `ANSWER` text protocol. The
24 tasks (ah00-ah23), tool stubs and grader (10 checks: 6 exact facts, 3 dependent tool calls, no side effects;
pass = all 10) are the same ones the Meta run uses.
- **raw:** tool outputs unchanged.
- **compressed:** TokenTrim's query-aware ToolOutputCompressor plus `retrieve_original` (grep or full).

| model | raw pass | compressed pass | paired diff (compressed - raw) [95% Newcombe CI] | retrieve calls (compressed) | CLI tokens raw / compressed |
|---|---|---|---|---|---|
| claude-haiku-5-5 | 23/24 | 24/24 | +4.2 pp [-10.1, +20.2] | 23 | 5.81M / 3.45M |
| gpt-6-luna | 23/24 | 20/24 | -12.5 pp [-32.3, +7.2] | 23 | 2.30M / 0.93M |

- The raw failures were one per model: haiku on ah15, luna on ah04. Both stopped early and never called
  `open_artifact_manifest`.
- **luna compressed failures (ah00, ah09, ah15, ah20):**
  - Three stopped before the last dependent call: they missed `inspect_spans` and/or `open_artifact_manifest`.
  - One (ah00) answered on turn 1 without calling any tool.
  - None of them failed because a compressed fact was unrecoverable. Each run that reached the log called
    `retrieve_original` and got the exception facts right.
- **Re-run of those 4 luna compressed episodes:** 4/4 passed
  (`cheap_probe_hard_gpt-6-luna_rerun_failed4.jsonl`; transcripts in `probe_transcripts/`).
  So the gap is consistent with run-to-run variance in when the model stops. It does not show a compression
  defect, but n=24 cannot rule one out either; see issues-found/67.
- Neither CI excludes zero, so no quality claim is made from these probes. They only gave the go-ahead for the
  Meta run: the task set is solvable, and the compressed path with retrieval works on two other model families.
