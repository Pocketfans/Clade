"""Repository-isolation coverage for the population snapshot stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from ..stages import SavePopulationSnapshotStage


class _RecordingSpeciesRepository:
    def __init__(self, species: list[object]) -> None:
        self.species = species
        self.list_calls = 0

    def list_species(self) -> list[object]:
        self.list_calls += 1
        return self.species


class _RecordingPopulationSnapshotService:
    def __init__(self, species_repository: object) -> None:
        self.species_repository = species_repository
        self.save_calls: list[tuple[list[object], int]] = []

    def save_snapshots(self, species: list[object], turn_index: int) -> None:
        self.save_calls.append((species, turn_index))


def test_save_population_snapshot_stage_uses_injected_species_repository(
    monkeypatch,
) -> None:
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _RecordingSpeciesRepository([object()])
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )

    snapshot_services: list[_RecordingPopulationSnapshotService] = []
    stages_module = importlib.import_module("app.simulation.stages")

    def create_snapshot_service(
        species_repository: object,
    ) -> _RecordingPopulationSnapshotService:
        service = _RecordingPopulationSnapshotService(species_repository)
        snapshot_services.append(service)
        return service

    monkeypatch.setattr(
        stages_module,
        "PopulationSnapshotService",
        create_snapshot_service,
    )

    repository_species = [SimpleNamespace(lineage_code="SP-A")]
    injected_repository = _RecordingSpeciesRepository(repository_species)
    context = SimpleNamespace(
        turn_index=7,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(species_repository=injected_repository)

    asyncio.run(SavePopulationSnapshotStage().execute(context, engine))

    assert injected_repository.list_calls == 1
    assert global_repository.list_calls == 0
    assert len(snapshot_services) == 1
    assert snapshot_services[0].species_repository is injected_repository
    assert snapshot_services[0].save_calls == [(repository_species, 7)]
