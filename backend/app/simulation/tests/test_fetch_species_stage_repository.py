"""Repository-isolation coverage for the fetch-species stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from .. import stages as stages_module
from ..stages import FetchSpeciesStage


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.list_calls = 0

    def list_species(self) -> list[object]:
        self.list_calls += 1
        return []


class _UnexpectedGlobalSpeciesRepository:
    def list_species(self) -> list[object]:
        raise AssertionError("FetchSpeciesStage must not use the global repository")


class _RecordingInterventionService:
    repositories: list[object] = []
    species_batches: list[list[object]] = []

    def __init__(self, species_repository: object, event_callback) -> None:
        self.repositories.append(species_repository)

    def update_intervention_status(self, species_list: list[object]) -> None:
        self.species_batches.append(species_list)


def test_fetch_species_stage_uses_engine_species_repository(monkeypatch) -> None:
    repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    repository = _RecordingSpeciesRepository()
    context = SimpleNamespace(
        turn_index=3,
        command=SimpleNamespace(pressures=[]),
        modifiers={},
        temp_delta=0.0,
        sea_delta=0.0,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        species_repository=repository,
        _use_embedding_integration=False,
    )
    monkeypatch.setattr(
        repository_module,
        "species_repository",
        _UnexpectedGlobalSpeciesRepository(),
    )
    monkeypatch.setattr(
        stages_module,
        "InterventionService",
        _RecordingInterventionService,
    )
    _RecordingInterventionService.repositories = []
    _RecordingInterventionService.species_batches = []

    asyncio.run(FetchSpeciesStage().execute(context, engine))

    assert repository.list_calls == 1
    assert context.all_species == []
    assert context.species_batch == []
    assert _RecordingInterventionService.repositories == [repository]
    assert _RecordingInterventionService.species_batches == [[]]
