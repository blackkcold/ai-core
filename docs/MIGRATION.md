# Incremental integration plan (no downstream repositories altered by this release)

Existing applications remain independently deployable. Integrate behind a feature flag, compare outputs and latency, and provide an immediate rollback to their previous transport.

| Application | Existing code to evaluate | Adopt from AI Core | Keep locally |
|---|---|---|---|
| news-bar | Sources/NewsBar/Services/Search/*, Services/AI/* | shared search policy and Swift SDK after contract parity | macOS secure key store, UI, evidence ranking, research pipeline |
| weibo-rd-observatory | src/ai_providers.py, src/intel/research/provider_catalog.py, search_client.py | Provider Registry, model discovery, search routing | research, analysis, fact verification and database |
| brand-dashboard | apps/api/app/ai/providers.py, connectors/live_search.py | Provider selection, common search, chat | entity/evidence storage, verification policy |
| alpha-loop | src/alpha_loop/agents/factor_planner.py and llm_ledger.py | LLM transport and model endpoints | immutable scientific admission, research ledger, trade authorization |
| family-ledger | src/core/ai/adapter.ts and dialect.ts | shared endpoint metadata and TS client if policy permits | privacy-first BYOK browser direct mode, financial data governance |
| sidexplorer | src/providers/registry.ts | common model metadata and transport config | browser UI and local OpenCode integration |
| open-mem | plugin/src/review/provider.ts and config.ts | Provider Registry / model discovery | memory pipeline and review restrictions |
| trendnews | trendradar/ai/client.py | shared Registry and search tools | LiteLLM orchestration and app-specific summarization |
| openchamber | OpenCode SDK integration | optional external MCP server only | original provider/runtime SDKs |

## Migration gates

1. Pin the old application's baseline commit and create deterministic old/new request and response fixtures.
2. Use a thin adapter to map app types to AI Core v1. Test auth, cancellation, retries, 402/429, streams, tool calls, data provenance and cost behavior.
3. Shadow test with no paid API calls. Compare evidence identity, citation coverage and output shape.
4. Enable per-project token and local limits. Confirm SQLite persistence and your external billing dashboard.
5. Gradually enable only one project, then roll out further while retaining a rollback toggle.
6. Remove duplicate code only after the new path passes reliability and security gates.

AI Core v1 does not automatically modify, deploy or migrate any of the existing application repositories.
