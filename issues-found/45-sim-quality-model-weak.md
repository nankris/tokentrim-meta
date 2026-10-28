# 45 — The simulator can't measure quality loss

- **Symptom:** pass outcomes are assumed probabilities by model tier and difficulty. With up to 4 attempts plus escalation, retries absorb most per-attempt quality loss. A `trim_penalty` of 8 pp shows up as dollars (saving drops from 11.5 to 9.9%) rather than as pass rate.
- **Other limits:**
  - The baseline pass rate (98.3%) is optimistic.
  - The `realistic` context sizes come from synthetic padding.
  - The output length is the same on both models.
  - Planning quality has no effect on edit success.
- **Status:** by design, this is open until real runs happen. Claims must use measured dollars and pass rates. `results/sim/` is labelled SIMULATION everywhere.
