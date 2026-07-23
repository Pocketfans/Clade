# M5 Plant Organ Changes Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move plant organ change processing out of `speciation.py` without changing validation, mutation, selection or compatibility behavior.

**Architecture:** Add one internal function to the existing `speciation_organs.py` module. Pass the current plant evolution service, reference-organ catalog and category configuration as internal arguments; keep `_process_plant_organ_changes` as a thin compatibility delegate.

**Tech Stack:** Python 3.12, pytest, existing plant evolution service and `Species` model.

## Global Constraints

- Extract only plant organ changes and their projection into the generic organ dictionary.
- Preserve invalid-item filtering, old/new parameter formats, validation order, two-level shallow copying, mutation sharing, parameter clamping, milestone protection, stable best-organ selection, log text and returned object identity.
- Do not extract normalization/deduplication, embedding inference, biological-domain selection, animal organ changes or organ inheritance/update orchestration.
- Do not change plant rules, models, repositories, formulas, dependencies, public interfaces or constructor arguments.
- Stop if a production file besides `speciation.py` and `speciation_organs.py` is required.

---

### Task 1: Extract plant organ changes

**Files:**
- Modify: `backend/app/services/species/speciation_organs.py`
- Modify: `backend/app/services/species/speciation.py:4493`
- Test: `backend/app/services/species/tests/test_speciation_organs.py`

**Interfaces:**
- Consumes: `organs: dict`, `organ_changes: list`, `parent: Species`, `turn_index: int`, the current plant evolution service, `PLANT_ORGANS`, and `PLANT_ORGAN_CATEGORIES`.
- Produces: `process_plant_organ_changes(...) -> dict`, returning the original `organs` object with generic projections and `_plant_organs`.
- Imports: add `Any` from `typing` to `speciation_organs.py`; import the two existing configuration dictionaries alongside the existing plant service in `speciation.py`.

- [ ] **Step 1: Write failing characterization tests**

Import the wished-for function and real plant dependencies, then add these tests:

