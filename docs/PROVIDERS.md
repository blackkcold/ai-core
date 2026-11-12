# Provider and Search API Catalog

This lists registered adapters, not guaranteed live access, account entitlement or billing. Verify each official endpoint, price and access policy before using it in production. The authoritative registration files are aicore/providers.json, aicore/search.py, aicore/search_free.py and aicore/search_extra.py.

## Model providers (22 registry profiles)

| Group | Provider IDs | Adapter | Notes |
|---|---|---|---|
| Major native | openai, anthropic, gemini | OpenAI Chat / native Messages / native generateContent | Capabilities vary by model |
| Aggregators | openrouter, opencode-go, opencode-zen | OpenAI Chat / catalog-only | Zen is catalog-only; free OpenRouter still needs a key |
| China / Asia | deepseek, kimi, glm, minimax, volcengine-ark, alibaba, siliconflow | OpenAI Chat | Regional endpoints and manual model IDs may be required |
| Other hosted | xai, mistral, groq, together, fireworks, cerebras | OpenAI Chat | OpenAI-compatible does not promise Responses API parity |
| Local / cloud Ollama | ollama-local, ollama-cloud | Native Ollama | Local no-key; cloud needs key and can cost money |
| Local OpenAI API | lm-studio-local | OpenAI Chat | Only works after a local engine is started and model loaded |

Registered does not imply successful live vendor authentication. External API probes require account credentials and operator consent. Official provider model-list endpoints are preferred; Models.dev is an unverified optional community reference.

### Free model selection

1. Discover local Ollama models from its native model list. Exclude cloud-proxied model IDs from free selection.
2. Discover local LM Studio models from its local OpenAI model listing.
3. If an operator already provided an OpenRouter key, allow the explicitly free **openrouter/free** route under its separate guarded quota.
4. Fail closed with an installation hint if no local model or permitted free route is ready. Never silently call paid models.

The HTTP service and default search start without a provider API key. Keyless model inference still requires an installed local engine and model. For Docker, enable the optional local-llm profile to download a small Qwen model.

## Search (19 registered adapters)

| ID | Corpus / usage | Authentication | Default |
|---|---|---|---|
| you-free-mcp | Real-time general web/news, hosted MCP | No key, vendor eval free tier (100/day advertised) | On, capped at 60/day |
| wikipedia | Encyclopedia and facts | None | On |
| hackernews | Tech news and discussions | None | On |
| openalex | Academic works metadata | Public API | On |
| crossref | DOI/publication metadata | Public API | On |
| europepmc | Biomedical publication metadata | Public API | On |
| stackoverflow | Developer Q&A | Public API | On |
| openlibrary | Book metadata | Public API | On |
| tavily | Web search | Experimental keyless or keyed | Off |
| firecrawl | Search and extraction | Key normally required | Off |
| tinyfish | Web search | Key required | Off |
| exa | Semantic search | Key required | Off |
| parallel | Web search | Key required | Off |
| brave | Independent web index | Key required | Off |
| perplexity | Web search | Key required | Off |
| you | You.com REST, distinct from keyless MCP | Key required | Off |
| jina | Search | Key required | Off |
| newsapi | News monitoring | Key; free developer account cannot be used in production | Off |
| searxng | Self-hosted metasearch | Local instance with JSON enabled | Off |

Web search supports query, limit, provider, category (general/research/news/developer/books), language, recency, mode and max_attempts. Sources do not provide identical indexes, so the router retains provenance. A missing publication date is never presented as verified recency; unsupported time windows fail explicitly.

Search mode free-first stops when a provider returns results; deep may aggregate several enabled sources within configured attempt limits. Page fetch is a separate HTTPS-only tool with public-IP/TLS protections. AI Core does not autonomously execute a returned tool call.

## Maintenance gate

1. Inspect official docs for endpoint, authentication, API version, region, model-list behavior, quotas and schema changes.
2. Add deterministic request/response/error fixtures, with SSE and tool-call cases when relevant.
3. Cover 401/402/429, 5xx, timeouts, invalid data, recency and concurrency budgets.
4. Require Python, TypeScript, Swift, Kotlin and Docker CI success before release.
5. Test actual third-party accounts only with a low-budget opt-in online check; without credentials label the adapter **offline contract only**.
6. Preserve the public v1 interface or release a documented breaking major version.

## Official reference documentation

[You.com free MCP](https://you.com/docs/agents/mcp-server) · [Ollama API](https://docs.ollama.com/api/introduction) · [LM Studio](https://lmstudio.ai/docs/developer/openai-compat) · [MediaWiki](https://www.mediawiki.org/wiki/API:Search) · [OpenAlex](https://help.openalex.org/api/) · [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) · [Europe PMC](https://europepmc.org/RestfulWebService) · [Stack Exchange](https://api.stackexchange.com/docs) · [Open Library](https://openlibrary.org/dev/docs/api/search) · [SearXNG](https://docs.searxng.org/dev/search_api.html)

See also [Compatibility](COMPATIBILITY.md), [Maintenance](MAINTENANCE.md) and [Security](SECURITY.md).
