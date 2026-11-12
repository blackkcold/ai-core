# Integration and deployment guide

## Local development

Install Python 3.11+, then:

```bash
python -m pip install -e .
ai-core providers
ai-core search-providers
ai-core serve
```

The API binds to `127.0.0.1:8765` by default. Search works without vendor credentials against the enabled specialist public sources. `/healthz` only proves that the gateway process is alive.

To enable no-key local inference, install and start Ollama, then run `ai-core setup-free` to explicitly download `qwen3:0.6b`; alternatively start LM Studio with an installed model. `ai-core chat --prompt "Hello"` auto-selects only installed local models, then an explicitly keyed `openrouter/free` if present. It never silently routes to paid models.

## Docker

```bash
cp .env.example .env
export AI_CORE_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
docker compose up -d --build
```

The container is writable only at its persisted `/data` volume and temporary paths. Docker does not automatically see host Ollama/LM Studio loopback services; for production, deploy a separately authenticated, explicitly reviewed network route rather than widening the provider registry to arbitrary addresses.

## Authentication and model call

```bash
export AI_CORE_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
curl -H "Authorization: Bearer $AI_CORE_TOKEN" http://127.0.0.1:8765/v1/free/models
curl -H "Authorization: Bearer $AI_CORE_TOKEN" http://127.0.0.1:8765/v1/providers
```

Local loopback without a configured token remains accessible to other processes on that host. Never bind a public interface without a strong token and trusted TLS reverse proxy. Use project tokens for tenant separation.

```bash
curl -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Authorization: Bearer $AI_CORE_TOKEN" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

An installed model is required for the preceding keyless chat request. Paid cloud calls require account keys and `AI_CORE_LLM_DAILY_LIMIT>0`. Cloud free-tier calls still need a provider key and may have independent rate limits.

## Searches

```bash
curl -X POST http://127.0.0.1:8765/v1/tools/web_search \
  -H "Content-Type: application/json" -H "Authorization: Bearer $AI_CORE_TOKEN" \
  -d '{"query":"machine learning","category":"research","limit":5}'
```

Categories: `general`, `research`, `news`, `developer`, `books`. Paid/API-key sources stay disabled until explicitly configured with limits. Public academic sources are metadata indexes, not a whole-web search system.

## API and MCP

OpenAPI: `/openapi.json`; stdio MCP: `ai-core-mcp`. Model tool calls are returned as inert data; a consuming application must authorize, log and execute them separately. Do not execute retrieved page content.
