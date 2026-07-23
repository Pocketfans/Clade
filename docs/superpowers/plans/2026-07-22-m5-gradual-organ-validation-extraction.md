# M5 Gradual Organ Validation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move gradual organ-evolution validation out of `speciation.py` without changing filtering, mutation, ordering or compatibility behavior.

**Architecture:** Add one internal function to the existing `speciation_organs.py` module. Pass the current constraint-lookup method as a callback so `SpeciationService` subclasses and the existing lazy call path keep working exactly as before; retain `_validate_gradual_evolution` as a thin delegate.

**Tech Stack:** Python 3.12, pytest, existing `Species` and speciation service code.

## Global Constraints

- Extract only gradual-evolution validation.
- Preserve empty-input handling, non-dictionary filtering, in-place dictionary mutations, rule order, logging category, constraint defaults, parent-stage lookup, stable ordering and the three-item cap.
- Do not extract plant organ changes, normalization/deduplication, embedding inference, biological-domain selection or organ inheritance/update orchestration.
- Do not change models, repositories, formulas, dependencies, public interfaces or constructor arguments.
- Stop if a production file besides `speciation.py` and `speciation_organs.py` is required.

---

### Task 1: Extract gradual organ validation

**Files:**
- Modify: `backend/app/services/species/speciation_organs.py`
- Modify: `backend/app/services/species/speciation.py:5195`
- Test: `backend/app/services/species/tests/test_speciation_organs.py`

**Interfaces:**
- Consumes: `organ_evolution: list`, `parent_organs: dict`, `biological_domain: str`, and `get_constraints: Callable[[str], dict]`.
- Produces: `validate_gradual_evolution(...) -> tuple[bool, list]` with the same mutated dictionaries and filtered list as the current method.
- Imports: add `Callable` from `typing` to `speciation_organs.py`; introduce no runtime dependency.

- [ ] **Step 1: Write failing characterization tests**

Add direct-function tests that use real dictionaries and a real callback:

```python
def test_gradual_validation_handles_empty_and_skips_non_dict_items() -> None:
    assert validate_gradual_evolution([], {}, "complexity_1", get_complexity_constraints) == (True, [])
    assert validate_gradual_evolution([None, "bad"], {}, "complexity_1", get_complexity_constraints) == (True, [])


def test_gradual_validation_applies_stage_rules_in_place() -> None:
    changes = [
        {"category": "sensory", "action": "enhance", "current_stage": 1, "target_stage": 4, "structure_name": "眼"},
        {"category": "defense", "action": "initiate", "current_stage": 0, "target_stage": 4, "structure_name": "壳"},
    ]
    valid, result = validate_gradual_evolution(changes, {"sensory": {"evolution_stage": 2}}, "complexity_1", get_complexity_constraints)
    assert valid is True
    assert result == changes
    assert result is not changes
    assert result[0] is changes[0]
    assert changes[0]["current_stage"] == 2
    assert changes[0]["target_stage"] == 3
    assert changes[1]["target_stage"] == 1


def test_gradual_validation_filters_prokaryote_forbidden_structures() -> None:
    forbidden = {"category": "metabolic", "action": "initiate", "target_stage": 1, "structure_name": "线粒体"}
    allowed = {"category": "defense", "action": "initiate", "target_stage": 1, "structure_name": "细胞壁"}
    assert validate_gradual_evolution([forbidden, allowed], {}, "complexity_0", get_complexity_constraints) == (True, [allowed])


def test_gradual_validation_converts_missing_parent_enhancement() -> None:
    change = {"category": "sensory", "action": "enhance", "current_stage": 3, "target_stage": 4, "structure_name": "眼"}
    assert validate_gradual_evolution([change], {}, "complexity_1", get_complexity_constraints) == (True, [change])
    assert change == {"category": "sensory", "action": "initiate", "current_stage": 0, "target_stage": 1, "structure_name": "眼"}


def test_gradual_validation_uses_callback_and_keeps_first_three() -> None:
    seen = []
    changes = [
        {"category": str(index), "action": "initiate", "target_stage": 0, "structure_name": str(index)}
        for index in range(4)
    ]

    def constraints(domain: str) -> dict:
        seen.append(domain)
        return {"origin_type": "eukaryote", "hard_forbidden": [], "max_organ_stage": 4}

    assert validate_gradual_evolution(changes, {}, "custom_domain", constraints) == (True, changes[:3])
    assert seen == ["custom_domain"]


def test_service_gradual_validation_delegate_matches_direct_function() -> None:
    changes = [{"category": "sensory", "action": "enhance", "current_stage": 0, "target_stage": 4, "structure_name": "眼"}]
    parent_organs = {"sensory": {"evolution_stage": 2}}
    service_changes = deepcopy(changes)
    direct_changes = deepcopy(changes)
    service = object.__new__(SpeciationService)

    assert service._validate_gradual_evolution(service_changes, parent_organs, "complexity_1") == validate_gradual_evolution(
        direct_changes,
        parent_organs,
        "complexity_1",
        get_complexity_constraints,
    )
    assert service_changes == direct_changes
```

