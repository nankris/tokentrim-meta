# v5.3 pre-Meta validation (harness checks, not results)

## 1. Mock harness: i = 300…395, 96 tasks × 3 arms (MOCK upstream, $0)
| policy | baseline | compression_only | guarded_full |
|---|---|---|---|
| oracle | 96/96 | 96/96 | 96/96 |
| lazy (never uses recovery) | 96/96 | 2/96 | 2/96 |
| guess | 0/96 | 0/96 | 0/96 |

The grader discriminates, and the compressed arms really need recovery (retrieve_original or grep). On every
hard task the guarded_full router gate fires ("low confidence"), so guarded_full sends all 32 tools there.

## 2. Cheap probe: claude-haiku-5-5 via `claude -p`, i = 500…523 (disjoint from the confirmatory set)
| arm | pass | retrieve calls | CLI tokens |
|---|---|---|---|
| raw | 23/24 (ah520 stopped before open_artifact_manifest) | 0 | 6.60M |
| compressed (auto JSON mode) | 24/24 | 24 | 4.93M |

Paired diff +4.2 pp [−10.1, +20.2] (Newcombe). This is a go/no-go check only; it supports no quality claim.
Rows: `cheap_probe_hard_claude-haiku-5-5.jsonl`.
