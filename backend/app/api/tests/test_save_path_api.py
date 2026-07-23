from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from fastapi.testclient import TestClient

from ...main import app
from ...security.save_paths import (
    InvalidSaveNameError,
    SavePathError,
    resolve_save_directory,
    validate_save_name,
)
from ..simulation import (
    _cleanup_old_autosaves,
    _is_numbered_autosave,
    _perform_autosave,
    autosave_prefixes,
    build_autosave_name,
)


PRIVATE_PATH_SENTINEL = r"C:\private\clade-tree\saves"


def test_short_autosave_name_keeps_the_existing_format() -> None:
    base = "原初大陆"

    assert build_autosave_name(base, 2) == f"{base}_autosave_2"


def test_long_autosave_name_is_valid_bounded_and_deterministic() -> None:
    base = "界" * 50

    first = build_autosave_name(base, 123)
    second = build_autosave_name(base, 123)

    assert first == second
    assert len(first) <= 50
    assert first.endswith("_autosave_123")
    assert validate_save_name(first) == first
    assert first in {prefix + "123" for prefix in autosave_prefixes(base)}


def test_long_autosave_bases_with_the_same_prefix_do_not_collide() -> None:
    left = build_autosave_name("A" * 49 + "B", 1)
    right = build_autosave_name("A" * 49 + "C", 1)

    assert left != right


def test_autosave_name_uses_bounded_fallback_for_multi_digit_slot() -> None:
    base = "a" * 39
    legacy, bounded = autosave_prefixes(base)

    assert len(legacy) == 49
    assert build_autosave_name(base, 1) == f"{base}_autosave_1"
    assert build_autosave_name(base, 123) == bounded + "123"
    assert len(build_autosave_name(base, 123)) <= 50


@pytest.mark.parametrize("base", ["short", "L" * 50])
def test_autosave_prefixes_always_return_legacy_then_bounded(base: str) -> None:
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]

    assert autosave_prefixes(base) == (
        f"{base}_autosave_",
        f"{base[:20]}_{digest}_autosave_",
    )


@pytest.mark.parametrize("slot", [0, -1])
def test_autosave_name_rejects_non_positive_slots_without_echoing_input(
    slot: int,
) -> None:
    base = "private-base-name"

    with pytest.raises(ValueError) as exc_info:
        build_autosave_name(base, slot)

    assert base not in str(exc_info.value)
    assert str(slot) not in str(exc_info.value)


def test_autosave_name_rejects_unbounded_slot_without_echoing_input() -> None:
    base = "private-base-name"
    slot = int("9" * 51)

    with pytest.raises(InvalidSaveNameError) as exc_info:
        build_autosave_name(base, slot)

    assert base not in str(exc_info.value)
    assert str(slot) not in str(exc_info.value)


def test_perform_autosave_uses_bounded_name_and_authoritative_turn() -> None:
    base = "A" * 50
    config = SimpleNamespace(
        autosave_enabled=True,
        autosave_interval=1,
        autosave_max_slots=3,
    )
    session = SimpleNamespace(
        current_save_name=base,
        increment_autosave_counter=MagicMock(return_value=123),
    )
    save_manager = MagicMock()
    save_manager.list_saves.return_value = []
    container = SimpleNamespace(
        config_service=SimpleNamespace(get_ui_config=MagicMock(return_value=config)),
        simulation_engine=SimpleNamespace(turn_counter=456),
        save_manager=save_manager,
    )

    assert _perform_autosave(455, session, container) is True

    expected_name = build_autosave_name(base, 123)
    save_manager.save_game.assert_called_once_with(expected_name, turn_index=456)
    assert len(expected_name) <= 50
    assert expected_name != autosave_prefixes(base)[0] + "123"


def test_cleanup_old_autosaves_matches_both_prefixes_and_numeric_slots() -> None:
    base = "a" * 39
    legacy, bounded = autosave_prefixes(base)
    saves = [
        {"name": legacy + "1", "timestamp": 50},
        {"name": bounded + "2", "timestamp": 40},
        {"name": legacy + "3", "timestamp": 30},
        {"name": bounded + "4", "timestamp": 20},
        {"name": legacy, "timestamp": 10},
        {"name": legacy + "latest", "timestamp": 100},
        {"name": bounded + "１２", "timestamp": 100},
        {"name": f"{base}x_autosave_5", "timestamp": 100},
    ]
    save_manager = MagicMock()
    save_manager.list_saves.return_value = saves
    container = SimpleNamespace(save_manager=save_manager)

    _cleanup_old_autosaves(base, 2, container)

    assert save_manager.delete_save.call_args_list == [
        call(legacy + "3"),
        call(bounded + "4"),
    ]


def test_autosave_match_checks_later_overlapping_prefixes() -> None:
    assert _is_numbered_autosave(
        "base_autosave_12",
        ("base_", "base_autosave_"),
    ) is True


@pytest.fixture
def client(mock_container, mock_session):
    app.state.container = mock_container
    app.state.session = mock_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        del app.state.container
        del app.state.session


