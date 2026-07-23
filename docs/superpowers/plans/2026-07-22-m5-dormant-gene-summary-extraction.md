# M5 Dormant Gene Summary Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rules disable subagents for this single responsibility.

**Goal:** Move the 198-line read-only dormant-gene scoring and summary behavior into the first function of the focused dormant-gene module without changing any AI prompt input.

**Architecture:** Create `speciation_dormant_genes.py` with a pure `summarize_dormant_genes` function. Keep `SpeciationService._summarize_dormant_genes` as a compatibility delegate; later batches will add activation and construction functions to the same module.

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- Modify only the new dormant-gene module, `speciation.py`, and one focused test file.
- Add no dependency or public API.
- Preserve all scores, thresholds, defaults, sort stability, limits, labels, warning text, and footer text.
- Change no AI prompt, gameplay rule, formula, database, repository, persisted identifier, or error behavior.
- Use one red-green cycle, at most one repair cycle, and at most two review rounds.
- Create one independent implementation commit, ordinary-push it to the current Fork branch, and update only PR #15.

---

### Task 1: Extract dormant-gene summarization

**Files:**

- Create: `backend/app/services/species/speciation_dormant_genes.py`
- Modify: `backend/app/services/species/speciation.py:4330-4527`
- Create: `backend/app/services/species/tests/test_speciation_dormant_genes.py`

**Interfaces:**

- Consumes: a `Species`-compatible object, optional pressure-type list, and pressure strength.
- Produces: `summarize_dormant_genes(species, pressure_types=None, pressure_strength=5.0) -> str`.
- Preserves: `SpeciationService._summarize_dormant_genes(species, pressure_types=None, pressure_strength=5.0) -> str`.

- [ ] **Step 1: Write the failing characterization tests**

Create `test_speciation_dormant_genes.py`:

```python
from types import SimpleNamespace

from ..speciation import SpeciationService
from ..speciation_dormant_genes import summarize_dormant_genes


def test_dormant_gene_summary_preserves_empty_messages() -> None:
    assert summarize_dormant_genes(SimpleNamespace(dormant_genes={})) == "无休眠基因"
    exhausted = SimpleNamespace(
        dormant_genes={
            "traits": {"耐寒": {"activated": True}},
            "organs": {
                "复眼": {"activated": True, "development_stage": 3}
            },
        }
    )
    assert summarize_dormant_genes(exhausted) == "无可激活基因"


def test_dormant_gene_summary_preserves_scoring_and_text() -> None:
    species = SimpleNamespace(
        dormant_genes={
            "traits": {
                "耐寒增强": {
                    "potential_value": 10,
                    "pressure_types": ["cold"],
                    "dominance": "dominant",
                },
                "普通代谢": {
                    "potential_value": 15,
                    "pressure_types": ["competition"],
                    "dominance": "recessive",
                },
                "有害甲": {"mutation_effect": "harmful"},
                "有害乙": {"mutation_effect": "lethal"},
            },
            "organs": {
                "厚甲": {
                    "pressure_types": ["cold"],
                    "development_stage": 1,
                    "organ_data": {"category": "defense"},
                }
            },
        }
    )

    assert summarize_dormant_genes(species, ["cold"], 8.0) == (
        "推荐特质: ⭐耐寒增强[显](10), 普通代谢[隐](15)\n"
        "推荐器官: 厚甲(defense)[初级]\n"
        "⚠️ 遗传负荷: 有害甲, 有害乙 (避免激活)\n"
        "(⭐=匹配当前压力优先激活; [显]=显性易表达; [隐]=隐性需高压激活)"
    )


def test_speciation_service_keeps_dormant_gene_summary_method() -> None:
    service = object.__new__(SpeciationService)
    species = SimpleNamespace(
        dormant_genes={
            "traits": {"耐热": {"pressure_types": ["heat"]}},
            "organs": {},
        }
    )

    assert service._summarize_dormant_genes(
        species, ["heat"], 7.0
    ) == summarize_dormant_genes(species, ["heat"], 7.0)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_dormant_genes.py -q
```

Expected: collection fails with `ModuleNotFoundError` because `speciation_dormant_genes.py` does not exist.

- [ ] **Step 3: Add the pure summary module**

Create `speciation_dormant_genes.py` with this complete implementation:

