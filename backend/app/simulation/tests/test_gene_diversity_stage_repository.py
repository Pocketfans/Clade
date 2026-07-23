"""Repository-isolation coverage for the gene-diversity stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from ..stages import GeneDiversityStage


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.upserted_species: list[object] = []

    def upsert(self, species: object) -> None:
        self.upserted_species.append(species)


class _UnexpectedGlobalSpeciesRepository:
    def __init__(self) -> None:
        self.attempted_species: list[object] = []

    def upsert(self, species: object) -> None:
        self.attempted_species.append(species)
        raise AssertionError("module-level species_repository must not be used")


class _RecordingGeneDiversityService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, int, float, int]] = []

    def update_per_turn(
        self,
        species: object,
        *,
        population: int,
        death_rate: float,
        turn_index: int,
    ) -> dict[str, object]:
        self.calls.append((species, population, death_rate, turn_index))
        return {
            "old": 0.4,
            "new": 0.45,
            "delta": 0.05,
            "reason": "repository isolation test",
        }


def test_gene_diversity_stage_uses_injected_species_repository(monkeypatch) -> None:
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _UnexpectedGlobalSpeciesRepository()
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )

    repository = _RecordingSpeciesRepository()
    gene_diversity_service = _RecordingGeneDiversityService()
    first_species = SimpleNamespace(
        lineage_code="SP-A",
        common_name="alpha",
        morphology_stats={"population": 1200},
    )
    second_species = SimpleNamespace(
        lineage_code="SP-B",
        common_name="beta",
        morphology_stats={"population": 3400},
    )
    species_batch = [first_species, second_species]
    context = SimpleNamespace(
        species_batch=species_batch,
        combined_results=[
            {"lineage_code": "SP-A", "death_rate": 0.25},
            {"lineage_code": "SP-B", "death_rate": 0.5},
        ],
        turn_index=7,
        plugin_data={},
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        gene_diversity_service=gene_diversity_service,
        species_repository=repository,
    )

    asyncio.run(GeneDiversityStage().execute(context, engine))

    assert gene_diversity_service.calls == [
        (first_species, 1200, 0.25, 7),
        (second_species, 3400, 0.5, 7),
    ]
    assert repository.upserted_species == species_batch
    assert global_repository.attempted_species == []
    assert context.plugin_data["gene_diversity"]["events"] == [
        {
            "lineage_code": "SP-A",
            "name": "alpha",
            "old": 0.4,
            "new": 0.45,
            "reason": "repository isolation test",
        },
        {
            "lineage_code": "SP-B",
            "name": "beta",
            "old": 0.4,
            "new": 0.45,
            "reason": "repository isolation test",
        },
    ]
