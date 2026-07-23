# M5 Habitat Inheritance Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move parent-to-child habitat inheritance into `speciation_habitat.py` without changing population transfer or persistence behavior.

**Architecture:** Add one internal function beside the already extracted initial-habitat functions. Keep `SpeciationService._inherit_habitat_distribution` as a delegate and pass its initial-habitat method as a callback so subclass overrides remain effective.

**Tech Stack:** Python 3.12, SQLModel models, pytest, existing repository singleton.

## Global Constraints

- Implement only parent-to-child habitat inheritance.
- Preserve integer truncation, assigned-tile filtering, transfer formulas, reproduction bonus, fallback populations, batch contents, write order, logger category and log text.
- Do not alter initial habitat selection, geographic isolation, connected clusters, offspring allocation, database models, dependencies, public interfaces or constructor arguments.
- Stop if implementation requires a production file other than the two listed below.

## File Map

- Modify `backend/app/services/species/speciation_habitat.py`: add the inheritance function.
- Modify `backend/app/services/species/speciation.py`: replace the inheritance body with a compatibility delegate.
- Modify `backend/app/services/species/tests/test_speciation_habitat.py`: add inheritance characterization tests.

---

### Task 1: Extract habitat inheritance

**Files:**
- Modify: `backend/app/services/species/speciation_habitat.py`
- Modify: `backend/app/services/species/speciation.py:3381-3521`
- Test: `backend/app/services/species/tests/test_speciation_habitat.py`

**Interfaces:**
- Consumes: parent and child species, current turn, optional assigned tile IDs, reproduction bonus and optional initial-habitat callback.
- Produces: `inherit_habitat_distribution(parent, child, turn_index, assigned_tiles=None, reproduction_bonus=0.0, initial_habitat_calculator=None) -> None`.

- [ ] **Step 1: Add failing characterization tests**

Import `inherit_habitat_distribution`, then add tests equivalent to:

```python
def _habitat(tile_id, species_id, population, suitability):
    return SimpleNamespace(
        tile_id=tile_id,
        species_id=species_id,
        population=population,
        suitability=suitability,
    )


def test_inheritance_transfers_assigned_population_and_writes_parent_second(monkeypatch):
    parent = _species(id=1, common_name="父代")
    child = _species(id=2, common_name="子代")
    habitats = [_habitat(10, 1, 100, 0.8), _habitat(20, 1, 40, 0.5)]
    batches = []
    monkeypatch.setattr(environment_repository, "latest_habitats", lambda: habitats)
    monkeypatch.setattr(environment_repository, "write_habitats", lambda rows: batches.append(list(rows)))

    inherit_habitat_distribution(
        parent, child, 15, assigned_tiles={10}, reproduction_bonus=0.4
    )

    assert len(batches) == 2
    assert [(row.tile_id, row.species_id, row.population, row.suitability, row.turn_index) for row in batches[0]] == [(10, 2, 132, 0.8, 15)]
    assert [(row.tile_id, row.species_id, row.population, row.suitability, row.turn_index) for row in batches[1]] == [(10, 1, 0, 0.8, 15)]


def test_inheritance_without_assignment_splits_population_without_parent_write(monkeypatch):
    parent = _species(id=1, common_name="父代")
    child = _species(id=2, common_name="子代")
    batches = []
    monkeypatch.setattr(environment_repository, "latest_habitats", lambda: [_habitat(10, 1, 101, 0.5)])
    monkeypatch.setattr(environment_repository, "write_habitats", lambda rows: batches.append(list(rows)))

    inherit_habitat_distribution(parent, child, 15, reproduction_bonus=0.2)

    assert len(batches) == 1
    assert batches[0][0].population == 55
    assert batches[0][0].species_id == 2


def test_inheritance_uses_assigned_tiles_when_parent_tiles_do_not_overlap(monkeypatch):
    parent = _species(id=1, common_name="父代")
    child = _species(id=2, common_name="子代", morphology_stats={"population": 9})
    batches = []
    monkeypatch.setattr(environment_repository, "latest_habitats", lambda: [_habitat(10, 1, 100, 0.8)])
    monkeypatch.setattr(environment_repository, "write_habitats", lambda rows: batches.append(list(rows)))

    inherit_habitat_distribution(parent, child, 15, assigned_tiles={30, 40})

    assert len(batches) == 1
    assert {row.tile_id for row in batches[0]} == {30, 40}
    assert {row.population for row in batches[0]} == {4}
    assert {row.suitability for row in batches[0]} == {0.5}


def test_service_inheritance_delegate_preserves_initial_habitat_override(monkeypatch):
    calls = []
    monkeypatch.setattr(environment_repository, "latest_habitats", lambda: [])

    class OverriddenSpeciationService(SpeciationService):
        def __init__(self):
            pass

        def _calculate_initial_habitat_for_child(self, child, parent, turn_index, assigned_tiles=None):
            calls.append((child.id, parent.id, turn_index, assigned_tiles))

    OverriddenSpeciationService()._inherit_habitat_distribution(
        _species(id=1), _species(id=2), 15, assigned_tiles={10}
    )

    assert calls == [(2, 1, 15, {10})]
```

- [ ] **Step 2: Verify the new boundary is missing**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_habitat.py -q
```

Expected: collection fails because `inherit_habitat_distribution` is not defined in `speciation_habitat`.

- [ ] **Step 3: Move the inheritance implementation**

Add these imports and signature to `speciation_habitat.py`:

```python
InitialHabitatCalculator = Callable[
    [Species, Species, int, set[int] | None],
    None,
]


