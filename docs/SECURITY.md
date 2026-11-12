# Security and privacy

- Store every API key in process environment or external secret manager. Never commit it, render it to web pages, or send it to a language model.
- Bind 127.0.0.1 by default. Non-loopback requires configured credentials. Put TLS and access controls in front of any remote deployment.
- AI_CORE_TOKEN is an administrative bearer token. Use AI_CORE_PROJECT_TOKENS with distinct 24+ character values to restrict non-admin projects; rotate and revoke via process config.
- Configure AI_CORE_ALLOWED_ORIGINS only for trusted browser clients. Never use a wildcard CORS origin with bearer tokens.
- Direct apps should not embed long-lived provider API keys. Use short-lived project tokens via an application backend or OS secret storage.
- Search uses default no-key endpoints only. Enabling metered APIs requires AI_CORE_ALLOW_METERED_SEARCH=1, specific enabled provider and explicit attempt caps. Quota counters are lower-bound request counts; vendor credit usage may differ.
- Model calls are disabled by default (AI_CORE_LLM_DAILY_LIMIT=0). The configured cap is shared globally across providers for a deployment, not multiplied by switching models. No automatic tool execution, model-to-shell execution, or permission escalation is implemented.
- Web fetch validates the DNS answer and pins the socket to public IP and TLS SNI. Redirects, non-HTTPS, unusual ports and binary content are rejected. This policy intentionally excludes local intranet URLs.
- Provider endpoints are selected from a reviewed registry. A request cannot submit an arbitrary LLM host.
- Search excerpts and fetched pages may contain prompt injection, misleading claims, PII and malicious code. Treat them as untrusted evidence, not instructions. Business applications must apply user-consent policies and citation verification.
- Current v1 does not implement server-wide per-tenant model-price USD authorization, payment reconciliation, encrypted on-disk SQLite, retention policy enforcement, distributed quotas or a user-facing secrets UI. Restrict sensitive usage until those controls exist.
- Test fixtures do not use network credentials; CI must not make live paid API calls.

Report vulnerabilities privately to the repository maintainer rather than publishing credentials or exploit details.
