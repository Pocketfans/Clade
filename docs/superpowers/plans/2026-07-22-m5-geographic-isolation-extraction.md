# M5 Geographic Isolation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move geographic-isolation detection and its legacy offspring-tile allocator into `speciation_habitat.py` without changing decisions or random allocation.

**Architecture:** Add two functions that receive the existing service methods as callbacks. Keep both `SpeciationService` methods as delegates so subclass overrides of cluster discovery and isolation detection still apply.

**Tech Stack:** Python 3.12, pytest, standard-library `random`, existing mortality cache.

## Global Constraints

- Preserve the `0.25` ecological-isolation threshold, physical-isolation rule, average-mortality ranking, stable sorting, set iteration, list mutation and every random shuffle.
- Do not change mortality-cache creation, speciation triggers, offspring count, formulas, repositories, dependencies, public interfaces or constructor arguments.
- Stop if implementation needs a production file outside `speciation.py` and `speciation_habitat.py`.

## File Map

- Modify `backend/app/services/species/speciation_habitat.py`: add isolation detection and legacy offspring allocation.
- Modify `backend/app/services/species/speciation.py`: replace both bodies with delegates.
- Modify `backend/app/services/species/tests/test_speciation_habitat.py`: add characterization tests.

---

### Task 1: Extract geographic isolation and legacy allocation

**Interfaces:**
- `detect_geographic_isolation(lineage_code, tile_mortality_cache, connected_cluster_finder) -> dict`.
- `allocate_tiles_to_offspring(parent_lineage_code, num_offspring, isolation_detector) -> list[set[int]]`.

- [ ] **Step 1: Add failing tests**

Add imports and checks for:

```python
def test_geographic_isolation_handles_insufficient_tile_rates():
    result = detect_geographic_isolation("A", {"A": {7: 0.2}}, lambda tiles: [])
    assert result == {
        "is_isolated": False,
        "num_clusters": 1,
        "mortality_gradient": 0.0,
        "clusters": [{7}],
        "best_cluster": {7},
    }


def test_geographic_isolation_detects_physical_isolation_and_best_cluster():
    result = detect_geographic_isolation(
        "A",
        {"A": {1: 0.1, 2: 0.2, 3: 0.7}},
        lambda tiles: [{1, 2}, {3}],
    )
    assert result["is_isolated"] is True
    assert result["num_clusters"] == 2
    assert result["mortality_gradient"] == pytest.approx(0.6)
    assert result["best_cluster"] == {1, 2}


def test_geographic_isolation_detects_ecological_isolation_in_one_cluster():
    result = detect_geographic_isolation(
        "A", {"A": {1: 0.1, 2: 0.4}}, lambda tiles: [{1, 2}]
    )
    assert result["is_isolated"] is True
    assert result["num_clusters"] == 1
    assert result["best_cluster"] == {1, 2}


def test_legacy_offspring_allocation_handles_no_clusters():
    result = allocate_tiles_to_offspring(
        "A", 3, lambda lineage: {"clusters": []}
    )
    assert result == [set(), set(), set()]


def test_legacy_offspring_allocation_spreads_too_few_tiles(monkeypatch):
    monkeypatch.setattr(random, "shuffle", lambda values: None)
    result = allocate_tiles_to_offspring(
        "A", 3, lambda lineage: {"clusters": [{1}, {2}]}
    )
    assert len(result) == 3
    assert set().union(*result) == {1, 2}
    assert sorted(len(group) for group in result) == [0, 1, 1]


def test_legacy_offspring_allocation_splits_large_region_without_loss(monkeypatch):
    monkeypatch.setattr(random, "shuffle", lambda values: None)
    result = allocate_tiles_to_offspring(
        "A", 3, lambda lineage: {"clusters": [{1, 2, 3, 4}]}
    )
    assert len(result) == 3
    assert all(result)
    assert set().union(*result) == {1, 2, 3, 4}
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(result)
        for right in result[index + 1 :]
    )


def test_service_legacy_allocator_preserves_isolation_override(monkeypatch):
    monkeypatch.setattr(random, "shuffle", lambda values: None)

    class OverriddenSpeciationService(SpeciationService):
        def __init__(self):
            pass

        def _detect_geographic_isolation(self, lineage_code):
            return {"clusters": [{1}, {2}]}

    result = OverriddenSpeciationService()._allocate_tiles_to_offspring("A", 2)
    assert result == [{1}, {2}]


def test_service_isolation_delegate_preserves_cluster_finder_override():
    class OverriddenSpeciationService(SpeciationService):
        def __init__(self):
            self._tile_mortality_cache = {"A": {1: 0.1, 2: 0.1}}

        def _find_connected_clusters(self, tile_ids):
            return [{1}, {2}]

    result = OverriddenSpeciationService()._detect_geographic_isolation("A")
    assert result["is_isolated"] is True
    assert result["clusters"] == [{1}, {2}]
```

