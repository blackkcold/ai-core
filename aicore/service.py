"""Opt-in HTTP API with project authentication and bounded requests."""
from __future__ import annotations

import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .errors import CoreError, InvalidRequest
from .generator import generate_setup
from .llm import ChatGateway
from .models import ModelCatalog
from .openapi import spec as openapi_spec
from .metadata import ReferenceCatalog
from .registry import list_providers
from .search import SearchRouter, list_search_providers
from .settings import Settings
from .free import free_catalog
from .store import Store
from .webfetch import fetch_page

MAX_BODY = 256_000
TENANT_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


class _Unauthorized(Exception):
    pass


class Service:
    def __init__(self, settings: Settings, store: Store | None = None,
                 *, transport=None, fetcher=None):
        self.settings = settings
        self.store = store or Store(str(settings.resolved_db))
        self.search = SearchRouter(settings, self.store, transport)
        self.models = ModelCatalog(self.store, transport, timeout=settings.timeout_seconds)
        self.reference = ReferenceCatalog(self.store, transport)
        self.chat = ChatGateway(self.store, transport,
                                timeout=max(settings.timeout_seconds, 60),
                                daily_limit=settings.llm_daily_limit,
                                free_cloud_daily_limit=settings.free_cloud_daily_limit)
        self.fetcher = fetcher or fetch_page

    def serve(self):
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AICore/1.0.0"

            def log_message(self, fmt, *args):
                return  # never log keys, URLs, request bodies or user queries

            def _cors(self):
                origin = self.headers.get("Origin", "")
                if origin and origin in service.settings.allowed_origins:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")

            def _json(self, status: int, payload: dict):
                data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self._cors()
                self.end_headers()
                self.wfile.write(data)

            def _error(self, exc):
                if isinstance(exc, CoreError):
                    self._json(exc.status, {"error": {"code": exc.code, "message": str(exc)}})
                elif isinstance(exc, (KeyError, ValueError, TypeError)):
                    self._json(422, {"error": {"code": "invalid_request", "message": "invalid input"}})
                else:
                    self._json(500, {"error": {"code": "internal_error", "message": "internal error"}})

            def _tenant(self):
                cfg = service.settings
                token = self.headers.get("X-AI-Core-Token", "")
                bearer = self.headers.get("Authorization", "")
                if bearer.startswith("Bearer "):
                    token = bearer[7:]
                if not cfg.token and not cfg.project_tokens:
                    # Settings prevents public binding without credentials.
                    tenant = self.headers.get("X-AI-Core-Project", "local")
                elif cfg.token and hmac.compare_digest(token, cfg.token):
                    tenant = self.headers.get("X-AI-Core-Project", "admin")
                else:
                    tenant = next((name for name, secret in cfg.project_tokens.items()
                                   if hmac.compare_digest(token, secret)), "")
                if not tenant:
                    raise _Unauthorized()
                if not TENANT_RE.fullmatch(tenant):
                    raise InvalidRequest("invalid project ID")
                return tenant

            def _params(self):
                parts = urlsplit(self.path)
                return parts.path.rstrip("/") or "/", parse_qs(parts.query)

            def _body(self):
                length = self.headers.get("Content-Length", "")
                if not length.isdigit() or not 0 <= int(length) <= MAX_BODY:
                    raise InvalidRequest("Content-Length missing or greater than 256 kB")
                try:
                    data = json.loads(self.rfile.read(int(length)).decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    raise InvalidRequest("invalid JSON body") from None
                if not isinstance(data, dict):
                    raise InvalidRequest("JSON body must be an object")
                return data

            def do_OPTIONS(self):
                if self.headers.get("Origin", "") not in service.settings.allowed_origins:
                    self._json(403, {"error": {"code": "cors_rejected", "message": "origin not allowed"}})
                    return
                self.send_response(204)
                self._cors()
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers",
                                 "Authorization, Content-Type, X-AI-Core-Token, X-AI-Core-Project")
                self.send_header("Access-Control-Max-Age", "3600")
                self.end_headers()

            def do_GET(self):
                try:
                    path, params = self._params()
                    if path == "/healthz":
                        self._json(200, {"ok": True, "version": "1.0.0"})
                        return
                    tenant = self._tenant()
                    if path == "/":
                        data = {"name": "AI Core", "version": "1.0.0",
                                "docs": "/openapi.json"}
                    elif path == "/openapi.json":
                        data = openapi_spec()
                    elif path == "/v1/providers":
                        data = {"providers": [p.public() for p in list_providers()]}
                    elif path == "/v1/search/providers":
                        data = {"providers": [{
                            **spec, "enabled": spec["id"] in service.settings.search_enabled,
                            "has_key": bool(os.getenv(spec["env"], "").strip()),
                            "metered_allowed": service.settings.search_allow_metered,
                            "local_daily_limit": service.settings.search_daily_limits.get(spec["id"]),
                            **service.store.quota_snapshot(spec["id"])}
                            for spec in list_search_providers()]}
                    elif path == "/v1/models/reference":
                        provider = (params.get("provider") or [""])[0]
                        data = service.reference.list(provider, refresh=(params.get("refresh") == ["1"]))
                    elif path == "/v1/models":
                        provider = (params.get("provider") or [None])[0]
                        if provider:
                            data = service.models.list(provider,
                                refresh=(params.get("refresh") == ["1"]), tenant=tenant)
                        else:
                            data = {"providers": [{"id": p.id, "models_url": p.models_url,
                                "discovery": "api" if p.models_url else "manual"} for p in list_providers()]}
                    elif path == "/v1/free/models":
                        data = free_catalog(service.chat.transport)
                    elif path == "/v1/usage":
                        data = {"search": [x for x in service.store.usage(tenant)
                                           if not x["provider"].startswith("llm:")],
                                "llm": service.store.llm_usage(tenant)}
                    elif path.startswith("/v1/providers/") and path.endswith("/setup"):
                        provider = path.removeprefix("/v1/providers/").removesuffix("/setup").strip("/")
                        data = generate_setup(
                            provider, language=(params.get("language") or ["python"])[0],
                            model=(params.get("model") or ["REPLACE_WITH_MODEL_ID"])[0],
                            mode=(params.get("mode") or ["core"])[0])
                    else:
                        self._json(404, {"error": {"code": "not_found", "message": "endpoint not found"}})
                        return
                    self._json(200, data)
                except _Unauthorized:
                    self._json(401, {"error": {"code": "unauthorized", "message": "invalid or missing token"}})
                except Exception as exc:
                    self._error(exc)

            def do_POST(self):
                try:
                    tenant = self._tenant()
                    path, _ = self._params()
                    body = self._body()
                    if path == "/v1/tools/web_search":
                        result = service.search.search(body, tenant)
                    elif path == "/v1/tools/web_fetch":
                        if not isinstance(body.get("url"), str):
                            raise InvalidRequest("url must be a string")
                        result = service.fetcher(body["url"])
                    elif path == "/v1/chat/completions":
                        if body.get("stream") is True:
                            self._stream(body, tenant)
                            return
                        result = service.chat.chat(body, tenant=tenant)
                    elif path.startswith("/v1/connections/") and path.endswith("/test"):
                        provider = path.removeprefix("/v1/connections/").removesuffix("/test").strip("/")
                        discovery = service.models.list(provider, refresh=True, tenant=tenant)
                        result = {"provider": provider, "discovery": discovery["source"],
                                  "models_discovered": len(discovery["models"])}
                    else:
                        self._json(404, {"error": {"code": "not_found", "message": "endpoint not found"}})
                        return
                    self._json(200, result)
                except _Unauthorized:
                    self._json(401, {"error": {"code": "unauthorized", "message": "invalid or missing token"}})
                except Exception as exc:
                    self._error(exc)

            def _stream(self, body, tenant):
                iterator = service.chat.stream(body, tenant=tenant)
                try:
                    first = next(iterator)  # validates auth and upstream before 200
                except StopIteration:
                    raise InvalidRequest("empty upstream stream") from None
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self._cors()
                self.end_headers()
                def send(item):
                    chunk = json.dumps(item, ensure_ascii=False).encode("utf-8")
                    self.wfile.write(b"data: " + chunk + b"\n\n")
                    self.wfile.flush()
                try:
                    send(first)
                    for event in iterator:
                        send(event)
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except OSError:
                    pass
                except CoreError as exc:
                    try:
                        send({"error": {"code": exc.code, "message": str(exc)}})
                    except OSError:
                        pass
                finally:
                    iterator.close()
                    self.close_connection = True

        return ThreadingHTTPServer((self.settings.host, self.settings.port), Handler)

    def run(self):
        server = self.serve()
        try:
            server.serve_forever(poll_interval=0.25)
        finally:
            server.server_close()
            self.store.close()
