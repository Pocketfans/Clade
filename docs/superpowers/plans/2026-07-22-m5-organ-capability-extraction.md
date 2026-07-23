# M5 Organ Capability Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move capability-label derivation out of `speciation.py` without changing labels, deduplication or list behavior.

**Architecture:** Create `speciation_organs.py` as the single internal organ/complexity function module. Keep `SpeciationService._update_capabilities` as a compatibility delegate.

**Tech Stack:** Python 3.12, pytest, existing `Species` model.

## Global Constraints

- Implement only capability-label derivation.
- Preserve the legacy map, unknown inherited labels, inactive-organ filtering, category branch order, keyword order, set deduplication and unsorted `list(capabilities)` result.
- Do not mutate the parent, organ data, formulas, repositories, dependencies, public interfaces or constructor arguments.
- Stop if implementation requires any production file besides `speciation.py` and `speciation_organs.py`.

## File Map

- Create `backend/app/services/species/speciation_organs.py`: capability derivation and the original logger category for later organ batches.
- Modify `backend/app/services/species/speciation.py`: import the function and retain the existing method as a delegate.
- Create `backend/app/services/species/tests/test_speciation_organs.py`: focused characterization and compatibility tests.

---

### Task 1: Extract capability-label derivation

**Interfaces:**
- Consumes: a species-like object with `capabilities` and an organ dictionary.
- Produces: `update_capabilities(parent: Species, organs: dict) -> list[str]`.

- [ ] **Step 1: Add failing tests**

Create `test_speciation_organs.py`:

```python
from copy import deepcopy
from types import SimpleNamespace

from ..speciation import SpeciationService
from ..speciation_organs import update_capabilities


def test_capabilities_convert_legacy_labels_preserve_unknown_and_deduplicate():
    parent = SimpleNamespace(
        capabilities=["photosynthesis", "光合作用", "custom", "venom"]
    )

    result = update_capabilities(parent, {})

    assert set(result) == {"光合作用", "custom", "毒素"}


def test_capabilities_derive_labels_from_each_active_organ_category():
    parent = SimpleNamespace(capabilities=[])
    organs = {
        "locomotion": {"type": "flagellum", "is_active": True},
        "sensory": {"type": "compound eye", "is_active": True},
        "metabolic": {"type": "chloroplast", "is_active": True},
        "digestive": {"type": "gut", "is_active": True},
        "defense": {"type": "shell", "is_active": True},
    }

    result = update_capabilities(parent, organs)

    assert set(result) == {
        "鞭毛运动",
        "感光",
        "视觉",
        "光合作用",
        "消化",
        "盔甲",
    }


def test_capabilities_skip_inactive_organs_and_preserve_keyword_priority():
    parent = SimpleNamespace(capabilities=[])
    organs = {
        "locomotion": {"type": "cilia leg fin", "is_active": True},
        "sensory": {"type": "eye", "is_active": False},
        "defense": {"type": "shell spine toxin", "is_active": True},
    }
    original = deepcopy(organs)

    result = update_capabilities(parent, organs)

    assert set(result) == {"纤毛运动", "盔甲"}
    assert organs == original


def test_service_capability_delegate_matches_direct_function():
    parent = SimpleNamespace(capabilities=["swimming"])
    organs = {"sensory": {"type": "chemoreceptor", "is_active": True}}
    service = object.__new__(SpeciationService)

    assert set(service._update_capabilities(parent, organs)) == set(
        update_capabilities(parent, organs)
    )
```

- [ ] **Step 2: Verify red**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
```

Expected: collection fails with `ModuleNotFoundError` for `speciation_organs`.

- [ ] **Step 3: Add the module and delegate**

Create `speciation_organs.py` with the mechanically moved implementation:

```python
from __future__ import annotations

import logging

from ...models.species import Species

logger = logging.getLogger(f"{__package__}.speciation")


def update_capabilities(parent: Species, organs: dict) -> list[str]:
    legacy_map = {
        "photosynthesis": "光合作用",
        "autotrophy": "自养",
        "flagellar_motion": "鞭毛运动",
        "chemical_detection": "化学感知",
        "heterotrophy": "异养",
        "chemosynthesis": "化能合成",
        "extremophile": "嗜极生物",
        "ciliary_motion": "纤毛运动",
        "limb_locomotion": "附肢运动",
        "swimming": "游泳",
        "light_detection": "感光",
        "vision": "视觉",
        "touch_sensation": "触觉",
        "aerobic_respiration": "有氧呼吸",
        "digestion": "消化",
        "armor": "盔甲",
        "spines": "棘刺",
        "venom": "毒素",
    }
    capabilities = set()
    for capability in parent.capabilities:
        if capability in legacy_map:
            capabilities.add(legacy_map[capability])
        else:
            capabilities.add(capability)
    for category, organ_data in organs.items():
        if not organ_data.get("is_active", True):
            continue
        organ_type = organ_data.get("type", "").lower()
        if category == "locomotion":
            if "flagella" in organ_type or "flagellum" in organ_type or "鞭毛" in organ_type:
                capabilities.add("鞭毛运动")
            elif "cilia" in organ_type or "纤毛" in organ_type:
                capabilities.add("纤毛运动")
            elif "leg" in organ_type or "limb" in organ_type or "足" in organ_type or "肢" in organ_type:
                capabilities.add("附肢运动")
            elif "fin" in organ_type or "鳍" in organ_type:
                capabilities.add("游泳")
        elif category == "sensory":
            if "eye" in organ_type or "ocellus" in organ_type or "眼" in organ_type:
                capabilities.add("感光")
                capabilities.add("视觉")
            elif "photoreceptor" in organ_type or "eyespot" in organ_type or "光感受" in organ_type or "眼点" in organ_type:
                capabilities.add("感光")
            elif "mechanoreceptor" in organ_type or "机械感受" in organ_type:
                capabilities.add("触觉")
            elif "chemoreceptor" in organ_type or "化学感受" in organ_type:
                capabilities.add("化学感知")
        elif category == "metabolic":
            if "chloroplast" in organ_type or "photosynthetic" in organ_type or "叶绿体" in organ_type or "光合" in organ_type:
                capabilities.add("光合作用")
            elif "mitochondria" in organ_type or "线粒体" in organ_type:
                capabilities.add("有氧呼吸")
        elif category == "digestive":
            if organ_data.get("is_active", True):
                capabilities.add("消化")
        elif category == "defense":
            if "shell" in organ_type or "carapace" in organ_type or "壳" in organ_type or "甲" in organ_type:
                capabilities.add("盔甲")
            elif "spine" in organ_type or "thorn" in organ_type or "刺" in organ_type or "棘" in organ_type:
                capabilities.add("棘刺")
            elif "toxin" in organ_type or "毒" in organ_type:
                capabilities.add("毒素")
    return list(capabilities)
```

Retain the original docstring and comments when applying the implementation. Import `update_capabilities` into `speciation.py` and replace the old method body with:

```python
return update_capabilities(parent, organs)
```

- [ ] **Step 4: Verify focused and direct regressions**

Run the new test file and all `app/services/species/tests`. Expected: four new tests and all existing tests pass.

- [ ] **Step 5: Review and run one full quality gate**

Verify AST equivalence, run `git diff --check`, backend full tests, frontend tests, build and lint once. Expected: no failures; lint 0 errors and no more than 162 warnings.

- [ ] **Step 6: Commit and ordinary-push**

Commit as `refactor(backend): extract organ capability derivation`, ordinary-push the current Fork branch, and update only PR #15. Do not merge, force-push, create a PR, release or tag.
