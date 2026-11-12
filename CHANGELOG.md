# Changelog

## 1.1.0 — 2026-11-12

- Extended LLM Provider registry to 22 and search sources to 19, including official keyless You.com hosted MCP and public specialist data sources.
- Added no-key local-model auto-discovery/selection, explicit guarded OpenRouter free model fallback and optional Docker Ollama bootstrap.
- Fixed shared streaming/nonstreaming LLM paid quota; expanded protocol and provider fixtures.
- Added MCP 2026-07-28 discovery with legacy compatibility, SDK parity and Kotlin compilation CI.
- Added concise English/Chinese READMEs, deployment, compatibility and maintenance instructions, version-aware release pipeline.


## 1.0.0 — 2026-11-12

- Optional, clearly labeled Models.dev community pricing/capability reference catalog.
- Versioned 13-provider catalog, vendor-native model discovery and manual-listing boundaries.
- OpenAI-compatible, Anthropic, Gemini and Ollama text/tool-call adapter paths with normalized streaming.
- Tavily, Firecrawl, TinyFish, Exa, Parallel and Brave search contracts with keyless-first protection.
- SQLite pre-dispatch quotas, persistent cooldowns, cache and token usage accounting.
- Safe pinned-IP HTTPS page reader, HTTP and MCP gateways, per-project bearer tokens.
- Python, TypeScript, Swift and Kotlin client sources; CLI and code generator.
- Offline Python matrix tests, release gating and deployment documentation.
