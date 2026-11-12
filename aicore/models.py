"""Live model discovery: provider API is authoritative; no invented model lists.

When a vendor does not document a stable list endpoint, return an explicit
manual-configuration state. Model metadata does not imply call entitlement.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from .errors import ProviderUnavailable
from .registry import get_provider
from .store import Store
from .transport import Transport


def credential_headers(provider, key: str) -> dict:
    if provider.auth == "none":
        return {}
    if not key:
        return {}
    if provider.auth == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    if provider.auth == "google":
        return {"x-goog-api-key": key}
    return {"Authorization": "Bearer " + key}


def _normalized(provider, payload: dict) -> list[dict]:
    if provider.protocol == "ollama":
        rows = payload.get("models") or []
    elif provider.protocol == "gemini":
        rows = payload.get("models") or []
    else:
        rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise ProviderUnavailable("invalid model catalog response")
    out = []
    seen = set()
    for item in rows[:5000]:
        if not isinstance(item, dict):
            continue
        ident = item.get("id") or item.get("name") or item.get("model")
        if not isinstance(ident, str):
            continue
        if provider.protocol == "gemini" and ident.startswith("models/"):
            ident = ident.removeprefix("models/")
        if not ident or ident in seen:
            continue
        seen.add(ident)
        capabilities = {}
        if isinstance(item.get("supportedGenerationMethods"), list):
            capabilities["generation_methods"] = item["supportedGenerationMethods"]
        if isinstance(item.get("inputModalities"), list):
            capabilities["input_modalities"] = item["inputModalities"]
        if isinstance(item.get("outputModalities"), list):
            capabilities["output_modalities"] = item["outputModalities"]
        for field in ("inputTokenLimit", "outputTokenLimit", "context_window"):
            if isinstance(item.get(field), int) and item[field] >= 0:
                capabilities[field] = item[field]
        out.append({"id": ident, "name": item.get("displayName") or ident,
                    "capabilities": capabilities, "capabilities_verified": bool(capabilities),
                    "pricing_url": provider.pricing})
        if len(out) >= 2000:
            break
    return out


class ModelCatalog:
    def __init__(self, store: Store, transport: Transport | None = None, *, timeout=20):
        self.store, self.transport, self.timeout = store, transport or Transport(), timeout

    def list(self, provider_id: str, *, refresh: bool = False, tenant: str = "local") -> dict:
        if provider_id == "auto":
            from .free import local_status
            statuses = local_status(self.transport, timeout=min(self.timeout, 4))
            return {"provider": "auto", "source": "local_discovery",
                    "models": [{**row, "provider": s["provider"]}
                               for s in statuses for row in s["models"]],
                    "note": "Only installed local models are listed; hosted free tiers need keys."}
        provider = get_provider(provider_id)
        key = os.getenv(provider.key_env, "").strip() if provider.key_env else ""
        if not provider.models_url:
            return {"provider": provider.id, "models": [], "source": "manual_required",
                    "message": "No verified model listing endpoint; configure an exact model ID.",
                    "pricing_url": provider.pricing}
        if not key and provider.auth != "none" and provider.id != "openrouter":
            return {"provider": provider.id, "models": [], "source": "credentials_required",
                    "key_env": provider.key_env, "pricing_url": provider.pricing}
        cache_key = "models:" + hashlib.sha256(
            (tenant + ":" + provider.id + ":" + key).encode("utf-8")).hexdigest()
        if not refresh:
            saved = self.store.cache_get(cache_key)
            if saved:
                return {**saved, "source": "cached_provider_api"}
        payload = self.transport.request_json(
            "GET", provider.models_url, headers=credential_headers(provider, key), timeout=self.timeout)
        models = _normalized(provider, payload)
        result = {"provider": provider.id, "models": models, "source": "provider_api",
                  "fetched_at": datetime.now(timezone.utc).isoformat(),
                  "pricing_url": provider.pricing,
                  "note": "Listed models are not necessarily enabled on this account; prices may differ by plan."}
        self.store.cache_put(cache_key, result, 3600)
        return result
