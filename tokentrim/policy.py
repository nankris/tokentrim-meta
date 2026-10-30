"""Quality-and-cost guard: run a transform only if its estimated net BILLED saving is positive.

Value of removing ``saved`` prompt tokens on each of ``future_calls`` calls, at hit probability ``h``:
    saved * future_calls * (h * p_cached + (1 - h) * p_input)
Cost: ``invalidated`` tokens that would have been cache hits and are now re-billed uncached once,
    invalidated * h * (p_input - p_cached), plus any extra model call the transform makes (``extra_usd``).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    apply: bool
    net_usd: float
    reason: str


def net_saving(rates: dict, saved_tokens: int, future_calls: int, invalidated_tokens: int = 0,
               hit_rate: float = 0.3, extra_usd: float = 0.0) -> Decision:
    p_in, p_c = rates["input"] / 1e6, rates["cached_input"] / 1e6
    gain = saved_tokens * max(1, future_calls) * (hit_rate * p_c + (1 - hit_rate) * p_in)
    loss = invalidated_tokens * hit_rate * (p_in - p_c) + extra_usd
    net = gain - loss
    return Decision(net > 0, net, f"est. net saving ${net:.6f} (gain ${gain:.6f} - cache/extra cost ${loss:.6f})")
