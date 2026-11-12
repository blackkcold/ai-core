# Compatibility and provider capability policy

## Protocol boundaries

- `openai` — Chat Completions compatibility only. Parameters, reasoning, tool calls and SSE vary by model/provider. Do not assume full OpenAI Responses API compatibility.
- `anthropic` — native Messages mapping; text and tool calls, not full multimodal parity.
- `gemini` — native generateContent mapping; text and tool calls, not full multimodal parity.
- `ollama` — native local or cloud chat, with NDJSON streaming; local cloud-proxied IDs may cost money.
- `catalog-only` — listing/metadata only; invocation is not supported until a native adapter is implemented.

A registered provider does **not** prove a valid account, model permission, enabled tools or live compatibility. Live connection tests require operator credentials and explicit consent.

## Search capabilities

| Source | Category | No API key | Recency |
|---|---|---:|---|
| Wikipedia | general reference | Yes | No (page revision is not publication date) |
| HN Algolia | technology news | Yes | Yes |
| OpenAlex | academic | Yes (limited) | Yes |
| Crossref | DOI metadata | Yes | Yes |
| Europe PMC | biomedical | Yes | Yes |
| Stack Overflow | developer Q&A | Yes | Yes |
| Open Library | book catalog | Yes | No |
| SearXNG | self-hosted | Yes if deployed | Instance-dependent |
| Tavily, Firecrawl, TinyFish, Parallel, Exa, Brave | vendor APIs | Key/terms dependent | Provider-dependent |
| Perplexity, You.com, Jina, NewsAPI | vendor APIs | Key required for REST | Provider-dependent |

The 18 registered search entries have separate corpora, not interchangeable full-text coverage. NewsAPI's free developer tier may **not** be used in production. You.com's separate free MCP profile is not equivalent to its keyed REST API.

## Cross-platform clients

| Client | Transport | Streaming | Notes |
|---|---|---|---|
| Python | stdlib HTTP | Gateway response only | No external runtime dependency |
| TypeScript | fetch | SSE | Node.js 18+ or modern browser |
| Swift | URLSession | SSE via async bytes | macOS/iOS runtime constraints |
| Kotlin | HttpURLConnection | Callback SSE | Call on background thread |

Android `127.0.0.1` means the *device*, not a host computer. Docker `127.0.0.1` means the container, not the host. Use a trusted reachable gateway with TLS, credential storage and network policy. Do not embed provider secrets in distributed clients.

## Stability gates

- Wire compatibility: JSON schema, documented status codes and streaming event order.
- Budget safety: shared paid quota for streaming and non-streaming, separate hard limits for explicit free hosted routes.
- Security: no arbitrary external provider URLs from untrusted requests; public fetch uses pinned DNS and TLS.
- Traceability: search hits retain URL, source name, rank, publication timestamp when known, and caveats about unknown recency.
