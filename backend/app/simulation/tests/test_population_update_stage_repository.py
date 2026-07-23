"""Regression coverage for PopulationUpdateStage repository isolation."""

import importlib
from types import SimpleNamespace

import pytest

from ...core import container as container_module
from ...models.species import Species
from ...repositories import species_repository as species_repository_module
from ...schemas.requests import TurnCommand
from ..context import SimulationContext
from ..species import MortalityResult
from ..stages import PopulationUpdateStage


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str, int]] = []

    def upsert(self, species: Species) -> Species:
        self.upserts.append(
            (
                species.lineage_code,
                species.status,
                int(species.morphology_stats["population"]),
            )
        )
        return species


class _StaticReproductionService:
    def update_environmental_modifier(self, temp_change, sea_level_change):
        return None

    def update_resource_boost(self, modifiers):
        return None

    def apply_reproduction(
        self,
        species_batch,
        niche_data,
        survival_rates,
        *,
        habitat_manager,
        turn_index,
    ):
        return {
            species.lineage_code: int(species.morphology_stats["population"])
            for species in species_batch
        }


class _RecordingEnvironmentRepository:
    def __init__(self, tiles: list[object]) -> None:
        self.tiles = tiles
        self.calls: list[str] = []

    def list_tiles(self) -> list[object]:
        self.calls.append("list_tiles")
        return self.tiles


class _RecordingResourceManager:
    def __init__(self) -> None:
        self.update_calls: list[tuple[list[object], dict[int, float], int]] = []

    def update_resource_dynamics(
        self,
        tiles: list[object],
        consumption_by_tile: dict[int, float],
        turn_index: int,
    ) -> None:
        self.update_calls.append((tiles, consumption_by_tile, turn_index))

    def get_stats(self) -> dict[str, int]:
        return {}


@pytest.mark.asyncio
async def test_population_update_uses_injected_species_repository(monkeypatch):
    injected_repository = _RecordingSpeciesRepository()
    module_global_repository = _RecordingSpeciesRepository()
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        module_global_repository,
    )

    ecology_config = SimpleNamespace(enable_kin_competition=False)
    config_service = SimpleNamespace(get_ecology_balance=lambda: ecology_config)
    monkeypatch.setattr(
        container_module,
        "get_container",
        lambda: SimpleNamespace(config_service=config_service),
    )

    species = Species(
        lineage_code="INJECTED_REPOSITORY",
        latin_name="Injectus repositorius",
        common_name="injected repository species",
        description="Population repository isolation test species",
        morphology_stats={
            "population": 1_000,
            "carrying_capacity": 1_000,
            "body_length_cm": 10.0,
            "body_weight_g": 100.0,
        },
        abstract_traits={},
        hidden_traits={},
        ecological_vector=[],
    )
    context = SimulationContext(
        turn_index=9,
        command=TurnCommand(rounds=1),
    )
    context.species_batch = [species]
    context.combined_results = [
        MortalityResult(
            species=species,
            initial_population=1_000,
            deaths=1_000,
            survivors=0,
            death_rate=1.0,
        )
    ]
    engine = SimpleNamespace(
        species_repository=injected_repository,
        reproduction_service=_StaticReproductionService(),
        speciation=SimpleNamespace(_config=None),
        migration_advisor=SimpleNamespace(
            update_decline_streak=lambda lineage_code, death_rate, growth_rate: None,
        ),
        resource_manager=None,
    )

    await PopulationUpdateStage().execute(context, engine)

    assert injected_repository.upserts == [
        ("INJECTED_REPOSITORY", "alive", 0),
        ("INJECTED_REPOSITORY", "extinct", 0),
    ]
    assert module_global_repository.upserts == []


def test_resource_dynamics_uses_injected_environment_repository(monkeypatch):
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    tiles = [object()]
    injected_repository = _RecordingEnvironmentRepository(tiles)
    global_repository = _RecordingEnvironmentRepository([object()])
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    resource_manager = _RecordingResourceManager()
    context = SimpleNamespace(combined_results=[], turn_index=9)
    engine = SimpleNamespace(
        environment_repository=injected_repository,
        resource_manager=resource_manager,
    )

    PopulationUpdateStage()._update_resource_dynamics(context, engine)

    assert injected_repository.calls == ["list_tiles"]
    assert global_repository.calls == []
    assert resource_manager.update_calls == [(tiles, {}, 9)]
