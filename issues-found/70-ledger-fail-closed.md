# 70: Ledger failure modes were not explicitly fail-closed

**Found:** v6 review (v5.1 step 3). **Status:** Fixed (v5.1).

## Problem
The reservation ledger already blocked calls over the cap, but some failure modes were untested or unsafe:
* a corrupt or malformed ledger file raised a bare `JSONDecodeError`/`TypeError` (not a budget error), and nothing
  guaranteed it would never be overwritten;
* `flock` waited forever (no lock timeout);
* if a billed call's commit failed (disk error), the reservation of a process that later exited was discarded,
  so that spend could be lost and the ledger would under-count;
* a metered upstream built without a ledger sent calls unreserved;
* the gateway's fail-open `except Exception` could in principle swallow a budget error raised inside a transform.

## Fix
* `LedgerUnavailable` (a subclass of `SpendCapExceeded`, so the server answers 402 and benchmarks stop and
  report). It is raised on: an unreadable, corrupt or malformed file (never overwritten); a lock timeout
  (`lock_timeout`, default 30 s); an OS or disk error while locking or writing a reservation; a metered upstream
  with no ledger.
* If a commit fails after a billed call, its amount goes to `<ledger>.unrecorded.jsonl`. That ledger object is
  then disabled, and every ledger (including new processes) refuses to reserve until a human reconciles the
  ledger and deletes that file. If a release fails, the reservation stays held (it over-counts, the safe
  direction).
* Optimizer errors still fail OPEN: the original request is forwarded, and it still needs a reservation.
  Fail-open handlers re-raise `SpendCapExceeded`.

## Regression
`tests/test_ledger_fail_closed.py` (11 tests) covers:
* a corrupt file;
* malformed fields;
* a lock timeout followed by recovery;
* a disk error on reserve;
* a disk error on commit (the ledger is poisoned, the side file is written, a fresh object also refuses, and
  sending works again after reconciliation);
* no ledger;
* the cap being exceeded;
* an upstream 401 (the reservation is released and $0 is booked);
* an optimizer exception (fail open, the original payload is forwarded);
* 12 threads on 4 ledger objects, and 6 forked processes, reserving near the cap.

In every case the upstream send counter stays at 0 when it must, and the committed total never exceeds the cap.
In the concurrency tests it lands exactly at floor(cap / cost) calls.
