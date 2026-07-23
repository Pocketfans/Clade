"""Achievement route contract tests for the split API router."""

from unittest.mock import create_autospec

import pytest
from fastapi.testclient import TestClient

from ...main import app
from ...services.analytics import achievements as achievements_module
from ...services.analytics.achievements import (
    AchievementCategory,
    AchievementDefinition,
    AchievementRarity,
    AchievementService,
    AchievementUnlockEvent,
)


@pytest.fixture
def achievement_service(monkeypatch: pytest.MonkeyPatch):
    """Replace only the stateful achievement service boundary."""
    service = create_autospec(AchievementService, instance=True)
    monkeypatch.setattr(achievements_module, "achievement_service", service)
    return service


@pytest.fixture
def client(mock_container, mock_session):
    app.state.container = mock_container
    app.state.session = mock_session
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        if hasattr(app.state, "container"):
            del app.state.container
        if hasattr(app.state, "session"):
            del app.state.session


def _achievement_payload() -> dict:
    return {
        "id": "explorer",
        "name": "探索者",
        "description": "探索三个不同功能",
        "category": "special",
        "rarity": "uncommon",
        "icon": "🧭",
        "target_value": 3,
        "current_value": 3,
        "unlocked": True,
        "unlock_time": "2026-07-20T12:00:00",
        "unlock_turn": 37,
        "hidden": False,
    }


def _unlock_event() -> AchievementUnlockEvent:
    definition = AchievementDefinition(
        id="explorer",
        name="探索者",
        description="探索三个不同功能",
        category=AchievementCategory.SPECIAL,
        rarity=AchievementRarity.UNCOMMON,
        icon="🧭",
        target_value=3,
        hidden=False,
    )
    return AchievementUnlockEvent(
        achievement=definition,
        turn_index=37,
        timestamp="2026-07-20T12:00:00",
    )


def test_get_achievements_preserves_the_service_response(
    client: TestClient,
    achievement_service,
) -> None:
    achievement = _achievement_payload()
    stats = {
        "total": 1,
        "unlocked": 1,
        "percentage": 100.0,
        "by_category": {"special": {"total": 1, "unlocked": 1}},
        "by_rarity": {"uncommon": {"total": 1, "unlocked": 1}},
    }
    achievement_service.get_all_achievements.return_value = [achievement]
    achievement_service.get_stats.return_value = stats

    response = client.get("/api/achievements")

    assert response.status_code == 200
    assert response.json() == {"achievements": [achievement], "stats": stats}


def test_get_unlocked_achievements_uses_the_real_service_contract(
    client: TestClient,
    achievement_service,
) -> None:
    achievement = _achievement_payload()
    achievement_service.get_unlocked_achievements.return_value = [achievement]

    response = client.get("/api/achievements/unlocked")

    assert response.status_code == 200
    assert response.json() == {"achievements": [achievement]}


def test_get_pending_achievements_serializes_unlock_events(
    client: TestClient,
    achievement_service,
) -> None:
    event = _unlock_event()
    achievement_service.get_pending_unlocks.return_value = [event]

    response = client.get("/api/achievements/pending")

    assert response.status_code == 200
    assert response.json() == {
        "events": [
            {
                "achievement": {
                    "id": "explorer",
                    "name": "探索者",
                    "description": "探索三个不同功能",
                    "icon": "🧭",
                    "rarity": "uncommon",
                    "category": "special",
                },
                "turn_index": 37,
                "timestamp": "2026-07-20T12:00:00",
            }
        ]
    }


def test_record_exploration_passes_the_current_turn_and_returns_unlock(
    client: TestClient,
    mock_container,
    achievement_service,
) -> None:
    mock_container.simulation_engine.turn_counter = 37
    achievement_service.record_exploration.return_value = _unlock_event()

    response = client.post("/api/achievements/exploration/genealogy")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "unlocked": {"id": "explorer", "name": "探索者", "icon": "🧭"},
    }
    achievement_service.record_exploration.assert_called_once_with("genealogy", 37)


def test_reset_achievements_preserves_the_legacy_response(
    client: TestClient,
    achievement_service,
) -> None:
    response = client.post("/api/achievements/reset")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "成就进度已重置"}
    achievement_service.reset.assert_called_once_with()
