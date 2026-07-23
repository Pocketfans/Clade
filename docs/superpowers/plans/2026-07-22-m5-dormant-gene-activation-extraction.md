# M5 Dormant Gene Activation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move AI-requested dormant-gene activation from `SpeciationService` into the focused dormant-gene module without changing mutations, return values, matching, logging, or callers.

**Architecture:** Add a module-level `process_ai_activated_genes` function beside the extracted summary function. Keep `SpeciationService._process_ai_activated_genes` and its documentation as a compatibility delegate, and bind the extracted module to the original `app.services.species.speciation` logger category.

**Tech Stack:** Python 3.12, SQLModel model shapes, pytest.

## Global Constraints

- Modify only the dormant-gene responsibility module, its compatibility facade, and its focused test file.
- Preserve fuzzy-match order, trait-before-organ processing, dominance factors, the 15.0 trait cap, harmful-mutation rejection, organ stage updates, returned count, log text, and log category.
- Add no dependency, constructor argument, public interface, catch/fallback behavior, database/schema change, persisted-format change, AI/gameplay output change, or unrelated cleanup.
- Use one implementation pass, at most one repair pass, and no subagents.
- Run one backend full suite and one frontend test/build/lint gate after focused tests pass.

---

### Task 1: Extract AI-requested dormant-gene activation

**Files:**
- Modify: `backend/app/services/species/speciation_dormant_genes.py`
- Modify: `backend/app/services/species/speciation.py:4207`
- Modify: `backend/app/services/species/tests/test_speciation_dormant_genes.py`

**Interfaces:**
- Consumes: a Species-compatible object, `list[str]` requested gene names, and an integer turn index.
- Produces: `process_ai_activated_genes(species: Species, activated_genes: list[str], turn_index: int) -> int`.
- Preserves: `SpeciationService._process_ai_activated_genes(species, activated_genes, turn_index) -> int`.

- [ ] **Step 1: Run the focused baseline**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_dormant_genes.py -q
```

Expected: the existing four summary tests pass.

- [ ] **Step 2: Add characterization tests before production code**

Add these imports and tests to `test_speciation_dormant_genes.py`:

```python
import copy
import logging

from ..speciation_dormant_genes import (
    process_ai_activated_genes,
    summarize_dormant_genes,
)


def _activation_species() -> SimpleNamespace:
    return SimpleNamespace(
        common_name="测试物种",
        abstract_traits={},
        organs={},
        dormant_genes={
            "traits": {
                "耐寒增强": {
                    "activated": False,
                    "potential_value": 12.0,
                    "dominance": "recessive",
                },
                "有害甲": {
                    "activated": False,
                    "mutation_effect": "harmful",
                },
            },
            "organs": {
                "厚甲": {
                    "activated": False,
                    "development_stage": 1,
                    "organ_data": {
                        "category": "defense",
                        "type": "shell",
                        "parameters": {"hardness": 2.0},
                    },
                }
            },
        },
    )


def test_ai_activated_genes_preserve_trait_and_organ_mutations() -> None:
    species = _activation_species()

    result = process_ai_activated_genes(
        species, ["耐寒", "有害甲", "厚甲"], turn_index=9
    )

    assert result == 2
    assert species.abstract_traits == {"耐寒增强": 3.0}
    assert species.dormant_genes["traits"]["耐寒增强"] == {
        "activated": True,
        "potential_value": 12.0,
        "dominance": "recessive",
        "activation_turn": 9,
        "expressed_value": 3.0,
    }
    assert species.dormant_genes["traits"]["有害甲"] == {
        "activated": False,
        "mutation_effect": "harmful",
    }
    assert species.dormant_genes["organs"]["厚甲"] == {
        "activated": True,
        "development_stage": 2,
        "stage_start_turn": 9,
        "activation_turn": 9,
        "organ_data": {
            "category": "defense",
            "type": "shell",
            "parameters": {"hardness": 2.0},
        },
    }
    assert species.organs == {
        "defense": {
            "type": "shell",
            "parameters": {
                "hardness": 2.0,
                "efficiency_modifier": 0.60,
            },
            "acquired_turn": 9,
            "is_active": True,
            "maturity": 0.60,
            "development_stage": 2,
        }
    }


def test_ai_activated_genes_preserve_warning_logger_category(caplog) -> None:
    species = _activation_species()

    with caplog.at_level(
        logging.WARNING, logger="app.services.species.speciation"
    ):
        result = process_ai_activated_genes(species, ["有害甲"], 9)

    assert result == 0
    assert [
        (record.name, record.getMessage()) for record in caplog.records
    ] == [
        (
            "app.services.species.speciation",
            "[AI基因激活] 阻止激活有害突变: 有害甲",
        )
    ]


def test_speciation_service_keeps_ai_activated_genes_method() -> None:
    direct_species = _activation_species()
    service_species = copy.deepcopy(direct_species)
    service = object.__new__(SpeciationService)

    direct_result = process_ai_activated_genes(
        direct_species, ["耐寒", "厚甲"], 9
    )
    service_result = service._process_ai_activated_genes(
        service_species, ["耐寒", "厚甲"], 9
    )

    assert service_result == direct_result
    assert vars(service_species) == vars(direct_species)
```

- [ ] **Step 3: Run the tests and verify the red state**

Run the focused command from Step 1.

Expected: collection fails with `ImportError: cannot import name 'process_ai_activated_genes'` because the new boundary does not yet exist.

- [ ] **Step 4: Add the extracted function with the original behavior**

Add `import logging` and the original logger category to `speciation_dormant_genes.py`:

```python
import logging