```python
from ..plant_evolution import (
    PLANT_ORGANS,
    PLANT_ORGAN_CATEGORIES,
    plant_evolution_service,
)
from ..speciation_organs import process_plant_organ_changes


def _process_plant_changes(organs, changes, parent, turn):
    return process_plant_organ_changes(
        organs,
        changes,
        parent,
        turn,
        plant_evolution_service,
        PLANT_ORGANS,
        PLANT_ORGAN_CATEGORIES,
    )


def test_plant_changes_empty_input_returns_same_generic_organs() -> None:
    organs = {"legacy": {"type": "legacy"}}
    parent = SimpleNamespace(life_form_stage=0, plant_organs=None)
    result = _process_plant_changes(organs, [], parent, 4)
    assert result is organs
    assert result == {"legacy": {"type": "legacy"}, "_plant_organs": {}}


def test_plant_changes_add_reference_milestone_organ_from_legacy_parameters() -> None:
    organs = {}
    parent = SimpleNamespace(life_form_stage=1, plant_organs=None)
    change = {"category": "photosynthetic", "change_type": "new", "organ_name": "叶绿体", "parameter": "efficiency", "delta": 9.0}
    result = _process_plant_changes(organs, [change], parent, 7)
    stored = result["_plant_organs"]["photosynthetic"]["叶绿体"]
    assert stored == {"efficiency": 5.0, "min_stage": 0, "acquired_turn": 7, "is_custom": False, "milestone_required": True, "milestone_id": "first_eukaryote"}
    assert result["photosynthetic"] == {"type": "叶绿体", "parameters": stored.copy(), "evolution_stage": 4, "evolution_progress": 1.0, "is_active": True}


def test_plant_changes_skip_unknown_and_stage_locked_categories() -> None:
    parent = SimpleNamespace(life_form_stage=0, plant_organs=None)
    changes = [
        {"category": "unknown", "change_type": "new", "organ_name": "未知", "parameters": {}},
        {"category": "root_system", "change_type": "new", "organ_name": "假根", "parameters": {"depth_cm": 1, "absorption": 1}},
    ]
    assert _process_plant_changes({}, changes, parent, 1) == {"_plant_organs": {}}


def test_plant_changes_enhance_and_degrade_shared_parent_records() -> None:
    photosynthetic = {"efficiency": 4.8, "min_stage": 0}
    protection = {"uv_resist": 1.0, "min_stage": 0}
    parent = SimpleNamespace(
        life_form_stage=3,
        plant_organs={
            "photosynthetic": {"自定义叶": photosynthetic},
            "protection": {"树脂层": protection},
        },
    )
    changes = [
        {"category": "photosynthetic", "change_type": "enhance", "organ_name": "自定义叶", "parameters": {"efficiency": 1.0}},
        {"category": "protection", "change_type": "degrade", "organ_name": "树脂层"},
    ]
    result = _process_plant_changes({}, changes, parent, 9)
    assert photosynthetic == {"efficiency": 5.0, "min_stage": 0, "modified_turn": 9}
    assert protection == {"uv_resist": 1.0, "min_stage": 0, "is_degraded": True, "degraded_turn": 9}
    assert result["photosynthetic"]["type"] == "自定义叶"
    assert "type" not in result["protection"]


def test_plant_changes_protect_milestones_and_keep_first_best_organ() -> None:
    first = {"efficiency": 2.0, "min_stage": 0}
    tied = {"efficiency": 2.0, "min_stage": 0}
    milestone = {"efficiency": 1.0, "min_stage": 0}
    parent = SimpleNamespace(
        life_form_stage=3,
        plant_organs={"photosynthetic": {"第一叶": first, "同值叶": tied, "叶绿体": milestone}},
    )
    changes = [{"category": "photosynthetic", "change_type": "degrade", "organ_name": "叶绿体"}]
    result = _process_plant_changes({}, changes, parent, 10)
    assert "is_degraded" not in milestone
    assert result["photosynthetic"]["type"] == "第一叶"


def test_service_plant_change_delegate_matches_direct_function() -> None:
    parent = SimpleNamespace(life_form_stage=1, plant_organs=None)
    changes = [{"category": "photosynthetic", "change_type": "new", "organ_name": "光合泡", "parameters": {"efficiency": 1.2}}]
    service_organs = {}
    direct_organs = {}
    service = object.__new__(SpeciationService)
    assert service._process_plant_organ_changes(service_organs, deepcopy(changes), parent, 3) == _process_plant_changes(direct_organs, deepcopy(changes), parent, 3)
    assert service_organs == direct_organs
```

