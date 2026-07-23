import logging
import random
from types import SimpleNamespace

import pytest

from ....repositories.environment_repository import environment_repository
from ..speciation import SpeciationService
from ..speciation_habitat import (
    allocate_tiles_from_clusters,
    allocate_tiles_to_offspring,
    calculate_initial_habitat_for_child,
    calculate_suitability_for_species,
    detect_geographic_isolation,
    find_connected_clusters,
    inherit_habitat_distribution,
)


def _species(**overrides) -> SimpleNamespace:
    values = {
        "id": 7,
        "common_name": "测试物种",
        "habitat_type": "terrestrial",
        "abstract_traits": {"耐热性": 5, "耐寒性": 5, "耐旱性": 5},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tile(
    tile_id: int,
    resources: float = 900.0,
    biome: str = "平原",
    temperature: float = 15.0,
    humidity: float = 0.6,
    is_lake: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=tile_id,
        biome=biome,
        temperature=temperature,
        humidity=humidity,
        resources=resources,
        is_lake=is_lake,
    )


def _habitat(
    tile_id: int,
    species_id: int,
    population: int,
    suitability: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        tile_id=tile_id,
        species_id=species_id,
        population=population,
        suitability=suitability,
    )


def test_suitability_preserves_temperature_humidity_and_resource_formula() -> None:
    species = _species()

    assert calculate_suitability_for_species(species, _tile(1)) == pytest.approx(
        1.0
    )
    assert calculate_suitability_for_species(
        species, _tile(2, resources=450.0)
    ) == pytest.approx(0.8)
    assert (
        calculate_suitability_for_species(
            species, _tile(3, temperature=30.0)
        )
        == 0.0
    )


def test_initial_habitat_filters_assigned_tiles_sorts_and_normalizes(
    monkeypatch,
) -> None:
    tiles = [_tile(1), _tile(2, resources=450.0), _tile(3)]
    written = []
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: tiles)
    monkeypatch.setattr(
        environment_repository,
        "write_habitats",
        lambda rows: written.extend(rows),
    )

    calculate_initial_habitat_for_child(
        _species(), SimpleNamespace(), 12, assigned_tiles={1, 2}
    )

    assert [row.tile_id for row in written] == [1, 2]
    assert [row.species_id for row in written] == [7, 7]
    assert [row.population for row in written] == [0, 0]
    assert [row.turn_index for row in written] == [12, 12]
    assert [row.suitability for row in written] == pytest.approx(
        [1 / 1.8, 0.8 / 1.8]
    )


def test_initial_habitat_preserves_logger_category_when_no_tiles(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: [])

    with caplog.at_level(
        logging.ERROR,
        logger="app.services.species.speciation",
    ):
        calculate_initial_habitat_for_child(_species(), SimpleNamespace(), 12)

    assert any(
        record.name == "app.services.species.speciation"
        and "没有可用地块" in record.getMessage()
        for record in caplog.records
    )


def test_service_delegate_preserves_overridden_suitability_method(
    monkeypatch,
) -> None:
    tiles = [_tile(1), _tile(2)]
    written = []
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: tiles)
    monkeypatch.setattr(
        environment_repository,
        "write_habitats",
        lambda rows: written.extend(rows),
    )

    class OverriddenSpeciationService(SpeciationService):
        def __init__(self) -> None:
            pass

        def _calculate_suitability_for_species(self, species, tile) -> float:
            return {1: 0.2, 2: 0.8}[tile.id]

    OverriddenSpeciationService()._calculate_initial_habitat_for_child(
        _species(), SimpleNamespace(), 12
    )

    assert [row.tile_id for row in written] == [2, 1]
    assert [row.suitability for row in written] == pytest.approx([0.8, 0.2])


