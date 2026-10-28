# Validation Errors

Refactor validate_user and validate_team to share validation rules while keeping their current list-of-error-codes API and error ordering (name first, count second). Names must now be strings with non-whitespace content; strip only for checking, without mutating data. Counts must be nonnegative ints and must reject bool (Python otherwise treats bool as int). Add validate_project using title/seats fields and error codes title_required, seats_invalid. Missing fields are invalid; extra fields are ignored.

Run `python -m unittest discover -s tests -q` from this directory.
