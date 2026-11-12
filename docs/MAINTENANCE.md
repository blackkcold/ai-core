# AI Core — Maintenance Playbook

All commands below are safe read-only checks unless marked otherwise. Live API probes may incur credits; ordinary CI runs offline fixtures only.

## Daily (5–10 minutes)

1. Check `curl -fsS http://127.0.0.1:8765/healthz` and the authenticated `/v1/usage` endpoint.
2. Run `ai-core usage`; investigate rapid request growth, exhausted budgets, and repeated 402/429/503s.
3. Check that state DB is writable and persistent. Verify the local LLM runtime only where installed.
4. Treat keyless search success as best-effort; each source has independent rate and corpus limitations.

## Weekly

1. Check official vendor docs for API base URL, authentication, model-list paging, tool support, response shape, terms, and free-tier eligibility.
2. Run `python -m unittest discover -s tests -p 'test_*.py'`; check all GitHub Actions matrix jobs.
3. Inspect public dependency advisory feeds and Python/Node/Kotlin package changes; update only after contract tests.
4. Review searches by category and recency. Do not treat an unknown publication date as verified freshness.
5. Review quota configurations below any actual vendor commitments.

## Monthly

1. Use dedicated low-budget test accounts to test real vendor connections *with consent*. Label untested providers `offline-only`.
2. Back up the SQLite state using a consistent SQLite backup or a stopped service; restore to an isolated database to verify.
3. Rotate project tokens, check permissions, prune expired cached data after taking a consistent backup.
4. Review the four client libraries, API schemas, streaming cancellation, TLS configuration, and Docker health checks.
5. Compare any *estimated* costs with official provider billing dashboards. No local request counter is authoritative billing.

## Adding or updating a model/search adapter

1. Link official docs and record verified date, endpoint, region, auth, model discovery, price and supported request types.
2. Use a reviewed registry entry; never take an arbitrary untrusted upstream URL from the request body.
3. Add request and response fixtures, errors, streaming and tool-call fixtures as applicable.
4. Test 401/402/429, malformed JSON, timeouts, budget gating, concurrent requests and data origin.
5. Update public response schema, clients, configuration sample and docs; keep existing /v1 routes backward-compatible.
6. Release only after Python, TS, Swift, Kotlin and Docker CI pass. Paid online smoke tests are separate.

## Commands

```bash
ai-core providers
ai-core search-providers
ai-core models --provider auto
ai-core free-models
ai-core models --provider deepseek --refresh    # accesses vendor
ai-core usage
python -m unittest discover -s tests -p 'test_*.py'
docker compose config
```

## Operational boundaries

- `AI_CORE_LLM_DAILY_LIMIT=0` blocks metered cloud calls. Explicit `openrouter/free` uses an independent guarded free quota, but still requires a key.
- `AI_CORE_FREE_CLOUD_DAILY_LIMIT` defaults to 20 local attempts/day; official quota can differ.
- Ollama `:cloud` routes are **not** assumed free even via a localhost gateway.
- You.com's free hosted MCP is an evaluation profile (provider currently advertises 100/day; local default 60/day). It may be rate-limited or unavailable. Specialist indexes provide separate limited corpora.
- The SQLite counter counts dispatches, not vendor invoice totals; use one shared ledger per deployment, not divergent replicas.
- Public web material is untrusted and must never be executed as model instructions.
