"""Regression coverage for core simulation data invariants."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from ...core import container as container_module
from ...core import database
from ...models.species import Species
from ...repositories.species_repository import species_repository
from ...schemas.requests import TurnCommand
from ..context import SimulationContext
from ..species import MortalityResult
from ..stages import PopulationUpdateStage


class _ExtremeReproductionService:
    """Provide deterministic extreme inputs around the real population Stage."""

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
            "OVER_CAPACITY": 1_000_000,
            "BELOW_ZERO": -1_000_000,
        }


def _species(lineage_code: str) -> Species:
    return Species(
        lineage_code=lineage_code,
        latin_name=f"{lineage_code.title()} testus",
        common_name=lineage_code,
        description="Core invariant test species",
        morphology_stats={
            "population": 1_000,
            "carrying_capacity": 500,
            "body_length_cm": 10.0,
            "body_weight_g": 100.0,
        },
        abstract_traits={},
        hidden_traits={},
        ecological_vector=[],
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_population_update_preserves_bounded_persistence_invariant(monkeypatch):
    """Population must stay bounded and identical in memory and storage."""

    test_database_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(database, "engine", test_database_engine)
    SQLModel.metadata.create_all(test_database_engine)

    ecology_config = SimpleNamespace(enable_kin_competition=False)
    config_service = SimpleNamespace(get_ecology_balance=lambda: ecology_config)
    monkeypatch.setattr(
        container_module,
        "get_container",
        lambda: SimpleNamespace(config_service=config_service),
    )

    over_capacity = _species("OVER_CAPACITY")
    below_zero = _species("BELOW_ZERO")
    with Session(test_database_engine, expire_on_commit=False) as session:
        session.add_all([over_capacity, below_zero])
        session.commit()

    context = SimulationContext(
        turn_index=7,
        command=TurnCommand(rounds=1),
    )
    context.species_batch = [over_capacity, below_zero]
    context.combined_results = [
        MortalityResult(
            species=over_capacity,
            initial_population=1_000,
            deaths=0,
            survivors=1_000,
            death_rate=-1.0,
        ),
        MortalityResult(
            species=below_zero,
            initial_population=1_000,
            deaths=1_000,
            survivors=0,
            death_rate=2.0,
        ),
    ]

    engine = SimpleNamespace(
        species_repository=species_repository,
        reproduction_service=_ExtremeReproductionService(),
        speciation=SimpleNamespace(_config=None),
        migration_advisor=SimpleNamespace(
            update_decline_streak=lambda lineage_code, death_rate, growth_rate: None,
        ),
        resource_manager=None,
    )

    try:
        await PopulationUpdateStage().execute(context, engine)

        expected_populations = {
            "OVER_CAPACITY": 500,
            "BELOW_ZERO": 0,
        }
        assert context.new_populations == expected_populations

        for result in context.combined_results:
            lineage_code = result.species.lineage_code
            expected_population = expected_populations[lineage_code]

            assert 0 <= result.final_population <= result.adjusted_k
            assert result.final_population == expected_population
            assert result.species.morphology_stats["population"] == expected_population

            persisted = species_repository.get_by_lineage(lineage_code)
            assert persisted is not None
            assert persisted.morphology_stats["population"] == expected_population
    finally:
        test_database_engine.dispose()
