from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..models.config import UIConfig


class UIConfigUpdateRequest(BaseModel):
    config: UIConfig
    clear_provider_api_keys: set[str] = Field(default_factory=set)


@dataclass(frozen=True)
class ProviderCredentials:
    base_url: str | None
    api_key: str
    provider_type: str


def resolve_provider_credentials(
    request: dict[str, Any],
    current: UIConfig,
) -> ProviderCredentials:
    provider_id = str(request.get("provider_id") or "")
    stored = current.providers.get(provider_id)
    explicit_key = request.get("api_key")
    if explicit_key:
        base_url = request.get("base_url") or (stored.base_url if stored else None)
        provider_type = request.get("provider_type") or (
            stored.provider_type if stored else "openai"
        )
        return ProviderCredentials(base_url, str(explicit_key), provider_type)

    if not stored or not stored.api_key:
        raise ValueError("API Key is not configured")
    if request.get("base_url") not in (None, "", stored.base_url):
        raise ValueError("A new API Key is required when changing provider endpoint")
    if request.get("provider_type") not in (None, "", stored.provider_type):
        raise ValueError("A new API Key is required when changing provider type")
    return ProviderCredentials(stored.base_url, stored.api_key, stored.provider_type)


def public_ui_config(config: UIConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    for provider in data.get("providers", {}).values():
        provider["api_key_configured"] = bool(provider.get("api_key"))
        provider["api_key"] = ""
    for field in ("ai_api_key", "embedding_api_key"):
        data[f"{field}_configured"] = bool(data.get(field))
        data[field] = ""
    return data


def merge_ui_config_secrets(
    current: UIConfig,
    incoming: UIConfig,
    clear_provider_api_keys: set[str],
) -> UIConfig:
    data = incoming.model_dump(mode="python")
    current_providers = current.providers
    for provider_id, provider in data.get("providers", {}).items():
        if provider_id in clear_provider_api_keys:
            provider["api_key"] = None
        elif not provider.get("api_key") and provider_id in current_providers:
            provider["api_key"] = current_providers[provider_id].api_key
    for field in ("ai_api_key", "embedding_api_key"):
        if not data.get(field):
            data[field] = getattr(current, field)
    return UIConfig.model_validate(data)