def inherit_habitat_distribution(
    parent: Species,
    child: Species,
    turn_index: int,
    assigned_tiles: set[int] | None = None,
    reproduction_bonus: float = 0.0,
    initial_habitat_calculator: InitialHabitatCalculator | None = None,
) -> None:
    from ...models.environment import HabitatPopulation
    from ...repositories.environment_repository import environment_repository

    if initial_habitat_calculator is None:
        initial_habitat_calculator = calculate_initial_habitat_for_child

    all_habitats = environment_repository.latest_habitats()
    parent_habitats = [h for h in all_habitats if h.species_id == parent.id]
    if not parent_habitats:
        logger.warning(
            f"[栖息地继承] 父代 {parent.common_name} 没有栖息地数据，立即为子代计算初始栖息地"
        )
        initial_habitat_calculator(child, parent, turn_index, assigned_tiles)
        return
    if child.id is None:
        logger.error(
            f"[栖息地继承] 严重错误：子代 {child.common_name} 没有 ID，无法继承栖息地"
        )
        return

    child_habitats = []
    parent_updated_habitats = []
    inherited_count = 0
    total_inherited_pop = 0
    total_parent_reduced = 0
    for parent_hab in parent_habitats:
        if assigned_tiles and parent_hab.tile_id not in assigned_tiles:
            continue
        tile_pop = parent_hab.population if parent_hab.population else 0
        if assigned_tiles:
            base_child_pop = tile_pop
            parent_remaining_pop = 0
        else:
            base_child_pop = int(tile_pop * 0.5)
            parent_remaining_pop = tile_pop - base_child_pop
        if reproduction_bonus > 0 and base_child_pop > 0:
            suitability_factor = parent_hab.suitability if parent_hab.suitability else 0.5
            effective_bonus = reproduction_bonus * suitability_factor
            child_pop = int(base_child_pop * (1 + effective_bonus))
        else:
            child_pop = base_child_pop
        child_habitats.append(
            HabitatPopulation(
                tile_id=parent_hab.tile_id,
                species_id=child.id,
                population=child_pop,
                suitability=parent_hab.suitability,
                turn_index=turn_index,
            )
        )
        if assigned_tiles and tile_pop > 0:
            parent_updated_habitats.append(
                HabitatPopulation(
                    tile_id=parent_hab.tile_id,
                    species_id=parent.id,
                    population=parent_remaining_pop,
                    suitability=parent_hab.suitability,
                    turn_index=turn_index,
                )
            )
            total_parent_reduced += tile_pop
        inherited_count += 1
        total_inherited_pop += child_pop

    if assigned_tiles and not child_habitats:
        logger.warning(
            f"[栖息地继承] {child.common_name} 分配的地块与父代不重叠，"
            f"将使用分配的地块: {assigned_tiles}"
        )
        child_total_pop = int(child.morphology_stats.get("population", 0) or 0)
        pop_per_tile = (
            max(1, child_total_pop // len(assigned_tiles))
            if assigned_tiles
            else 0
        )
        for tile_id in assigned_tiles:
            child_habitats.append(
                HabitatPopulation(
                    tile_id=tile_id,
                    species_id=child.id,
                    population=pop_per_tile,
                    suitability=0.5,
                    turn_index=turn_index,
                )
            )

    if child_habitats:
        environment_repository.write_habitats(child_habitats)
        if assigned_tiles:
            logger.info(
                f"[基于地块分化] {child.common_name} 继承了 {len(child_habitats)}/{len(parent_habitats)} 个地块 "
                f"(种群:{total_inherited_pop:,}, 地理隔离分化)"
            )
        else:
            logger.info(
                f"[栖息地继承] {child.common_name} 继承了 {len(child_habitats)} 个栖息地"
            )
    if parent_updated_habitats:
        environment_repository.write_habitats(parent_updated_habitats)
        logger.debug(
            f"[地块分化] 父代 {parent.common_name} 在 {len(parent_updated_habitats)} 个地块上"
            f"减少种群 {total_parent_reduced:,}（已转移给子代）"
        )
```

Retain the original docstring and comments during the mechanical move. Import the new function into `speciation.py` and replace the old body with:

```python
return inherit_habitat_distribution(
    parent,
    child,
    turn_index,
    assigned_tiles,
    reproduction_bonus,
    self._calculate_initial_habitat_for_child,
)
```

- [ ] **Step 4: Run focused and direct regressions**

Run the habitat test file, then all `app/services/species/tests`. Expected: all pass, with four new tests added to the existing 48.

- [ ] **Step 5: Review and run the batch quality gate**

Verify AST equivalence after substituting the callback call, run `git diff --check`, then run one backend full suite and one frontend test/build/lint gate. Expected: no failures, build success, lint 0 errors and at most 162 warnings.

- [ ] **Step 6: Commit and ordinary-push**

```powershell
git add -- backend/app/services/species/speciation_habitat.py backend/app/services/species/speciation.py backend/app/services/species/tests/test_speciation_habitat.py
git commit -m "refactor(backend): extract habitat inheritance"
git push fork HEAD:phase-2c-outbound-url-security
```

Update only PR #15 with the commit and actual test results. Do not merge, force-push, create another PR, release or tag.
