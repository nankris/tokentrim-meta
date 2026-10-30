---
name: tokentrim
description: Cut the cost of a coding or agent task without losing correctness. Use when a task involves large tool outputs (test logs, JSON, diffs), many tools, long conversations, repeated failing commands, or when the user mentions token cost, context size, budget, or caching.
---

# TokenTrim — spend less per successful task

Goal: the cheapest path to a **correct** result. Tokens saved on a failed task are worth nothing.

## Never trade away
Correctness, security checks, required tests, exact values (numbers, ids, paths, error text), and explicit
user instructions. When unsure whether something is needed, keep it.

## Decision ladder (stop at the first rung that works)
1. **Avoid the call.** Is the answer already in context (an earlier read, tool result, or message)? Use it.
2. **Reuse, don't resend.** Keep stable text (instructions, tool list) first and unchanged between calls so
   the provider cache can hit. Do not put timestamps or random ids at the top of prompts.
3. **Ask for less.** Read one function or line range, not the whole file; search before reading; call the one
   relevant tool, not a broad one.
4. **Shrink tool output, keep the evidence.** From a long log keep the failures, error lines, file:line
   references, exit codes and the summary counts; drop the passing noise. Keep a way back to the original.
5. **Summarize stale history** into a short state (goal, constraints, decisions, done, failed attempts, open
   tasks, exact facts) only when the conversation is long, and keep the transcript recoverable.
6. **Only optimize when it pays.** Rewriting early context breaks the cache; a cheap cached prefix can cost
   less than a "shorter" uncached one.

## Doing the work
- Make the smallest complete change; reuse existing code and dependencies; no speculative abstractions.
- Do not repeat a failing command unchanged. After the same error twice, change approach.
- Final reports: result first, then only the evidence needed to verify it.

## When you need more
- Coding workflow details: `references/coding.md`
- Prompt-cache rules: `references/caching.md`
- Compressing tool output safely: `references/tool_compression.md`
- History / memory compaction: `references/memory.md`
- `python3 scripts/analyze.py <session.jsonl|request.json>` — finds the biggest token sinks in a saved
  request or session (tool schemas, tool outputs, volatile prefix lines) and suggests a rung.
- `python3 scripts/report.py <results.jsonl>` — cost per successful task and token categories.
