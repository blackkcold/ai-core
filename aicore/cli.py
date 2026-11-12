"""Command-line entrypoint: serve, mcp, providers, models, search, fetch and setup."""
from __future__ import annotations

import argparse
import json
import sys

from .errors import CoreError
from .generator import generate_setup
from .registry import list_providers
from .service import Service
from .settings import Settings
from .search import list_search_providers


def parser():
    p = argparse.ArgumentParser(prog="ai-core", description="Shared AI provider and search toolkit")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Start local HTTP gateway")
    sub.add_parser("mcp", help="Run JSON-RPC MCP stdio server")
    sub.add_parser("providers", help="List LLM providers")
    sub.add_parser("search-providers", help="List search adapters")
    models = sub.add_parser("models", help="Discover live provider models")
    models.add_argument("--provider", default="auto")
    models.add_argument("--refresh", action="store_true")
    reference = sub.add_parser("model-reference", help="Opt-in Models.dev reference prices and capabilities")
    reference.add_argument("--provider", required=True)
    reference.add_argument("--refresh", action="store_true")
    search = sub.add_parser("search", help="Run an explicitly budgeted web search")
    search.add_argument("query")
    search.add_argument("--provider")
    search.add_argument("--limit", type=int, default=6)
    search.add_argument("--recency")
    search.add_argument("--mode", choices=["free-first", "deep"], default="free-first")
    fetch = sub.add_parser("fetch", help="Read a public HTTPS page")
    fetch.add_argument("url")
    setup = sub.add_parser("setup", help="Generate connection example")
    setup.add_argument("--provider", required=True)
    setup.add_argument("--language", choices=["python", "typescript", "swift", "curl"], default="python")
    setup.add_argument("--model", default="REPLACE_WITH_MODEL_ID")
    setup.add_argument("--mode", choices=["core", "native"], default="core")
    chat = sub.add_parser("chat", help="Send one model request (requires explicit daily budget)")
    chat.add_argument("--provider", default="auto")
    chat.add_argument("--model", default="auto")
    chat.add_argument("--prompt", required=True)
    sub.add_parser("free-models", help="Show available local and key-required free-tier models")
    bootstrap = sub.add_parser("setup-free", help="Download a small free model using installed Ollama (explicit opt-in)")
    bootstrap.add_argument("--model", default="qwen3:0.6b")
    sub.add_parser("usage", help="Display local request and model usage")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "providers":
            value = {"providers": [x.public() for x in list_providers()]}
        elif args.command == "search-providers":
            value = {"providers": list_search_providers()}
        elif args.command == "setup":
            value = generate_setup(args.provider, language=args.language,
                                   model=args.model, mode=args.mode)
        elif args.command == "mcp":
            from .mcp import main as mcp_main
            mcp_main()
            return 0
        elif args.command == "setup-free":
            import re
            import shutil
            import subprocess
            if not re.fullmatch(r"[A-Za-z0-9_.:/+-]{1,180}", args.model):
                raise ValueError("invalid local model ID")
            if not shutil.which("ollama"):
                raise ValueError("Ollama is not installed; visit https://ollama.com/download")
            return subprocess.run(["ollama", "pull", args.model], check=False).returncode
        else:
            service = Service(Settings.from_env())
            if args.command == "serve":
                service.run()
                return 0
            try:
                if args.command == "models":
                    value = service.models.list(args.provider, refresh=args.refresh)
                elif args.command == "model-reference":
                    value = service.reference.list(args.provider, refresh=args.refresh)
                elif args.command == "search":
                    value = service.search.search({"query": args.query, "limit": args.limit,
                        "recency": args.recency, "provider": args.provider, "mode": args.mode})
                elif args.command == "fetch":
                    value = service.fetcher(args.url)
                elif args.command == "chat":
                    value = service.chat.chat({"provider": args.provider, "model": args.model,
                                               "messages": [{"role": "user", "content": args.prompt}]})
                elif args.command == "free-models":
                    from .free import free_catalog
                    value = free_catalog(service.chat.transport)
                elif args.command == "usage":
                    value = {"search": service.store.usage(), "llm": service.store.llm_usage()}
                else:
                    raise ValueError("unknown command")
            finally:
                service.store.close()
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (CoreError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
