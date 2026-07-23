"""Repository-isolation coverage for the food-web stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from ..stages import FoodWebStage


class _RecordingSpeciesRepository:
    def __init__(self, species: list[object]) -> None:
        self.species = species
        self.list_calls = 0

    def list_species(self) -> list[object]:
        self.list_calls += 1
        return self.species


class _UnexpectedGlobalSpeciesRepository:
    def list_species(self) -> list[object]:
        raise AssertionError("FoodWebStage must not use the global repository")


class _RecordingFoodWebManager:
    def __init__(self) -> None:
        self.repositories: list[object] = []

    def maintain_food_web(
        self,
        all_species: list[object],
        species_repository: object,
        turn_index: int,
        **_kwargs,
    ) -> SimpleNamespace:
        self.repositories.append(species_repository)
        return SimpleNamespace(
            new_producers=[],
            prey_shortage_species=[],
            bottleneck_warnings=[],
            health_score=1.0,
            total_links=0,
            orphaned_consumers=[],
        )

    def get_changes(self) -> list[object]:
        return [object()]

    def generate_trophic_signals(
        self,
        analysis: SimpleNamespace,
        all_species: list[object],
    ) -> dict[str, object]:
        return {}


def _species(lineage_code: str, status: str = "alive") -> SimpleNamespace:
    return SimpleNamespace(
        lineage_code=lineage_code,
        status=status,
        morphology_stats={"tile_ids": []},
    )


def test_food_web_stage_uses_engine_species_repository(monkeypatch) -> None:
    repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    reloaded_species = [_species("alive"), _species("extinct", "extinct")]
    repository = _RecordingSpeciesRepository(reloaded_species)
    food_web_manager = _RecordingFoodWebManager()
    context = SimpleNamespace(
        all_species=[_species("initial")],
        species_batch=[],
        turn_index=4,
        trophic_interactions={},
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        species_repository=repository,
        food_web_manager=food_web_manager,
    )
    monkeypatch.setattr(
        repository_module,
        "species_repository",
        _UnexpectedGlobalSpeciesRepository(),
    )

    asyncio.run(FoodWebStage().execute(context, engine))

    assert food_web_manager.repositories == [repository]
    assert repository.list_calls == 1
    assert context.all_species == reloaded_species
    assert context.species_batch == [reloaded_species[0]]
