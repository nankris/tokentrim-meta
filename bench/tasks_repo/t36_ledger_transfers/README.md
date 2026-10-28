# Ledger Transfers

Add exact-cent money handling and atomic transfers across money.py and ledger.py. to_cents(value) accepts decimal strings or Decimal, rounds half-up to cents (including negative halves), returns int, and raises ValueError for invalid/nonfinite values. format_cents(int) returns a signed decimal string with two places. Ledger(opening) converts each opening balance with to_cents and rejects negative balances. balance(account) returns formatted money and raises KeyError for unknown accounts. transfer(source, target, amount) converts amount once, rejects nonpositive rounded amounts with ValueError, checks both accounts (KeyError) and sufficient funds (ValueError), then updates atomically. A self-transfer still validates amount/accounts/funds but leaves balance unchanged. Never mutate opening.

Run `python -m unittest discover -s tests -q` from this directory.
