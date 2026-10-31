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
- **Fix (v5.1):** `compress_json` is now structure-preserving.
  - Column-table flattening is gone. Each record is one compact JSON object, with its own keys, on its own line,
    prefixed by its JSON Pointer (`/spans/21 {...}`).
  - A header lists the pointers of records that match an error or a task identifier.
  - `mode="conservative"` is lossless.
  - `mode="lossy"` keeps flagged records, their parent chain and the first/last rows, and announces every gap with
    its pointer range.
- **Regression:**
  - `tests/test_json_structure.py`: 100 generated documents (`benchmarks/json_extraction.py`) with similar release
    names, nested objects and misleading neighbours, plus the ah43 spans themselves.
  - Structural check (error record id + status + release on one keyed line; parent record present):
    - legacy table: 50/100
    - structured: 100/100
    - structured lossy: 100/100
- **Status:** Fixed (v5.1).
