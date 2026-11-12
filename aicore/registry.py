"""Versioned registry for known, documented provider endpoints.

Server callers choose provider IDs, not arbitrary URLs. This is intentional:
untrusted base_url fields would turn the gateway into an SSRF proxy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from urllib.parse import urlsplit


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    base_url: str
    models_url: str | None
    protocol: str
    auth: str
    key_env: str
    docs: str
    pricing: str
    regions: tuple[str, ...] = ()
    regional_base_urls: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def endpoint(self, region: str | None = None) -> str:
        if region:
            if region not in self.regions:
                raise RegistryError("unsupported region: " + region)
            return self.regional_base_urls.get(region, self.base_url)
        return self.base_url

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "base_url": self.base_url,
            "models_url": self.models_url, "protocol": self.protocol,
            "auth": self.auth, "key_env": self.key_env, "docs": self.docs,
            "pricing": self.pricing, "regions": list(self.regions),
            "regional_base_urls": dict(self.regional_base_urls), "note": self.note,
            "supports_chat": self.protocol != "catalog-only",
            "supports_discovery": self.models_url is not None,
        }


def _validate_endpoint(url: str, *, local: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme != ("http" if local else "https"):
        raise RegistryError("invalid provider URL scheme")
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise RegistryError("invalid provider URL")
    if local and (parts.hostname not in {"localhost", "127.0.0.1", "::1"}):
        raise RegistryError("local URLs must be loopback-only")
    if not local and parts.port not in (None, 443):
        raise RegistryError("public provider URLs must use 443")


@lru_cache(maxsize=1)
def _registry() -> dict[str, Provider]:
    raw = json.loads(files("aicore").joinpath("providers.json").read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise RegistryError("unsupported registry schema version")
    result: dict[str, Provider] = {}
    for entry in raw["providers"]:
        local = entry["id"] == "ollama-local"
        urls = [entry["base_url"], *(entry.get("regional_base_urls") or {}).values()]
        if entry.get("models_url"):
            urls.append(entry["models_url"])
        for url in urls:
            _validate_endpoint(url, local=local)
        item = Provider(
            id=entry["id"], name=entry["name"], base_url=entry["base_url"],
            models_url=entry.get("models_url"), protocol=entry["protocol"],
            auth=entry["auth"], key_env=entry["key_env"], docs=entry["docs"],
            pricing=entry["pricing"], regions=tuple(entry.get("regions", [])),
            regional_base_urls=entry.get("regional_base_urls", {}),
            note=entry.get("note", ""),
        )
        if item.id in result:
            raise RegistryError("duplicate provider: " + item.id)
        result[item.id] = item
    return result


def list_providers() -> list[Provider]:
    return list(_registry().values())


def get_provider(provider_id: str) -> Provider:
    try:
        return _registry()[provider_id]
    except KeyError as exc:
        raise RegistryError("unknown provider: " + provider_id) from exc
