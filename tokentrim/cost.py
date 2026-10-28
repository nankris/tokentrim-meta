"""Billing estimates: input includes its cached subset."""
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


def cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    for count in (input_tokens, cached_tokens, output_tokens):
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("Token counts must be nonnegative integers")
    if cached_tokens > input_tokens:
        raise ValueError("Cached tokens cannot exceed input tokens")
    rates = load_prices()[model]
    return ((input_tokens - cached_tokens) * rates["input"] + cached_tokens * rates["cached_input"]
            + output_tokens * rates["output"]) / 1_000_000
