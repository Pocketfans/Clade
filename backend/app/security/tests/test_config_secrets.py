import pytest

from app.models.config import ProviderConfig, UIConfig
from app.security.config_secrets import (
    merge_ui_config_secrets,
    public_ui_config,
    resolve_provider_credentials,
)


def config_with_key(key: str = "sk-secret") -> UIConfig:
    return UIConfig(
        providers={
            "main": ProviderConfig(
                id="main",
                name="Main",
                provider_type="openai",
                api_key=key,
            )
        },
        ai_api_key="legacy-chat",
        embedding_api_key="legacy-embedding",
    )


def test_public_config_never_contains_stored_secrets() -> None:
    public = public_ui_config(config_with_key())
    assert public["providers"]["main"]["api_key"] == ""
    assert public["providers"]["main"]["api_key_configured"] is True
    assert public["ai_api_key"] == ""
    assert public["ai_api_key_configured"] is True
    assert public["embedding_api_key"] == ""
    assert public["embedding_api_key_configured"] is True
    assert "sk-secret" not in str(public)


def test_empty_key_preserves_existing_secret() -> None:
    incoming = config_with_key("")
    merged = merge_ui_config_secrets(config_with_key(), incoming, set())
    assert merged.providers["main"].api_key == "sk-secret"


def test_non_empty_key_replaces_existing_secret() -> None:
    incoming = config_with_key("sk-new")
    merged = merge_ui_config_secrets(config_with_key(), incoming, set())
    assert merged.providers["main"].api_key == "sk-new"


def test_explicit_clear_removes_provider_secret() -> None:
    incoming = config_with_key("")
    merged = merge_ui_config_secrets(config_with_key(), incoming, {"main"})
    assert merged.providers["main"].api_key is None


def test_removed_provider_is_not_reintroduced() -> None:
    incoming = UIConfig(providers={})
    merged = merge_ui_config_secrets(config_with_key(), incoming, set())
    assert merged.providers == {}


def test_provider_id_resolves_stored_credentials() -> None:
    credentials = resolve_provider_credentials(
        {"provider_id": "main"},
        config_with_key(),
    )
    assert credentials.base_url is None
    assert credentials.api_key == "sk-secret"
    assert credentials.provider_type == "openai"


@pytest.mark.parametrize(
    "override",
    [
        {"base_url": "https://changed.example/v1"},
        {"provider_type": "anthropic"},
    ],
)
def test_stored_key_rejects_changed_credential_tuple_without_new_key(override):
    current = config_with_key()
    current.providers["main"].base_url = "https://saved.example/v1"
    with pytest.raises(ValueError, match="new API Key"):
        resolve_provider_credentials(
            {"provider_id": "main", "api_key": "", **override}, current
        )


def test_stored_key_accepts_matching_public_provider_fields():
    current = config_with_key()
    current.providers["main"].base_url = "https://saved.example/v1"
    credentials = resolve_provider_credentials(
        {
            "provider_id": "main",
            "base_url": "https://saved.example/v1",
            "api_key": "",
            "provider_type": "openai",
        },
        current,
    )
    assert credentials.base_url == "https://saved.example/v1"
    assert credentials.api_key == "sk-secret"
    assert credentials.provider_type == "openai"


def test_unsaved_values_override_stored_credentials() -> None:
    credentials = resolve_provider_credentials(
        {
            "provider_id": "main",
            "base_url": "https://new.example/v1",
            "api_key": "sk-unsaved",
            "provider_type": "anthropic",
        },
        config_with_key(),
    )
    assert credentials.base_url == "https://new.example/v1"
    assert credentials.api_key == "sk-unsaved"
    assert credentials.provider_type == "anthropic"


def test_unknown_provider_without_explicit_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="API Key"):
        resolve_provider_credentials({"provider_id": "missing"}, config_with_key())
