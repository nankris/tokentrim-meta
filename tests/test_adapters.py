"""Offline translations and loopback HTTP integration tests for the proxy adapters."""
import copy
from http.client import HTTPConnection
import json
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from tokentrim.adapters.anthropic import (
    messages_to_chat, chat_to_messages_response, messages_sse,
)
from tokentrim.adapters.openai_sse import chat_sse
from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.ledger import SpendLedger
from tokentrim.server import DEFAULT_MODEL, main, make_server
from tokentrim.upstream import MockChatUpstream


def response(text="hello", calls=None, finish="stop"):
    return {"id": "chatcmpl-test", "model": DEFAULT_MODEL, "created": 123,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text,
                                                  "tool_calls": calls or []},
                         "finish_reason": finish}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                      "prompt_tokens_details": {"cached_tokens": 30}},
            "x_tokentrim": {"usd": 0.01}}


def tool_call(arguments='{"b": 2, "a": 1}'):
    return {"id": "call_1", "type": "function", "function": {
        "name": "lookup", "arguments": arguments}}


def events(body):
    return [json.loads(line[6:]) for line in body.decode().splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"]


class TranslationTests(unittest.TestCase):
    def test_text_system_and_options(self):
        payload = {"model": "claude-example", "system": [
            {"type": "text", "text": "first", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "second"}],
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "hello"}, {"type": "image", "source": {}}]}],
            "max_tokens": 20, "temperature": 0.5, "top_p": 0.9, "stop_sequences": ["END"],
            "metadata": {}, "thinking": {}, "cache_control": {}}
        before = copy.deepcopy(payload)
        chat = messages_to_chat(payload)
        self.assertEqual(chat["messages"], [{"role": "system", "content": "firstsecond"},
                                            {"role": "user", "content": "hello[image omitted]"}])
        self.assertEqual(chat["stop"], ["END"])
        for key in ("model", "max_tokens", "temperature", "top_p"):
            self.assertEqual(chat[key], payload[key])
        self.assertFalse({"metadata", "thinking", "cache_control"} & chat.keys())
        self.assertEqual(payload, before)
        payload["system"] = "plain system"
        self.assertEqual(messages_to_chat(payload)["messages"][0]["content"], "plain system")
        msg = chat_to_messages_response(response(), payload["model"])
        self.assertEqual(msg["content"], [{"type": "text", "text": "hello"}])
        self.assertEqual(msg["model"], payload["model"])
        self.assertEqual(msg["usage"], {"input_tokens": 70, "cache_read_input_tokens": 30,
                                       "cache_creation_input_tokens": 0, "output_tokens": 10})
        self.assertTrue(msg["id"].startswith("msg_"))
        self.assertEqual(msg["x_tokentrim"], {"usd": 0.01})

    def test_tools_round_trip_and_result_order(self):
        payload = {"messages": [
            {"role": "assistant", "content": [{"type": "text", "text": "Looking"},
                {"type": "tool_use", "id": "call_1", "name": "lookup", "input": {"b": 2, "a": 1}}]},
            {"role": "user", "content": [{"type": "text", "text": "continue"},
                {"type": "tool_result", "tool_use_id": "call_1", "content": [
                    {"type": "text", "text": "failed"}], "is_error": True}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_2",
                                           "content": "ok"}]}],
            "tools": [{"name": "lookup", "description": "Find it", "input_schema": {"type": "object"}}]}
        chat = messages_to_chat(payload)
        self.assertEqual(chat["messages"][0]["tool_calls"], [tool_call()])
        self.assertEqual(chat["messages"][1], {"role": "tool", "tool_call_id": "call_1",
                                               "content": "ERROR: failed"})
        self.assertEqual(chat["messages"][2], {"role": "user", "content": "continue"})
        self.assertEqual(chat["messages"][3]["content"], "ok")
        self.assertEqual(len(chat["messages"]), 4)
        self.assertEqual(chat["tools"], [{"type": "function", "function": {
            "name": "lookup", "description": "Find it", "parameters": {"type": "object"}}}])
        msg = chat_to_messages_response(response("Looking", [tool_call()], "tool_calls"), "claude")
        self.assertEqual(msg["content"], payload["messages"][0]["content"])
        self.assertEqual(msg["stop_reason"], "tool_use")

    def test_tool_choices_and_finish_reasons(self):
        for choice, expected in [({"type": "auto"}, "auto"), ({"type": "any"}, "required"),
                                 ("none", "none"), ({"type": "none"}, "none"),
                                 ({"type": "tool", "name": "lookup"},
                                  {"type": "function", "function": {"name": "lookup"}})]:
            with self.subTest(choice=choice):
                self.assertEqual(messages_to_chat({"messages": [], "tool_choice": choice})[
                    "tool_choice"], expected)
        for finish, expected in [("stop", "end_turn"), ("length", "max_tokens"),
                                 ("tool_calls", "tool_use")]:
            self.assertEqual(chat_to_messages_response(response(finish=finish), "m")[
                "stop_reason"], expected)
        msg = chat_to_messages_response(response(None, [tool_call("invalid")]), "m")
        self.assertEqual(msg["content"][0]["input"], {})
        self.assertEqual(len(msg["content"]), 1)

    def test_anthropic_sse(self):
        msg = chat_to_messages_response(response("hello", [tool_call()], "tool_calls"), "m")
        before = copy.deepcopy(msg)
        frames = messages_sse(msg)
        data = events(b"".join(frames))
        self.assertEqual([e["type"] for e in data], ["message_start", "ping",
            "content_block_start", "content_block_delta", "content_block_stop",
            "content_block_start", "content_block_delta", "content_block_stop",
            "message_delta", "message_stop"])
        for frame, event in zip(frames, data):
            self.assertTrue(frame.startswith(f"event: {event['type']}\ndata: ".encode()))
            self.assertTrue(frame.endswith(b"\n\n"))
        self.assertEqual(data[0]["message"]["content"], [])
        self.assertEqual(data[0]["message"]["usage"]["output_tokens"], 0)
        self.assertIsNone(data[0]["message"]["stop_reason"])
        self.assertEqual(data[3]["delta"], {"type": "text_delta", "text": "hello"})
        self.assertEqual(data[5]["content_block"]["input"], {})
        self.assertEqual(json.loads(data[6]["delta"]["partial_json"]), {"b": 2, "a": 1})
        self.assertEqual(data[-2]["usage"], {"output_tokens": 10})
        self.assertEqual(data[-2]["delta"]["stop_reason"], "tool_use")
        self.assertEqual(msg, before)

    def test_openai_sse(self):
        resp = response("a" * 451, [tool_call(), {**tool_call(), "id": "call_2"}], "tool_calls")
        for include in (False, True):
            with self.subTest(include_usage=include):
                frames = chat_sse(resp, include)
                self.assertEqual(frames[-1], b"data: [DONE]\n\n")
                data = events(b"".join(frames))
                self.assertEqual(data[0]["choices"][0]["delta"], {"role": "assistant", "content": ""})
                self.assertEqual([len(d["choices"][0]["delta"]["content"]) for d in data[1:4]],
                                 [200, 200, 51])
                self.assertEqual(data[4]["choices"][0]["delta"]["tool_calls"][0],
                                 {"index": 0, **tool_call()})
                self.assertEqual(data[5]["choices"][0]["delta"]["tool_calls"][0]["index"], 1)
                final = data[-2] if include else data[-1]
                self.assertEqual(final["choices"][0]["finish_reason"], "tool_calls")
                self.assertTrue(all(d["object"] == "chat.completion.chunk" for d in data))
                if include:
                    self.assertEqual(data[-1]["choices"], [])
                    self.assertEqual(data[-1]["usage"], resp["usage"])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.upstream = MockChatUpstream()
        self.gateway = Gateway(self.upstream, GatewayConfig(cache_prefix=False))
        self.factory = Mock(return_value=self.gateway)
        self.logs = []
        self.server = make_server(self.factory, log=self.logs.append)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, path, payload=None, headers=None, raw=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            body = raw if raw is not None else json.dumps(payload) if payload is not None else None
            conn.request("POST" if body is not None else "GET", path, body=body,
                         headers=headers or {})
            resp = conn.getresponse()
            return resp.status, resp.getheader("Content-Type"), resp.read()
        finally:
            conn.close()

    def payload(self, **kwargs):
        return {"model": DEFAULT_MODEL, "messages": [{"role": "user", "content": "hi"}], **kwargs}

    def test_plain_chat_and_shared_gateway(self):
        original = self.gateway.complete
        with patch.object(self.gateway, "complete", wraps=original) as complete:
            for _ in range(2):
                status, _, body = self.request("/v1/chat/completions", self.payload(tokentrim_unknown=1),
                    {"X-TokenTrim-Conversation": "same", "Authorization": "Bearer SECRET"})
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["choices"][0]["message"]["content"], "MOCK reply")
            self.assertEqual(complete.call_args.kwargs["conversation_id"], "same")
        self.factory.assert_called_once_with()
        self.assertEqual(len(self.upstream.calls), 2)
        self.assertNotIn("tokentrim_unknown", self.upstream.calls[0])
        self.assertNotIn("SECRET", "".join(self.logs))

    def test_tool_calls_and_model_mapping(self):
        self.upstream.responder = lambda _: {"role": "assistant", "content": None,
                                              "tool_calls": [tool_call()]}
        for path in ("/v1/chat/completions", "/v1/messages?beta=true"):
            status, _, body = self.request(path, self.payload(model="claude-example"),
                {"x-api-key": "SECRET", "anthropic-version": "SECRET"})
            self.assertEqual(status, 200, body)
            data = json.loads(body)
            if "messages" in path:
                self.assertEqual(data["content"][0]["input"], {"b": 2, "a": 1})
                self.assertEqual(data["stop_reason"], "tool_use")
                self.assertEqual(data["model"], "claude-example")
            else:
                self.assertEqual(data["choices"][0]["message"]["tool_calls"], [tool_call()])
            self.assertEqual(self.upstream.calls[-1]["model"], DEFAULT_MODEL)
        self.assertNotIn("SECRET", "".join(self.logs))

    def test_streaming_endpoints(self):
        for path in ("/v1/chat/completions", "/v1/messages"):
            status, content_type, body = self.request(path, self.payload(
                stream=True, stream_options={"include_usage": True}))
            self.assertEqual(status, 200, body)
            self.assertEqual(content_type, "text/event-stream")
            data = events(body)
            if "messages" in path:
                self.assertEqual(data[0]["type"], "message_start")
                self.assertEqual(data[-1]["type"], "message_stop")
            else:
                self.assertEqual(data[-1]["choices"], [])
                self.assertIn("prompt_tokens", data[-1]["usage"])
                self.assertTrue(body.endswith(b"data: [DONE]\n\n"))
            self.assertNotIn("stream", self.upstream.calls[-1])

    def test_cap_rejected_before_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.upstream.ledger = SpendLedger(Path(tmp) / "ledger.json", 1e-12, 1e-12, "test")
            for path in ("/v1/chat/completions", "/v1/messages"):
                status, _, body = self.request(path, self.payload(stream=True))
                self.assertEqual(status, 402, body)
                self.assertEqual(json.loads(body)["error"]["type"], "spend_cap")
            self.assertEqual(self.upstream.calls, [])

    def test_health_models_count_and_errors(self):
        self.assertEqual(json.loads(self.request("/health")[2]), {"ok": True})
        self.assertEqual(json.loads(self.request("/v1/models")[2])["data"][0]["id"], DEFAULT_MODEL)
        raw = json.dumps(self.payload())
        self.assertEqual(json.loads(self.request("/v1/messages/count_tokens?beta=true", raw=raw)[2]),
                         {"input_tokens": len(raw) // 4})
        for raw in ("{", "[]", "{}", '{"messages": 3}'):
            self.assertEqual(self.request("/v1/messages", raw=raw)[0], 400)
        self.assertEqual(self.request("/missing")[0], 404)
        with patch.object(self.gateway, "complete", side_effect=RuntimeError("SECRET")):
            status, _, body = self.request("/v1/messages", self.payload())
            self.assertEqual(status, 502)
            self.assertEqual(json.loads(body), {"error": {"type": "RuntimeError"}})
        self.assertNotIn("SECRET", "".join(self.logs))


class HandlerTests(unittest.TestCase):
    """Exercise HTTP framing without sockets, independently of gateway transforms."""
    def test_routes_errors_and_logging(self):
        logs = []
        gateway = Mock()
        gateway.complete.return_value = (response(), Mock(explanations=["saved prefix"]))
        with patch("tokentrim.server.ThreadingHTTPServer") as server_class:
            make_server(lambda: gateway, log=logs.append)
            handler_class = server_class.call_args.args[1]

        def request(path, payload, method="POST"):
            raw = json.dumps(payload).encode()
            handler = object.__new__(handler_class)
            handler.rfile = BytesIO(raw)
            handler.wfile = BytesIO()
            handler.headers = {"Content-Length": str(len(raw)), "Authorization": "SECRET",
                               "X-TokenTrim-Conversation": "conversation"}
            handler.command, handler.path = method, path
            handler.request_version = "HTTP/1.1"
            handler.requestline = method + " " + path + " HTTP/1.1"
            handler.handle_request()
            headers, body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
            return int(headers.split()[1]), body

        payload = {"model": "claude-example", "messages": [], "tokentrim_extra": True}
        status, body = request("/v1/messages?beta=true", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["model"], "claude-example")
        sent = gateway.complete.call_args
        self.assertEqual(sent.args[0], {"model": DEFAULT_MODEL, "messages": []})
        self.assertEqual(sent.kwargs["conversation_id"], "conversation")
        for path in ("/v1/messages", "/v1/chat/completions"):
            status, body = request(path, {**payload, "stream": True})
            self.assertEqual(status, 200)
            self.assertTrue(events(body))
        self.assertIn("[tokentrim]   saved prefix", logs)
        self.assertNotIn("SECRET", "".join(logs))
        from tokentrim.guard import SpendCapExceeded
        for exception, status in [(SpendCapExceeded("cap"), 402), (ValueError("SECRET"), 400),
                                  (KeyError("SECRET"), 400), (RuntimeError("SECRET"), 502)]:
            gateway.complete.side_effect = exception
            actual, body = request("/v1/messages", payload)
            self.assertEqual(actual, status)
            self.assertNotIn(b"SECRET", body)


class CLITests(unittest.TestCase):
    def test_mock_configuration(self):
        server = Mock(server_port=8787)
        server.serve_forever.side_effect = KeyboardInterrupt
        with patch("tokentrim.server.make_server", return_value=server) as make, \
                patch("tokentrim.server.SpendLedger") as ledger, patch("builtins.print"):
            main(["--mock", "--tool-output", "--schema-router", "--history", "--lean-skill",
                  "--no-cache-prefix"])
            gateway = make.call_args.args[0]()
        ledger.assert_not_called()
        self.assertIsInstance(gateway.upstream, MockChatUpstream)
        self.assertIsNone(gateway.upstream.ledger)
        self.assertTrue(all(getattr(gateway.config, k) for k in
                            ("tool_output", "schema_router", "history", "lean_skill")))
        self.assertFalse(gateway.config.cache_prefix)
        server.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
