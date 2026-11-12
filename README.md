# AI Core

[![Version](https://img.shields.io/github/v/release/blackkcold/ai-core?label=version)](https://github.com/blackkcold/ai-core/releases/latest)
[![CI](https://github.com/blackkcold/ai-core/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/blackkcold/ai-core/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
[![MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**English** · [简体中文](README.zh-CN.md)

A lightweight, MIT-licensed AI integration core for multiple applications.

## Features

- 22 model-provider profiles, official model discovery and free-model discovery
- Chat, tool calls, normalized streaming and OpenAI/Anthropic/Gemini/Ollama adapters
- 18 search sources: credential-free public sources, opt-in keyed APIs and self-hosted search
- Authenticated REST gateway, MCP tools, safe HTTPS reader, caching and usage quotas
- Python, TypeScript, Swift and Kotlin clients; Docker or local deployment
- Local-first free inference with Ollama or LM Studio; optional keyed OpenRouter free route

## Install

```bash
git clone https://github.com/blackkcold/ai-core.git
cd ai-core
python -m pip install -e .
ai-core serve
```

Gateway: `http://127.0.0.1:8765`. No vendor API key is required to **start** the service or use default public search.

## Free AI without an API key

Install [Ollama](https://ollama.com/download) and run:

```bash
ai-core setup-free                  # pulls qwen3:0.6b (~523 MB)
ai-core chat --prompt "Hello"       # auto-selects an installed local model
ai-core free-models                 # local readiness + keyed free-tier options
```

Alternatively start LM Studio's local server with a model. No local runtime/model means **chat is not available** without a provider key. Hosted free tiers such as `openrouter/free` still require an account API key and have limits. Paid cloud inference is disabled unless explicitly budgeted.

## Search

```bash
ai-core search "Python"
ai-core search "research papers" --provider openalex
ai-core search "startup news" --provider hackernews
```

The default keyless providers are **specialist data sources**, not a complete general-web search engine. Select `category=research|news|developer|books` in the HTTP/MCP request to route by corpus.

## Docker

```bash
cp .env.example .env
export AI_CORE_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
docker compose up -d --build
```

Configure search keys and paid budgets explicitly in the environment. Docker does not automatically inherit a host-only local LLM server.

## Documentation

[Providers](docs/PROVIDERS.md) · [Integration](docs/INTEGRATION.md) · [Compatibility](docs/COMPATIBILITY.md) · [Maintenance](docs/MAINTENANCE.md) · [Security](docs/SECURITY.md)

## License

[MIT](LICENSE)
