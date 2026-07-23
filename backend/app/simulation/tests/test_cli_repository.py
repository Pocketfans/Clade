"""Repository isolation tests for the simulation command-line runner."""

import importlib
from types import SimpleNamespace

import pytest

from ..cli import run_simulation


class _RecordingSpeciesRepository:
    def __init__(self, species=None):
        self.species = list(species or [])
        self.list_calls = 0

    def list_species(self):
        self.list_calls += 1
        return self.species


class _RecordingEnvironmentRepository:
    def __init__(self, state=None):
        self.state = state
        self.get_state_calls = 0

    def get_state(self):
        self.get_state_calls += 1
        return self.state


@pytest.mark.asyncio
async def test_run_simulation_uses_engine_repositories(monkeypatch):
    """CLI statistics must read from the repositories owned by its engine."""
    engine_module = importlib.import_module("app.simulation.engine")
    stage_config_module = importlib.import_module("app.simulation.stage_config")
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )

    species = [
        SimpleNamespace(status="alive"),
        SimpleNamespace(status="extinct"),
    ]
    map_state = SimpleNamespace(global_avg_temperature=21.5, sea_level=4.0)
    injected_species_repository = _RecordingSpeciesRepository(species)
    global_species_repository = _RecordingSpeciesRepository()
    injected_environment_repository = _RecordingEnvironmentRepository(map_state)
    global_environment_repository = _RecordingEnvironmentRepository()

    class FakeEngine:
        def __init__(self):
            self.species_repository = injected_species_repository
            self.environment_repository = injected_environment_repository

        async def run_turns_async(self, _command):
            return []

    monkeypatch.setattr(engine_module, "SimulationEngine", FakeEngine)
    monkeypatch.setattr(
        stage_config_module,
        "load_mode_with_parameters",
        lambda *_args, **_kwargs: ([], {}),
    )
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_species_repository,
    )
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_environment_repository,
    )

    result = await run_simulation(mode="standard", turns=1, seed=42)

    assert result.success is True
    assert result.initial_species_count == 1
    assert result.final_species_count == 1
    assert result.extinct_species_count == 1
    assert result.final_temperature == 21.5
    assert result.final_sea_level == 4.0
    assert injected_species_repository.list_calls == 2
    assert injected_environment_repository.get_state_calls == 1
    assert global_species_repository.list_calls == 0
    assert global_environment_repository.get_state_calls == 0
