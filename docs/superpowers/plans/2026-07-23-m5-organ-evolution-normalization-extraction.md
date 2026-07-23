# M5 Organ Evolution Normalization Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move animal organ-evolution normalization and deduplication out of `speciation.py` without changing filtering, mutation, radius-limit, similarity or compatibility behavior.

**Architecture:** Add one internal function to the existing `speciation_organs.py` module. Pass the current instance organ catalog as an internal argument, and retain `_normalize_organ_evolution` as a thin compatibility delegate so callers and per-instance catalog behavior remain unchanged.

**Tech Stack:** Python 3.12, pytest, standard-library `re` and `difflib.SequenceMatcher`, existing `Species` model.

## Global Constraints

- Extract only organ-evolution normalization and deduplication.
- Preserve empty-input handling, non-dictionary filtering, closed `organ_key` catalog, name guessing order, category replacement, `> 0.85` parent-name similarity, the actual `gene_diversity_radius >= 0.4` new-organ boundary, one-new-key limit, first-item retention, maximum-stage merge and in-place mutation.
- Preserve the current implementation's actual behavior: same-batch entries are deduplicated by `organ_key`; no new same-batch fuzzy-name comparison is added.
- Keep the existing service method signature, including the currently unused `turn_index` argument.
- Do not extract embedding inference, biological-domain selection, organ inheritance/update orchestration, or modify catalogs, thresholds, gameplay rules, models, repositories, dependencies, public interfaces or constructor arguments.
- Stop if a production file besides `speciation.py` and `speciation_organs.py` is required.

---

### Task 1: Extract organ-evolution normalization and deduplication

**Files:**
- Modify: `backend/app/services/species/speciation_organs.py`
- Modify: `backend/app/services/species/speciation.py:5078`
- Test: `backend/app/services/species/tests/test_speciation_organs.py`

**Interfaces:**
- Consumes: `organ_evolution: list`, `parent: Species`, `turn_index: int`, `gene_diversity_radius: float`, `organ_catalog: list[dict]`.
- Produces: `normalize_organ_evolution(...) -> list`, containing the same input dictionaries currently retained and mutated by the service method.
- Compatibility: `SpeciationService._normalize_organ_evolution(...)` delegates with `self._organ_catalog`.

- [ ] **Step 1: Write failing characterization tests**

Import the wished-for function and add a helper using the exact current catalog:

```python
from ..speciation_organs import normalize_organ_evolution


ORGAN_CATALOG = [
    {"organ_key": "vision_simple_eye", "category": "sensory", "default_name": "眼点"},
    {"organ_key": "vision_complex_eye", "category": "sensory", "default_name": "成像眼"},
    {"organ_key": "locomotion_fins", "category": "locomotion", "default_name": "鳍状运动"},
]


def _normalize(changes, parent, radius):
    return normalize_organ_evolution(changes, parent, 8, radius, ORGAN_CATALOG)
```

Add focused tests proving:

```python
def test_organ_normalization_empty_input_returns_new_empty_list() -> None:
    parent = SimpleNamespace(organs={})
    assert _normalize([], parent, 0.4) == []


def test_organ_normalization_filters_invalid_items_and_unknown_keys() -> None:
    parent = SimpleNamespace(organs={})
    changes = [None, "bad", {"organ_key": "unknown", "structure_name": "未知"}]
    assert _normalize(changes, parent, 0.4) == []


def test_organ_normalization_guesses_key_and_overwrites_category_in_place() -> None:
    parent = SimpleNamespace(organs={})
    change = {
        "organ_key": "unknown",
        "category": "wrong",
        "action": "initiate",
        "structure_name": "强化-眼点!",
        "target_stage": 1,
    }
    assert _normalize([change], parent, 0.4) == [change]
    assert change["organ_key"] == "vision_simple_eye"
    assert change["category"] == "sensory"


def test_organ_normalization_converts_similar_parent_initiate_to_enhance() -> None:
    parent = SimpleNamespace(organs={"sensory": {"type": "强化眼点"}})
    change = {
        "organ_key": "vision_simple_eye",
        "category": "wrong",
        "action": "initiate",
        "structure_name": "强化眼点",
        "target_stage": 1,
    }
    assert _normalize([change], parent, 0.0) == [change]
    assert change["action"] == "enhance"
    assert change["category"] == "sensory"


def test_organ_normalization_radius_boundary_converts_or_drops_new_organs() -> None:
    existing_category_parent = SimpleNamespace(organs={"sensory": {"type": "不同名称"}})
    missing_category_parent = SimpleNamespace(organs={})
    converted = {"organ_key": "vision_simple_eye", "action": "initiate", "target_stage": 1}
    dropped = {"organ_key": "vision_simple_eye", "action": "initiate", "target_stage": 1}
    assert _normalize([converted], existing_category_parent, 0.39) == [converted]
    assert converted["action"] == "enhance"
    assert _normalize([dropped], missing_category_parent, 0.39) == []


def test_organ_normalization_allows_only_first_new_key_at_boundary() -> None:
    parent = SimpleNamespace(organs={})
    first = {"organ_key": "vision_simple_eye", "action": "initiate", "target_stage": 1}
    second = {"organ_key": "locomotion_fins", "action": "initiate", "target_stage": 1}
    assert _normalize([first, second], parent, 0.4) == [first]


def test_organ_normalization_deduplicates_by_key_into_first_item() -> None:
    parent = SimpleNamespace(organs={})
    first = {"organ_key": "vision_simple_eye", "action": "enhance", "target_stage": 2, "description": "first"}
    duplicate = {"organ_key": "vision_simple_eye", "action": "enhance", "target_stage": 4, "description": "second"}
    result = _normalize([first, duplicate], parent, 0.4)
    assert result == [first]
    assert result[0] is first
    assert first["target_stage"] == 4
    assert first["description"] == "first"


def test_service_organ_normalization_delegate_matches_direct_function() -> None:
    parent = SimpleNamespace(organs={})
    service = object.__new__(SpeciationService)
    service._organ_catalog = deepcopy(ORGAN_CATALOG)
    service_changes = [{"organ_key": "vision_simple_eye", "action": "initiate", "target_stage": 1}]
    direct_changes = deepcopy(service_changes)
    assert service._normalize_organ_evolution(service_changes, parent, 8, 0.4) == normalize_organ_evolution(
        direct_changes, parent, 8, 0.4, service._organ_catalog
    )
    assert service_changes == direct_changes
```

