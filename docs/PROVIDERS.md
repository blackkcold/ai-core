# Provider catalog maintenance

Versioned source: aicore/providers.json. Always prefer vendor documentation and account-visible model APIs over copied lists. No real user API tokens are checked into source.

## Model providers

| Provider | Protocol | Discovery behavior |
|---|---|---|
| OpenAI | OpenAI chat | GET /v1/models |
| Anthropic | Messages | GET /v1/models |
| Gemini | Native generateContent | GET /v1beta/models |
| DeepSeek | OpenAI-compatible | GET /models |
| Kimi / Moonshot | OpenAI-compatible | GET /v1/models |
| GLM | OpenAI-compatible | Manual exact model ID |
| OpenRouter | OpenAI-compatible | GET /api/v1/models |
| Ollama local | Native Ollama | GET /api/tags |
| Ollama Cloud | Native Ollama | Exact enabled model ID; listing not assumed |
| MiniMax | OpenAI-compatible | GET /v1/models |
| Volcengine Ark | OpenAI-compatible | Console-managed endpoint IDs |
| OpenCode Go | OpenAI-compatible | Verified inference model-list URL |
| OpenCode Zen | Model-specific protocols | Catalog listing only; no blind chat compatibility claim |

Primary provider entry stores original base URL, models URL if supported, authentication type, regional overrides, documentation link and pricing link. A change to one field must not silently mutate another region.

## Search providers

| Provider | Key usage | Primary use |
|---|---|---|
| Tavily | optional; explicit keyless header | general web search with optional inline content |
| Firecrawl | optional; keyless may be IP-limited | search; separate fetch for full articles |
| TinyFish | API key required | fast search |
| Exa | API key required | semantic or highlight search |
| Parallel | API key required | objective/search query search |
| Brave | API key required | independent web index |

Quota limits in AI Core are locally configured dispatch controls, not published entitlements or accurate billing calculations. Pricing can change at any time. Keyed provider calls may consume credits or money.

## Update checklist

- Confirm official base, auth, version and model-list endpoints.
- Confirm error codes, quota headers, and new API response shapes against vendor fixtures.
- Test tool calls, streaming and reasoning parameters separately where supported.
- Update regression fixtures; preserve backwards compatibility within major versions.
- Review the pricing URL, never fabricate tokens/USD from incomplete usage.
- Increment release notes and verify Python 3.11/3.12/3.13 CI.
