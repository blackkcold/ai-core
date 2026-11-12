# AI Core v1.1.0 — Free-first multi-provider integration

This minor release extends the independent reusable AI integration core without changing downstream application repositories.

## Included

- 22 registered model-provider profiles, including eight additional keyed cloud providers and local LM Studio; selected protocols remain catalog-only or require a verified exact model ID.
- Local Ollama/LM Studio no-key model discovery and automatic selection; a one-command Ollama model pull and optional Docker local-llm profile. No local engine/model = no guaranteed keyless LLM inference.
- Guarded OpenRouter openrouter/free fallback only when an operator supplies the key. Other paid cloud models remain disabled by default.
- 19 search adapters, including official keyless You.com hosted web-search MCP and seven free public specialist sources, five optional new providers/self-hosted options, and the six previous integrations.
- Search source categorization, metadata provenance, bounded MCP JSON/SSE parsing, caching and per-provider quotas.
- Fixed shared global budget for streamed and ordinary metered LLM calls; separated keyless local inference and explicitly free hosted requests.
- MCP protocol 2026-07-28 stateless discovery alongside legacy 2025-era stdio clients.
- Updated Python/TypeScript/Swift/Kotlin SDK capabilities, Kotlin JVM compilation CI, concise bilingual READMEs and detailed maintenance/compatibility/deployment guides.
- Version-synchronized CLI, OpenAPI, MCP, HTTP service, health endpoint and release metadata.

## Verification and boundaries

CI covers offline provider fixtures and security/budget regression tests on Python 3.11–3.13, TypeScript and Swift type checking, Kotlin compilation, and Docker build/health. It does not use paid vendor API credentials or guarantee live third-party quotas, account permissions, model availability, production-grade free-tier terms, or unrestricted throughput. A running local LLM still requires model weights and resources. The You.com hosted keyless MCP is an evaluation route and subject to vendor limits. Live provider checks need operator-supplied credentials and consent.

MIT licensed. See the repository's documentation for deployment and operation.
