"""Environment-repository isolation for tiering and niche analysis."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from ..stages import PostMigrationNicheStage, TieringAndNicheStage


class _RecordingEnvironmentRepository:
    def __init__(self, habitats: list[object], tiles: list[object]) -> None:
        self.habitats = habitats
        self.tiles = tiles
        self.calls: list[str] = []

    def latest_habitats(self) -> list[object]:
        self.calls.append("latest_habitats")
        return self.habitats

    def list_tiles(self) -> list[object]:
        self.calls.append("list_tiles")
        return self.tiles


class _RecordingNicheAnalyzer:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[list[object], list[object]]] = []

    def analyze(
        self,
        species_batch: list[object],
        habitat_data: list[object],
    ) -> object:
        self.calls.append((species_batch, habitat_data))
        return self.result


@pytest.mark.asyncio
async def test_tiering_and_niche_uses_engine_environment_repository(
    monkeypatch,
) -> None:
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    habitats = [object()]
    tiles = [object()]
    injected_repository = _RecordingEnvironmentRepository(habitats, tiles)
    global_repository = _RecordingEnvironmentRepository([object()], [object()])
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    species_batch = [object()]
    tiered = SimpleNamespace(critical=[], focus=[], background=[])
    niche_metrics = object()
    niche_analyzer = _RecordingNicheAnalyzer(niche_metrics)
    context = SimpleNamespace(
        species_batch=species_batch,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        environment_repository=injected_repository,
        watchlist=set(),
        tiering=SimpleNamespace(classify=lambda *_args: tiered),
        niche_analyzer=niche_analyzer,
    )

    await TieringAndNicheStage().execute(context, engine)

    assert context.tiered is tiered
    assert context.all_habitats is habitats
    assert context.all_tiles is tiles
    assert context.niche_metrics is niche_metrics
    assert injected_repository.calls == ["latest_habitats", "list_tiles"]
    assert global_repository.calls == []
    assert niche_analyzer.calls == [(species_batch, habitats)]


@pytest.mark.asyncio
async def test_post_migration_niche_uses_engine_environment_repository(
    monkeypatch,
) -> None:
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    habitats = [object()]
    injected_repository = _RecordingEnvironmentRepository(habitats, [])
    global_repository = _RecordingEnvironmentRepository([object()], [])
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    species_batch = [object()]
    niche_metrics = object()
    niche_analyzer = _RecordingNicheAnalyzer(niche_metrics)
    context = SimpleNamespace(
        migration_count=1,
        species_batch=species_batch,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        environment_repository=injected_repository,
        niche_analyzer=niche_analyzer,
    )

    await PostMigrationNicheStage().execute(context, engine)

    assert context.all_habitats is habitats
    assert context.niche_metrics is niche_metrics
    assert injected_repository.calls == ["latest_habitats"]
    assert global_repository.calls == []
    assert niche_analyzer.calls == [(species_batch, habitats)]
