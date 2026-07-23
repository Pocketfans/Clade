# M5 Speciation Organ Summary Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rules disable subagents for this single responsibility.

**Goal:** Extract deterministic organ-summary formatting from `SpeciationService` without changing any output or call site.

**Architecture:** Add one pure function to the existing `speciation_context.py` module. Keep the existing private service method as a compatibility delegate that passes `species.organs` into the pure function.

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- Modify only `speciation_context.py`, `speciation.py`, and `test_speciation_context.py`.
- Add no dependency or public API.
- Change no output text, order, defaults, threshold, formatting, repository behavior, AI behavior, gameplay rule, or formula.
- Use one red-green cycle, at most one repair cycle, and at most two review rounds.
- Create one independent implementation commit, ordinary-push it to the current Fork branch, and update only PR #15.

---

### Task 1: Extract organ-summary formatting

**Files:**

- Modify: `backend/app/services/species/speciation_context.py`
- Modify: `backend/app/services/species/speciation.py:6154-6190`
- Modify: `backend/app/services/species/tests/test_speciation_context.py`

**Interfaces:**

- Consumes: `dict | None` containing the existing organ mapping.
- Produces: `summarize_organs(organs: dict | None) -> str`.
- Preserves: `SpeciationService._summarize_organs(species) -> str`.

- [ ] **Step 1: Write the failing output-contract tests**

Append to `test_speciation_context.py`:

```python
def test_organ_summary_preserves_stage_order_and_inactive_filter() -> None:
    organs = {
        "locomotion": {
            "type": "鳍",
            "evolution_stage": 2,
            "evolution_progress": 0.456,
        },
        "defense": {"type": "甲壳", "is_active": False},
        "sensory": {"type": "复眼", "evolution_stage": 4},
    }

    assert summarize_organs(organs) == (
        "- 运动系统: 鳍（阶段2/初级，进度46%）\n"
        "- 感觉系统: 复眼（完善）"
    )


def test_organ_summary_preserves_fallbacks() -> None:
    assert summarize_organs(None) == "无已记录的器官系统"
    assert summarize_organs({}) == "无已记录的器官系统"
    assert summarize_organs(
        {"defense": {"type": "甲壳", "is_active": False}}
    ) == "无已记录的器官系统"
    assert summarize_organs(
        {"custom": {"evolution_stage": 3, "evolution_progress": 0.5}}
    ) == "- custom: 未知（阶段3/功能化，进度50%）"


def test_speciation_service_keeps_organ_summary_method() -> None:
    service = object.__new__(SpeciationService)
    organs = {"metabolic": {"type": "线粒体", "evolution_stage": 4}}
    species = SimpleNamespace(organs=organs)

    assert service._summarize_organs(species) == summarize_organs(organs)
```

Add `summarize_organs` to the existing import from `speciation_context`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_context.py -q
```

Expected: collection fails with `ImportError` because `summarize_organs` does not exist.

- [ ] **Step 3: Add the pure formatter**

Append to `speciation_context.py`:

```python
def summarize_organs(organs: dict | None) -> str:
    """生成器官系统的文本摘要，包含进化阶段信息。"""
    organs = organs or {}
    if not organs:
        return "无已记录的器官系统"

    summaries = []
    for category, organ_data in organs.items():
        if not organ_data.get("is_active", True):
            continue

        organ_type = organ_data.get("type", "未知")
        stage = organ_data.get("evolution_stage", 4)
        progress = organ_data.get("evolution_progress", 1.0)
        stage_names = {0: "无", 1: "原基", 2: "初级", 3: "功能化", 4: "完善"}
        stage_name = stage_names.get(stage, "完善")
        category_names = {
            "locomotion": "运动系统",
            "sensory": "感觉系统",
            "metabolic": "代谢系统",
            "digestive": "消化系统",
            "defense": "防御系统",
            "reproductive": "生殖系统",
        }
        category_name = category_names.get(category, category)

        if stage < 4:
            summaries.append(
                f"- {category_name}: {organ_type}（阶段{stage}/{stage_name}，"
                f"进度{progress * 100:.0f}%）"
            )
        else:
            summaries.append(f"- {category_name}: {organ_type}（完善）")

    return "\n".join(summaries) if summaries else "无已记录的器官系统"
```

- [ ] **Step 4: Preserve the compatibility method**

Add `summarize_organs` to the existing `speciation_context` import in `speciation.py`, then replace only the old method body:

```python
def _summarize_organs(self, species: Species) -> str:
    return summarize_organs(species.organs)
```

- [ ] **Step 5: Run focused and direct regression tests**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_context.py backend/app/services/species/tests/test_speciation_import.py backend/app/services/species/tests/test_speciation_repository.py backend/app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Review the exact diff**

Verify that only the three planned files changed, `git diff --check` succeeds, the compatibility method remains, and every original label/default/formatting rule appears in the pure function.

- [ ] **Step 7: Run the one final quality gate**

Run backend full pytest once, frontend full Vitest once, frontend production build once, and frontend quiet lint once. Every command must exit 0.

- [ ] **Step 8: Commit and publish**

```powershell
git add -- backend/app/services/species/speciation_context.py backend/app/services/species/speciation.py backend/app/services/species/tests/test_speciation_context.py
git commit -m "refactor(backend): extract speciation organ summary"
git push fork HEAD:phase-2c-outbound-url-security
```

Comment on PR #15 with the focused and full results. Confirm local HEAD, Fork branch, and PR head match and the worktree is clean.
