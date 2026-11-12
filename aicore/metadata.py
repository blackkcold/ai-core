"""Optional Models.dev reference catalog, never a billing authority.

The official provider /models response remains the only claim about actual
vendor-advertised models. This community catalog adds candidate model names,
indicative USD/1M-token pricing and capabilities, all clearly marked unverified
for any specific account. Network fetch happens ONLY on explicit request.
"""
from __future__ import annotations

from .errors import InvalidRequest, ProviderUnavailable
from .registry import get_provider
from .store import Store
from .transport import Transport


MODELS_DEV_URL = "https://models.dev/api.json?type=all"
PROVIDER_IDS = {
    "openai": "openai", "anthropic": "anthropic", "gemini": "google",
    "deepseek": "deepseek", "kimi": "moonshotai", "glm": "zai",
    "openrouter": "openrouter", "ollama-local": "ollama",
    "ollama-cloud": "ollama", "minimax": "minimax",
    "volcengine-ark": "volcengine", "opencode-go": "opencode",
    "opencode-zen": "opencode",
}


def normalize_reference(provider_id: str, snapshot: dict, *, limit=500) -> dict:
    get_provider(provider_id)  # validates known provider ID
    source_id = PROVIDER_IDS.get(provider_id, provider_id)
    group = snapshot.get(source_id) or {}
    items = group.get("models") or {}
    if not isinstance(items, dict):
        items = {}
    candidates = []
    for name, metadata in items.items():
        if len(candidates) >= limit:
            break
        if not isinstance(name, str) or not isinstance(metadata, dict):
            continue
        cost = metadata.get("cost") or {}
        limits = metadata.get("limit") or {}
        if not isinstance(cost, dict):
            cost = {}
        if not isinstance(limits, dict):
            limits = {}
        def numeric_values(obj):
            return {k: v for k, v in obj.items()
                    if isinstance(k, str) and type(v) in {int, float} and v >= 0}
        features = {k: metadata[k] for k in ("reasoning", "tool_call", "structured_output")
                    if type(metadata.get(k)) is bool}
        candidates.append({
            "id": name,
            "name": metadata.get("name") or name,
            "cost_usd_per_million_tokens": numeric_values(cost),
            "token_limits": numeric_values(limits),
            "features": features,
            "reference_source": MODELS_DEV_URL,
            "account_entitlement_verified": False,
            "billing_authoritative": False,
        })
    return {"provider": provider_id, "source": "models.dev_community_reference",
            "models": candidates,
            "reference_url": MODELS_DEV_URL,
            "account_entitlement_verified": False,
            "billing_authoritative": False,
            "message": "Indicative community metadata only. Validate model access and actual rates with the vendor."}


class ReferenceCatalog:
    def __init__(self, store: Store, transport: Transport | None = None, *, timeout=30):
        self.store = store
        self.transport = transport or Transport()
        self.timeout = timeout

    def list(self, provider_id: str, *, refresh: bool = False, limit: int = 500):
        get_provider(provider_id)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise InvalidRequest("reference model limit must be 1..1000")
        snapshot = None if refresh else self.store.cache_get("modelsdev:v1")
        if snapshot is None:
            snapshot = self.transport.request_json(
                "GET", MODELS_DEV_URL, timeout=self.timeout, max_bytes=24_000_000)
            if not isinstance(snapshot, dict) or not snapshot:
                raise ProviderUnavailable("invalid Models.dev snapshot")
            self.store.cache_put("modelsdev:v1", snapshot, 86400)
        return normalize_reference(provider_id, snapshot, limit=limit)
