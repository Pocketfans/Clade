"""Container wiring coverage for simulation-engine repositories."""

from __future__ import annotations

from app.core.container import ServiceContainer
from app.repositories.environment_repository import EnvironmentRepository
from app.repositories.species_repository import SpeciesRepository


def test_simulation_engine_uses_container_repositories() -> None:
    container = ServiceContainer()
    species_repository = SpeciesRepository()
    environment_repository = EnvironmentRepository()
    container.override("species_repository", species_repository)
    container.override("environment_repository", environment_repository)

    engine = container.simulation_engine

    assert engine.species_repository is species_repository
    assert engine.environment_repository is environment_repository
