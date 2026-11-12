"""MCP JSON-RPC stdio server (newline-delimited UTF-8 JSON messages).

Tools are explicit and inert: web search, web fetch and model chat do not
execute any returned model tool calls. All runtime secrets stay server-side.
"""
from __future__ import annotations

import json
import sys

from .errors import CoreError, InvalidRequest
from .generator import generate_setup
from .registry import list_providers
from .search import list_search_providers
from .service import Service
from .settings import Settings


TOOLS = [
    {"name": "web_search", "description": "Search the web with configured provider quotas and source citations.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20},
         "recency": {"type": "string"}, "provider": {"type": "string"},
         "mode": {"type": "string", "enum": ["free-first", "deep"]}},
         "required": ["query"]}},
    {"name": "web_fetch", "description": "Fetch public HTTPS textual page via pinned-DNS safe reader.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "list_providers", "description": "List registered model and search providers.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_models", "description": "Discover available model IDs from a provider API, when supported.",
     "inputSchema": {"type": "object", "properties": {
         "provider": {"type": "string"}, "refresh": {"type": "boolean"}}, "required": ["provider"]}},
    {"name": "list_model_reference", "description": "Opt-in Models.dev community reference metadata; never an account or billing guarantee.",
     "inputSchema": {"type": "object", "properties": {"provider": {"type": "string"}, "refresh": {"type": "boolean"}}, "required": ["provider"]}},
    {"name": "chat", "description": "Call a configured model; tool calls in replies are inert data.",
     "inputSchema": {"type": "object", "properties": {
         "provider": {"type": "string"}, "model": {"type": "string"},
         "messages": {"type": "array"}, "max_tokens": {"type": "integer"},
         "tools": {"type": "array"}}, "required": ["provider", "model", "messages"]}},
    {"name": "generate_setup", "description": "Generate connection code for Python, TypeScript, Swift or curl.",
     "inputSchema": {"type": "object", "properties": {
         "provider": {"type": "string"}, "language": {"type": "string"},
         "model": {"type": "string"}, "mode": {"type": "string"}}, "required": ["provider"]}},
]


class MCPServer:
    def __init__(self, service: Service):
        self.service = service

    def call_tool(self, name: str, arguments: dict):
        if not isinstance(arguments, dict):
            raise InvalidRequest("tool arguments must be an object")
        if name == "web_search":
            return self.service.search.search(arguments, tenant="mcp")
        if name == "web_fetch":
            if not isinstance(arguments.get("url"), str):
                raise InvalidRequest("url must be a string")
            return self.service.fetcher(arguments["url"])
        if name == "list_providers":
            return {"models": [p.public() for p in list_providers()],
                    "search": list_search_providers()}
        if name == "list_models":
            return self.service.models.list(arguments["provider"], tenant="mcp",
                                            refresh=arguments.get("refresh") is True)
        if name == "list_model_reference":
            return self.service.reference.list(arguments["provider"], refresh=arguments.get("refresh") is True)
        if name == "chat":
            return self.service.chat.chat({**arguments, "stream": False}, tenant="mcp")
        if name == "generate_setup":
            return generate_setup(arguments["provider"],
                                  language=arguments.get("language", "python"),
                                  model=arguments.get("model", "REPLACE_WITH_MODEL_ID"),
                                  mode=arguments.get("mode", "core"))
        raise InvalidRequest("unknown MCP tool: " + name)

    def handle(self, request: dict):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                    "error": {"code": -32600, "message": "invalid JSON-RPC request"}}
        method = request.get("method")
        ident = request.get("id")
        if "id" not in request:
            return None  # notifications, including notifications/initialized
        try:
            if method == "initialize":
                params = request.get("params") or {}
                version = params.get("protocolVersion", "2025-03-26")
                result = {"protocolVersion": version, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "ai-core", "version": "1.0.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request.get("params") or {}
                value = self.call_tool(params.get("name", ""), params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                          "structuredContent": value, "isError": False}
            else:
                return {"jsonrpc": "2.0", "id": ident,
                        "error": {"code": -32601, "message": "unknown JSON-RPC method"}}
            return {"jsonrpc": "2.0", "id": ident, "result": result}
        except (CoreError, KeyError, TypeError, ValueError) as exc:
            message = str(exc) if isinstance(exc, CoreError) else "invalid parameters"
            if method == "tools/call":
                result = {"content": [{"type": "text", "text": message}], "isError": True}
                return {"jsonrpc": "2.0", "id": ident, "result": result}
            return {"jsonrpc": "2.0", "id": ident,
                    "error": {"code": -32602, "message": message}}
        except Exception:
            return {"jsonrpc": "2.0", "id": ident,
                    "error": {"code": -32603, "message": "internal error"}}


def main():
    service = Service(Settings.from_env())
    mcp = MCPServer(service)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = mcp.handle(request)
            except ValueError:
                response = {"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32700, "message": "parse error"}}
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
    finally:
        service.store.close()


if __name__ == "__main__":
    main()
