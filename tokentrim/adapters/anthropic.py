"""Pure translations between Anthropic Messages and OpenAI Chat Completions."""
import copy
import json


def _text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError("content must be text or a list of blocks")
    return "".join("[image omitted]" if b["type"] == "image" else b.get("text", "")
                   for b in content if b["type"] in {"text", "image"})


def messages_to_chat(payload: dict) -> dict:
    result = {k: copy.deepcopy(payload[k]) for k in
              ("model", "max_tokens", "temperature", "top_p") if k in payload}
    if "stop_sequences" in payload:
        result["stop"] = copy.deepcopy(payload["stop_sequences"])
    messages = []
    if "system" in payload:
        messages.append({"role": "system", "content": _text(payload["system"])})
    for message in payload["messages"]:
        role, content = message["role"], message["content"]
        text = _text(content)
        calls, results = [], []
        for block in content if isinstance(content, list) else []:
            if role == "assistant" and block["type"] == "tool_use":
                calls.append({"id": block["id"], "type": "function", "function": {
                    "name": block["name"], "arguments": json.dumps(block["input"], sort_keys=False)}})
            elif role == "user" and block["type"] == "tool_result":
                results.append({"role": "tool", "tool_call_id": block["tool_use_id"],
                                "content": ("ERROR: " if block.get("is_error") else "")
                                + _text(block.get("content", ""))})
        messages.extend(results)
        if text or calls or not results:
            translated = {"role": role, "content": text}
            if calls:
                translated["tool_calls"] = calls
            messages.append(translated)
    result["messages"] = messages
    if "tools" in payload:
        result["tools"] = [{"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": copy.deepcopy(t["input_schema"])}} for t in payload["tools"]]
    if "tool_choice" in payload:
        choice = payload["tool_choice"]
        kind = choice if isinstance(choice, str) else choice["type"]
        result["tool_choice"] = ({"type": "function", "function": {"name": choice["name"]}}
                                 if kind == "tool" else {"auto": "auto", "any": "required",
                                                        "none": "none"}[kind])
    return result


def chat_to_messages_response(resp: dict, model: str) -> dict:
    choice = resp["choices"][0]
    message, content = choice["message"], []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for call in message.get("tool_calls") or []:
        function = call["function"]
        try:
            arguments = json.loads(function["arguments"])
        except (ValueError, TypeError):
            arguments = {}
        content.append({"type": "tool_use", "id": call["id"],
                        "name": function["name"], "input": arguments})
    usage = resp.get("usage") or {}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    ident = str(resp.get("id", "local"))
    result = {"id": ident if ident.startswith("msg_") else "msg_" + ident,
              "type": "message", "role": "assistant", "model": model, "content": content,
              "stop_reason": {"stop": "end_turn", "length": "max_tokens",
                              "tool_calls": "tool_use"}.get(choice.get("finish_reason"), "end_turn"),
              "stop_sequence": None,
              "usage": {"input_tokens": usage.get("prompt_tokens", 0) - cached,
                        "cache_read_input_tokens": cached, "cache_creation_input_tokens": 0,
                        "output_tokens": usage.get("completion_tokens", 0)}}
    if "x_tokentrim" in resp:
        result["x_tokentrim"] = copy.deepcopy(resp["x_tokentrim"])
    return result


def messages_sse(msg: dict) -> list[bytes]:
    events = []

    def emit(kind, **data):
        events.append(f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n".encode())

    start = copy.deepcopy(msg)
    start["content"] = []
    start["stop_reason"] = start["stop_sequence"] = None
    start["usage"]["output_tokens"] = 0
    emit("message_start", message=start)
    emit("ping")
    for index, block in enumerate(msg["content"]):
        initial = dict(block)
        if block["type"] == "text":
            initial["text"] = ""
            delta = {"type": "text_delta", "text": block["text"]}
        else:
            initial["input"] = {}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        emit("content_block_start", index=index, content_block=initial)
        emit("content_block_delta", index=index, delta=delta)
        emit("content_block_stop", index=index)
    emit("message_delta", delta={"stop_reason": msg["stop_reason"],
                                 "stop_sequence": msg["stop_sequence"]},
         usage={"output_tokens": msg["usage"]["output_tokens"]})
    emit("message_stop")
    return events
