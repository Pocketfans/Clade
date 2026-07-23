from ..speciation import SpeciationService
from ..speciation_lineage import (
    generate_multiple_lineage_codes,
    next_lineage_code,
)


def test_next_lineage_code_preserves_numbered_suffix_search() -> None:
    existing = {"A1a1", "A1a2"}

    assert next_lineage_code("A1", existing) == "A1a3"
    assert existing == {"A1a1", "A1a2"}


def test_multiple_lineage_codes_preserve_order_and_collisions() -> None:
    assert generate_multiple_lineage_codes("A1", set(), 3) == [
        "A1a",
        "A1b",
        "A1c",
    ]

    existing = {"A1a", "A1a1", "A1b"}
    assert generate_multiple_lineage_codes("A1", existing, 3) == [
        "A1a2",
        "A1b1",
        "A1c",
    ]
    assert existing == {"A1a", "A1a1", "A1b"}


def test_multiple_lineage_codes_preserve_count_boundaries() -> None:
    assert generate_multiple_lineage_codes("A1", set(), 0) == []

    codes = generate_multiple_lineage_codes("A1", set(), 27)

    assert codes[25] == "A1z"
    assert codes[26] == "A1a"


def test_speciation_service_keeps_lineage_code_methods() -> None:
    service = object.__new__(SpeciationService)
    existing = {"A1a"}

    assert service._next_lineage_code("A1", existing) == next_lineage_code(
        "A1", existing
    )
    assert service._generate_multiple_lineage_codes(
        "A1", existing, 2
    ) == generate_multiple_lineage_codes("A1", existing, 2)
