"""Repository-isolation coverage for the deprecated gene-library service."""

from __future__ import annotations

import warnings

from ....models.genus import Genus
from ..gene_library import GeneLibraryService


class _InMemoryGenusRepository:
    def __init__(self, genus: Genus) -> None:
        self.genus = genus
        self.upserted: list[Genus] = []

    def get_by_code(self, code: str) -> Genus | None:
        return self.genus if self.genus.code == code else None

    def upsert(self, genus: Genus) -> Genus:
        self.genus = genus
        self.upserted.append(genus)
        return genus


def _service(repository: _InMemoryGenusRepository) -> GeneLibraryService:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return GeneLibraryService(genus_repository=repository)


def test_record_discovery_uses_injected_genus_repository() -> None:
    genus = Genus(
        code="GEN-TEST",
        name_latin="Testus",
        name_common="test genus",
        gene_library={},
    )
    repository = _InMemoryGenusRepository(genus)

    _service(repository).record_discovery(
        "GEN-TEST",
        {"new_traits": {"cold_tolerance": {"max_value": 4.0}}},
        discoverer_code="SP-TEST",
        turn=3,
    )

    discovered = repository.genus.gene_library["traits"]["cold_tolerance"]
    assert discovered["max_value"] == 4.0
    assert discovered["discovered_by"] == "SP-TEST"
    assert repository.genus.updated_turn == 3
    assert repository.upserted == [genus]


def test_update_activation_count_uses_injected_genus_repository() -> None:
    genus = Genus(
        code="GEN-TEST",
        name_latin="Testus",
        name_common="test genus",
        gene_library={
            "traits": {
                "cold_tolerance": {
                    "activation_count": 2,
                }
            }
        },
    )
    repository = _InMemoryGenusRepository(genus)

    _service(repository).update_activation_count(
        "GEN-TEST",
        "cold_tolerance",
        "traits",
    )

    activated = repository.genus.gene_library["traits"]["cold_tolerance"]
    assert activated["activation_count"] == 3
    assert repository.upserted == [genus]
