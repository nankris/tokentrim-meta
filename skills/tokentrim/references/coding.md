# Coding with fewer tokens

Before writing code:
1. Does this need to be built? Re-read the request; drop anything not asked for.
2. Does the repository already do it? Search for an existing function, helper, or config option.
3. Does an installed dependency or the platform already do it? Prefer it over new code.
4. Otherwise write the smallest complete implementation, including input validation, error handling and
   the tests the task requires.

Reading code:
- `grep`/search first, then read the matching range (e.g. 40 lines around the hit), not the whole file.
- Do not re-read a file you already have unless it changed.

Running tests:
- Run the narrowest test target that proves the change (one test file or `-k name`), then the full suite once.
- Read failures from the end of the log: the summary and the first failing assertion usually suffice.

Reporting:
- One line with the outcome, then the changed files and the test result. No restating of the task.
