"""Repository isolation tests for the simulation regression runner."""

import importlib
from types import SimpleNamespace

import pytest

from ..regression_test import RegressionTestRunner


class _RecordingSpeciesRepository:
    def __init__(self, species=None):
        self.species = list(species or [])
        self.list_calls = 0

    def list_species(self):
        self.list_calls += 1
        return self.species


@pytest.mark.asyncio
async def test_regression_runner_uses_engine_species_repository(monkeypatch):
    """Captured snapshots must describe the engine being exercised."""
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    species = SimpleNamespace(
        lineage_code="SP007",
        common_name="Test species",
        status="alive",
        trophic_level=2.0,
        habitat_type="terrestrial",
        morphology_stats={"population": 25, "body_weight_g": 3.0},
    )
    injected_repository = _RecordingSpeciesRepository([species])
    global_repository = _RecordingSpeciesRepository()
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )
    original_callback = object()
    report = SimpleNamespace(
        turn_index=4,
        species=[],
        branching_events=[],
        sea_level=1.5,
        global_temperature=19.0,
    )

    class FakeEngine:
        def __init__(self):
            self.species_repository = injected_repository
            self._event_callback = original_callback

        async def run_turns_async(self, _command):
            return [report]

    engine = FakeEngine()

    snapshots = await RegressionTestRunner().run_engine_with_snapshots(
        engine,
        command=object(),
        capture_callback=None,
    )

    assert injected_repository.list_calls == 1
    assert global_repository.list_calls == 0
    assert snapshots[0].species_data["SP007"].population == 25
    assert snapshots[0].total_biomass == 75
    assert engine._event_callback is original_callback
