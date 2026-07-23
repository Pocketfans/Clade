"""Environment-repository isolation for database maintenance."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from ..stages import DatabaseMaintenanceStage


class _RecordingEnvironmentRepository:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def cleanup_old_habitats(self, keep_turns: int) -> int:
        self.calls.append(("cleanup_old_habitats", keep_turns))
        return 2

    def ensure_indexes(self) -> dict[str, bool]:
        self.calls.append("ensure_indexes")
        return {"habitat_turn": True, "tile_coordinate": False}

    def optimize_database(self) -> dict[str, bool]:
        self.calls.append("optimize_database")
        return {"vacuum": True}


@pytest.mark.asyncio
async def test_database_maintenance_uses_engine_environment_repository(
    monkeypatch,
) -> None:
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    injected_repository = _RecordingEnvironmentRepository()
    global_repository = _RecordingEnvironmentRepository()
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    events: list[tuple[object, ...]] = []
    context = SimpleNamespace(
        turn_index=50,
        emit_event=lambda *args: events.append(args),
    )
    engine = SimpleNamespace(environment_repository=injected_repository)
    stage = DatabaseMaintenanceStage(
        maintenance_interval=10,
        keep_habitat_turns=5,
        enable_vacuum=True,
    )

    await stage.execute(context, engine)

    assert injected_repository.calls == [
        ("cleanup_old_habitats", 5),
        "ensure_indexes",
        "optimize_database",
    ]
    assert global_repository.calls == []
    assert events == [
        ("maintenance", "🔧 数据库维护完成 (清理 2 条记录)", "系统")
    ]
