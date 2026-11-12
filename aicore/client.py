"""Dependency-free Python client for the optional AI Core HTTP gateway."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class AICoreClient:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 project: str | None = None, timeout: int = 90):
        self.base_url = (base_url or os.getenv("AI_CORE_URL", "http://127.0.0.1:8765")).rstrip("/")
        self.token = token if token is not None else os.getenv("AI_CORE_TOKEN", "")
        self.project = project
        self.timeout = timeout

    def _send(self, path: str, data: dict | None = None):
        if not path.startswith("/v1/"):
            raise ValueError("only versioned /v1 routes are allowed")
        url = self.base_url + path
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.project:
            headers["X-AI-Core-Project"] = self.project
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                         headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise RuntimeError("AI Core returned HTTP " + str(status)) from None

    def providers(self):
        return self._send("/v1/providers")

    def search_providers(self):
        return self._send("/v1/search/providers")

    def models(self, provider: str, refresh: bool = False):
        query = urllib.parse.urlencode({"provider": provider, "refresh": "1" if refresh else "0"})
        return self._send("/v1/models?" + query)

    def search(self, query: str, *, limit: int = 6, provider: str | None = None, mode="free-first"):
        body = {"query": query, "limit": limit, "mode": mode}
        if provider:
            body["provider"] = provider
        return self._send("/v1/tools/web_search", body)

    def fetch(self, url: str):
        return self._send("/v1/tools/web_fetch", {"url": url})

    def chat(self, provider: str, model: str, messages: list[dict], **kwargs):
        return self._send("/v1/chat/completions", {
            "provider": provider, "model": model, "messages": messages, **kwargs})

    def usage(self):
        return self._send("/v1/usage")
