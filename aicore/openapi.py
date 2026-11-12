"""OpenAPI 3.1 schema for generated integration clients.

All protected routes use bearer auth or X-AI-Core-Token, with optional
X-AI-Core-Project identifying sub-usage only for the master token.
"""
from __future__ import annotations


def spec() -> dict:
    schemas = {
        "ChatMessage": {"type": "object", "required": ["role"], "properties": {
            "role": {"type": "string", "enum": ["system", "developer", "user", "assistant", "tool"]},
            "content": {"oneOf": [{"type": "string"}, {"type": "array"}, {"type": "null"}]},
            "tool_calls": {"type": "array", "items": {"type": "object"}},
            "tool_call_id": {"type": "string"}}},
        "ChatRequest": {"type": "object", "required": ["messages"], "properties": {
            "provider": {"type": "string"}, "model": {"type": "string"},
            "messages": {"type": "array", "items": {"$ref": "#/components/schemas/ChatMessage"}},
            "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8192},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "stream": {"type": "boolean"},
            "tools": {"type": "array", "items": {"type": "object"}},
            "reasoning_effort": {"type": "string", "enum": ["none", "minimal", "low", "medium", "high", "xhigh"]}}},
        "SearchRequest": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 600},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            "provider": {"type": "string"},
            "recency": {"type": ["string", "null"], "enum": ["24h", "7d", "30d", "90d", "1y", None]},
            "mode": {"type": "string", "enum": ["free-first", "deep"]},
            "max_attempts": {"type": "integer", "minimum": 1, "maximum": 6}}},
        "FetchRequest": {"type": "object", "required": ["url"], "properties": {
            "url": {"type": "string", "format": "uri", "maxLength": 4096}}},
        "SearchHit": {"type": "object", "properties": {
            "url": {"type": "string", "format": "uri"}, "title": {"type": "string"},
            "snippet": {"type": "string"}, "published_at": {"type": ["string", "null"]},
            "provider": {"type": "string"}, "rank": {"type": "integer"},
            "inline_content": {"type": ["string", "null"]}}},
        "SearchResponse": {"type": "object", "properties": {
            "query": {"type": "string"}, "hits": {"type": "array", "items": {"$ref": "#/components/schemas/SearchHit"}},
            "providers": {"type": "array", "items": {"type": "string"}},
            "attempts": {"type": "integer"}, "cached": {"type": "boolean"},
            "failures": {"type": "array", "items": {"type": "object"}},
            "warnings": {"type": "array", "items": {"type": "string"}}}},
        "Error": {"type": "object", "properties": {"error": {"type": "object",
            "properties": {"code": {"type": "string"}, "message": {"type": "string"}}}}},
    }
    json_response = {"description": "JSON", "content": {
        "application/json": {"schema": {"type": "object"}}}}
    def operation(label, *, body=None, parameters=None, responses=None, security=None):
        item = {"summary": label, "responses": responses or {
            "200": json_response, "401": {"description": "Unauthorized"},
            "422": {"description": "Invalid request"},
            "429": {"description": "Local budget reached"}, "503": {"description": "Unavailable"}}}
        if body:
            item["requestBody"] = {"required": True, "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/" + body}}}}
        if parameters:
            item["parameters"] = parameters
        if security is not None:
            item["security"] = security
        return item
    def query(name, required=False):
        return {"name": name, "in": "query", "required": required,
                "schema": {"type": "string"}}
    def path(name):
        return {"name": name, "in": "path", "required": True,
                "schema": {"type": "string"}}
    paths = {
        "/healthz": {"get": operation("Minimal public health check", security=[])},
        "/v1/providers": {"get": operation("Provider profiles and official endpoints")},
        "/v1/search/providers": {"get": operation("Search providers and local quota state")},
        "/v1/models": {"get": operation("Provider API model listing",
                                     parameters=[query("provider"), query("refresh")])},
        "/v1/models/reference": {"get": operation("Explicit Models.dev community reference",
                                     parameters=[query("provider", True), query("refresh")])},
        "/v1/providers/{provider}/setup": {"get": operation("Credential-free integration code",
            parameters=[path("provider"), query("language"), query("model"), query("mode")])},
        "/v1/tools/web_search": {"post": operation("Quota-guarded web search", body="SearchRequest")},
        "/v1/tools/web_fetch": {"post": operation("Pinned-IP public HTTPS page extraction", body="FetchRequest")},
        "/v1/chat/completions": {"post": operation("Text chat, tool calls or normalized SSE", body="ChatRequest")},
        "/v1/usage": {"get": operation("Tenant-specific search and model usage")},
        "/v1/free/models": {"get": operation("Local no-key and account-key free tier model discovery")},
        "/v1/connections/{provider}/test": {"post": operation("Explicit model discovery test",
            parameters=[path("provider")])},
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "AI Core API", "version": "1.0.0",
                 "description": "Opt-in, budgeted AI and search gateway. Model references and local counts do not establish billing."},
        "servers": [{"url": "http://127.0.0.1:8765"}],
        "security": [{"bearerAuth": []}, {"projectToken": []}],
        "components": {"securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
            "projectToken": {"type": "apiKey", "in": "header", "name": "X-AI-Core-Token"}},
            "schemas": schemas},
        "paths": paths,
    }