- [ ] **Step 2: Run the focused file and verify red**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
```

Expected: collection fails because `validate_gradual_evolution` does not yet exist.

- [ ] **Step 3: Add the minimal internal function**

Move the existing method body mechanically to:

```python
def validate_gradual_evolution(
    organ_evolution: list,
    parent_organs: dict,
    biological_domain: str,
    get_constraints: Callable[[str], dict],
) -> tuple[bool, list]:
    if not organ_evolution:
        return True, []

    valid_evolutions = []
    constraints = get_constraints(biological_domain)
    hard_forbidden = constraints.get("hard_forbidden", [])
    max_stage = constraints.get("max_organ_stage", 4)
    origin_type = constraints.get("origin_type", "eukaryote")

    for evo in organ_evolution:
        if not isinstance(evo, dict):
            continue

        category = evo.get("category", "")
        action = evo.get("action", "")
        current_stage = evo.get("current_stage", 0)
        target_stage = evo.get("target_stage", 0)
        structure_name = evo.get("structure_name", "")

        stage_jump = target_stage - current_stage
        if stage_jump > 2:
            logger.info(
                f"[渐进式] 修正跳跃: {structure_name} {current_stage}→{target_stage} "
                f"改为 →{min(current_stage + 2, max_stage)}"
            )
            target_stage = min(current_stage + 2, max_stage)
            evo["target_stage"] = target_stage

        if action == "initiate" and target_stage > 1:
            logger.info(f"[渐进式] 新器官从原基开始: {structure_name}")
            evo["target_stage"] = 1

        if origin_type == "prokaryote" and hard_forbidden:
            if any(forbidden in structure_name for forbidden in hard_forbidden):
                logger.warning(
                    f"[生物学约束] 原核生物不能发展真核结构: {structure_name} "
                    f"(需要内共生事件，非渐进演化)"
                )
                continue

        if action == "enhance":
            if category not in parent_organs:
                logger.debug(f"[器官] {category}不存在，转为新发展")
                evo["action"] = "initiate"
                evo["current_stage"] = 0
                evo["target_stage"] = 1
            else:
                actual_stage = parent_organs[category].get("evolution_stage", 4)
                if current_stage != actual_stage:
                    evo["current_stage"] = actual_stage
                    if target_stage - actual_stage > 2:
                        evo["target_stage"] = min(actual_stage + 2, max_stage)

        valid_evolutions.append(evo)

    if len(valid_evolutions) > 3:
        logger.info("[器官验证] 单次分化器官变化限制为3个")
        valid_evolutions = valid_evolutions[:3]

    return True, valid_evolutions
```

Use `get_constraints(biological_domain)` at the existing lookup point. Do not copy inputs, reorder rules, add catches or normalize values.

- [ ] **Step 4: Keep the service compatibility delegate**

Import the new function into `speciation.py` and replace only the old method body with:

```python
return validate_gradual_evolution(
    organ_evolution,
    parent_organs,
    biological_domain,
    self._get_complexity_constraints,
)
```

- [ ] **Step 5: Verify focused and direct regressions**

Run the focused file, then all `app/services/species/tests`. Expected: every test passes and no new warning category appears.

- [ ] **Step 6: Review and run one full quality gate**

Compare the moved executable body by AST after replacing the constraint call with its callback equivalent, run `git diff --check`, inspect only the current diff, then run the backend full suite and frontend test, build and lint once. Expected: no failures; lint remains at 0 errors and no more than 162 warnings.

- [ ] **Step 7: Commit and ordinary-push**

Commit the implementation as `refactor(backend): extract gradual organ validation`, ordinary-push `phase-2c-outbound-url-security` to the Fork, and add one result comment to `Pocketfans/Clade#15`. Do not merge, force-push, create a PR, release or tag.
