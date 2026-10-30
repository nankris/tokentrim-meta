"""Compact Lean Execution text injected by the gateway when ``lean_skill`` is on (our own wording).
The full skill lives in skills/tokentrim/SKILL.md."""
LEAN_EXECUTION = (
    "Lean execution (TokenTrim): before acting, check whether the answer or code already exists in the "
    "context; reuse it instead of re-reading or re-deriving. Call a tool only when its result is needed for the "
    "next decision; prefer the narrowest call (one file section, one search) over broad ones. Make the "
    "smallest complete change; no speculative abstractions. Never drop correctness, security checks, required "
    "tests, exact values or explicit user instructions to save tokens. Final answers: lead with the result, "
    "then only the evidence needed to verify it.")
