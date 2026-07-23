"""Repository-isolation coverage for the gene-activation stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from ..stages import GeneActivationStage


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.upserted_species: list[object] = []

    def upsert(self, species: object) -> None:
        self.upserted_species.append(species)


class _UnexpectedGlobalSpeciesRepository:
    def upsert(self, species: object) -> None:
        raise AssertionError("module-level species_repository must not be used")


class _RecordingGeneActivationService:
    def __init__(self) -> None:
        self.calls: list[tuple[list[object], list[object], int]] = []
        self.events = [object()]

    def batch_check(
        self,
        species_batch: list[object],
        combined_results: list[object],
        turn_index: int,
    ) -> list[object]:
        self.calls.append((species_batch, combined_results, turn_index))
        return self.events


def test_gene_activation_stage_uses_injected_species_repository(monkeypatch) -> None:
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        _UnexpectedGlobalSpeciesRepository(),
    )

    repository = _RecordingSpeciesRepository()
    gene_activation_service = _RecordingGeneActivationService()
    species_batch = [object(), object()]
    combined_results = [object()]
    context = SimpleNamespace(
        species_batch=species_batch,
        combined_results=combined_results,
        turn_index=4,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        gene_activation_service=gene_activation_service,
        species_repository=repository,
    )

    asyncio.run(GeneActivationStage().execute(context, engine))

    assert gene_activation_service.calls == [
        (species_batch, combined_results, 4)
    ]
    assert repository.upserted_species == species_batch
    assert context.activation_events is gene_activation_service.events
