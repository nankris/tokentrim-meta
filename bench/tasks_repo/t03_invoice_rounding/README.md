# Invoice Rounding

Invoice totals lose cents. invoice_total(lines) receives (unit_price_string, integer_quantity) pairs. Round each extended line to cents with decimal ROUND_HALF_UP, then sum. Return Decimal with two decimal places, including for no lines. Negative lines are credits and use the same rounding rule.

Run `python -m unittest discover -s tests -q` from this directory.
