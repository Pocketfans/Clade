"""Repository-isolation coverage for the speciation service."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from ....models.config import SpeciationConfig
from ....models.genus import Genus
from ....models.species import Species

# Mirror normal application startup; direct service import has a pre-existing cycle.
from ....simulation import SimulationEngine as _SimulationEngine
from .. import speciation as speciation_module
from ..speciation import SpeciationService


class _InMemoryGenusRepository:
    def __init__(self, genus: Genus) -> None:
        self.genus = genus
        self.requested_codes: list[str] = []

    def get_by_code(self, code: str) -> Genus | None:
        self.requested_codes.append(code)
        return self.genus if self.genus.code == code else None

    def update_distances(
        self,
        code: str,
        distances: dict[str, float],
        turn: int,
    ) -> None:
        if self.genus.code != code:
            return
        self.genus.genetic_distances.update(distances)
        self.genus.updated_turn = turn


class _InMemorySpeciesRepository:
    def __init__(self, species: list[Species]) -> None:
        self.species = species

    def list_species(self) -> list[Species]:
        return self.species


class _FixedGeneticDistanceCalculator:
    def calculate_distance(self, first: Species, second: Species) -> float:
        return 0.25


def _species(lineage_code: str) -> Species:
    return Species(
        lineage_code=lineage_code,
        latin_name=f"{lineage_code.title()} testus",
        common_name=lineage_code.lower(),
        description="Speciation repository test species",
        morphology_stats={},
        abstract_traits={},
        hidden_traits={},
        ecological_vector=[],
        genus_code="GEN-TEST",
        status="alive",
        updated_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )


def test_update_genetic_distances_uses_injected_genus_repository(
    monkeypatch,
) -> None:
    genus = Genus(
        code="GEN-TEST",
        name_latin="Testus",
        name_common="test genus",
        genetic_distances={},
    )
    genus_repository = _InMemoryGenusRepository(genus)
    sibling = _species("SP-C")
    monkeypatch.setattr(
        speciation_module,
        "species_repository",
        _InMemorySpeciesRepository([sibling]),
    )
    service = SpeciationService(
        router=SimpleNamespace(),
        config=SpeciationConfig(),
        genus_repository=genus_repository,
    )
    service.genetic_calculator = _FixedGeneticDistanceCalculator()

    service._update_genetic_distances(
        offspring=_species("SP-B"),
        parent=_species("SP-A"),
        turn_index=7,
    )

    assert genus_repository.requested_codes == ["GEN-TEST"]
    assert genus.genetic_distances == {"SP-B-SP-C": 0.25}
    assert genus.updated_turn == 7
