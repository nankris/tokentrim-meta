# Retry Budget

run_with_retry(operation, attempts, retry_on, sleep) should make at most attempts total calls (attempts must be >= 1). Retry only exceptions matching retry_on, a tuple of exception classes. Sleep 1, 2, 4, ... seconds only between retries. Return successful values, including falsey ones; propagate the last exception unchanged when exhausted, and never sleep after the final attempt.

Run `python -m unittest discover -s tests -q` from this directory.
