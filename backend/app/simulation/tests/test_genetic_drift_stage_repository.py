"""Repository-isolation coverage for the genetic-drift stage."""

from __future__ import annotations

import asyncio
import importlib
import random
from types import SimpleNamespace

import pytest

from ..stages import GeneticDriftStage


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.upserted_species: list[object] = []

    def upsert(self, species: object) -> None:
        self.upserted_species.append(species)


def test_genetic_drift_stage_uses_injected_species_repository(monkeypatch) -> None:
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _RecordingSpeciesRepository()
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "choice", lambda values: values[0])
    monkeypatch.setattr(random, "gauss", lambda _mu, _sigma: 0.1)

    injected_repository = _RecordingSpeciesRepository()
    drifting_species = SimpleNamespace(
        status="alive",
        morphology_stats={"population": 500},
        hidden_traits={"resilience": 1.0},
    )
    steady_species = SimpleNamespace(
        status="alive",
        morphology_stats={"population": 2000},
        hidden_traits={"resilience": 2.0},
    )
    species_batch = [drifting_species, steady_species]
    context = SimpleNamespace(species_batch=species_batch)
    engine = SimpleNamespace(species_repository=injected_repository)

    asyncio.run(GeneticDriftStage().execute(context, engine))

    assert context.genetic_drift_count == 1
    assert drifting_species.hidden_traits["resilience"] == pytest.approx(1.1)
    assert steady_species.hidden_traits["resilience"] == 2.0
    assert injected_repository.upserted_species == species_batch
    assert global_repository.upserted_species == []
