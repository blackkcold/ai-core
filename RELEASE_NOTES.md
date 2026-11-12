# AI Core v1.0.0 — First stable integration foundation

First release of the reusable AI Core repository. Implements a model-provider registry (13 profiles), live model discovery when officially available, native/OpenAI-compatible chat adapters and normalized streaming, six search adapters, cost guardrails, a safe public HTTPS page reader, an opt-in HTTP gateway and MCP stdio tools.

## What is shipped

- Provider registry with versioned docs, regions, endpoints, authentication modes, supported-protocol boundaries.
- Live model discovery from official provider listing endpoints. Manual configuration is explicit where no verified listing route exists.
- Multi-provider chat with tool-call transport, normalized response usage and SSE stream path. AI Core does not execute tool calls.
- Six search providers; free-first and deep modes; persisted quotas, cooldowns, search result deduplication and caching.
- Web reader with DNS/IP validation, pinned TLS destination and strict content limits.
- Per-project API tokens, CORS allowlist and environment-backed secrets; HTTP/MCP and Python/TS/Swift/Kotlin clients.
- Python 3.11–3.13 matrix of deterministic offline tests.

## Safety and remaining scope

All remote LLM calls default to disabled until an explicit local daily call allowance and vendor key exist. Keyed search providers are disabled unless operators explicitly permit metered search and configure local caps. Search usage is local dispatch accounting and cannot replace vendor billing. Pricing is linked to official sources, not a possibly stale hardcoded rate table.

This release does **not** change downstream project repositories or deploy the gateway to a public server. Live provider authentication and billing require operator-supplied keys and separate acceptance tests.