```python
from __future__ import annotations

from ...models.species import Species


def summarize_dormant_genes(
    species: Species,
    pressure_types: list[str] | None = None,
    pressure_strength: float = 5.0,
) -> str:
    if not species.dormant_genes:
        return "无休眠基因"

    pressure_types = pressure_types or ["competition"]
    dormant_traits = species.dormant_genes.get("traits", {})
    dormant_organs = species.dormant_genes.get("organs", {})
    available_traits = [
        (name, data)
        for name, data in dormant_traits.items()
        if not data.get("activated", False)
    ]
    available_organs = [
        (name, data)
        for name, data in dormant_organs.items()
        if not data.get("activated", False)
        or data.get("development_stage", 3) < 3
    ]
    if not available_traits and not available_organs:
        return "无可激活基因"

    harmful_traits = []
    beneficial_traits = []
    for name, data in available_traits:
        mutation_effect = data.get("mutation_effect", "beneficial")
        if mutation_effect in ("mildly_harmful", "harmful", "lethal"):
            harmful_traits.append((name, data))
        else:
            beneficial_traits.append((name, data))

    pressure_type_set = set(pressure_types)

    def score_trait(item: tuple) -> float:
        name, data = item
        score = data.get("potential_value", 5.0) / 5.0
        if set(data.get("pressure_types", [])) & pressure_type_set:
            score += 5.0
        score += min(data.get("exposure_count", 0) * 0.5, 2.0)
        dominance = data.get("dominance", "codominant")
        if dominance == "dominant":
            score += 1.0
        elif dominance == "overdominant":
            score += 1.5
        elif dominance == "recessive":
            score -= 0.5
        if pressure_strength >= 7:
            pressure_keywords = {
                "cold": ["耐寒", "寒"],
                "heat": ["耐热", "热"],
                "drought": ["耐旱", "旱", "保水"],
                "temperature_fluctuation": ["耐寒", "耐热", "温度", "适应"],
                "competition": ["竞争", "适应", "运动", "效率"],
                "predation": ["防御", "速度", "感知", "逃避"],
                "hunting": ["捕猎", "追踪", "攻击"],
                "starvation": ["代谢", "储能", "消化", "效率"],
                "disease": ["免疫", "抗性"],
                "salinity": ["耐盐", "渗透"],
                "pressure_deep": ["耐压", "深海"],
                "light_limitation": ["光合", "弱光"],
            }
            for pressure_type in pressure_types:
                for keyword in pressure_keywords.get(pressure_type, []):
                    if keyword in name:
                        score += 3.0
                        break
        return score

    top_traits = sorted(
        beneficial_traits, key=score_trait, reverse=True
    )[:3]

    def score_organ(item: tuple) -> float:
        _, data = item
        score = 0.0
        category = data.get("organ_data", {}).get("category", "")
        if set(data.get("pressure_types", [])) & pressure_type_set:
            score += 3.0
        if pressure_strength >= 7 and category in ["defense", "sensory"]:
            score += 2.0
        development_stage = data.get("development_stage")
        if development_stage is not None:
            score += (development_stage + 1) * 0.5
        score += min(data.get("exposure_count", 0) * 0.3, 1.0)
        return score

    top_organs = sorted(
        available_organs, key=score_organ, reverse=True
    )[:1]
    lines = []

    if top_traits:
        trait_items = []
        for name, data in top_traits:
            potential = data.get("potential_value", 8.0)
            dominance = data.get("dominance", "codominant")
            dominance_mark = ""
            if dominance == "dominant":
                dominance_mark = "[显]"
            elif dominance == "recessive":
                dominance_mark = "[隐]"
            elif dominance == "overdominant":
                dominance_mark = "[超显]"
            is_matched = (
                "⭐"
                if set(data.get("pressure_types", [])) & pressure_type_set
                else ""
            )
            trait_items.append(
                f"{is_matched}{name}{dominance_mark}({potential:.0f})"
            )
        lines.append(f"推荐特质: {', '.join(trait_items)}")

    if top_organs:
        name, data = top_organs[0]
        category = data.get("organ_data", {}).get("category", "")
        development_stage = data.get("development_stage")
        stage_mark = ""
        if development_stage is not None:
            stage_names = {0: "原基", 1: "初级", 2: "功能", 3: "成熟"}
            stage_mark = f"[{stage_names.get(development_stage, '未知')}]"
        lines.append(f"推荐器官: {name}({category}){stage_mark}")

    if len(harmful_traits) >= 2:
        harmful_names = [name for name, _ in harmful_traits[:2]]
        lines.append(
            f"⚠️ 遗传负荷: {', '.join(harmful_names)} (避免激活)"
        )
    if not lines:
        return "无推荐基因"
    lines.append(
        "(⭐=匹配当前压力优先激活; [显]=显性易表达; "
        "[隐]=隐性需高压激活)"
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Preserve the service compatibility method**

Import `summarize_dormant_genes` in `speciation.py` and replace only the original 198-line method body:

```python
def _summarize_dormant_genes(
    self,
    species: Species,
    pressure_types: list[str] | None = None,
    pressure_strength: float = 5.0,
) -> str:
    return summarize_dormant_genes(
        species, pressure_types, pressure_strength
    )
```

- [ ] **Step 5: Run focused and direct regression tests**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_dormant_genes.py backend/app/services/species/tests/test_speciation_import.py backend/app/services/species/tests/test_speciation_repository.py backend/app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Review and run the final quality gate**

Verify only the three planned files changed, `git diff --check` passes, all constants and strings match the original, and the compatibility method remains. Then run backend full pytest once, frontend full Vitest once, frontend build once, and quiet lint once; every command must exit 0.

- [ ] **Step 7: Commit and publish**

```powershell
git add -- backend/app/services/species/speciation_dormant_genes.py backend/app/services/species/speciation.py backend/app/services/species/tests/test_speciation_dormant_genes.py
git commit -m "refactor(backend): extract dormant gene summary"
git push fork HEAD:phase-2c-outbound-url-security
```

Comment on PR #15 with exact results. Confirm local HEAD, Fork branch, and PR head match and the worktree is clean.
