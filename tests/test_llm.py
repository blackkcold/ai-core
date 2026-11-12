import io
import json
import os
import unittest
from unittest.mock import patch

from aicore.errors import BudgetExceeded, MissingCredential, InvalidRequest
from aicore.llm import ChatGateway, _build_request, _stream_objects, validate_chat
from aicore.store import Store


class MockTransport:
    def __init__(self):
        self.calls = []
    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if "/messages" in url:
            return {"content": [{"type": "text", "text": "Hi Claude"}],
                    "usage": {"input_tokens": 4, "output_tokens": 6},
                    "stop_reason": "end_turn"}
        if ":generateContent" in url:
            return {"candidates": [{"content": {"parts": [{"text": "Hi Gemini"}]}}],
                    "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 8}}
        if "/api/chat" in url:
            return {"message": {"content": "Hi Ollama"},
                    "prompt_eval_count": 3, "eval_count": 7}
        return {"id": "sample", "choices": [{"message": {"content": "Hi OpenAI"},
                                              "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 5}}
    def open(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if "/api/chat" in url:
            return io.BytesIO(b'{"message":{"content":"A"},"done":false}\n{"message":{"content":"B"},"done":true,"prompt_eval_count":3,"eval_count":2}\n')
        return io.BytesIO(b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                          b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n'
                          b'data: [DONE]\n\n')


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.transport = MockTransport()
        self.gateway = ChatGateway(self.store, self.transport, daily_limit=3)
        self.raw = {"provider": "deepseek", "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "Hello"}]}

    def tearDown(self):
        self.store.close()

    def test_paid_calls_default_blocked(self):
        g = ChatGateway(self.store, self.transport)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}):
            with self.assertRaises(BudgetExceeded):
                g.chat(self.raw)
        self.assertEqual(len(self.transport.calls), 0)

    def test_openai_compatible(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}):
            result = self.gateway.chat(self.raw)
        self.assertEqual(result["choices"][0]["message"]["content"], "Hi OpenAI")
        self.assertEqual(result["usage"]["total_tokens"], 7)
        self.assertTrue(self.transport.calls[0][1].endswith("/chat/completions"))
        self.assertEqual(self.store.llm_usage()[0]["calls"], 1)

    def test_anthropic(self):
        raw = {"provider": "anthropic", "model": "claude-test",
               "messages": [{"role": "system", "content": "Be concise"},
                            {"role": "user", "content": "Hello"}], "max_tokens": 100}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake"}):
            result = self.gateway.chat(raw)
        self.assertEqual(result["choices"][0]["message"]["content"], "Hi Claude")
        self.assertEqual(self.transport.calls[0][2]["headers"]["x-api-key"], "fake")
        self.assertEqual(self.transport.calls[0][2]["body"]["system"], "Be concise")

    def test_gemini_native(self):
        raw = {"provider": "gemini", "model": "gemini-2.5-flash",
               "messages": [{"role": "user", "content": "Hello"}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
            result = self.gateway.chat(raw)
        self.assertEqual(result["usage"]["completion_tokens"], 8)

    def test_ollama_local(self):
        raw = {"provider": "ollama-local", "model": "llama3.2:latest",
               "messages": [{"role": "user", "content": "Hello"}]}
        result = self.gateway.chat(raw)
        self.assertEqual(result["choices"][0]["message"]["content"], "Hi Ollama")

    def test_missing_key_is_rejected_before_request(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(MissingCredential):
                self.gateway.chat(self.raw)
        self.assertFalse(self.transport.calls)

    def test_openai_stream_is_normalized(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}):
            chunks = list(self.gateway.stream({**self.raw, "stream": True}))
        self.assertEqual(chunks[0]["choices"][0]["delta"]["role"], "assistant")
        self.assertEqual(chunks[1]["choices"][0]["delta"]["content"], "Hello")
        self.assertEqual(chunks[-1]["usage"]["completion_tokens"], 2)

    def test_ollama_stream_ndjson(self):
        raw = {"provider": "ollama-local", "model": "llama3.2",
               "messages": [{"role": "user", "content": "Hello"}]}
        chunks = list(self.gateway.stream(raw))
        self.assertTrue(any(c.get("choices") and c["choices"][0]["delta"].get("content") == "B"
                            for c in chunks))

    def test_validations(self):
        for change in ({"max_tokens": 100000}, {"model": "../evil?key=x"},
                       {"messages": []}, {"temperature": float("nan")}):
            with self.assertRaises(InvalidRequest):
                validate_chat({**self.raw, **change})

    def test_tool_calls_are_inert_data(self):
        transport = self.transport
        def result(*args, **kwargs):
            return {"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "web_search",
                                                              "arguments": '{"query":"hello"}'}}]},
                                 "finish_reason": "tool_calls"}]}
        transport.request_json = result
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}):
            reply = self.gateway.chat({**self.raw, "tools": [{"type": "function",
                "function": {"name": "web_search", "parameters": {"type": "object"}}}]})
        self.assertEqual(reply["choices"][0]["message"]["tool_calls"][0]["id"], "c1")



    def test_global_budget_cannot_be_bypassed_by_switching_provider(self):
        gateway = ChatGateway(self.store, self.transport, daily_limit=1)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake", "ANTHROPIC_API_KEY": "fake"}):
            gateway.chat(self.raw)
            with self.assertRaises(BudgetExceeded):
                gateway.chat({"provider": "anthropic", "model": "claude-test",
                              "messages": [{"role": "user", "content": "hello"}]})

    def test_anthropic_stream_tool_arguments_are_openai_style(self):
        import io
        stream = io.BytesIO(
            b'event: content_block_start\n'
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"t1","name":"web_search"}}\n\n'
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"query\\":\\"hi\\"}"}}\n\n'
        )
        chunks = list(_stream_objects("anthropic", stream))
        self.assertEqual(chunks[0]["delta"]["tool_calls"][0]["id"], "t1")
        self.assertEqual(chunks[1]["delta"]["tool_calls"][0]["function"]["arguments"], '{"query":"hi"}')

    def test_gemini_tool_result_resolves_call_id(self):
        from aicore.llm import _gemini_messages
        system, contents = _gemini_messages([
            {"role": "user", "content": "search"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call1", "function": {"name": "web_search", "arguments": '{"query":"test"}'}}]},
            {"role": "tool", "tool_call_id": "call1", "content": "results"},
        ])
        self.assertEqual(contents[-1]["parts"][0]["functionResponse"]["name"], "web_search")

if __name__ == "__main__":
    unittest.main()
