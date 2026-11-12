# AI Core

A shared, opt-in AI integration foundation for independent applications. It provides a versioned provider registry, live model discovery, cross-provider chat, six web-search adapters, a protected page reader, budget ledgers, an HTTP gateway, MCP tools and platform clients.

**Release:** v1.0.0 | **Runtime:** Python 3.11+ | **License:** MIT | **Core dependencies:** Python standard library

## Scope and boundaries

- **Included:** known vendor endpoints, model discovery, model protocol adapters, chat and tool-call transport, web search, source normalization, HTTPS fetch, settings code generation, per-project tokens and usage ledgers.
- **Not included:** autonomous agent orchestration, executing model-suggested tools, trading decisions, research approval, a managed secret vault, current vendor billing reconciliation or the host application's memory and UI.
- **Design:** local SDK use where privacy matters; optional shared HTTP/MCP gateway when cross-project access is useful. No central server is mandatory.

## Quick start

~~~bash
python -m pip install -e .
ai-core providers
ai-core search-providers
ai-core setup --provider deepseek --language python
ai-core serve
~~~

The gateway listens on **127.0.0.1:8765** by default. It can start without external API keys. Search defaults to the keyless paths of Tavily and Firecrawl with conservative **local** 100/day and 40/day attempt caps. These are protection thresholds, not official provider entitlements or a guarantee of continued keyless access.

For authentication, set an AI Core token before exposing the service to a private network. To send real billable model calls, also configure the vendor credential and an explicit call budget:

~~~bash
export AI_CORE_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(36))')"
export AI_CORE_LLM_DAILY_LIMIT=10
export DEEPSEEK_API_KEY="YOUR_SECRET_FROM_PROVIDER"
ai-core serve
~~~

Test the registry:

~~~bash
curl -H "Authorization: Bearer $AI_CORE_TOKEN" http://127.0.0.1:8765/v1/providers
~~~

Discover models directly from the provider when a documented listing endpoint and credential exist:

~~~bash
ai-core models --provider deepseek
~~~

Model IDs may be unavailable or require manual configuration on some vendors. A catalog listing does not guarantee that the account is authorized to call every model.

### Search

~~~bash
curl -sS -X POST http://127.0.0.1:8765/v1/tools/web_search \
  -H "Authorization: Bearer $AI_CORE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"AI research 2026","limit":5,"recency":"7d"}'
~~~

All search requests are bounded and counted transactionally before dispatch. The response includes provider, URL, rank, snippet, published date if known, and routing diagnostics. Requests for a 90-day window never silently become 30-day searches.

### Paid or keyed search is opt-in

~~~bash
export AI_CORE_SEARCH_ENABLED=tavily,firecrawl,tinyfish,parallel,exa,brave
export AI_CORE_ALLOW_METERED_SEARCH=1
export AI_CORE_SEARCH_DAILY_LIMITS=tavily=50,firecrawl=20,tinyfish=30,parallel=10,exa=10,brave=10
export TINYFISH_API_KEY="YOUR_SEARCH_KEY"
~~~

Keyed search may incur credits or money. Official free quotas can change; **configure local caps lower than actual available budgets**. No automatic escalation to keyed routes is permitted without enabling metered search. The local SQLite ledger is NOT a substitute for the vendor's invoice or credit balance.

### Chat

~~~bash
curl -sS -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Authorization: Bearer $AI_CORE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"deepseek","model":"deepseek-chat","messages":[{"role":"user","content":"Hello!"}],"max_tokens":100}'
~~~

Include "stream": true for normalized SSE. Tool calls are returned as data and **are never executed by AI Core**. Integrators must authorize, audit and execute tools in their own application.

### MCP / command line

~~~bash
ai-core-mcp
ai-core search "web research"
ai-core fetch https://example.org/
ai-core usage
~~~

Generic MCP client declaration:

~~~json
{
  "mcpServers": {
    "ai-core": {
      "command": "ai-core-mcp"
    }
  }
}
~~~

Environment credentials are inherited from the launching process. Adjust the declaration to the MCP client's own configuration format.

## HTTP API

| Route | Method | Function |
|---|---|---|
| /healthz | GET | Minimal unauthenticated health |
| /v1/providers | GET | 13 provider profiles, endpoints and auth modes |
| /v1/models?provider=deepseek | GET | Live model discovery, cache or explicit manual state |
| /v1/models/reference?provider=deepseek | GET | Opt-in Models.dev reference prices and capabilities |
| /v1/search/providers | GET | Six search service configurations and local guards |
| /v1/providers/deepseek/setup?language=python | GET | Safe, credential-free code sample |
| /v1/tools/web_search | POST | Rate-guarded normalized web search |
| /v1/tools/web_fetch | POST | Public HTTPS text extraction |
| /v1/chat/completions | POST | Native/OpenAI-compatible chat and SSE |
| /v1/connections/deepseek/test | POST | Explicit model-discovery connectivity check |
| /v1/usage | GET | Per-project search/model usage |
| /openapi.json | GET | OpenAPI route specification |

For **explicit, non-authoritative** community model capability and indicative pricing metadata, use /v1/models/reference?provider=deepseek or ai-core model-reference --provider deepseek. AI Core never treats Models.dev prices as a billing authority or as proof of account entitlement.

The Python package also exposes an AICoreClient in aicore.client. Other clients live in clients/typescript, clients/swift and clients/kotlin.

## Supported providers

LLMs: OpenAI, Anthropic, Gemini, DeepSeek, Moonshot/Kimi, GLM, OpenRouter, Ollama Local, Ollama Cloud, MiniMax, Volcengine Ark, OpenCode Go and OpenCode Zen (catalog-only until protocol selection).

Search: Tavily, Firecrawl, TinyFish, Exa, Parallel and Brave. Every adapter has an independent auth/response mapping; provider response fields and billing change, so revalidate against the official documents before production.

## Operational guidance

- Default is loopback-only. Non-loopback binding requires a 24+ character master token or a JSON map of 24+ character project tokens in AI_CORE_PROJECT_TOKENS.
- For multi-tenant deployments, issue distinct project tokens. Do not embed vendor secrets in distributed apps.
- Persist AI_CORE_STATE_DB on a writable volume. The SQLite ledger tracks **local dispatches**, not authoritative upstream billing.
- Search snippets and web pages are untrusted data. Never follow their embedded instructions automatically.
- Continuous integration performs offline protocol contract tests and CLI smoke checks, **not paid live integration tests**.

Further documentation: docs/ARCHITECTURE.md, docs/SECURITY.md, docs/MIGRATION.md, docs/PROVIDERS.md and RELEASE_NOTES.md.
