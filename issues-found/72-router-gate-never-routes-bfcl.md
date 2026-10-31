# 72: The router's safety gate never routes on natural BFCL catalogues

**Found:** public slices round (2026-10-31), offline. **Status:** Documented (by design; see the measured result).

## Observation
On all 1,053 BFCL v3 `live_multiple` items, the shipped gate (`router_gating=True`) kept the full catalogue every
time. 1,051 items have 16 tools or fewer ("few tools"), and 2 were skipped for low confidence. Natural BFCL
catalogues are too small for routing to matter, so the shipped router has **no effect** on this benchmark as
published. To test the router hypothesis, the pre-registered slice augments each catalogue to 40 tools with
distractor functions from other BFCL groups. That is a TokenTrim construction and is not the leaderboard setting.
On the augmented slice, the gate still routed only 9/100 items in the mock run (91 skipped for low confidence).
So the realistic savings come from `router_forced`, and its accuracy is the open question the measured run answers.
