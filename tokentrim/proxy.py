"""Minimal loopback OpenAI-compatible ``/v1/chat/completions`` proxy; request bodies are never logged.

Run against any OpenAI-compatible upstream (default: the Meta Model API)::

    set -a; . ~/.config/meta/env; set +a        # provides META_API_KEY (never printed)
    python3 -m tokentrim.proxy --port 8787 --upstream-base-url https://api.meta.ai/v1

then point a standard OpenAI client at ``http://127.0.0.1:8787/v1``. The proxy authenticates to
the upstream with its own key (``TOKENTRIM_UPSTREAM_API_KEY``, else ``META_API_KEY``/``MODEL_API_KEY``);
the client's Authorization header is ignored and never forwarded.

Scope (prototype): text ``messages`` (string or text-part content), ``model``, ``max_tokens`` /
``max_completion_tokens``. ``tools``/``tool_choice``, streaming, images and sampling parameters are
NOT forwarded; requests that set ``stream: true`` or ``tools`` are rejected with HTTP 400 rather
than silently changed. Anthropic Messages and OpenAI Responses APIs are planned, not built.
"""
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
                if payload.get("stream") or payload.get("tools") or payload.get("functions"):
                    self._json(400, {"error": {"type": "unsupported", "message":
                        "TokenTrim proxy prototype does not support stream/tools yet"}})
                    return
                mode = payload.get("metadata", {}).get("tokentrim_mode", "tokentrim")
                items = []
                for index, message in enumerate(messages):
                    role, content = message["role"], message["content"]
                    if isinstance(content, list):  # OpenAI text content parts
                        content = "".join(part.get("text", "") for part in content
                                          if isinstance(part, dict) and part.get("type") == "text")
                    if not isinstance(content, str):
                        raise ValueError("message content must be text")
                    if role == "system":
                        items.append(ContextItem(f"m-{index}", "system", content, index, pinned=True, role=role))
                    elif role in {"tool", "function"}:
                        items.append(ContextItem(f"m-{index}", "tool_output", content, index, role=role))
                    else:
                        items.append(ContextItem(f"m-{index}", "message", content, index, role=role))
                if mode not in {"baseline", "tokentrim"}:
                    raise ValueError("unknown tokentrim_mode")
                model = payload.get("model")
                middleware = middleware_factory(upstream, model) if _takes_model(middleware_factory) \
                    else middleware_factory(upstream)
                max_tokens = int(payload.get("max_completion_tokens") or payload.get("max_tokens") or 1024)
                response, record = middleware.complete(items, Step("unknown"), max_tokens=max_tokens, mode=mode)
                meta = dict(getattr(upstream, "last_meta", {}) or {})
                self._json(200, {"id": "chatcmpl-tokentrim-" + str(meta.get("request_id") or "local"),
                    "object": "chat.completion", "model": record.decision.model.split("/", 1)[-1],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": response.text},
                                 "finish_reason": meta.get("finish_reason") or "stop"}],
                    "usage": {"prompt_tokens": response.usage.input,
                              "completion_tokens": response.usage.output,
                              "total_tokens": response.usage.input + response.usage.output,
                              "prompt_tokens_details": {"cached_tokens": response.usage.cached_input}},
                    "x_tokentrim": {"routing_reason": record.decision.reason, "dollars": record.dollars,
                                    "fail_open": record.fail_open,
                                    "data_kind": getattr(upstream, "data_kind", "REAL upstream")}}, mode)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": {"type": type(exc).__name__}})
            except Exception as exc:
                status = 402 if type(exc).__name__ == "SpendCapExceeded" else 502
                self._json(status, {"error": {"type": type(exc).__name__}})

    return ThreadingHTTPServer((host, port), Handler)


def _takes_model(factory) -> bool:
    import inspect
    try:
        return len(inspect.signature(factory).parameters) >= 2
    except (TypeError, ValueError):
        return False


def main(argv=None):
    import argparse
    from .clients.meta import MetaModelClient
    from .guard import SpendGuard
    from .middleware import TokenTrim
    from .router import HeuristicRouter
    parser = argparse.ArgumentParser(description="TokenTrim loopback OpenAI-compatible proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--upstream-base-url", default=None,
                        help="OpenAI-compatible base URL (default $TOKENTRIM_UPSTREAM_BASE_URL, "
                             "$META_API_BASE_URL or https://api.meta.ai/v1)")
    parser.add_argument("--default-model", default="meta/muse-spark-1.3")
    parser.add_argument("--ledger", default=None, help="persisted SpendGuard ledger path")
    parser.add_argument("--global-cap-usd", type=float, default=1.0)
    parser.add_argument("--per-request-cap-usd", type=float, default=0.25)
    args = parser.parse_args(argv)
    import os
    upstream = MetaModelClient(base_url=args.upstream_base_url or os.environ.get("TOKENTRIM_UPSTREAM_BASE_URL"))
    guard = SpendGuard(per_task_usd=args.per_request_cap_usd, global_usd=args.global_cap_usd,
                       ledger_path=args.ledger, max_steps=10**9)

    def factory(client, model=None):
        name = model or args.default_model
        if "/" not in name:
            name = "meta/" + name  # price-table names are "meta/<api id>"
        guard.start_task("proxy-request")
        return TokenTrim(client, token_budget=200_000, strong_model=name, guard=guard,
                         router=HeuristicRouter(name, name), savers={"prune", "trim", "cache_layout"})

    server = make_server(args.host, args.port, upstream, factory)
    print(f"TokenTrim proxy on http://{args.host}:{server.server_port}/v1 -> {upstream.base_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
