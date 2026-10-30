"""Meta Model API transport (OpenAI-compatible ``/v1/chat/completions``).

Opt-in only: tests and the offline benchmarks never construct it. The API key is read from the
environment (``META_API_KEY``, falling back to ``MODEL_API_KEY``) and is never logged, stored on
disk or included in exceptions. Verified against https://api.meta.ai/v1 on 2026-10-30:

* ``usage.prompt_tokens`` is total input and *includes* ``usage.prompt_tokens_details.cached_tokens``;
* ``usage.completion_tokens`` *includes* ``completion_tokens_details.reasoning_tokens`` (billed as output);
* reasoning tokens count against ``max_tokens``; a small ``max_tokens`` can end with
  ``finish_reason == "length"`` and empty ``content``;
* 429 responses are retried with exponential backoff (``Retry-After`` honoured when present).
"""
import json
import os
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import ModelResponse, Usage

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
MODEL_PREFIX = "meta/"  # price-table names are "meta/<api model id>"


class MetaAPIError(RuntimeError):
    """Non-retryable or exhausted API failure. Never contains the API key."""


def api_model_id(model: str) -> str:
    return model[len(MODEL_PREFIX):] if model.startswith(MODEL_PREFIX) else model


class MetaModelClient:
    def __init__(self, timeout: float = 180, max_retries: int = 5, base_url: str | None = None,
                 sleep=time.sleep):
        self.base_url = (base_url or os.environ.get("META_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        if not self.base_url.startswith("https://"):
            raise ValueError("META_API_BASE_URL must use HTTPS")
        self._api_key = os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY") or ""
        if not self._api_key:
            raise ValueError("MetaModelClient requires META_API_KEY (or MODEL_API_KEY) in the environment")
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep
        self.last_meta: dict = {}

    def __repr__(self):  # never expose the key
        return f"MetaModelClient(base_url={self.base_url!r})"

    def _post(self, payload: bytes) -> dict:
        request = Request(self.base_url + "/chat/completions", data=payload, method="POST",
                          headers={"Content-Type": "application/json",
                                   "Authorization": "Bearer " + self._api_key})
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    self.last_meta = {"request_id": response.headers.get("x-request-id"),
                                      "ratelimit_remaining_requests":
                                          response.headers.get("x-ratelimit-remaining-requests"),
                                      "retries": attempt}
                    return json.load(response)
            except HTTPError as error:
                body = error.read(300).decode("utf-8", "replace")
                retryable = error.code == 429 or error.code >= 500
                if not retryable or attempt == self.max_retries:
                    raise MetaAPIError(f"HTTP {error.code}: {body}") from None
                retry_after = error.headers.get("Retry-After") if error.headers else None
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else delay
            except (URLError, TimeoutError) as error:
                if attempt == self.max_retries:
                    raise MetaAPIError(f"Transport error: {type(error).__name__}") from None
                wait = delay
            self._sleep(wait + random.uniform(0, 0.5))
            delay = min(delay * 2, 60)
        raise MetaAPIError("unreachable")

    @staticmethod
    def parse(data: dict) -> ModelResponse:
        usage = data.get("usage") or {}
        prompt = int(usage.get("prompt_tokens", 0))
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        output = int(usage.get("completion_tokens", 0))
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        return ModelResponse(text, Usage(prompt, min(cached, prompt), output))

    def complete(self, messages: list[dict[str, str]], model: str, max_tokens: int) -> ModelResponse:
        payload = json.dumps({"model": api_model_id(model), "messages": messages,
                              "max_tokens": max_tokens}).encode()
        data = self._post(payload)
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        self.last_meta.update({
            "finish_reason": choice.get("finish_reason"),
            "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
            "served_model": data.get("model")})
        return self.parse(data)
