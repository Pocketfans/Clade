# M5 Initial Habitat Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move habitat suitability scoring and initial child-habitat selection out of `speciation.py` without changing observable behavior.

**Architecture:** Add a focused function module and keep both existing underscore-prefixed `SpeciationService` methods as compatibility delegates. Pass the service suitability method into the extracted selector so subclass overrides continue to control scoring.

**Tech Stack:** Python 3.12, SQLModel models, pytest, existing repository singletons.

## Global Constraints

- This batch implements only initial habitat selection and suitability scoring.
- Do not change formulas, filters, thresholds, ordering, normalization, log text, repository calls, database models, dependencies, public interfaces, or constructor arguments.
- Do not extract inheritance, connected clusters, geographic isolation, or offspring allocation in this batch.
- Preserve the logger category `app.services.species.speciation`.
- Stop if implementation needs any file outside the files listed below.

## File Map

- Create `backend/app/services/species/speciation_habitat.py`: suitability calculation and initial habitat selection.
- Modify `backend/app/services/species/speciation.py`: imports plus two compatibility delegates.
- Create `backend/app/services/species/tests/test_speciation_habitat.py`: characterization and compatibility tests.

---

### Task 1: Extract initial habitat selection

**Files:**
- Create: `backend/app/services/species/speciation_habitat.py`
- Modify: `backend/app/services/species/speciation.py:3516-3672`
- Test: `backend/app/services/species/tests/test_speciation_habitat.py`

**Interfaces:**
- Consumes: `Species`, tile objects with the existing map-tile fields, and `environment_repository`.
- Produces: `calculate_suitability_for_species(species: Species, tile: Any) -> float` and `calculate_initial_habitat_for_child(child: Species, parent: Species, turn_index: int, assigned_tiles: set[int] | None = None, suitability_calculator: SuitabilityCalculator | None = None) -> None`.

- [ ] **Step 1: Write the failing characterization tests**

Create `test_speciation_habitat.py` with four checks:

```python
import logging
from types import SimpleNamespace

import pytest

from ....repositories.environment_repository import environment_repository
from ..speciation import SpeciationService
from ..speciation_habitat import (
    calculate_initial_habitat_for_child,
    calculate_suitability_for_species,
)


def _species(**overrides):
    values = {
        "id": 7,
        "common_name": "测试物种",
        "habitat_type": "terrestrial",
        "abstract_traits": {"耐热性": 5, "耐寒性": 5, "耐旱性": 5},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tile(tile_id, resources=900.0, biome="平原", temperature=15.0,
          humidity=0.6, is_lake=False):
    return SimpleNamespace(
        id=tile_id,
        biome=biome,
        temperature=temperature,
        humidity=humidity,
        resources=resources,
        is_lake=is_lake,
    )


def test_suitability_preserves_temperature_humidity_and_resource_formula():
    species = _species()
    assert calculate_suitability_for_species(species, _tile(1)) == pytest.approx(1.0)
    assert calculate_suitability_for_species(species, _tile(2, resources=450.0)) == pytest.approx(0.8)
    assert calculate_suitability_for_species(species, _tile(3, temperature=30.0)) == 0.0


def test_initial_habitat_filters_assigned_tiles_sorts_and_normalizes(monkeypatch):
    tiles = [_tile(1), _tile(2, resources=450.0), _tile(3)]
    written = []
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: tiles)
    monkeypatch.setattr(environment_repository, "write_habitats", lambda rows: written.extend(rows))

    calculate_initial_habitat_for_child(
        _species(), SimpleNamespace(), 12, assigned_tiles={1, 2}
    )

    assert [row.tile_id for row in written] == [1, 2]
    assert [row.species_id for row in written] == [7, 7]
    assert [row.population for row in written] == [0, 0]
    assert [row.turn_index for row in written] == [12, 12]
    assert [row.suitability for row in written] == pytest.approx([1 / 1.8, 0.8 / 1.8])


def test_initial_habitat_preserves_logger_category_when_no_tiles(monkeypatch, caplog):
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: [])
    with caplog.at_level(logging.ERROR, logger="app.services.species.speciation"):
        calculate_initial_habitat_for_child(_species(), SimpleNamespace(), 12)
    assert any(
        record.name == "app.services.species.speciation"
        and "没有可用地块" in record.getMessage()
        for record in caplog.records
    )


def test_service_delegate_preserves_overridden_suitability_method(monkeypatch):
    tiles = [_tile(1), _tile(2)]
    written = []
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: tiles)
    monkeypatch.setattr(environment_repository, "write_habitats", lambda rows: written.extend(rows))

    class OverriddenSpeciationService(SpeciationService):
        def __init__(self):
            pass

        def _calculate_suitability_for_species(self, species, tile):
            return {1: 0.2, 2: 0.8}[tile.id]

    OverriddenSpeciationService()._calculate_initial_habitat_for_child(
        _species(), SimpleNamespace(), 12
    )

    assert [row.tile_id for row in written] == [2, 1]
    assert [row.suitability for row in written] == pytest.approx([0.8, 0.2])
```

