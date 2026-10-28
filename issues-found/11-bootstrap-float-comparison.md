# Floating-point bootstrap assertions

- Symptom: an exact comparison expected a 50% interval endpoint but received 49.99999999999999.
- Repro: bootstrap paired samples `[2, 4, 6]` and `[1, 2, 3]`, then compare the computed percentage bounds with exact equality.
- Root cause: ordinary floating-point rounding in resampled means and percentage arithmetic.
- Fix/status: use approximate assertions for percentage endpoints; retain exact assertions for constant integer samples. Production estimates retain full precision; the dashboard rounds only for display.
