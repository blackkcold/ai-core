import http.client
import io
import json
import os
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from aicore.service import Service
from aicore.settings import Settings
from aicore.store import Store


class FakeTransport:
    def open(self, *args, **kwargs):
        return io.BytesIO(b'data: {"choices":[{"delta":{"content":"works"}}]}\n\n'
                          b'data: [DONE]\n\n')
    def request_json(self, *args, **kwargs):
        return {"data": []}


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        cfg = replace(Settings(), host="127.0.0.1", port=0, token="X" * 32,
                      llm_daily_limit=2, search_enabled=())
        self.service = Service(cfg, self.store, transport=FakeTransport(),
                               fetcher=lambda url: {"url": url, "text": "ok"})
        self.server = self.service.serve()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.store.close()

    def call(self, method, path, body=None, authenticated=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + "X" * 32
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                     headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode()
        code = resp.status
        conn.close()
        return code, data

    def test_health_unauthenticated(self):
        status, data = self.call("GET", "/healthz", authenticated=False)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])

    def test_protected_endpoints(self):
        status, _ = self.call("GET", "/v1/providers", authenticated=False)
        self.assertEqual(status, 401)
        status, data = self.call("GET", "/v1/providers")
        self.assertEqual(status, 200)
        self.assertGreater(len(json.loads(data)["providers"]), 10)

    def test_model_manual_state(self):
        status, data = self.call("GET", "/v1/models?provider=glm")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["source"], "manual_required")

    def test_setup_endpoint(self):
        status, data = self.call("GET", "/v1/providers/deepseek/setup?language=typescript")
        self.assertEqual(status, 200)
        self.assertIn("fetch(", json.loads(data)["code"])

    def test_fetch_route(self):
        status, data = self.call("POST", "/v1/tools/web_fetch", {"url": "https://example.org/"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["text"], "ok")

    def test_search_disabled(self):
        status, _ = self.call("POST", "/v1/tools/web_search", {"query": "hello"})
        self.assertEqual(status, 503)

    def test_malformed_request(self):
        status, data = self.call("POST", "/v1/chat/completions", {"provider": "deepseek"})
        self.assertIn(status, (400, 422))
        self.assertIn("error", json.loads(data))

    def test_streaming_sse(self):
        raw = {"provider": "deepseek", "model": "deepseek-chat", "stream": True,
               "messages": [{"role": "user", "content": "Hi"}]}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}):
            status, data = self.call("POST", "/v1/chat/completions", raw)
        self.assertEqual(status, 200)
        self.assertIn('data: [DONE]', data)
        self.assertIn('works', data)


if __name__ == "__main__":
    unittest.main()
