"""Cheap estimates, not provider billing counts. Inject a tokenizer if needed."""
from typing import Callable

TokenEstimator = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4
