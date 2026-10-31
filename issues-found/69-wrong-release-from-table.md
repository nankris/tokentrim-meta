# 69: Full picked a wrong release from the tabularized span JSON (ah43)

- **Where:** v5 Meta run A, agentic_hard ah43, arm `full`. This is a REAL run.
- **Observed:** the model answered release `rel-2374` / `BATCH_LIMIT=20`. The right answer is `rel-1309` /
  `BATCH_LIMIT=2`. Baseline was correct on the same task.
  - The exception facts, request id and trace ref were all correct.
  - All three dependent tools were called. The manifest call used the wrong build.
- **Check (offline):**
  - The compressed span output (10,498 -> 5,124 chars) keeps every row in a `span_id | parent | ... | release |
    note` table, so the correct value and the ERROR row were present.
  - Nothing was lost. This is a reading or selection error on a table where rel-1309 and rel-2374 alternate across
    58 rows.
- **Assessment:** one failure, so it is not attributable with confidence.
  - The table form could make it harder to find the release of the single ERROR row.
  - A safer option is to always lift rows that match error/exception/fail out of the table as a "flagged rows" header.
- **Status:** Open (fix proposed, not applied in the frozen-code v5 round).