logger = logging.getLogger(f"{__package__}.speciation")
```

Add the following function, retaining the original executable body:

```python
def process_ai_activated_genes(
    species: Species,
    activated_genes: list[str],
    turn_index: int,
) -> int:
    """处理 AI 指定要激活的休眠基因 v2.0。"""
    if not activated_genes:
        return 0

    if not species.dormant_genes:
        return 0

    try:
        from .gene_constants import (
            DOMINANCE_EXPRESSION_FACTOR,
            DominanceType,
            OrganStage,
        )
    except ImportError:
        DOMINANCE_EXPRESSION_FACTOR = {
            "recessive": 0.25,
            "codominant": 0.60,
            "dominant": 1.0,
            "overdominant": 1.15,
        }
        DominanceType = None
        OrganStage = None

    activated_count = 0

    for gene_name in activated_genes:
        if "traits" in species.dormant_genes:
            for trait_name, gene_data in species.dormant_genes[
                "traits"
            ].items():
                if (
                    gene_name in trait_name or trait_name in gene_name
                ) and not gene_data.get("activated", False):
                    mutation_effect = gene_data.get(
                        "mutation_effect", "beneficial"
                    )
                    if mutation_effect in (
                        "mildly_harmful",
                        "harmful",
                        "lethal",
                    ):
                        logger.warning(
                            f"[AI基因激活] 阻止激活有害突变: {trait_name}"
                        )
                        continue

                    potential_value = gene_data.get("potential_value", 8.0)
                    dominance = gene_data.get("dominance", "codominant")

                    if DominanceType:
                        try:
                            dom_type = DominanceType(dominance)
                            expression_factor = (
                                DOMINANCE_EXPRESSION_FACTOR.get(dom_type, 0.6)
                            )
                        except ValueError:
                            expression_factor = (
                                DOMINANCE_EXPRESSION_FACTOR.get(
                                    dominance, 0.6
                                )
                            )
                    else:
                        expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(
                            dominance, 0.6
                        )

                    expressed_value = potential_value * expression_factor

                    species.abstract_traits[trait_name] = min(
                        15.0, expressed_value
                    )
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn_index
                    gene_data["expressed_value"] = expressed_value
                    activated_count += 1

                    dom_label = {
                        "dominant": "显性",
                        "recessive": "隐性",
                        "codominant": "共显性",
                        "overdominant": "超显性",
                    }.get(dominance, "")
                    logger.info(
                        f"[AI基因激活] {species.common_name} 激活特质: "
                        f"{trait_name} = {expressed_value:.1f} "
                        f"(潜力{potential_value:.1f}, {dom_label})"
                    )
                    break

        if "organs" in species.dormant_genes:
            for organ_name, gene_data in species.dormant_genes[
                "organs"
            ].items():
                dev_stage = gene_data.get("development_stage")
                is_already_active = (
                    gene_data.get("activated", False) and dev_stage == 3
                )

                if (
                    gene_name in organ_name or organ_name in gene_name
                ) and not is_already_active:
                    organ_data = gene_data.get("organ_data", {})
                    organ_category = organ_data.get("category", "sensory")

                    if dev_stage is None or dev_stage < 2:
                        gene_data["development_stage"] = 2
                        gene_data["stage_start_turn"] = turn_index
                        efficiency = 0.60
                    else:
                        efficiency = {
                            0: 0.0,
                            1: 0.25,
                            2: 0.60,
                            3: 1.0,
                        }.get(dev_stage, 0.6)

                    species.organs[organ_category] = {
                        "type": organ_data.get("type", organ_name),
                        "parameters": {
                            **organ_data.get("parameters", {}),
                            "efficiency_modifier": efficiency,
                        },
                        "acquired_turn": turn_index,
                        "is_active": True,
                        "maturity": efficiency,
                        "development_stage": gene_data.get(
                            "development_stage", 2
                        ),
                    }
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn_index
                    activated_count += 1

                    stage_names = {
                        0: "原基",
                        1: "初级",
                        2: "功能原型",
                        3: "成熟",
                    }
                    logger.info(
                        f"[AI基因激活] {species.common_name} 激活器官: "
                        f"{organ_name} "
                        f"({stage_names.get(gene_data.get('development_stage'), '未知')}, "
                        f"效率{efficiency:.0%})"
                    )
                    break

    return activated_count
```

- [ ] **Step 5: Replace the service body with a compatibility delegate**

Import `process_ai_activated_genes` beside `summarize_dormant_genes`, keep the existing service method signature and full docstring, and replace only its executable body:

```python
return process_ai_activated_genes(species, activated_genes, turn_index)
```

- [ ] **Step 6: Verify focused and directly related tests**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_dormant_genes.py -q
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests -q
```

Expected: all tests pass.

- [ ] **Step 7: Review only this diff and prove structural preservation**

Verify:

- the extracted function's executable AST matches the original method after excluding docstrings;
- the compatibility method keeps its original normalized documentation;
- the logger name is `app.services.species.speciation`;
- `git diff --check` exits zero;
- only the three listed implementation/test files changed.

- [ ] **Step 8: Run the single full quality gate**

Run once:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend -q
npm run test:run
npm run build
npm run lint
```

Expected: backend and frontend tests pass, build exits zero, and lint reports zero errors without exceeding its 162-warning ceiling.

- [ ] **Step 9: Create one implementation commit and update the existing PR**

Stage only the three listed implementation/test files and commit:

```text
refactor(backend): extract dormant gene activation
```

Ordinary-push `phase-2c-outbound-url-security` to the Fork, add one concise progress comment to `Pocketfans/Clade#15`, verify PR #15 remains open/draft/unmerged, and verify local/Fork/PR head equality plus a clean worktree. Do not force-push, merge, create another PR, publish, or modify tags.