- [ ] **Step 2: Run the new test to prove the boundary is missing**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_habitat.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.services.species.speciation_habitat'`.

- [ ] **Step 3: Add the focused module and compatibility delegates**

In `speciation_habitat.py`, bind the original log category and move the two existing method bodies without formula or message edits:

```python
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ...models.species import Species

logger = logging.getLogger(f"{__package__}.speciation")

SuitabilityCalculator = Callable[[Species, Any], float]


def calculate_initial_habitat_for_child(
    child: Species,
    parent: Species,
    turn_index: int,
    assigned_tiles: set[int] | None = None,
    suitability_calculator: SuitabilityCalculator | None = None,
) -> None:
    from ...models.environment import HabitatPopulation
    from ...repositories.environment_repository import environment_repository

    if suitability_calculator is None:
        suitability_calculator = calculate_suitability_for_species

    logger.info(f"[栖息地计算] 为 {child.common_name} 计算初始栖息地")
    all_tiles = environment_repository.list_tiles()
    if not all_tiles:
        logger.error(
            f"[栖息地计算] 没有可用地块，无法为 {child.common_name} 计算栖息地"
        )
        return

    if assigned_tiles:
        all_tiles = [tile for tile in all_tiles if tile.id in assigned_tiles]
        if not all_tiles:
            logger.warning(
                f"[栖息地计算] {child.common_name} 分配的地块在数据库中不存在，"
                f"使用全部地块"
            )
            all_tiles = environment_repository.list_tiles()

    habitat_type = getattr(child, "habitat_type", "terrestrial")
    suitable_tiles = []
    for tile in all_tiles:
        biome = tile.biome.lower()
        is_suitable = False
        if habitat_type == "marine" and ("浅海" in biome or "中层" in biome):
            is_suitable = True
        elif habitat_type == "deep_sea" and "深海" in biome:
            is_suitable = True
        elif habitat_type == "coastal" and ("海岸" in biome or "浅海" in biome):
            is_suitable = True
        elif habitat_type == "freshwater" and getattr(tile, "is_lake", False):
            is_suitable = True
        elif habitat_type == "terrestrial" and "海" not in biome:
            is_suitable = True
        elif habitat_type == "amphibious" and (
            "海岸" in biome or ("平原" in biome and tile.humidity > 0.4)
        ):
            is_suitable = True
        elif habitat_type == "aerial" and "海" not in biome and "山" not in biome:
            is_suitable = True
        if is_suitable:
            suitable_tiles.append(tile)

    if not suitable_tiles:
        logger.warning(
            f"[栖息地计算] {child.common_name} ({habitat_type}) 没有合适的地块"
        )
        suitable_tiles = all_tiles[:10] if all_tiles else []

    tile_suitability = []
    for tile in suitable_tiles:
        suitability = suitability_calculator(child, tile)
        if suitability > 0.1:
            tile_suitability.append((tile, suitability))
    if not tile_suitability:
        logger.warning(
            f"[栖息地计算] {child.common_name} 没有适宜度>0.1的地块，使用前10个"
        )
        tile_suitability = [(tile, 0.5) for tile in suitable_tiles[:10]]

    tile_suitability.sort(key=lambda item: item[1], reverse=True)
    top_tiles = tile_suitability[: min(10, len(tile_suitability))]
    total_suitability = sum(score for _, score in top_tiles)
    if total_suitability == 0:
        total_suitability = 1.0

    child_habitats = [
        HabitatPopulation(
            tile_id=tile.id,
            species_id=child.id,
            population=0,
            suitability=raw_suitability / total_suitability,
            turn_index=turn_index,
        )
        for tile, raw_suitability in top_tiles
    ]
    if child_habitats:
        environment_repository.write_habitats(child_habitats)
        if assigned_tiles:
            logger.info(
                f"[基于地块分化] {child.common_name} 在分配区域内计算得到 "
                f"{len(child_habitats)} 个栖息地"
            )
        else:
            logger.info(
                f"[栖息地计算] {child.common_name} 计算得到 "
                f"{len(child_habitats)} 个栖息地"
            )


def calculate_suitability_for_species(species: Species, tile: Any) -> float:
    heat_res = species.abstract_traits.get("耐热性", 5)
    cold_res = species.abstract_traits.get("耐寒性", 5)
    optimal_temp = 15.0 + (heat_res - cold_res) * 2.0
    tolerance_range = (cold_res + heat_res) * 1.0
    min_temp = optimal_temp - tolerance_range / 2
    max_temp = optimal_temp + tolerance_range / 2
    if min_temp <= tile.temperature <= max_temp:
        temp_score = 1.0
    else:
        diff = min(abs(tile.temperature - min_temp), abs(tile.temperature - max_temp))
        temp_score = max(0.0, 1.0 - diff * 0.4)
    if temp_score == 0.0:
        return 0.0
    drought_pref = species.abstract_traits.get("耐旱性", 5)
    best_humidity = 1.0 - (drought_pref * 0.08)
    humidity_score = max(0.0, 1.0 - abs(tile.humidity - best_humidity) * 4.0)
    resource_score = min(1.0, tile.resources / 900.0)
    return max(
        0.0,
        temp_score * 0.35 + humidity_score * 0.25 + resource_score * 0.40,
    )
```

