"""Native/OpenAI-compatible chat adapter with tools and normalized SSE streams.

Only pre-registered providers may be addressed. No autonomous tool execution.
A returned tool call is inert data until a calling application authorizes it.
All billable chat calls require an explicit model name and a configured key.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from urllib.parse import quote

from .errors import InvalidRequest, MissingCredential, ProviderUnavailable
from .models import credential_headers
from .registry import get_provider
from .store import Store
from .transport import Transport

MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9_./:+-]{1,180}$")
MAX_REQUEST_BYTES = 256_000
MAX_STREAM_BYTES = 8_000_000


def validate_chat(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise InvalidRequest("chat request must be an object")
    provider, model = raw.get("provider"), raw.get("model")
    if not isinstance(provider, str) or not isinstance(model, str) or not MODEL_PATTERN.fullmatch(model):
        raise InvalidRequest("provider and exact model ID are required")
    messages = raw.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 80:
        raise InvalidRequest("messages must contain 1..80 entries")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {
                "system", "developer", "user", "assistant", "tool"}:
            raise InvalidRequest("invalid message role")
        if not isinstance(message.get("content", ""), (str, list, type(None))):
            raise InvalidRequest("invalid message content")
    max_tokens = raw.get("max_tokens", 1024)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 8192:
        raise InvalidRequest("max_tokens must be 1..8192")
    if "temperature" in raw and (isinstance(raw["temperature"], bool) or
                                 not isinstance(raw["temperature"], (int, float)) or
                                 not 0 <= raw["temperature"] <= 2):
        raise InvalidRequest("temperature must be 0..2")
    if "tools" in raw and (not isinstance(raw["tools"], list) or len(raw["tools"]) > 32):
        raise InvalidRequest("tools must contain no more than 32 definitions")
    if type(raw.get("stream", False)) is not bool:
        raise InvalidRequest("stream must be boolean")
    try:
        encoded = json.dumps(raw, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise InvalidRequest("invalid chat JSON") from None
    if len(encoded) > MAX_REQUEST_BYTES:
        raise InvalidRequest("chat payload exceeds 256 kB")
    return raw


def _anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system, converted = [], []
    for msg in messages:
        role = msg["role"]
        if role in {"system", "developer"}:
            if not isinstance(msg.get("content"), str):
                raise InvalidRequest("Anthropic system messages must be strings")
            system.append(msg["content"])
        elif role == "tool":
            call_id = msg.get("tool_call_id")
            if not isinstance(call_id, str):
                raise InvalidRequest("Anthropic tool results need tool_call_id")
            converted.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": call_id,
                "content": str(msg.get("content") or "")}]})
        elif role in {"user", "assistant"}:
            content = msg.get("content") or ""
            if not isinstance(content, str):
                raise InvalidRequest("Anthropic adapter currently needs text content")
            blocks = [{"type": "text", "text": content}] if content else []
            for call in msg.get("tool_calls", []):
                func = call.get("function") or {}
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except (TypeError, ValueError):
                    raise InvalidRequest("invalid tool arguments") from None
                blocks.append({"type": "tool_use", "id": call["id"],
                               "name": func["name"], "input": args})
            converted.append({"role": role, "content": blocks if blocks else ""})
    return "\n\n".join(system), converted


def _gemini_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system, contents = [], []
    tool_names = {}
    for msg in messages:
        role = msg["role"]
        if role in {"system", "developer"}:
            if not isinstance(msg.get("content"), str):
                raise InvalidRequest("Gemini system messages must be strings")
            system.append(msg["content"])
            continue
        if role == "tool":
            name = msg.get("name") or tool_names.get(msg.get("tool_call_id"))
            if not isinstance(name, str) or not name:
                raise InvalidRequest("Gemini tool result needs name or preceding tool_call_id")
            contents.append({"role": "user", "parts": [{
                "functionResponse": {"name": name,
                                     "response": {"result": msg.get("content") or ""}}}]})
            continue
        if not isinstance(msg.get("content"), (str, type(None))):
            raise InvalidRequest("Gemini adapter currently needs text content")
        parts = [{"text": msg["content"]}] if msg.get("content") else []
        for call in msg.get("tool_calls", []):
            func = call.get("function") or {}
            if call.get("id") and func.get("name"):
                tool_names[call["id"]] = func["name"]
            try:
                args = json.loads(func.get("arguments", "{}"))
            except (TypeError, ValueError):
                raise InvalidRequest("invalid tool arguments") from None
            parts.append({"functionCall": {"name": func.get("name"), "args": args}})
        contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
    return "\n\n".join(system), contents


def _build_request(raw: dict, stream: bool) -> tuple[str, str, dict, dict, str]:
    provider = get_provider(raw["provider"])
    if provider.protocol == "catalog-only":
        raise InvalidRequest("this provider's models require a selected native protocol")
    model, proto = raw["model"], provider.protocol
    region = raw.get("region")
    if region is not None and not isinstance(region, str):
        raise InvalidRequest("region must be a string")
    base = provider.endpoint(region).rstrip("/")
    key = os.getenv(provider.key_env, "").strip() if provider.key_env else ""
    if provider.auth != "none" and not key:
        raise MissingCredential("configure " + provider.key_env + " before calling " + provider.id)
    headers = credential_headers(provider, key)
    messages = raw["messages"]
    maximum = raw.get("max_tokens", 1024)
    if proto == "openai":
        url = base + "/chat/completions"
        body = {"model": model, "messages": messages, "stream": stream}
        if "max_tokens" in raw:
            body["max_tokens"] = maximum
        if "temperature" in raw:
            body["temperature"] = raw["temperature"]
        if "tools" in raw:
            body["tools"] = raw["tools"]
        if "tool_choice" in raw:
            body["tool_choice"] = raw["tool_choice"]
        if stream:
            body["stream_options"] = {"include_usage": True}
        if "reasoning_effort" in raw:
            if not isinstance(raw["reasoning_effort"], str) or raw["reasoning_effort"] not in {
                    "none", "minimal", "low", "medium", "high", "xhigh"}:
                raise InvalidRequest("invalid reasoning_effort")
            body["reasoning_effort"] = raw["reasoning_effort"]
    elif proto == "anthropic":
        url = base + "/messages"
        system, converted = _anthropic_messages(messages)
        body = {"model": model, "messages": converted, "max_tokens": maximum, "stream": stream}
        if system:
            body["system"] = system
        if "temperature" in raw:
            body["temperature"] = raw["temperature"]
        if "tools" in raw:
            body["tools"] = [
                {"name": t["function"]["name"],
                 "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}})}
                for t in raw["tools"]]
    elif proto == "gemini":
        suffix = ":streamGenerateContent?alt=sse" if stream else ":generateContent"
        url = base + "/models/" + quote(model.removeprefix("models/"), safe="") + suffix
        system, contents = _gemini_messages(messages)
        body = {"contents": contents, "generationConfig": {"maxOutputTokens": maximum}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if "temperature" in raw:
            body["generationConfig"]["temperature"] = raw["temperature"]
        if "tools" in raw:
            body["tools"] = [{"functionDeclarations": [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "parameters": t["function"].get("parameters", {"type": "object", "properties": {}})}
                for t in raw["tools"]]}]
    elif proto == "ollama":
        url = base + "/api/chat"
        body = {"model": model, "messages": messages, "stream": stream,
                "options": {"num_predict": maximum}}
        if "temperature" in raw:
            body["options"]["temperature"] = raw["temperature"]
        if "tools" in raw:
            body["tools"] = raw["tools"]
    else:
        raise InvalidRequest("unsupported provider protocol")
    return url, proto, headers, body, model


def _normalized(provider: str, model: str, proto: str, data: dict) -> dict:
    finish = "stop"
    calls = []
    content = ""
    if proto == "openai":
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        calls = msg.get("tool_calls") or []
        finish = choice.get("finish_reason") or "stop"
        usage = data.get("usage") or {}
        inp, out = usage.get("prompt_tokens"), usage.get("completion_tokens")
    elif proto == "anthropic":
        for part in data.get("content") or []:
            if part.get("type") == "text":
                content += part.get("text") or ""
            elif part.get("type") == "tool_use":
                calls.append({"id": part.get("id"), "type": "function",
                              "function": {"name": part.get("name"),
                                           "arguments": json.dumps(part.get("input") or {})}})
        finish = {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length"}.get(
            data.get("stop_reason"), "stop")
        inp = (data.get("usage") or {}).get("input_tokens")
        out = (data.get("usage") or {}).get("output_tokens")
    elif proto == "gemini":
        choices = data.get("candidates") or []
        choice = choices[0] if choices else {}
        for part in (choice.get("content") or {}).get("parts") or []:
            content += part.get("text") or ""
            if part.get("functionCall"):
                fn = part["functionCall"]
                calls.append({"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                              "function": {"name": fn.get("name"),
                                           "arguments": json.dumps(fn.get("args") or {})}})
        finish = "length" if choice.get("finishReason") == "MAX_TOKENS" else "stop"
        usage = data.get("usageMetadata") or {}
        inp, out = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
    elif proto == "ollama":
        msg = data.get("message") or {}
        content, calls = msg.get("content") or "", msg.get("tool_calls") or []
        inp, out = data.get("prompt_eval_count"), data.get("eval_count")
    else:
        raise InvalidRequest("unsupported response protocol")
    message = {"role": "assistant", "content": content, "tool_calls": calls}
    return {"id": data.get("id") or "chatcmpl-" + uuid.uuid4().hex,
            "object": "chat.completion", "provider": provider, "model": model,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if calls and finish == "stop" else finish}],
            "usage": {"prompt_tokens": inp, "completion_tokens": out,
                      "total_tokens": inp + out if isinstance(inp, int) and isinstance(out, int) else None,
                      "known": isinstance(inp, int) and isinstance(out, int)}}


def _stream_objects(proto: str, response):
    """Yield normalized deltas and usage from upstream SSE or NDJSON."""
    received = 0
    event_lines = []
    while True:
        line = response.readline(131073)
        if not line:
            break
        received += len(line)
        if received > MAX_STREAM_BYTES or len(line) > 131072:
            raise ProviderUnavailable("stream exceeds size limit")
        line = line.decode("utf-8", errors="replace").strip()
        if proto == "ollama":
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            msg = obj.get("message") or {}
            if msg.get("content"):
                yield {"delta": {"content": msg["content"]}}
            if msg.get("tool_calls"):
                yield {"delta": {"tool_calls": msg["tool_calls"]}}
            if obj.get("done"):
                yield {"usage": {"prompt_tokens": obj.get("prompt_eval_count"),
                                 "completion_tokens": obj.get("eval_count")}}
            continue
        if line.startswith("data:"):
            event_lines.append(line[5:].strip())
        if line and not line.startswith("data:"):
            continue
        if not event_lines:
            continue
        payload = "\n".join(event_lines)
        event_lines = []
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except ValueError:
            continue
        if proto == "openai":
            for choice in obj.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta:
                    yield {"delta": delta}
                if choice.get("finish_reason"):
                    yield {"finish_reason": choice["finish_reason"]}
            if obj.get("usage"):
                usage = obj["usage"]
                yield {"usage": {"prompt_tokens": usage.get("prompt_tokens"),
                                 "completion_tokens": usage.get("completion_tokens")}}
        elif proto == "anthropic":
            kind = obj.get("type")
            if kind == "content_block_delta":
                delta = obj.get("delta") or {}
                if delta.get("type") == "text_delta":
                    yield {"delta": {"content": delta.get("text") or ""}}
                if delta.get("type") == "input_json_delta":
                    yield {"delta": {"tool_calls": [{"index": obj.get("index", 0),
                        "function": {"arguments": delta.get("partial_json") or ""}}]}}
            elif kind == "content_block_start":
                block = obj.get("content_block") or {}
                if block.get("type") == "tool_use":
                    yield {"delta": {"tool_calls": [{"index": obj.get("index", 0),
                        "id": block.get("id"), "type": "function",
                        "function": {"name": block.get("name"), "arguments": ""}}]}}
            elif kind == "message_start":
                u = (obj.get("message") or {}).get("usage") or {}
                yield {"usage": {"prompt_tokens": u.get("input_tokens"), "completion_tokens": None}}
            elif kind == "message_delta":
                u = obj.get("usage") or {}
                yield {"usage": {"prompt_tokens": None, "completion_tokens": u.get("output_tokens")}}
        elif proto == "gemini":
            for candidate in obj.get("candidates") or []:
                for part in (candidate.get("content") or {}).get("parts") or []:
                    if part.get("text"):
                        yield {"delta": {"content": part["text"]}}
                    if part.get("functionCall"):
                        yield {"delta": {"tool_calls": [{"index": 0, "type": "function",
                            "function": {"name": part["functionCall"].get("name"),
                                         "arguments": json.dumps(part["functionCall"].get("args") or {})}}]}}
            u = obj.get("usageMetadata") or {}
            if u:
                yield {"usage": {"prompt_tokens": u.get("promptTokenCount"),
                                 "completion_tokens": u.get("candidatesTokenCount")}}
    # Consume a final SSE event with no blank-line terminator.
    if event_lines:
        try:
            obj = json.loads("\n".join(event_lines))
            if proto == "openai" and obj.get("usage"):
                yield {"usage": {"prompt_tokens": obj["usage"].get("prompt_tokens"),
                                 "completion_tokens": obj["usage"].get("completion_tokens")}}
        except ValueError:
            pass


class ChatGateway:
    def __init__(self, store: Store, transport: Transport | None = None, *, timeout=60, daily_limit=0):
        self.store, self.transport, self.timeout = store, transport or Transport(), timeout
        self.daily_limit = daily_limit  # explicit opt-in; zero means no billable calls

    def chat(self, data: dict, *, tenant: str = "local") -> dict:
        raw = validate_chat(data)
        url, proto, headers, body, model = _build_request(raw, stream=False)
        provider = raw["provider"]
        ticket = self.store.reserve("llm:global", tenant, self.daily_limit)
        usage = None
        status = "failed"
        try:
            payload = self.transport.request_json("POST", url, headers=headers, body=body, timeout=self.timeout)
            out = _normalized(provider, model, proto, payload)
            usage = out["usage"]
            status = "success"
            return out
        finally:
            self.store.finish(ticket, status)
            self.store.record_llm(tenant, provider, model,
                                  usage.get("prompt_tokens") if usage else None,
                                  usage.get("completion_tokens") if usage else None)

    def stream(self, data: dict, *, tenant: str = "local"):
        raw = validate_chat({**data, "stream": True})
        url, proto, headers, body, model = _build_request(raw, stream=True)
        provider = raw["provider"]
        reply_id = "chatcmpl-" + uuid.uuid4().hex
        counts = {"prompt_tokens": None, "completion_tokens": None}
        def generate():
            ticket = self.store.reserve("llm:global", tenant, self.daily_limit)
            status = "failed"
            try:
                with self.transport.open("POST", url, headers=headers, body=body, timeout=self.timeout) as response:
                    yield {"id": reply_id, "object": "chat.completion.chunk",
                           "provider": provider, "model": model,
                           "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
                    for event in _stream_objects(proto, response):
                        if event.get("usage"):
                            for k, v in event["usage"].items():
                                if isinstance(v, int):
                                    counts[k] = v
                            yield {"id": reply_id, "object": "chat.completion.chunk",
                                   "provider": provider, "model": model,
                                   "choices": [], "usage": dict(counts)}
                        else:
                            yield {"id": reply_id, "object": "chat.completion.chunk",
                                   "provider": provider, "model": model,
                                   "choices": [{"index": 0,
                                               "delta": event.get("delta", {}),
                                               "finish_reason": event.get("finish_reason")}]}
                    status = "success"
            finally:
                self.store.finish(ticket, status)
                self.store.record_llm(tenant, provider, model,
                                      counts["prompt_tokens"], counts["completion_tokens"])
        return generate()