- [ ] **Step 2: Run the focused file and verify red**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
```

Expected: collection fails because `normalize_organ_evolution` does not yet exist.

- [ ] **Step 3: Add the minimal internal function**

Move the existing method body mechanically to `speciation_organs.py`, replacing only `self._organ_catalog` with the `organ_catalog` parameter:

```python
def normalize_organ_evolution(
    organ_evolution: list,
    parent: Species,
    turn_index: int,
    gene_diversity_radius: float,
    organ_catalog: list[dict],
) -> list:
    if not organ_evolution:
        return []

    import re
    from difflib import SequenceMatcher

    catalog = {item["organ_key"]: item for item in organ_catalog}

    def _normalize_name(name: str) -> str:
        normalized_name = (name or "").lower()
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized_name)

    def _guess_key_by_name(name: str) -> str | None:
        normalized_name = _normalize_name(name)
        for key, metadata in catalog.items():
            base = _normalize_name(metadata["default_name"])
            if base and base in normalized_name:
                return key
        return None

    def _similar(left: str, right: str) -> float:
        return SequenceMatcher(None, left, right).ratio()

    parent_index = []
    for category, data in (parent.organs or {}).items():
        if isinstance(data, dict):
            parent_index.append({
                "category": category,
                "name_norm": _normalize_name(data.get("type", "")),
                "raw": data.get("type", ""),
            })

    new_allowed = gene_diversity_radius >= 0.4
    new_count = 0
    normalized = []
    for evolution in organ_evolution:
        if not isinstance(evolution, dict):
            continue
        raw_name = evolution.get("structure_name", "") or evolution.get("description", "") or evolution.get("organ_key", "")
        organ_key = evolution.get("organ_key") or _guess_key_by_name(raw_name)
        if organ_key not in catalog:
            organ_key = _guess_key_by_name(raw_name)
        if organ_key not in catalog:
            continue
        category = catalog[organ_key]["category"]
        evolution["organ_key"] = organ_key
        evolution["category"] = category
        name_norm = _normalize_name(raw_name)
        action = evolution.get("action", "enhance")
        similar_parent = any(
            metadata["category"] == category
            and _similar(name_norm, metadata["name_norm"]) > 0.85
            for metadata in parent_index
        )
        if similar_parent and action == "initiate":
            evolution["action"] = "enhance"
        is_new = evolution.get("action", "enhance") == "initiate"
        if is_new:
            if not new_allowed:
                if category in (parent.organs or {}):
                    evolution["action"] = "enhance"
                else:
                    continue
            else:
                if new_count >= 1:
                    continue
                new_count += 1
        existing = next((item for item in normalized if item.get("organ_key") == organ_key), None)
        if existing:
            existing["target_stage"] = max(existing.get("target_stage", 1), evolution.get("target_stage", 1))
            continue
        normalized.append(evolution)
    return normalized
```

When applying the move, retain the original docstring, comments, variable names, loop structure and unused `turn_index` argument so normalized AST comparison can prove that only the catalog dependency changed.

- [ ] **Step 4: Keep the service compatibility delegate**

Import the new function and replace only the old method body with:

```python
return normalize_organ_evolution(
    organ_evolution,
    parent,
    turn_index,
    gene_diversity_radius,
    self._organ_catalog,
)
```

- [ ] **Step 5: Verify focused and species regressions**

Run the focused file, then all `app/services/species/tests`. Expected: every test passes and no new warning category appears.

- [ ] **Step 6: Review and run one full quality gate**

Compare the moved executable body after normalizing only the catalog dependency, run `git diff --check`, and inspect only the current diff and direct caller. Then run the backend full suite and frontend test, build and lint once. Expected: no failures; lint remains at 0 errors and no more than 162 warnings.

- [ ] **Step 7: Commit and ordinary-push**

Commit the implementation as `refactor(backend): extract organ normalization`, ordinary-push `phase-2c-outbound-url-security` to the Fork, and add one result comment to `Pocketfans/Clade#15`. Do not merge, force-push, create a PR, release or tag.
