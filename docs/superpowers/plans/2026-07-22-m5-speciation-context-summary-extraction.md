# M5 Speciation Context Summary Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagents are disabled by the project resource rules.

**Goal:** Extract three pure context-summary behaviors from the 6724-line `SpeciationService` while preserving every existing output and call site.

**Architecture:** Add a dependency-free `speciation_context.py` module with three pure functions. Keep the existing private service methods as compatibility delegates so the surrounding speciation pipeline does not change.

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- Modify only the new context module, the existing speciation service, and one focused test file.
- Add no dependency or public API.
- Change no gameplay formula, threshold, database behavior, repository contract, AI behavior, or output text.
- Use one red-green implementation cycle, at most one repair cycle, and at most two review rounds.
- Create one independent implementation commit, ordinary-push it to the current Fork branch, and update only PR #15.

---

### Task 1: Extract context-summary pure functions

**Files:**
- Create: `backend/app/services/species/speciation_context.py`
- Modify: `backend/app/services/species/speciation.py:4225-4326`
- Test: `backend/app/services/species/tests/test_speciation_context.py`

**Interfaces:**
- Consumes: the existing food-chain mapping, map-change list, and major-event list inputs.
- Produces: `summarize_food_chain_status(trophic_interactions) -> str`, `summarize_map_changes(map_changes) -> str`, and `summarize_major_events(major_events) -> str`.
- Preserves: `SpeciationService._summarize_food_chain_status`, `_summarize_map_changes`, and `_summarize_major_events`.

- [ ] **Step 1: Write the failing boundary and output-contract test**

Create `test_speciation_context.py`:

```python
from types import SimpleNamespace

from ..speciation import SpeciationService
from ..speciation_context import (
    summarize_food_chain_status,
    summarize_major_events,
    summarize_map_changes,
)


def test_food_chain_summary_preserves_existing_messages() -> None:
    assert summarize_food_chain_status(None) == "食物链状态未知"
    assert summarize_food_chain_status({}) == "食物链状态未知"
    assert summarize_food_chain_status({"t2_scarcity": 0.0}) == "食物链稳定，各营养级食物充足"
    assert summarize_food_chain_status({"t2_scarcity": 0.75}) == (
        "生产者(T1)紧张，初级消费者(T2)面临食物压力"
    )
    cascade = summarize_food_chain_status({"t2_scarcity": 1.6, "t3_scarcity": 1.1})
    assert "生产者(T1)短缺" in cascade
    assert "⚠️ 食物链底层崩溃，可能引发级联灭绝" in cascade


def test_map_change_summary_preserves_limits_and_input_shapes() -> None:
    changes = [
        {"change_type": "uplift"},
        SimpleNamespace(change_type="volcanic"),
        {"change_type": "glaciation"},
        {"change_type": "subsidence"},
    ]
    assert summarize_map_changes(changes) == "地壳抬升、火山活动、冰川推进"
    assert summarize_map_changes([{"change_type": "unknown"}]) == "地形变化"
    assert summarize_map_changes([]) == ""


def test_major_event_summary_preserves_first_event_rule() -> None:
    events = [
        {"description": "火山喷发", "severity": "严重"},
        SimpleNamespace(description="不应使用", severity="高"),
    ]
    assert summarize_major_events(events) == "严重级火山喷发"
    assert summarize_major_events([SimpleNamespace(description="冰期", severity="高")]) == "高级冰期"
    assert summarize_major_events([{"description": "", "severity": "低"}]) == "重大环境事件"
    assert summarize_major_events([]) == ""


def test_speciation_service_keeps_compatibility_methods() -> None:
    service = object.__new__(SpeciationService)
    interactions = {"t4_scarcity": 0.75}
    changes = [{"change_type": "subsidence"}]
    events = [{"description": "海退", "severity": "中"}]

    assert service._summarize_food_chain_status(interactions) == summarize_food_chain_status(interactions)
    assert service._summarize_map_changes(changes) == summarize_map_changes(changes)
    assert service._summarize_major_events(events) == summarize_major_events(events)
```

The initial failure must be `ModuleNotFoundError: app.services.species.speciation_context`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_context.py -q
```

Expected: collection fails because `speciation_context.py` does not exist.

- [ ] **Step 3: Add the pure module with the existing behavior**

Create `speciation_context.py` with these exact signatures:

```python
from __future__ import annotations


