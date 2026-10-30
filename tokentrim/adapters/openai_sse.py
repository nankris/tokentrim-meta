"""Render a completed OpenAI response as Chat Completions SSE chunks."""
import json


def chat_sse(resp: dict, include_usage: bool) -> list[bytes]:
    base = {"id": resp["id"], "object": "chat.completion.chunk",
            "created": resp.get("created", 0), "model": resp["model"]}
    events = []

    def emit(choices, **extra):
        chunk = {**base, "choices": choices, **extra}
        if include_usage:
            chunk.setdefault("usage", None)
        events.append(("data: " + json.dumps(chunk) + "\n\n").encode())

    for choice in resp["choices"]:
        index = choice.get("index", 0)

        def delta(value, finish=None):
            emit([{"index": index, "delta": value, "finish_reason": finish}])

        message = choice["message"]
        delta({"role": "assistant", "content": ""})
        text = message.get("content") or ""
        for offset in range(0, len(text), 200):
            delta({"content": text[offset:offset + 200]})
        for tool_index, call in enumerate(message.get("tool_calls") or []):
            delta({"tool_calls": [{"index": tool_index, "id": call["id"],
                                   "type": call["type"], "function": call["function"]}]})
        delta({}, choice.get("finish_reason"))
    if include_usage:
        emit([], usage=resp.get("usage", {}))
    events.append(b"data: [DONE]\n\n")
    return events
