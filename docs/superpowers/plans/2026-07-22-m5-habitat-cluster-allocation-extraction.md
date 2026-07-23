# M5 Habitat Cluster Allocation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move connected-tile discovery and cluster-based offspring allocation into `speciation_habitat.py` without changing ordering or randomness behavior.

**Architecture:** Add two pure internal functions. Keep both existing `SpeciationService` private methods as delegates; pass the service adjacency mapping into connected-cluster discovery.

**Tech Stack:** Python 3.12, pytest, standard-library `random`, existing service adjacency mapping.

## Global Constraints

- Implement only connected-cluster discovery and allocation from precomputed clusters.
- Preserve set/dict iteration, union-find behavior, sort stability, every `random.shuffle` call, round-robin assignment, cluster filtering and split behavior.
- Do not change adjacency construction, geographic-isolation decisions, mortality data, offspring count, database behavior, dependencies, public interfaces or constructor arguments.
- Stop if implementation requires a production file other than `speciation.py` and `speciation_habitat.py`.

## File Map

- Modify `backend/app/services/species/speciation_habitat.py`: add two cluster functions.
- Modify `backend/app/services/species/speciation.py`: keep two compatibility delegates.
- Modify `backend/app/services/species/tests/test_speciation_habitat.py`: add focused cluster tests.

---

### Task 1: Extract connected clusters and allocation

**Files:**
- Modify: `backend/app/services/species/speciation_habitat.py`
- Modify: `backend/app/services/species/speciation.py:3643-3769`
- Test: `backend/app/services/species/tests/test_speciation_habitat.py`

**Interfaces:**
- Produces: `find_connected_clusters(tile_ids: set[int], tile_adjacency: dict[int, set[int]]) -> list[set[int]]`.
- Produces: `allocate_tiles_from_clusters(clusters: list[set[int]], candidate_tiles: set[int], num_offspring: int) -> list[set[int]]`.

- [ ] **Step 1: Add failing tests**

Import both new functions and add these checks:

```python
def test_connected_clusters_preserves_empty_and_missing_adjacency_behavior():
    assert find_connected_clusters(set(), {}) == []
    tile_ids = {1, 2}
    result = find_connected_clusters(tile_ids, {})
    assert result == [tile_ids]
    assert result[0] is tile_ids


def test_connected_clusters_uses_service_adjacency():
    adjacency = {1: {2}, 2: {1, 3}, 3: {2}, 4: set()}
    result = find_connected_clusters({1, 2, 3, 4}, adjacency)
    assert {frozenset(cluster) for cluster in result} == {
        frozenset({1, 2, 3}),
        frozenset({4}),
    }


def test_cluster_allocation_round_robins_candidates_without_clusters(monkeypatch):
    monkeypatch.setattr("random.shuffle", lambda values: None)
    allocations = allocate_tiles_from_clusters([], {1, 2, 3, 4}, 2)
    assert len(allocations) == 2
    assert allocations[0].isdisjoint(allocations[1])
    assert allocations[0] | allocations[1] == {1, 2, 3, 4}
    assert [len(allocation) for allocation in allocations] == [2, 2]


def test_cluster_allocation_filters_candidates_before_selecting_regions(monkeypatch):
    monkeypatch.setattr("random.shuffle", lambda values: None)
    allocations = allocate_tiles_from_clusters(
        [{1, 2}, {3, 4}, {5}],
        {1, 3, 5},
        2,
    )
    assert allocations == [{1}, {3}]


def test_cluster_allocation_splits_largest_region_without_losing_tiles(monkeypatch):
    monkeypatch.setattr("random.shuffle", lambda values: None)
    allocations = allocate_tiles_from_clusters([{1, 2, 3, 4}], {1, 2, 3, 4}, 3)
    assert len(allocations) == 3
    assert all(allocations)
    assert set().union(*allocations) == {1, 2, 3, 4}
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(allocations)
        for right in allocations[index + 1 :]
    )


def test_service_connected_cluster_delegate_uses_current_adjacency():
    service = object.__new__(SpeciationService)
    service._tile_adjacency = {1: {2}, 2: {1}, 3: set()}
    assert {frozenset(cluster) for cluster in service._find_connected_clusters({1, 2, 3})} == {
        frozenset({1, 2}),
        frozenset({3}),
    }
```

