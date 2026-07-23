"""Repository-isolation coverage for the speciation stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from ..stages import SpeciationStage


class _RecordingSpeciesRepository:
    def __init__(self, species: list[object]) -> None:
        self.species = species
        self.list_calls = 0

    def list_species(self) -> list[object]:
        self.list_calls += 1
        return self.species


class _SpeciationService:
    def __init__(self, branching_events: list[object]) -> None:
        self.branching_events = branching_events
        self.calls: list[dict[str, object]] = []

    async def process_async(self, **kwargs) -> list[object]:
        self.calls.append(kwargs)
        return self.branching_events


def test_speciation_stage_uses_injected_species_repository(monkeypatch) -> None:
    existing_species = SimpleNamespace(
        status="alive",
        lineage_code="SP-A",
        common_name="alpha",
        parent_code=None,
        morphology_stats={},
    )
    new_species = SimpleNamespace(
        status="alive",
        lineage_code="SP-B",
        common_name="beta",
        parent_code="SP-A",
        morphology_stats={},
    )
    repository_species = [existing_species, new_species]

    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _RecordingSpeciesRepository(repository_species)
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )

    injected_repository = _RecordingSpeciesRepository(repository_species)
    branching_events = [{"parent": "SP-A", "child": "SP-B"}]
    speciation_service = _SpeciationService(branching_events)
    context = SimpleNamespace(
        species_batch=[existing_species],
        modifiers={},
        critical_results=[],
        focus_results=[],
        combined_results=[],
        turn_index=7,
        map_changes=[],
        major_events=[],
        pressures=[],
        trophic_interactions=[],
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        _use_embedding_integration=False,
        speciation=speciation_service,
        species_repository=injected_repository,
    )
    food_web_updates: list[tuple[list[object], object]] = []
    stage = SpeciationStage()

    def record_food_web_update(
        species: list[object],
        _context: object,
        _engine: object,
        repository: object,
    ) -> None:
        food_web_updates.append((species, repository))

    monkeypatch.setattr(
        stage,
        "_integrate_new_species_to_food_web",
        record_food_web_update,
    )

    asyncio.run(stage.execute(context, engine))

    assert injected_repository.list_calls == 1
    assert global_repository.list_calls == 0
    assert context.branching_events == branching_events
    assert context.species_batch == [existing_species, new_species]
    assert food_web_updates == [([new_species], injected_repository)]
    assert len(speciation_service.calls) == 1
