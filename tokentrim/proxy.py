"""Minimal loopback OpenAI-compatible proxy; request bodies are never logged."""
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json

from .pruner import ContextItem
from .router import Step


def make_server(host="127.0.0.1", port=0, upstream=None, middleware_factory=None, *, allow_remote=False):
    try:
        if not ipaddress.ip_address(host).is_loopback and not allow_remote:
            raise ValueError("Refusing non-loopback bind without allow_remote=True")
    except ValueError:
        if host != "localhost" or allow_remote:
            raise
    if upstream is None or middleware_factory is None:
        raise ValueError("upstream and middleware_factory are required")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _json(self, status, value, mode=None):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            if mode:
                self.send_header("x-tokentrim-mode", mode)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self._json(404, {"error": "not found"})
                return
            try:
                size = int(self.headers.get("content-length", "0"))
                if size <= 0 or size > 10_000_000:
                    raise ValueError("invalid body size")
                payload = json.loads(self.rfile.read(size))
                messages = payload["messages"]
                if not isinstance(messages, list):
                    raise ValueError("messages must be a list")
                mode = payload.get("metadata", {}).get("tokentrim_mode", "tokentrim")
                items = []
                for index, message in enumerate(messages):
                    role, content = message["role"], message["content"]
                    if role == "system":
                        items.append(ContextItem(f"m-{index}", "system", content, index, pinned=True, role=role))
                    elif role in {"tool", "function"}:
                        items.append(ContextItem(f"m-{index}", "tool_output", content, index, role=role))
                    else:
                        items.append(ContextItem(f"m-{index}", "message", content, index, role=role))
                middleware = middleware_factory(upstream)
                response, record = middleware.complete(items, Step("unknown"),
                    max_tokens=int(payload.get("max_tokens", 256)), mode=mode)
                self._json(200, {"id": "chatcmpl-tokentrim-simulation", "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": response.text},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": response.usage.input,
                              "completion_tokens": response.usage.output,
                              "total_tokens": response.usage.input + response.usage.output,
                              "prompt_tokens_details": {"cached_tokens": response.usage.cached_input}},
                    "x_tokentrim": {"routing_reason": record.decision.reason, "dollars": record.dollars,
                                    "fail_open": record.fail_open, "data_kind": "SIMULATION"}}, mode)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": {"type": type(exc).__name__}})
            except Exception as exc:
                self._json(500, {"error": {"type": type(exc).__name__}})

    return ThreadingHTTPServer((host, port), Handler)
