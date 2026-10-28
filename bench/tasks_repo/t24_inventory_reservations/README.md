# Inventory Reservations

Add reservations to Inventory. Initial stock maps SKU to nonnegative integers. reserve(token, items) takes nonnegative integer quantities: atomically subtract all if available, otherwise raise ValueError (also for unknown SKUs or negative quantities). A repeated active token with the same items is an idempotent no-op; different items raise ValueError. release(token) restores stock once and returns True, or False if unknown/already released. available(sku) returns stock or zero. Defensively copy stock and reservation inputs. Released tokens may be reused.

Run `python -m unittest discover -s tests -q` from this directory.
