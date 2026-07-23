from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.models.config import UIConfig
from app.security.admin_token import (
    AdminTokenValidationError,
    require_admin_token,
    validate_admin_token,
)


def test_ui_config_defaults_local_ai_endpoints_to_disabled():
    assert UIConfig.model_validate({"providers": {}}).allow_local_ai_endpoints is False


def test_ui_config_round_trips_local_ai_endpoint_setting():
    config = UIConfig(allow_local_ai_endpoints=True)
    restored = UIConfig.model_validate_json(config.model_dump_json())

    assert restored.allow_local_ai_endpoints is True


@pytest.mark.parametrize("provided", [None, "wrong-token"])
def test_validate_admin_token_uses_same_safe_rejection(provided):
    with pytest.raises(AdminTokenValidationError) as exc_info:
        validate_admin_token(provided, "expected-token")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "admin_token_invalid"


@pytest.mark.parametrize("configured", [None, ""])
def test_validate_admin_token_rejects_unconfigured_token(configured):
    with pytest.raises(AdminTokenValidationError) as exc_info:
        validate_admin_token("provided-token", configured)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "admin_token_unconfigured"
    assert exc_info.value.public_message == "管理员功能未启用"


def test_validate_admin_token_accepts_exact_token():
    assert validate_admin_token("expected-token", "expected-token") is None


@pytest.mark.parametrize(
    ("provided", "configured"),
    [
        ("supplied-secret", "configured-secret"),
        (None, "configured-secret"),
        ("supplied-secret", None),
    ],
)
def test_validate_admin_token_errors_do_not_echo_tokens(provided, configured):
    with pytest.raises(AdminTokenValidationError) as exc_info:
        validate_admin_token(provided, configured)

    error_text = str(exc_info.value)
    if provided:
        assert provided not in error_text
    if configured:
        assert configured not in error_text


def make_client(server_token: str | None) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        clade_admin_token=server_token
    )

    @app.get("/probe", dependencies=[Depends(require_admin_token)])
    def get_probe() -> dict[str, bool]:
        return {"ok": True}

    @app.head("/probe", dependencies=[Depends(require_admin_token)])
    def head_probe() -> None:
        return None

    @app.post("/probe", dependencies=[Depends(require_admin_token)])
    def post_probe() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_get_and_head_allow_read_access_without_configured_token() -> None:
    client = make_client(None)

    assert client.get("/probe").status_code == 200
    assert client.head("/probe").status_code == 200


@pytest.mark.parametrize("server_token", [None, ""], ids=["none", "empty"])
def test_post_returns_503_when_server_token_is_not_configured(
    server_token: str | None,
) -> None:
    response = make_client(server_token).post("/probe")

    assert response.status_code == 503
    assert response.json() == {"detail": "管理员功能未启用"}


def test_missing_and_wrong_tokens_return_the_same_403_response() -> None:
    client = make_client("expected-token")

    missing_response = client.post("/probe")
    wrong_response = client.post(
        "/probe", headers={"X-Clade-Admin-Token": "wrong-token"}
    )

    expected_response = {"detail": "管理员令牌无效"}
    assert missing_response.status_code == 403
    assert missing_response.json() == expected_response
    assert wrong_response.status_code == 403
    assert wrong_response.json() == expected_response


def test_exact_configured_token_allows_post() -> None:
    response = make_client("expected-token").post(
        "/probe", headers={"X-Clade-Admin-Token": "expected-token"}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_non_ascii_override_returns_403_for_missing_and_wrong_headers() -> None:
    client = make_client("管理员令牌")

    missing_response = client.post("/probe")
    wrong_response = client.post(
        "/probe", headers={"X-Clade-Admin-Token": "wrong-token"}
    )

    expected_response = {"detail": "管理员令牌无效"}
    assert missing_response.status_code == 403
    assert missing_response.json() == expected_response
    assert wrong_response.status_code == 403
    assert wrong_response.json() == expected_response


def test_settings_accepts_visible_ascii_admin_token() -> None:
    settings = Settings(
        CLADE_ADMIN_TOKEN="Letters123!#$%&*+-./:=?@^_~",
        _env_file=None,
    )

    assert settings.clade_admin_token == "Letters123!#$%&*+-./:=?@^_~"


@pytest.mark.parametrize(
    "invalid_token",
    [
        "管理员令牌",
        "line\nbreak",
        " leading-token",
        "trailing-token ",
    ],
    ids=["non-ascii", "control-character", "leading-space", "trailing-space"],
)
def test_settings_rejects_unsafe_admin_token_without_echoing_input(
    invalid_token: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(CLADE_ADMIN_TOKEN=invalid_token, _env_file=None)

    assert invalid_token not in str(exc_info.value)


def test_settings_repr_and_dump_exclude_admin_token() -> None:
    token = "private-token-123!"
    settings = Settings(CLADE_ADMIN_TOKEN=token, _env_file=None)

    assert token not in repr(settings)
    assert "clade_admin_token" not in repr(settings)
    assert token not in repr(settings.model_dump())
    assert "clade_admin_token" not in settings.model_dump()
