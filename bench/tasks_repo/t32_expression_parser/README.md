# Expression Parser

Replace evaluate(text)’s ad hoc arithmetic handling with a structured parser while preserving sums/subtractions of nonnegative integers. Add multiplication, true division, parentheses, and unary +/-. Use ordinary precedence (unary, then */ left-to-right, then +- left-to-right); allow repeated unary signs and arbitrary whitespace between tokens. Numbers are ASCII nonnegative integer literals (no decimals). Reject empty input, invalid characters, missing operands, unbalanced parentheses, adjacent numbers, and trailing tokens with ValueError. Division by zero raises ZeroDivisionError. Do not execute input as Python.

Run `python -m unittest discover -s tests -q` from this directory.
