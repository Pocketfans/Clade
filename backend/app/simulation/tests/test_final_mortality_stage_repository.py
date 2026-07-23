"""Environment-repository isolation for final mortality analysis."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from ..stages import FinalMortalityStage


class _RecordingEnvironmentRepository:
    def __init__(self, habitats: list[object]) -> None:
        self.habitats = habitats
        self.calls: list[str] = []

    def latest_habitats(self) -> list[object]:
        self.calls.append("latest_habitats")
        return self.habitats


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


class _RecordingTileMortality:
    def __init__(self) -> None:
        self.build_calls: list[tuple[list[object], list[object], list[object]]] = []

    def build_matrices(
        self,
        species_batch: list[object],
        tiles: list[object],
        habitats: list[object],
    ) -> None:
        self.build_calls.append((species_batch, tiles, habitats))

    def evaluate(self, *_args, **_kwargs) -> list[object]:
        return []


@pytest.mark.asyncio
async def test_final_mortality_uses_engine_environment_repository(
    monkeypatch,
) -> None:
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    habitats = [object()]
    injected_repository = _RecordingEnvironmentRepository(habitats)
    global_repository = _RecordingEnvironmentRepository([object()])
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    species_batch = [object()]
    tiles = [object()]
    niche_metrics = object()
    niche_analyzer = _RecordingNicheAnalyzer(niche_metrics)
    tile_mortality = _RecordingTileMortality()
    context = SimpleNamespace(
        migration_count=1,
        species_batch=species_batch,
        all_tiles=tiles,
        tiered=SimpleNamespace(critical=[], focus=[], background=[]),
        modifiers={},
        niche_metrics=object(),
        trophic_interactions={},
        extinct_codes=set(),
        turn_index=1,
        preliminary_mortality=[],
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        environment_repository=injected_repository,
        niche_analyzer=niche_analyzer,
        _use_tile_based_mortality=True,
        tile_mortality=tile_mortality,
    )

    await FinalMortalityStage().execute(context, engine)

    assert context.all_habitats is habitats
    assert context.niche_metrics is niche_metrics
    assert injected_repository.calls == ["latest_habitats", "latest_habitats"]
    assert global_repository.calls == []
    assert niche_analyzer.calls == [(species_batch, habitats)]
    assert tile_mortality.build_calls == [(species_batch, tiles, habitats)]