def test_inheritance_transfers_assigned_population_and_writes_parent_second(
    monkeypatch,
) -> None:
    parent = _species(id=1, common_name="父代")
    child = _species(id=2, common_name="子代")
    habitats = [
        _habitat(10, 1, 100, 0.8),
        _habitat(20, 1, 40, 0.5),
    ]
    batches = []
    monkeypatch.setattr(
        environment_repository,
        "latest_habitats",
        lambda: habitats,
    )
    monkeypatch.setattr(
        environment_repository,
        "write_habitats",
        lambda rows: batches.append(list(rows)),
    )

    inherit_habitat_distribution(
        parent,
        child,
        15,
        assigned_tiles={10},
        reproduction_bonus=0.4,
    )

    assert len(batches) == 2
    assert [
        (
            row.tile_id,
            row.species_id,
            row.population,
            row.suitability,
            row.turn_index,
        )
        for row in batches[0]
    ] == [(10, 2, 132, 0.8, 15)]
    assert [
        (
            row.tile_id,
            row.species_id,
            row.population,
            row.suitability,
            row.turn_index,
        )
        for row in batches[1]
    ] == [(10, 1, 0, 0.8, 15)]


def test_inheritance_without_assignment_splits_population_without_parent_write(
    monkeypatch,
) -> None:
    parent = _species(id=1, common_name="父代")
    child = _species(id=2, common_name="子代")
    batches = []
    monkeypatch.setattr(
        environment_repository,
        "latest_habitats",
        lambda: [_habitat(10, 1, 101, 0.5)],
    )
    monkeypatch.setattr(
        environment_repository,
        "write_habitats",
        lambda rows: batches.append(list(rows)),
    )

    inherit_habitat_distribution(
        parent,
        child,
        15,
        reproduction_bonus=0.2,
    )

    assert len(batches) == 1
    assert batches[0][0].population == 55
    assert batches[0][0].species_id == 2


def test_inheritance_uses_assigned_tiles_when_parent_tiles_do_not_overlap(
    monkeypatch,
) -> None:
    parent = _species(id=1, common_name="父代")
    child = _species(
        id=2,
        common_name="子代",
        morphology_stats={"population": 9},
    )
    batches = []
    monkeypatch.setattr(
        environment_repository,
        "latest_habitats",
        lambda: [_habitat(10, 1, 100, 0.8)],
    )
    monkeypatch.setattr(
        environment_repository,
        "write_habitats",
        lambda rows: batches.append(list(rows)),
    )

    inherit_habitat_distribution(
        parent,
        child,
        15,
        assigned_tiles={30, 40},
    )

    assert len(batches) == 1
    assert {row.tile_id for row in batches[0]} == {30, 40}
    assert {row.population for row in batches[0]} == {4}
    assert {row.suitability for row in batches[0]} == {0.5}


def test_service_inheritance_delegate_preserves_initial_habitat_override(
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(environment_repository, "latest_habitats", lambda: [])

    class OverriddenSpeciationService(SpeciationService):
        def __init__(self) -> None:
            pass

        def _calculate_initial_habitat_for_child(
            self,
            child,
            parent,
            turn_index,
            assigned_tiles=None,
        ) -> None:
            calls.append((child.id, parent.id, turn_index, assigned_tiles))

    OverriddenSpeciationService()._inherit_habitat_distribution(
        _species(id=1),
        _species(id=2),
        15,
        assigned_tiles={10},
    )

    assert calls == [(2, 1, 15, {10})]


def test_connected_clusters_preserves_empty_and_missing_adjacency_behavior() -> None:
    assert find_connected_clusters(set(), {}) == []

    tile_ids = {1, 2}
    result = find_connected_clusters(tile_ids, {})

    assert result == [tile_ids]
    assert result[0] is tile_ids


def test_connected_clusters_uses_service_adjacency() -> None:
    adjacency = {
        1: {2},
        2: {1, 3},
        3: {2},
        4: set(),
    }

    result = find_connected_clusters({1, 2, 3, 4}, adjacency)

    assert {frozenset(cluster) for cluster in result} == {
        frozenset({1, 2, 3}),
        frozenset({4}),
    }


def test_cluster_allocation_round_robins_candidates_without_clusters(
    monkeypatch,
) -> None:
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    allocations = allocate_tiles_from_clusters([], {1, 2, 3, 4}, 2)

    assert len(allocations) == 2
    assert allocations[0].isdisjoint(allocations[1])
    assert allocations[0] | allocations[1] == {1, 2, 3, 4}
    assert [len(allocation) for allocation in allocations] == [2, 2]


def test_cluster_allocation_filters_candidates_before_selecting_regions(
    monkeypatch,
) -> None:
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    allocations = allocate_tiles_from_clusters(
        [{1, 2}, {3, 4}, {5}],
        {1, 3, 5},
        2,
    )

    assert allocations == [{1}, {3}]


def test_cluster_allocation_splits_largest_region_without_losing_tiles(
    monkeypatch,
) -> None:
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    allocations = allocate_tiles_from_clusters(
        [{1, 2, 3, 4}],
        {1, 2, 3, 4},
        3,
    )

    assert len(allocations) == 3
    assert all(allocations)
    assert set().union(*allocations) == {1, 2, 3, 4}
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(allocations)
        for right in allocations[index + 1 :]
    )


