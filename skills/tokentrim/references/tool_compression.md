# Compressing tool output without losing evidence

Always keep verbatim: exception names and messages, tracebacks, failing assertions, `file:line` references,
exit codes, error/warning lines, summary counts ("3 failed, 850 passed"), identifiers and numbers the task
asks about.

By content type:
- **Test output**: keep failure sections and the summary; replace passing lines by a count.
- **Logs**: collapse lines that repeat apart from the timestamp (keep the count); keep error lines with one
  line of context; keep the first and last few lines.
- **JSON**: minify; render homogeneous arrays of flat objects as a column table (lossless); only then trim
  long tables, keeping rows that mention errors.
- **Diffs**: keep file headers, hunk headers and changed lines; drop most unchanged context.

Keep the original retrievable (TokenTrim returns a `retrieve_original("<ref>")` reference). If the compressed
view does not answer the question, fetch the original instead of guessing.
