# Ttl Boundary

Fix TTLCache using its injected clock. put(key, value, ttl) expires at clock()+ttl; get returns default when now >= expiry. Nonpositive TTL invalidates that key immediately. Missing/expired keys must not hide live falsey values, and reading must not extend expiry. Replacing a key resets its expiry.

Run `python -m unittest discover -s tests -q` from this directory.