def test_service_connected_cluster_delegate_uses_current_adjacency() -> None:
    service = object.__new__(SpeciationService)
    service._tile_adjacency = {1: {2}, 2: {1}, 3: set()}

    result = service._find_connected_clusters({1, 2, 3})

    assert {frozenset(cluster) for cluster in result} == {
        frozenset({1, 2}),
        frozenset({3}),
    }


def test_geographic_isolation_handles_insufficient_tile_rates() -> None:
    result = detect_geographic_isolation(
        "A",
        {"A": {7: 0.2}},
        lambda tiles: [],
    )

    assert result == {
        "is_isolated": False,
        "num_clusters": 1,
        "mortality_gradient": 0.0,
        "clusters": [{7}],
        "best_cluster": {7},
    }


def test_geographic_isolation_detects_physical_isolation_and_best_cluster() -> None:
    result = detect_geographic_isolation(
        "A",
        {"A": {1: 0.1, 2: 0.2, 3: 0.7}},
        lambda tiles: [{1, 2}, {3}],
    )

    assert result["is_isolated"] is True
    assert result["num_clusters"] == 2
    assert result["mortality_gradient"] == pytest.approx(0.6)
    assert result["best_cluster"] == {1, 2}


def test_geographic_isolation_detects_ecological_isolation_in_one_cluster() -> None:
    result = detect_geographic_isolation(
        "A",
        {"A": {1: 0.1, 2: 0.4}},
        lambda tiles: [{1, 2}],
    )

    assert result["is_isolated"] is True
    assert result["num_clusters"] == 1
    assert result["best_cluster"] == {1, 2}


def test_legacy_offspring_allocation_handles_no_clusters() -> None:
    result = allocate_tiles_to_offspring(
        "A",
        3,
        lambda lineage: {"clusters": []},
    )

    assert result == [set(), set(), set()]


def test_legacy_offspring_allocation_spreads_too_few_tiles(
    monkeypatch,
) -> None:
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    result = allocate_tiles_to_offspring(
        "A",
        3,
        lambda lineage: {"clusters": [{1}, {2}]},
    )

    assert len(result) == 3
    assert set().union(*result) == {1, 2}
    assert sorted(len(group) for group in result) == [0, 1, 1]


def test_legacy_offspring_allocation_splits_large_region_without_loss(
    monkeypatch,
) -> None:
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    result = allocate_tiles_to_offspring(
        "A",
        3,
        lambda lineage: {"clusters": [{1, 2, 3, 4}]},
    )

    assert len(result) == 3
    assert all(result)
    assert set().union(*result) == {1, 2, 3, 4}
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(result)
        for right in result[index + 1 :]
    )


def test_service_legacy_allocator_preserves_isolation_override(
    monkeypatch,
) -> None:
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    class OverriddenSpeciationService(SpeciationService):
        def __init__(self) -> None:
            pass

        def _detect_geographic_isolation(self, lineage_code):
            return {"clusters": [{1}, {2}]}

    result = OverriddenSpeciationService()._allocate_tiles_to_offspring("A", 2)

    assert result == [{1}, {2}]


def test_service_isolation_delegate_preserves_cluster_finder_override() -> None:
    class OverriddenSpeciationService(SpeciationService):
        def __init__(self) -> None:
            self._tile_mortality_cache = {"A": {1: 0.1, 2: 0.1}}

        def _find_connected_clusters(self, tile_ids):
            return [{1}, {2}]

    result = OverriddenSpeciationService()._detect_geographic_isolation("A")

    assert result["is_isolated"] is True
    assert result["clusters"] == [{1}, {2}]
