"""Offline provider-cache SIMULATION and secret-free JSONL recording helpers."""
from dataclasses import asdict
import json
from pathlib import Path

from .base import ModelResponse, Usage
from ..tokens import estimate_tokens


class MockProviderClient:
    """SIMULATION: exact message-boundary prefix cache with block rounding and TTL."""
    def __init__(self, responder=None, *, cache_block_tokens=128, min_cacheable_tokens=1024,
                 ttl_steps=10, charges_cache_write=False, estimator=estimate_tokens):
        self.responder = responder or (lambda messages, model: ("SIMULATION deterministic response", 8))
        self.cache_block_tokens = cache_block_tokens
        self.min_cacheable_tokens = min_cacheable_tokens
        self.ttl_steps = ttl_steps
        self.charges_cache_write = charges_cache_write
        self.estimator = estimator
        self.step = 0
        self._cache = {}

    def complete(self, messages, model, max_tokens):
        if max_tokens < 0:
            raise ValueError("max_tokens must be nonnegative")
        self.step += 1
        total = sum(self.estimator(m["content"]) for m in messages)
        cached = 0
        old = self._cache.get(model)
        if old and self.step - old[2] <= self.ttl_steps:
            common = 0
            for current, previous in zip(messages, old[0]):
                if current != previous:
                    break
                common += self.estimator(current["content"])
            cached = common - common % self.cache_block_tokens if self.cache_block_tokens else common
            if cached < self.min_cacheable_tokens:
                cached = 0
        cacheable = total - total % self.cache_block_tokens if self.cache_block_tokens else total
        can_store = cacheable >= self.min_cacheable_tokens
        write = max(0, cacheable - cached) if can_store and self.charges_cache_write else 0
        if can_store:
            self._cache[model] = ([dict(m) for m in messages], cacheable, self.step)
        text, output = self.responder(messages, model)
        return ModelResponse(text, Usage(total, min(cached, total), min(max_tokens, output), write))


class RecordedClient:
    def __init__(self, path):
        self.rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        self.index = 0

    def complete(self, messages, model, max_tokens):
        if self.index >= len(self.rows):
            raise IndexError("Recording exhausted")
        row = self.rows[self.index]
        if row.get("step_index", row.get("step", self.index)) != self.index:
            raise ValueError("Recording step mismatch")
        self.index += 1
        return ModelResponse(row["text"], Usage(**row["usage"]))


class RecordingClient:
    def __init__(self, inner, path):
        self.inner, self.path, self.step = inner, Path(path), 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def complete(self, messages, model, max_tokens):
        response = self.inner.complete(messages, model, max_tokens)
        row = {"step_index": self.step, "model": model, "text": response.text, "usage": asdict(response.usage)}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
        self.step += 1
        return response
