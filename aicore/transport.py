"""Small, dependency-free JSON transport. No redirects; bounded responses.

The transport is injectable, so adapters can be contract tested without real
keys or live requests. Upstream response bodies are never included in errors.
"""
from __future__ import annotations

import json
import gzip
import io
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import InvalidRequest, ProviderUnavailable, UpstreamError

MAX_RESPONSE_BYTES = 2_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self):
        self._opener = urllib.request.build_opener(_NoRedirect())

    def open(self, method: str, url: str, *, headers: dict | None = None,
             body: dict | None = None, timeout: int = 20):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise InvalidRequest("invalid upstream URL")
        if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise InvalidRequest("plaintext upstream requests must stay on loopback")
        if parts.username or parts.password:
            raise InvalidRequest("upstream URL must not contain credentials")
        data = None
        request_headers = {"Accept": "application/json",
                           "User-Agent": "ai-core/1.1 (+https://github.com/blackkcold/ai-core)",
                           **(headers or {})}
        if body is not None:
            try:
                data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise InvalidRequest("invalid JSON request payload") from exc
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            return self._opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            retry = min(3600, max(0, int(retry_after))) if retry_after.isdigit() else None
            exc.close()
            raise UpstreamError(exc.code, retry_after=retry) from None
        except (socket.timeout, TimeoutError, urllib.error.URLError, OSError):
            raise ProviderUnavailable("upstream connection failed") from None

    def request_json(self, method: str, url: str, *, headers: dict | None = None,
                     body: dict | None = None, timeout: int = 20, max_bytes: int = MAX_RESPONSE_BYTES) -> dict:
        with self.open(method, url, headers=headers, body=body, timeout=timeout) as response:
            if not 1 <= max_bytes <= 24_000_000:
                raise InvalidRequest("invalid upstream response size budget")
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise InvalidRequest("upstream response exceeds configured size budget")
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                        payload = stream.read(max_bytes + 1)
                except (OSError, EOFError):
                    raise ProviderUnavailable("invalid compressed upstream JSON") from None
                if len(payload) > max_bytes:
                    raise InvalidRequest("decompressed upstream JSON exceeds size budget")
            try:
                result = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise ProviderUnavailable("upstream returned invalid JSON") from None
            if not isinstance(result, dict):
                raise ProviderUnavailable("upstream returned non-object JSON")
            return result