def summarize_food_chain_status(
    trophic_interactions: dict[str, float] | None,
) -> str:
    if not trophic_interactions:
        return "食物链状态未知"

    status_parts = []
    t2_scarcity = trophic_interactions.get("t2_scarcity", 0.0)
    t3_scarcity = trophic_interactions.get("t3_scarcity", 0.0)
    t4_scarcity = trophic_interactions.get("t4_scarcity", 0.0)
    t5_scarcity = trophic_interactions.get("t5_scarcity", 0.0)

    if t2_scarcity > 0.5:
        status_parts.append(
            f"生产者(T1){'紧张' if t2_scarcity < 1.0 else '短缺'}，初级消费者(T2)面临食物压力"
        )
    if t3_scarcity > 0.5:
        status_parts.append(
            f"初级消费者(T2){'紧张' if t3_scarcity < 1.0 else '短缺'}，次级消费者(T3)面临食物压力"
        )
    if t4_scarcity > 0.5:
        status_parts.append(
            f"次级消费者(T3){'紧张' if t4_scarcity < 1.0 else '短缺'}，三级消费者(T4)面临食物压力"
        )
    if t5_scarcity > 0.5:
        status_parts.append(
            f"三级消费者(T4){'紧张' if t5_scarcity < 1.0 else '短缺'}，顶级捕食者(T5)面临食物压力"
        )
    if t2_scarcity > 1.5 and t3_scarcity > 1.0:
        status_parts.append("⚠️ 食物链底层崩溃，可能引发级联灭绝")
    if not status_parts:
        return "食物链稳定，各营养级食物充足"
    return "；".join(status_parts)


def summarize_map_changes(map_changes: list) -> str:
    if not map_changes:
        return ""

    change_types = []
    labels = {
        "uplift": "地壳抬升",
        "volcanic": "火山活动",
        "glaciation": "冰川推进",
        "subsidence": "地壳下沉",
    }
    for change in map_changes[:3]:
        change_type = (
            change.get("change_type", "")
            if isinstance(change, dict)
            else getattr(change, "change_type", "")
        )
        if change_type in labels:
            change_types.append(labels[change_type])
    return "、".join(change_types) if change_types else "地形变化"


def summarize_major_events(major_events: list) -> str:
    if not major_events:
        return ""

    event = major_events[0]
    if isinstance(event, dict):
        description = event.get("description", "")
        severity = event.get("severity", "")
    else:
        description = getattr(event, "description", "")
        severity = getattr(event, "severity", "")
    if description:
        return f"{severity}级{description}"
    return "重大环境事件"
```

The mapping form is equivalent to the existing branches and keeps the same four recognized values, first-three limit, ordering, and fallback text.

- [ ] **Step 4: Replace the large service method bodies with compatibility delegates**

Import the three functions into `speciation.py` and use:

```python
def _summarize_food_chain_status(self, trophic_interactions):
    return summarize_food_chain_status(trophic_interactions)

def _summarize_map_changes(self, map_changes):
    return summarize_map_changes(map_changes)

def _summarize_major_events(self, major_events):
    return summarize_major_events(major_events)
```

- [ ] **Step 5: Run focused and direct regression tests and verify GREEN**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_context.py backend/app/services/species/tests/test_speciation_import.py backend/app/services/species/tests/test_speciation_repository.py backend/app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Review the exact diff**

Verify that only the three planned production/test files changed, `git diff --check` succeeds, the compatibility method names remain, and no output string or threshold changed.

- [ ] **Step 7: Run the one final quality gate**

Run backend full pytest once, frontend full Vitest once, frontend production build once, and frontend quiet lint once. All commands must exit 0.

- [ ] **Step 8: Commit and publish the implementation**

```powershell
git add -- backend/app/services/species/speciation_context.py backend/app/services/species/speciation.py backend/app/services/species/tests/test_speciation_context.py
git commit -m "refactor(backend): extract speciation context summaries"
git push fork HEAD:phase-2c-outbound-url-security
```

Add one progress comment to PR #15 with the focused and full quality-gate results. Confirm local HEAD, Fork branch, and PR head are identical and the worktree is clean.