@pytest.fixture
def stub_complex_route_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep create/load error tests focused on save-manager boundaries."""
    from ...core import database, seed
    from ...services.analytics import achievements, game_hints
    from ...services.species import dispersal_engine, habitat_manager
    from ...services.system import divine_energy, divine_progression

    fake_db_session = MagicMock()
    fake_db_session.exec.return_value.all.return_value = []

    @contextmanager
    def fake_session_scope():
        yield fake_db_session

    monkeypatch.setattr(database, "session_scope", fake_session_scope)
    monkeypatch.setattr(seed, "seed_defaults", lambda: None)
    monkeypatch.setattr(divine_energy.energy_service, "reset", lambda: None)
    monkeypatch.setattr(divine_progression.divine_progression_service, "reset", lambda: None)
    monkeypatch.setattr(achievements.achievement_service, "reset", lambda: None)
    monkeypatch.setattr(game_hints.game_hints_service, "clear_cooldown", lambda: None)
    monkeypatch.setattr(habitat_manager.habitat_manager, "clear_all_caches", lambda: None)
    monkeypatch.setattr(dispersal_engine.dispersal_engine, "clear_caches", lambda: None)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/saves/create", {"save_name": "../outside", "scenario": "原初大陆"}),
        ("post", "/api/saves/save", {"save_name": r"..\outside"}),
        ("post", "/api/saves/load", {"save_name": "NUL"}),
        ("delete", "/api/saves/CON", None),
    ],
)
def test_save_routes_reject_unsafe_names_before_manager_access(
    client: TestClient,
    mock_container,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    response = client.request(method.upper(), path, json=body)

    assert response.status_code in {400, 422}
    assert response.json().get("detail")
    mock_container.save_manager.create_save.assert_not_called()
    mock_container.save_manager.save_game.assert_not_called()
    mock_container.save_manager.load_game.assert_not_called()
    mock_container.save_manager.delete_save.assert_not_called()


def test_unicode_save_name_reaches_the_manager_unchanged(
    client: TestClient,
    mock_container,
) -> None:
    mock_container.simulation_engine.turn_counter = 4

    response = client.post("/api/saves/save", json={"save_name": "历史 存档-1"})

    assert response.status_code == 200
    mock_container.save_manager.save_game.assert_called_once_with(
        "历史 存档-1",
        turn_index=4,
    )


@pytest.mark.parametrize(
    ("method", "path", "body", "manager_method"),
    [
        ("post", "/api/saves/create", {"save_name": "safe-create"}, "create_save"),
        ("post", "/api/saves/save", {"save_name": "safe-save"}, "save_game"),
        ("post", "/api/saves/load", {"save_name": "safe-load"}, "load_game"),
        ("delete", "/api/saves/safe-delete", None, "delete_save"),
    ],
)
def test_save_routes_map_manager_path_errors_to_safe_422(
    client: TestClient,
    mock_container,
    stub_complex_route_side_effects: None,
    method: str,
    path: str,
    body: dict | None,
    manager_method: str,
) -> None:
    manager_call = getattr(mock_container.save_manager, manager_method)
    with pytest.raises(SavePathError) as exc_info:
        resolve_save_directory(PRIVATE_PATH_SENTINEL, PRIVATE_PATH_SENTINEL)
    manager_call.side_effect = exc_info.value

    response = client.request(method.upper(), path, json=body)

    assert response.status_code == 422
    assert response.json().get("detail")
    assert PRIVATE_PATH_SENTINEL not in response.text


@pytest.mark.parametrize(
    ("method", "path", "body", "manager_method", "expected_detail"),
    [
        (
            "post",
            "/api/saves/create",
            {"save_name": "safe-create"},
            "create_save",
            "创建存档失败",
        ),
        (
            "post",
            "/api/saves/save",
            {"save_name": "safe-save"},
            "save_game",
            "保存游戏失败",
        ),
        (
            "post",
            "/api/saves/load",
            {"save_name": "safe-load"},
            "load_game",
            "加载存档失败",
        ),
        (
            "delete",
            "/api/saves/safe-delete",
            None,
            "delete_save",
            "删除存档失败",
        ),
    ],
)
def test_save_routes_hide_generic_error_paths_from_response_and_logs(
    client: TestClient,
    mock_container,
    stub_complex_route_side_effects: None,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
    body: dict | None,
    manager_method: str,
    expected_detail: str,
) -> None:
    manager_call = getattr(mock_container.save_manager, manager_method)
    manager_call.side_effect = RuntimeError(f"failed under {PRIVATE_PATH_SENTINEL}")

    with caplog.at_level(logging.ERROR, logger="app.api.simulation"):
        response = client.request(method.upper(), path, json=body)

    assert response.status_code == 500
    assert response.json()["detail"] == expected_detail
    assert PRIVATE_PATH_SENTINEL not in response.text
    assert PRIVATE_PATH_SENTINEL not in caplog.text


def test_delete_save_returns_manager_result_as_found(
    client: TestClient,
    mock_container,
) -> None:
    mock_container.save_manager.delete_save.return_value = False

    response = client.delete("/api/saves/missing-save")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "deleted": "missing-save",
        "found": False,
    }
    mock_container.save_manager.delete_save.assert_called_once_with("missing-save")