- [ ] **Step 2: Verify red**

Run the habitat test file. Expected: collection fails because the new functions are absent.

- [ ] **Step 3: Add the functions and delegates**

Use these callback types and mechanically moved bodies in `speciation_habitat.py`:

```python
ConnectedClusterFinder = Callable[[set[int]], list[set[int]]]
IsolationDetector = Callable[[str], dict]


def detect_geographic_isolation(
    lineage_code: str,
    tile_mortality_cache: dict[str, dict[int, float]],
    connected_cluster_finder: ConnectedClusterFinder,
) -> dict:
    tile_rates = tile_mortality_cache.get(lineage_code, {})
    if len(tile_rates) < 2:
        return {
            "is_isolated": False,
            "num_clusters": 1,
            "mortality_gradient": 0.0,
            "clusters": [set(tile_rates.keys())],
            "best_cluster": set(tile_rates.keys()),
        }
    rates = list(tile_rates.values())
    mortality_gradient = max(rates) - min(rates)
    clusters = connected_cluster_finder(set(tile_rates.keys()))
    ecological_isolation = mortality_gradient > 0.25
    physical_isolation = len(clusters) >= 2
    is_isolated = physical_isolation or ecological_isolation
    if clusters:
        cluster_avg_rates = []
        for cluster in clusters:
            avg_rate = sum(tile_rates.get(tile, 0.5) for tile in cluster) / len(cluster)
            cluster_avg_rates.append((cluster, avg_rate))
        cluster_avg_rates.sort(key=lambda item: item[1])
        best_cluster = cluster_avg_rates[0][0]
    else:
        best_cluster = set(tile_rates.keys())
    return {
        "is_isolated": is_isolated,
        "num_clusters": len(clusters),
        "mortality_gradient": mortality_gradient,
        "clusters": clusters,
        "best_cluster": best_cluster,
    }


def allocate_tiles_to_offspring(
    parent_lineage_code: str,
    num_offspring: int,
    isolation_detector: IsolationDetector,
) -> list[set[int]]:
    import random

    geo_data = isolation_detector(parent_lineage_code)
    clusters = geo_data["clusters"]
    if not clusters:
        return [set() for _ in range(num_offspring)]
    all_tiles = set()
    for cluster in clusters:
        all_tiles.update(cluster)
    if len(all_tiles) < num_offspring:
        tile_list = list(all_tiles)
        random.shuffle(tile_list)
        allocations = [set() for _ in range(num_offspring)]
        for index, tile in enumerate(tile_list):
            allocations[index % num_offspring].add(tile)
        return allocations
    if len(clusters) >= num_offspring:
        random.shuffle(clusters)
        return [clusters[index] for index in range(num_offspring)]
    if len(clusters) < num_offspring:
        allocations = [set() for _ in range(num_offspring)]
        for index, cluster in enumerate(clusters):
            if index < num_offspring:
                allocations[index] = cluster
        largest_index = max(
            range(len(allocations)), key=lambda index: len(allocations[index])
        )
        largest_cluster = list(allocations[largest_index])
        need_more = num_offspring - len(clusters)
        if need_more > 0 and len(largest_cluster) > 1:
            random.shuffle(largest_cluster)
            split_size = max(1, len(largest_cluster) // (need_more + 1))
            remaining = set(largest_cluster)
            for index in range(num_offspring):
                if not allocations[index]:
                    take = set(list(remaining)[:split_size])
                    allocations[index] = take
                    remaining -= take
                    if not remaining:
                        break
            allocations[largest_index] = remaining
        return allocations
    return [all_tiles.copy() for _ in range(num_offspring)]
```

Retain original variable names, comments and docstrings during implementation. Delegates in `speciation.py` must call:

```python
return detect_geographic_isolation(
    lineage_code,
    self._tile_mortality_cache,
    self._find_connected_clusters,
)
```

```python
return allocate_tiles_to_offspring(
    parent_lineage_code,
    num_offspring,
    self._detect_geographic_isolation,
)
```

- [ ] **Step 4: Verify focused/direct regressions and equivalence**

Run the habitat test file and all species-service tests. Verify AST equivalence after substituting the two callbacks.

- [ ] **Step 5: Run one full quality gate**

Run backend full tests, frontend tests, build and lint once. Expected: no failures; lint 0 errors and no more than 162 warnings.

- [ ] **Step 6: Commit and ordinary-push**

Commit as `refactor(backend): extract geographic isolation allocation`, ordinary-push the current Fork branch, and update only PR #15. Do not merge, force-push, create a PR, release or tag.
