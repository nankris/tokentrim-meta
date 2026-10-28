"""Opt-in transport stub. Never used by the offline benchmark."""
import json
import os
from urllib.request import Request, urlopen

from .base import ModelResponse, Usage


class MetaModelClient:
    def __init__(self, timeout: float = 60):
        self.base_url = os.environ.get("META_API_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("META_API_KEY", "")
        if not self.base_url or not self.api_key:
            raise ValueError("MetaModelClient requires META_API_BASE_URL and META_API_KEY")
        if not self.base_url.startswith("https://"):
            raise ValueError("META_API_BASE_URL must use HTTPS")
        self.timeout = timeout

    def complete(self, messages: list[dict[str, str]], model: str, max_tokens: int) -> ModelResponse:
        payload = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens}).encode()
        request = Request(self.base_url + "/chat/completions", data=payload,
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key})
        with urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        usage = data["usage"]
        return ModelResponse(data["choices"][0]["message"]["content"],
                             Usage(usage["prompt_tokens"],
                                   (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                                   usage["completion_tokens"]))
