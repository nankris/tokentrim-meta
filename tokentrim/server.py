"""HTTP adapters for a shared TokenTrim gateway; upstream streaming is buffered."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit
import uuid

from .adapters.anthropic import messages_to_chat, chat_to_messages_response, messages_sse
from .adapters.openai_sse import chat_sse
from .gateway import Gateway, GatewayConfig
from .guard import SpendCapExceeded
from .ledger import SpendLedger
from .upstream import ChatUpstream, MockChatUpstream

DEFAULT_MODEL = "muse-spark-1.3-contributor"


def make_server(gateway_factory, host="127.0.0.1", port=0, log=print,
                default_model=DEFAULT_MODEL):
    gateway = gateway_factory()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Never log incoming headers or arbitrary request text.

        def send_body(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, value):
            self.send_body(status, json.dumps(value).encode())

        def handle_request(self):
            path = urlsplit(self.path).path
            model, usage, dollars, explanations = "-", {}, 0, []
            # Unknown paths are deliberately omitted from logs (they may contain secrets).
            route = path if path in {"/health", "/v1/models", "/v1/messages",
                                    "/v1/messages/count_tokens", "/v1/chat/completions"} else "<unknown>"
            try:
                if self.command == "GET":
                    if path == "/health":
                        self.send_json(200, {"ok": True})
                    elif path == "/v1/models":
                        self.send_json(200, {"object": "list", "data": [
                            {"id": default_model, "object": "model"}]})
                    else:
                        self.send_json(404, {"error": {"type": "not_found"}})
                    return
                if route not in {"/v1/messages", "/v1/messages/count_tokens", "/v1/chat/completions"}:
                    self.send_json(404, {"error": {"type": "not_found"}})
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0:
                    raise ValueError("missing body")
                raw = self.rfile.read(size).decode("utf-8")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("body must be an object")
                if path == "/v1/messages/count_tokens":
                    self.send_json(200, {"input_tokens": len(raw) // 4})
                    return
                payload = {k: v for k, v in payload.items() if not k.startswith("tokentrim_")}
                streaming = payload.pop("stream", False)
                options = payload.pop("stream_options", None) or {}
                if not isinstance(options, dict) or not isinstance(payload["messages"], list):
                    raise ValueError("invalid request")
                requested_model = payload.get("model", default_model)
                if not isinstance(requested_model, str):
                    raise ValueError("model must be a string")
                model = default_model if requested_model.startswith("claude") else requested_model
                payload["model"] = model
                anthropic = path == "/v1/messages"
                chat = messages_to_chat(payload) if anthropic else payload
                with lock:
                    response, report = gateway.complete(
                        chat, conversation_id=self.headers.get("X-TokenTrim-Conversation"))
                usage, explanations = response.get("usage", {}), report.explanations
                dollars = response.get("x_tokentrim", {}).get("usd", 0)
                result = chat_to_messages_response(response, requested_model) if anthropic else response
                if streaming:
                    events = messages_sse(result) if anthropic else chat_sse(
                        result, bool(options.get("include_usage")))
                    self.send_body(200, b"".join(events), "text/event-stream")
                else:
                    self.send_json(200, result)
            except SpendCapExceeded as exc:
                self.send_json(402, {"error": {"type": "spend_cap", "message": str(exc)}})
            except (KeyError, ValueError) as exc:
                self.send_json(400, {"error": {"type": type(exc).__name__}})
            except Exception as exc:
                self.send_json(502, {"error": {"type": type(exc).__name__}})
            finally:
                if log:
                    safe_model = json.dumps(model, ensure_ascii=True)
                    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                    log(f"[tokentrim] {self.command} {route} model={safe_model} "
                        f"prompt={usage.get('prompt_tokens', 0)} cached={cached} "
                        f"out={usage.get('completion_tokens', 0)} ${dollars:.6f} ")
                    for explanation in explanations:
                        for line in explanation.splitlines():
                            log("[tokentrim]   " + line)

        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--upstream-base-url")
    parser.add_argument("--default-model", default=DEFAULT_MODEL)
    parser.add_argument("--ledger", default="/workspace/tokentrim-work/spend_ledger.json")
    parser.add_argument("--job-cap-usd", type=float, default=12)
    parser.add_argument("--run-cap-usd", type=float, default=0.25)
    parser.add_argument("--mock", action="store_true")
    for flag in ("tool-output", "schema-router", "history", "lean-skill", "no-cache-prefix"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args(argv)
    config = GatewayConfig(tool_output=args.tool_output, schema_router=args.schema_router,
                           history=args.history, lean_skill=args.lean_skill,
                           cache_prefix=not args.no_cache_prefix)
    if args.mock:
        upstream = MockChatUpstream()
    else:
        ledger = SpendLedger(args.ledger, args.job_cap_usd, args.run_cap_usd, uuid.uuid4().hex)
        upstream = ChatUpstream(base_url=args.upstream_base_url, ledger=ledger)
    server = make_server(lambda: Gateway(upstream, config), args.host, args.port,
                         default_model=args.default_model)
    print(f"TokenTrim proxy on http://{args.host}:{server.server_port} "
          f"(upstream {getattr(upstream, 'base_url', 'MOCK')})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
