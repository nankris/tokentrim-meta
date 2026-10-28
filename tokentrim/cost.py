"""Billing estimates; rates are assumptions until independently verified."""
import hashlib
import json
import math
import os
from pathlib import Path
import tomllib


def load_prices(path: str | Path | None = None) -> dict:
    source = Path(path or os.environ.get("TOKENTRIM_PRICES") or Path(__file__).with_name("prices.toml"))
    with source.open("rb") as stream:
        table = tomllib.load(stream)["models"]
    for model, rates in table.items():
        for key in ("input", "output", "cached_input"):
            value = rates[key]
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {key} price for {model}")
    return table


class CostModel:
    """Price usage in dollars from a deterministic local TOML price table."""

    def __init__(self, prices: dict | None = None, path=None, overrides: dict | None = None):
        base = prices if prices is not None else load_prices(path)
        self.prices = {name: dict(rates) for name, rates in base.items()}
        for name, rates in (overrides or {}).items():
            if isinstance(rates, (tuple, list)) and len(rates) == 3:
                rates = dict(zip(("input", "cached_input", "output"), rates))
            if not isinstance(rates, dict):
                raise ValueError("Per-model overrides must be a rate mapping or three prices")
            self.prices.setdefault(name, {}).update(rates)
        for name, rates in self.prices.items():
            for key in ("input", "cached_input", "output"):
                value = rates.get(key)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"Invalid {key} price for {name}")
            rates.setdefault("cache_write", rates["input"])
            rates.setdefault("min_cacheable_tokens", 1024)
            rates.setdefault("cache_ttl_steps", 10)
            if any(not isinstance(rates[key], (int, float)) or rates[key] < 0
                   for key in ("cache_write", "min_cacheable_tokens", "cache_ttl_steps")):
                raise ValueError(f"Invalid cache metadata for {name}")

    def cost(self, model: str, usage) -> tuple[float, dict[str, float]]:
        values = {key: getattr(usage, key, 0) if not isinstance(usage, dict) else usage.get(key, 0)
                  for key in ("input", "cached_input", "output", "cache_write")}
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values.values()):
            raise ValueError("Token counts must be nonnegative integers")
        if values["cached_input"] > values["input"] or values["cache_write"] > values["input"] - values["cached_input"]:
            raise ValueError("Cached/write tokens must be subsets of input")
        rates = self.prices[model]
        # Written tokens use the write rate instead of the ordinary input rate.
        ordinary = values["input"] - values["cached_input"] - values["cache_write"]
        breakdown = {
            "uncached": ordinary * rates["input"] / 1_000_000,
            "cached": values["cached_input"] * rates["cached_input"] / 1_000_000,
            "cache_write": values["cache_write"] * rates["cache_write"] / 1_000_000,
            "output": values["output"] * rates["output"] / 1_000_000,
        }
        return sum(breakdown.values()), breakdown

    def breakeven_compaction(self, model: str, prefix_tokens_invalidated: int,
                             tokens_saved_per_step: int, remaining_steps: int) -> dict:
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0
               for v in (prefix_tokens_invalidated, tokens_saved_per_step, remaining_steps)):
            raise ValueError("Token and step counts must be nonnegative integers")
        r = self.prices[model]
        # Re-sending replaces a cached read and may incur a write premium.
        invalidation = prefix_tokens_invalidated * (r["input"] - r["cached_input"] +
                                                     max(0, r["cache_write"] - r["input"])) / 1_000_000
        saving = tokens_saved_per_step * remaining_steps * r["cached_input"] / 1_000_000
        net = saving - invalidation
        return {"should_compact": net > 0, "net_saving_usd": net}

    def prices_hash(self) -> str:
        canonical = json.dumps(self.prices, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


def prices_hash(path: str | Path | None = None) -> str:
    return CostModel(path=path).prices_hash()


def cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    from .clients.base import Usage
    return CostModel().cost(model, Usage(input_tokens, cached_tokens, output_tokens))[0]