- [ ] **Step 2: Verify red**

Run the habitat test file. Expected: collection fails because the two new functions are absent.

- [ ] **Step 3: Add the functions and delegates**

Add these implementations to `speciation_habitat.py`:

```python
def find_connected_clusters(
    tile_ids: set[int],
    tile_adjacency: dict[int, set[int]],
) -> list[set[int]]:
    if not tile_ids:
        return []
    if not tile_adjacency:
        return [tile_ids]
    parent = {tile_id: tile_id for tile_id in tile_ids}

    def find(tile_id):
        if parent[tile_id] != tile_id:
            parent[tile_id] = find(parent[tile_id])
        return parent[tile_id]

    def union(left, right):
        left_parent, right_parent = find(left), find(right)
        if left_parent != right_parent:
            parent[left_parent] = right_parent

    for tile_id in tile_ids:
        neighbors = tile_adjacency.get(tile_id, set())
        for neighbor in neighbors:
            if neighbor in tile_ids:
                union(tile_id, neighbor)
    clusters_map: dict[int, set[int]] = {}
    for tile_id in tile_ids:
        root = find(tile_id)
        if root not in clusters_map:
            clusters_map[root] = set()
        clusters_map[root].add(tile_id)
    return list(clusters_map.values())


def allocate_tiles_from_clusters(
    clusters: list[set[int]],
    candidate_tiles: set[int],
    num_offspring: int,
) -> list[set[int]]:
    import random

    if not clusters:
        if not candidate_tiles:
            return [set() for _ in range(num_offspring)]
        tile_list = list(candidate_tiles)
        random.shuffle(tile_list)
        allocations = [set() for _ in range(num_offspring)]
        for index, tile in enumerate(tile_list):
            allocations[index % num_offspring].add(tile)
        return allocations
    filtered_clusters = []
    for cluster in clusters:
        filtered = cluster & candidate_tiles
        if filtered:
            filtered_clusters.append(filtered)
    if not filtered_clusters:
        tile_list = list(candidate_tiles)
        random.shuffle(tile_list)
        allocations = [set() for _ in range(num_offspring)]
        for index, tile in enumerate(tile_list):
            allocations[index % num_offspring].add(tile)
        return allocations
    filtered_clusters.sort(key=len, reverse=True)
    if len(filtered_clusters) >= num_offspring:
        random.shuffle(filtered_clusters)
        return [filtered_clusters[index] for index in range(num_offspring)]
    allocations = [set() for _ in range(num_offspring)]
    for index, cluster in enumerate(filtered_clusters):
        if index < num_offspring:
            allocations[index] = cluster
    remaining_slots = [index for index in range(num_offspring) if not allocations[index]]
    if remaining_slots and allocations[0]:
        largest = list(allocations[0])
        random.shuffle(largest)
        split_size = max(1, len(largest) // (len(remaining_slots) + 1))
        for slot_index in remaining_slots:
            take = set(largest[:split_size])
            largest = largest[split_size:]
            allocations[slot_index] = take
        allocations[0] = set(largest)
    return allocations
```

Retain the original docstrings/comments and original local variable names during the mechanical move. Add imports in `speciation.py`, then use these exact delegate bodies:

```python
return find_connected_clusters(tile_ids, self._tile_adjacency)
```

```python
return allocate_tiles_from_clusters(clusters, candidate_tiles, num_offspring)
```

- [ ] **Step 4: Verify focused and direct regressions**

Run the habitat test file and all species-service tests. Expected: all pass, with six tests added to the existing 52.

- [ ] **Step 5: Review and run one full quality gate**

Verify AST equivalence after replacing `self._tile_adjacency` with the function parameter. Run `git diff --check`, backend full tests, frontend tests, build and lint once. Expected: no failures; lint remains at 0 errors and no more than 162 warnings.

- [ ] **Step 6: Commit and ordinary-push**

Commit as `refactor(backend): extract habitat cluster allocation`, ordinary-push the current Fork branch, and update only PR #15 with actual results. Do not merge, force-push, create a PR, release or tag.