Retain the existing selector and scorer docstrings/comments when applying this code. Then import both functions into `speciation.py` and replace the old bodies with these exact delegates:

```python
def _calculate_initial_habitat_for_child(
    self,
    child: Species,
    parent: Species,
    turn_index: int,
    assigned_tiles: set[int] | None = None,
) -> None:
    return calculate_initial_habitat_for_child(
        child,
        parent,
        turn_index,
        assigned_tiles,
        self._calculate_suitability_for_species,
    )

def _calculate_suitability_for_species(self, species: Species, tile) -> float:
    return calculate_suitability_for_species(species, tile)
```

- [ ] **Step 4: Run the focused test and direct species-service regression**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_habitat.py app/services/species/tests -q
```

Expected: all tests pass, including the four new tests and the existing 44 tests.

- [ ] **Step 5: Review the current diff**

Check only the three implementation files. Verify that formulas, strings, ordering and repository writes are byte-for-byte equivalent except for the function boundary and callback. Run `git diff --check`; expected exit code is 0.

- [ ] **Step 6: Run the batch quality gate once**

Run the repository's established full backend test, frontend test, production build and lint commands. Expected: backend and frontend tests pass, build succeeds, lint has 0 errors and does not exceed the existing warning ceiling of 162.

- [ ] **Step 7: Commit and ordinary-push the completed behavior**

```powershell
git add -- backend/app/services/species/speciation_habitat.py backend/app/services/species/speciation.py backend/app/services/species/tests/test_speciation_habitat.py
git commit -m "refactor(backend): extract initial habitat selection"
git push fork HEAD:phase-2c-outbound-url-security
```

Expected: one independent implementation commit is added to the Fork branch; no force push, merge, new PR, release or tag operation occurs.
