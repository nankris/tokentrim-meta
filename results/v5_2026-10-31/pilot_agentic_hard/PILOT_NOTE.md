# v5 cost pilot (tasks ah100-ah103, all 6 arms; excluded from analysis per pre-registration)

- Spend: $0.1784, measured by the ledger. Mean $/task: baseline 0.00690, skill 0.00899, tool_output 0.00358,
  schema_router 0.01225, full_no_router 0.00399, full 0.00887. All 24 runs passed.
- **Projection.** These are estimates from the pilot, not results:
  - run A (tasks 0-47, 6 arms): about $2.14
  - run B (tasks 48-95, baseline + full): about $0.76
  - long chat (24 tasks, 3 arms): about $0.6
  - total about $3.5, plus the pilot, which is under the $5 round cap.
- **n stays 96 as pre-registered, so no amendment is needed.**
- Early signal to check at full n: on this set the router deliberately misses the needed tools, and Full cost more
  than Baseline in the pilot. Full made extra search_tools rounds and got few cache hits.
