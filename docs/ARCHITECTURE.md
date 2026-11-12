# AI Core v1 Architecture

## Components

1. **aicore.registry / providers.json**: static, versioned, audited endpoint and protocol registry. No user-controlled upstream URL at request time.
2. **aicore.models**: live /models or vendor-native /api/tags discovery; account-specific cache, no fabricated model availability.
3. **aicore.llm**: OpenAI-compatible, Anthropic Messages, Gemini generateContent and Ollama chat request/response adapters; structured tool calls; normalized streaming. Adapter errors are safe and hide upstream bodies.
4. **aicore.search**: nineteen search contracts, including keyless hosted general-web MCP and specialist public sources and multi-provider routing. Free-first is the default; deep mode aggregates and deduplicates at most three providers by default.
5. **aicore.webfetch**: HTTPS-only, port 443 only; resolves host to public IP and pins the TCP connection to validated IP while using original TLS SNI; rejects redirects, oversized/binary pages and private DNS answers.
6. **aicore.store**: SQLite transactional pre-dispatch reservations, cooldowns, tenant-aware cache, and model token usage. Failure attempts remain counted.
7. **aicore.service / aicore.mcp**: optional HTTP and stdio tools; no implicit cross-project writes.

## Data flow

Project -> local SDK or authenticated HTTP -> Registry -> explicit Provider Adapter
                                                -> Search Router -> evidence
                                                -> Store (pre-dispatch reservations + usage)

The HTTP gateway does not manage external provider keys per user: secrets are controlled by the operator's environment. A project token determines who can call the gateway and which usage partition records the call. Provider quota counters are deliberately shared across project tokens so changing project ID cannot reset upstream allowance.

## Invariants

- No model or search query initiates a paid call unless the explicit local paid-budget configuration permits it.
- Model names are not an entitlement check; the vendor remains authoritative for actual permitted use.
- Search source data retains origin URL, provider, timestamp when known, rank and recency uncertainty.
- Date filters unsupported upstream must not silently become narrower windows.
- Tools provided to a model are declarations only. Execution is a separate, audited business decision.
- Unknown upstream pricing or usage is never recorded as zero dollars.
- Changes to provider protocol adapters require fixture tests, official document review and independent release notes.

## Scope limitations

No fleet-wide distributed quota locks across multiple AI Core deployments that use different SQLite files. The HTTP process coordinates threads and same-file SQLite writers, but organizations running multiple replicas should use one shared gateway or implement a transactional centralized ledger.

An MCP stdio instance and a network gateway may use the same SQLite file on a single host, but vendor credentials stay with each process environment. API tokens are configured through the environment; no built-in credential management UI or HSM integration.