- [ ] **Step 2: Run the focused file and verify red**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
```

Expected: collection fails because `process_plant_organ_changes` does not yet exist.

- [ ] **Step 3: Add the minimal internal function**

Move the existing method body mechanically to this function, replacing only the three locally imported dependency names with parameters:

```python
def process_plant_organ_changes(
    organs: dict,
    organ_changes: list,
    parent: Species,
    turn_index: int,
    plant_evolution: Any,
    plant_organ_catalog: dict,
    plant_organ_categories: dict,
) -> dict:
    current_stage = getattr(parent, "life_form_stage", 0)
    plant_organs = getattr(parent, "plant_organs", None)
    if plant_organs is None:
        plant_organs = {}
    else:
        plant_organs = dict(plant_organs)
        for category, category_organs in plant_organs.items():
            if isinstance(category_organs, dict):
                plant_organs[category] = dict(category_organs)

    for change in organ_changes:
        if not isinstance(change, dict):
            continue
        category = change.get("category", "")
        change_type = change.get("change_type", "new")
        organ_name = change.get("organ_name", "")
        parameters = change.get("parameters", {})
        if not parameters:
            parameter_name = change.get("parameter", "")
            delta = change.get("delta", 0)
            if parameter_name:
                parameters = {parameter_name: delta}
        if category not in plant_organ_categories:
            logger.warning(f"[植物器官] 未知类别 {category}，跳过")
            continue
        category_config = plant_organ_categories[category]
        minimum_stage = category_config.get("min_stage", 0)
        if current_stage < minimum_stage:
            logger.warning(f"[植物器官] {organ_name} 需要阶段{minimum_stage}，当前阶段{current_stage}，跳过")
            continue
        is_milestone_organ, milestone_id = plant_evolution.is_milestone_required_organ(organ_name)

        if change_type == "new":
            if category not in plant_organs:
                plant_organs[category] = {}
            valid, reason, corrected_parameters = plant_evolution.validate_custom_organ(category, organ_name, parameters, current_stage)
            if valid:
                plant_organs[category][organ_name] = {
                    **corrected_parameters,
                    "acquired_turn": turn_index,
                    "is_custom": organ_name not in plant_organ_catalog.get(category, {}),
                }
                if is_milestone_organ:
                    plant_organs[category][organ_name]["milestone_required"] = True
                    plant_organs[category][organ_name]["milestone_id"] = milestone_id
                organ_type = "自定义" if plant_organs[category][organ_name]["is_custom"] else "参考"
                logger.info(f"[植物器官] 新增{organ_type}器官: {organ_name} ({category})")
            else:
                logger.warning(f"[植物器官] 验证失败: {reason}")
        elif change_type == "enhance":
            if category in plant_organs and organ_name in plant_organs[category]:
                existing = plant_organs[category][organ_name]
                parameter_ranges = category_config.get("param_ranges", {})
                for parameter, delta in parameters.items():
                    current_value = existing.get(parameter, 0)
                    new_value = current_value + delta
                    if parameter in parameter_ranges:
                        minimum_value, maximum_value = parameter_ranges[parameter]
                        new_value = max(minimum_value, min(maximum_value, new_value))
                    existing[parameter] = new_value
                existing["modified_turn"] = turn_index
                logger.info(f"[植物器官] 增强器官: {organ_name} ({category})")
            else:
                logger.warning(f"[植物器官] 增强失败: 器官 {organ_name} 不存在于 {category}")
        elif change_type == "degrade":
            if category in plant_organs and organ_name in plant_organs[category]:
                if is_milestone_organ:
                    logger.warning(f"[植物器官] 里程碑器官 {organ_name} 不能退化")
                    continue
                existing = plant_organs[category][organ_name]
                existing["is_degraded"] = True
                existing["degraded_turn"] = turn_index
                logger.info(f"[植物器官] 退化器官: {organ_name} ({category})")

    for category, category_organs in plant_organs.items():
        if category not in organs:
            organs[category] = {}
        if category_organs:
            best_organ = None
            best_value = -1
            for name, data in category_organs.items():
                if data.get("is_degraded"):
                    continue
                category_config = plant_organ_categories.get(category, {})
                main_parameter = (category_config.get("required_params") or ["efficiency"])[0]
                value = data.get(main_parameter, 0)
                if value > best_value:
                    best_value = value
                    best_organ = name
            if best_organ:
                organs[category]["type"] = best_organ
                organs[category]["parameters"] = dict(category_organs[best_organ])
                organs[category]["evolution_stage"] = 4
                organs[category]["evolution_progress"] = 1.0
                organs[category]["is_active"] = True
    organs["_plant_organs"] = plant_organs
    return organs
```

Retain the original docstring, comments, variable names and logging layout when applying the move so the executable body remains mechanically comparable.

- [ ] **Step 4: Keep the service compatibility delegate**

Import `PLANT_ORGANS` and `PLANT_ORGAN_CATEGORIES` with the existing plant evolution imports, import the new function, and replace only the old method body with:

```python
return process_plant_organ_changes(
    organs,
    organ_changes,
    parent,
    turn_index,
    plant_evolution_service,
    PLANT_ORGANS,
    PLANT_ORGAN_CATEGORIES,
)
```

- [ ] **Step 5: Verify focused and direct regressions**

Run the focused file, then all `app/services/species/tests`. Expected: every test passes and no new warning category appears.

- [ ] **Step 6: Review and run one full quality gate**

Compare the moved executable body after normalizing the three dependency names, run `git diff --check`, inspect only the current diff, then run the backend full suite and frontend test, build and lint once. Expected: no failures; lint remains at 0 errors and no more than 162 warnings.

- [ ] **Step 7: Commit and ordinary-push**

Commit the implementation as `refactor(backend): extract plant organ changes`, ordinary-push `phase-2c-outbound-url-security` to the Fork, and add one result comment to `Pocketfans/Clade#15`. Do not merge, force-push, create a PR, release or tag.
