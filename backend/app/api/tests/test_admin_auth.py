from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import admin_routes
from app.core.config import get_settings


def make_client(server_token: str | None) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        clade_admin_token=server_token
    )
    app.include_router(admin_routes.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def safe_admin_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        admin_routes,
        "session_scope",
        Mock(side_effect=RuntimeError("admin handler reached session_scope")),
    )
    monkeypatch.setattr(
        admin_routes.environment_repository,
        "ensure_indexes",
        Mock(return_value={}),
    )
    monkeypatch.setattr(
        admin_routes.environment_repository,
        "optimize_database",
        Mock(return_value={"vacuum": False, "analyze": False}),
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/admin/reset", {"keep_saves": True, "keep_map": True}),
        ("/api/admin/drop-database", {"confirm": False}),
        ("/api/admin/optimize-database", {}),
        ("/api/admin/cleanup-habitat-history", {"confirm": False}),
        ("/api/admin/create-indexes", None),
    ],
)
def test_admin_writes_return_503_when_server_token_is_not_configured(
    path: str,
    body: dict[str, bool] | None,
    safe_admin_handlers: None,
) -> None:
    client = make_client(None)

    if body is None:
        response = client.post(path)
    else:
        response = client.post(path, json=body)

    assert response.status_code == 503


def test_wrong_token_is_rejected_before_create_indexes_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_indexes = Mock(
        side_effect=AssertionError("ensure_indexes must not run for a wrong token")
    )
    monkeypatch.setattr(
        admin_routes.environment_repository,
        "ensure_indexes",
        ensure_indexes,
    )

    response = make_client("expected-token").post(
        "/api/admin/create-indexes",
        headers={"X-Clade-Admin-Token": "wrong-token"},
    )

    assert response.status_code == 403
    ensure_indexes.assert_not_called()


def test_correct_token_reaches_create_indexes_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin_routes.environment_repository,
        "ensure_indexes",
        Mock(return_value={"idx_habitats": True}),
    )

    response = make_client("expected-token").post(
        "/api/admin/create-indexes",
        headers={"X-Clade-Admin-Token": "expected-token"},
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 1


def test_admin_health_remains_readable_without_a_token() -> None:
    response = make_client(None).get("/api/admin/health")

    assert response.status_code == 200


def test_openapi_documents_admin_token_header_for_write_route() -> None:
    openapi = make_client(None).get("/openapi.json").json()
    parameters = openapi["paths"]["/api/admin/drop-database"]["post"]["parameters"]

    assert any(
        parameter["name"] == "X-Clade-Admin-Token"
        and parameter["in"] == "header"
        for parameter in parameters
    )
