"""Budget-enforced, rate-limited OpenAI-compatible Chat Completions upstream (Meta API by default).

``ChatUpstream.create(payload)`` sends a full Chat Completions payload (messages, tools, tool_choice,
...) and returns ``(response_json, CallUsage)``. Before every metered call it reserves the worst-case
cost (conservative prompt estimate + ``max_tokens`` at the output rate) on a ``SpendLedger`` and refuses
to send if a cap could be exceeded. The API key is read from the environment, never logged or stored.

``MockChatUpstream`` is a deterministic offline stand-in with an exact-prefix cache model; it is used
by all tests and dry runs (zero spend).
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
import random
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .cost import CostModel
from .guard import LedgerUnavailable
from .clients.base import Usage

DEFAULT_BASE_URL = "https://api.meta.ai/v1"


class UpstreamError(RuntimeError):
    """Never contains the API key."""


@dataclass
class CallUsage:
    model: str
    prompt_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    finish_reason: str | None = None
    latency_s: float = 0.0
    usd: float = 0.0
    usd_uncached: float = 0.0
    usd_cached: float = 0.0
    usd_cache_write: float = 0.0
    usd_output: float = 0.0
    retries: int = 0
    data_kind: str = "REAL"
    over_reservation: bool = False

    @property
    def uncached_tokens(self) -> int:
        return self.prompt_tokens - self.cached_tokens - self.cache_write_tokens

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uncached_tokens"] = self.uncached_tokens
        d["truncated"] = self.truncated
        return d


def usage_from_openai(data: dict) -> tuple[int, int, int, int, int]:
    """(prompt, cached, cache_write, completion, reasoning) from an OpenAI-style ``usage`` object.
    On Meta, prompt_tokens INCLUDES cached_tokens and completion_tokens INCLUDES reasoning_tokens."""
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = min(int(details.get("cached_tokens") or 0), prompt)
    write = int(details.get("cache_write_tokens") or details.get("cache_creation_tokens") or 0)
    write = max(0, min(write, prompt - cached))
    completion = int(usage.get("completion_tokens") or 0)
    reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    return prompt, cached, write, completion, reasoning


def price_name(model: str) -> str:
    return model if "/" in model else "meta/" + model


class RateLimiter:
    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm else 0.0
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self):
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next_at)
            self.next_at = at + self.interval
        if at > now:
            time.sleep(at - now)


class _Base:
    data_kind = "REAL"
    metered = True  # every non-mock upstream must have a ledger (fail closed)

    def __init__(self, ledger=None, cost_model: CostModel | None = None, default_max_tokens: int = 16000,
                 max_tokens_ceiling: int = 32000):
        self.ledger = ledger
        self.cost_model = cost_model or CostModel()
        self.default_max_tokens = default_max_tokens
        self.max_tokens_ceiling = max_tokens_ceiling

    def _prepare(self, payload: dict) -> tuple[dict, str, float]:
        payload = dict(payload)
        payload.pop("stream", None)
        payload.pop("stream_options", None)
        mt = payload.pop("max_completion_tokens", None) or payload.get("max_tokens") or self.default_max_tokens
        payload["max_tokens"] = min(int(mt), self.max_tokens_ceiling)
        model = price_name(payload["model"])
        payload["model"] = model.split("/", 1)[1] if model.startswith("meta/") else payload["model"]
        rates = self.cost_model.prices[model]
        est_prompt = len(json.dumps(payload)) // 3 + 64  # conservative: ~3 chars per token
        worst = (est_prompt * rates["input"] + payload["max_tokens"] * rates["output"]) / 1e6
        return payload, model, worst

    def _price(self, model, data, latency, retries) -> CallUsage:
        prompt, cached, write, completion, reasoning = usage_from_openai(data)
        usd, parts = self.cost_model.cost(model, Usage(prompt, cached, completion, write))
        choice = (data.get("choices") or [{}])[0]
        return CallUsage(model, prompt, cached, write, completion, reasoning, choice.get("finish_reason"),
                         round(latency, 3), usd, parts["uncached"], parts["cached"], parts["cache_write"],
                         parts["output"], retries, self.data_kind)

    def create(self, payload: dict, note: str = "") -> tuple[dict, CallUsage]:
        payload, model, worst = self._prepare(payload)
        if self.ledger is None and self.metered:  # fail closed: never send an unreserved metered call
            raise LedgerUnavailable("no spend ledger configured for a metered upstream; refusing to send")
        # Reservation is held across all retries of this call; worst case = one billed attempt.
        token = self.ledger.reserve(worst) if self.ledger else None
        t0 = time.monotonic()
        try:
            data, retries = self._send(payload)
        except BaseException:
            if self.ledger:
                self.ledger.release(token)
            raise
        usage = self._price(model, data, time.monotonic() - t0, retries)
        if usage.usd > worst:
            usage.over_reservation = True
        if self.ledger:
            self.ledger.commit(token, usage.usd, note)
        return data, usage


class ChatUpstream(_Base):
    def __init__(self, base_url: str | None = None, ledger=None, rpm: float = 120, timeout: float = 300,
                 max_retries: int = 5, **kw):
        super().__init__(ledger=ledger, **kw)
        self.base_url = (base_url or os.environ.get("TOKENTRIM_UPSTREAM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        parsed = urlparse(self.base_url)
        loopback = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if not (self.base_url.startswith("https://") or loopback):
            raise ValueError("upstream base URL must use HTTPS (plain HTTP only for loopback)")
        self._key = (os.environ.get("TOKENTRIM_UPSTREAM_API_KEY") or os.environ.get("META_API_KEY") or "")
        if not self._key:
            raise ValueError("ChatUpstream requires META_API_KEY (or TOKENTRIM_UPSTREAM_API_KEY)")
        self.limiter = RateLimiter(rpm)
        self.timeout, self.max_retries = timeout, max_retries
        if loopback:
            self.data_kind = "LOCAL upstream"

    def __repr__(self):
        return f"ChatUpstream(base_url={self.base_url!r})"

    def _send(self, payload: dict) -> tuple[dict, int]:
        body = json.dumps(payload).encode()
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            request = Request(self.base_url + "/chat/completions", data=body, method="POST",
                              headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._key})
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.load(response), attempt
            except HTTPError as error:
                text = error.read(400).decode("utf-8", "replace").replace(self._key, "***")
                if not (error.code == 429 or error.code >= 500) or attempt == self.max_retries:
                    raise UpstreamError(f"HTTP {error.code}: {text}") from None
                ra = error.headers.get("Retry-After") if error.headers else None
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else delay
            except (URLError, TimeoutError) as error:
                if attempt == self.max_retries:
                    raise UpstreamError(f"transport error: {type(error).__name__}") from None
                wait = delay
            time.sleep(wait + random.uniform(0, 0.5))
            delay = min(delay * 2, 60)
        raise UpstreamError("unreachable")


class MockChatUpstream(_Base):
    """SIMULATION: deterministic responder + exact-prefix cache (128-token blocks, >=1024 tokens).

    ``responder(payload) -> message dict`` (default: echo a short text). Usage is estimated at
    4 chars/token. Records every payload in ``self.calls`` for assertions."""
    data_kind = "MOCK"
    metered = False

    def __init__(self, responder=None, ledger=None, block=128, min_cacheable=1024, **kw):
        super().__init__(ledger=ledger, **kw)
        self.responder = responder or (lambda payload: {"role": "assistant", "content": "MOCK reply"})
        self.block, self.min_cacheable = block, min_cacheable
        self.calls: list[dict] = []
        self._prefixes: set[str] = set()
        self.lock = threading.Lock()

    def _send(self, payload: dict) -> tuple[dict, int]:
        with self.lock:
            self.calls.append(payload)
            head = json.dumps({"tools": payload.get("tools"), "model": payload["model"]}, sort_keys=True)
            pieces = [head] + [json.dumps(m, sort_keys=True) for m in payload["messages"]]
            text = "".join(pieces)
            total = (len(text) + 3) // 4
            cached = 0
            acc = ""
            for piece in pieces:
                acc += piece
                key = hashlib.sha256(acc.encode()).hexdigest()
                if key in self._prefixes:
                    cached = (len(acc) + 3) // 4
                self._prefixes.add(key)
            cached -= cached % self.block
            if cached < self.min_cacheable:
                cached = 0
        message = self.responder(payload)
        out_text = (message.get("content") or "") + json.dumps(message.get("tool_calls") or "")
        completion = min(payload["max_tokens"], (len(out_text) + 3) // 4 + 5)
        finish = "tool_calls" if message.get("tool_calls") else "stop"
        return {"id": "mock", "object": "chat.completion", "model": payload["model"],
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                "usage": {"prompt_tokens": total, "completion_tokens": completion,
                          "total_tokens": total + completion,
                          "prompt_tokens_details": {"cached_tokens": min(cached, total)}}}, 0
