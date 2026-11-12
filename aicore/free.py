"""Free-model discovery and fail-closed default selection.

An unauthenticated *hosted* LLM is not a reliable public infrastructure
contract. No-key generation requires an installed/running local runtime.
OpenRouter's explicit zero-price 'openrouter/free' route still needs a key.
Never select an arbitrary hosted model or silently enable paid inference.
"""
from __future__ import annotations

import os

from .errors import ProviderUnavailable, UpstreamError, InvalidRequest
from .registry import get_provider
from .models import _normalized


LOCAL_PROVIDERS = ("ollama-local", "lm-studio-local")
FREE_CLOUD = (
    {
        "provider": "openrouter", "model": "openrouter/free",
        "tier": "zero-priced-routed", "requires_api_key": True,
        "docs": "https://openrouter.ai/collections/free-models",
        "note": "Rate-limited; account key required. Model selected by OpenRouter.",
    },
    {
        "provider": "gemini", "model": "gemini-2.5-flash",
        "tier": "free-tier-conditional", "requires_api_key": True,
        "docs": "https://ai.google.dev/gemini-api/docs/pricing",
        "note": "Free-tier eligibility, region and billing configuration depend on account.",
    },
)
LOCAL_PREFERRED = os.getenv("AI_CORE_LOCAL_MODEL", "").strip()


def local_is_unmetered(provider_id: str, model: str) -> bool:
    if provider_id not in LOCAL_PROVIDERS:
        return False
    # An Ollama local gateway can proxy authenticated cloud models.
    if provider_id == "ollama-local" and (
        model.lower().endswith(":cloud") or model.lower().endswith("-cloud")
    ):
        return False
    return True


def free_cloud_route(provider_id: str, model: str) -> bool:
    # Only explicitly documented and fixed zero-priced models skip paid budget.
    return provider_id == "openrouter" and model == "openrouter/free"


def _local_models(provider_id: str, transport, *, timeout=4) -> list[dict]:
    provider = get_provider(provider_id)
    try:
        result = transport.request_json(
            "GET", provider.models_url, timeout=timeout)
        models = _normalized(provider, result)
        return [row for row in models if local_is_unmetered(provider_id, row["id"])]
    except (ProviderUnavailable, UpstreamError, InvalidRequest, OSError, ValueError):
        return []


def local_status(transport, *, timeout=4) -> list[dict]:
    states = []
    for provider in LOCAL_PROVIDERS:
        models = _local_models(provider, transport, timeout=timeout)
        states.append({
            "provider": provider, "requires_api_key": False,
            "engine_ready": bool(models), "models": models,
            "note": "A local runtime and an installed model are required.",
        })
    return states


def free_catalog(transport, *, timeout=4) -> dict:
    return {
        "local": local_status(transport, timeout=timeout),
        "cloud": list(FREE_CLOUD),
        "default_policy": "local-first; optionally OpenRouter's explicit free route if keyed",
        "note": "Free tiers are not anonymous. No local runtime means no guaranteed keyless LLM.",
    }


def choose_free_model(transport, *, preferred_provider: str | None = None,
                      timeout=4) -> tuple[str, str]:
    order = [preferred_provider] if preferred_provider else list(LOCAL_PROVIDERS)
    for provider in order:
        if provider not in LOCAL_PROVIDERS:
            raise InvalidRequest("unsupported default local provider")
        models = _local_models(provider, transport, timeout=timeout)
        if models:
            preference = os.getenv("AI_CORE_LOCAL_MODEL", "").strip()
            chosen = next((m for m in models if m["id"] == preference), models[0])
            return provider, chosen["id"]
    if not preferred_provider and os.getenv("OPENROUTER_API_KEY", "").strip():
        return "openrouter", "openrouter/free"
    raise ProviderUnavailable(
        "No ready keyless model. Start Ollama and pull qwen3:0.6b, "
        "or start LM Studio with a model; see README. "
        "Cloud free-tier inference still requires an account API key."
    )
