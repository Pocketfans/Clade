"""Repository-isolation coverage for the gene-flow stage."""

from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

from ...models.genus import Genus
from ...models.species import Species
from ..context import SimulationContext
from ..stages import GeneFlowStage


class _InMemoryGenusRepository:
    def __init__(self, genus: Genus) -> None:
        self.genus = genus
        self.requested_codes: list[str] = []

    def get_by_code(self, code: str) -> Genus | None:
        self.requested_codes.append(code)
        return self.genus if self.genus.code == code else None


class _RecordingGeneFlowService:
    def __init__(self, flow_count: int = 0) -> None:
        self.calls: list[tuple[Genus, list[Species]]] = []
        self.flow_count = flow_count

    def apply_gene_flow(self, genus: Genus, species: list[Species]) -> int:
        self.calls.append((genus, species))
        return self.flow_count


class _RecordingSpeciesRepository:
    def __init__(self) -> None:
        self.upserted_species: list[Species] = []

    def upsert(self, species: Species) -> None:
        self.upserted_species.append(species)


class _UnexpectedGlobalSpeciesRepository:
    def __init__(self) -> None:
        self.attempted_species: list[Species] = []

    def upsert(self, species: Species) -> None:
        self.attempted_species.append(species)
        raise AssertionError("module-level species_repository must not be used")


def _species(lineage_code: str) -> Species:
    return Species(
        lineage_code=lineage_code,
        latin_name=f"{lineage_code.title()} testus",
        common_name=lineage_code.lower(),
        description="Gene-flow repository test species",
        morphology_stats={},
        abstract_traits={},
        hidden_traits={},
        ecological_vector=[],
        genus_code="GEN-TEST",
        updated_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )


def test_gene_flow_stage_uses_injected_genus_repository() -> None:
    genus = Genus(
        code="GEN-TEST",
        name_latin="Testus",
        name_common="test genus",
    )
    repository = _InMemoryGenusRepository(genus)
    gene_flow_service = _RecordingGeneFlowService()
    species_batch = [_species("SP-A"), _species("SP-B")]
    context = SimulationContext(species_batch=species_batch)
    engine = SimpleNamespace(gene_flow_service=gene_flow_service)

    asyncio.run(
        GeneFlowStage(genus_repository=repository).execute(context, engine)
    )

    assert repository.requested_codes == ["GEN-TEST"]
    assert gene_flow_service.calls == [(genus, species_batch)]
    assert context.gene_flow_count == 0


def test_gene_flow_stage_uses_injected_species_repository(monkeypatch) -> None:
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _UnexpectedGlobalSpeciesRepository()
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )

    genus = Genus(
        code="GEN-TEST",
        name_latin="Testus",
        name_common="test genus",
    )
    genus_repository = _InMemoryGenusRepository(genus)
    species_repository = _RecordingSpeciesRepository()
    gene_flow_service = _RecordingGeneFlowService(flow_count=1)
    species_batch = [_species("SP-A"), _species("SP-B")]
    context = SimulationContext(species_batch=species_batch)
    engine = SimpleNamespace(
        gene_flow_service=gene_flow_service,
        species_repository=species_repository,
    )

    asyncio.run(
        GeneFlowStage(genus_repository=genus_repository).execute(context, engine)
    )

    assert genus_repository.requested_codes == ["GEN-TEST"]
    assert gene_flow_service.calls == [(genus, species_batch)]
    assert species_repository.upserted_species == species_batch
    assert global_repository.attempted_species == []
    assert context.gene_flow_count == 1
