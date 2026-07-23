"""Repository-isolation coverage for the auto-hybridization stage."""

from __future__ import annotations

import asyncio
import importlib
import random
from types import SimpleNamespace

from ..stages import AutoHybridizationStage


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.upserted_species: list[object] = []

    def upsert(self, species: object) -> None:
        self.upserted_species.append(species)


class _HybridizationService:
    def __init__(self, hybrid: object) -> None:
        self.hybrid = hybrid

    def can_hybridize(self, _first: object, _second: object) -> tuple[bool, float]:
        return True, 0.5

    def create_hybrid(
        self,
        _first: object,
        _second: object,
        _turn_index: int,
        *,
        existing_codes: set[str],
    ) -> object:
        return self.hybrid


class _TensorCompute:
    def __init__(self, candidate: object) -> None:
        self.candidate = candidate

    def find_hybrid_candidates(self, **_kwargs) -> tuple[list[object], object]:
        return [self.candidate], SimpleNamespace(total_time_ms=0.0)


def test_auto_hybridization_stage_uses_injected_species_repository(
    monkeypatch,
) -> None:
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _RecordingSpeciesRepository()
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )

    first_parent = SimpleNamespace(
        id=1,
        status="alive",
        lineage_code="SP-A",
        common_name="alpha",
        morphology_stats={"population": 1000},
        parent_code=None,
        created_turn=0,
    )
    second_parent = SimpleNamespace(
        id=2,
        status="alive",
        lineage_code="SP-B",
        common_name="beta",
        morphology_stats={"population": 1000},
        parent_code=None,
        created_turn=0,
    )
    hybrid = SimpleNamespace(
        lineage_code="SP-H",
        common_name="hybrid",
        morphology_stats={},
    )
    candidate = SimpleNamespace(
        species1_code="SP-A",
        species2_code="SP-B",
        sympatry_ratio=1.0,
        fertility=0.5,
    )
    hybridization_service = _HybridizationService(hybrid)

    hybridization_module = importlib.import_module(
        "app.services.species.hybridization"
    )
    monkeypatch.setattr(
        hybridization_module,
        "HybridizationService",
        lambda *_args, **_kwargs: hybridization_service,
    )
    tensor_module = importlib.import_module("app.tensor.hybridization_tensor")
    monkeypatch.setattr(
        tensor_module,
        "get_hybridization_tensor_compute",
        lambda: _TensorCompute(candidate),
    )
    monkeypatch.setattr(random, "random", lambda: 0.0)

    injected_repository = _RecordingSpeciesRepository()
    config = SimpleNamespace(
        auto_hybridization_chance=1.0,
        hybridization_success_rate=1.0,
        max_hybrids_per_turn=1,
        min_population_for_hybridization=500,
        max_hybrids_per_parent_per_turn=1,
        min_offspring_population=1,
    )
    context = SimpleNamespace(
        species_batch=[first_parent, second_parent],
        all_habitats=[],
        turn_index=7,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        speciation=SimpleNamespace(_config=config),
        router=None,
        gene_diversity_service=object(),
        species_repository=injected_repository,
    )
    enhancement_repositories: list[object] = []
    stage = AutoHybridizationStage()

    async def record_enhancement_repository(
        _context: object,
        _engine: object,
        repository: object,
    ) -> None:
        enhancement_repositories.append(repository)

    monkeypatch.setattr(
        stage,
        "_enhance_hybrid_descriptions",
        record_enhancement_repository,
    )

    asyncio.run(stage.execute(context, engine))

    assert injected_repository.upserted_species == [
        hybrid,
        first_parent,
        second_parent,
    ]
    assert global_repository.upserted_species == []
    assert context.auto_hybrids == [hybrid]
    assert context.species_batch == [first_parent, second_parent, hybrid]
    assert hybrid.morphology_stats["population"] == 100
    assert first_parent.morphology_stats["population"] == 950
    assert second_parent.morphology_stats["population"] == 950
    assert enhancement_repositories == [injected_repository]
