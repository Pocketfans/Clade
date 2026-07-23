# M5 Dormant Gene Construction Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move LLM-generated dormant-gene construction from `SpeciationService` into the focused dormant-gene module without changing validation, normalization, mutations, logging, exceptions, or callers.

**Architecture:** Add `process_ai_new_dormant_genes` beside the already extracted summary and activation functions. Keep `SpeciationService._process_ai_new_dormant_genes` and its full documentation as a compatibility delegate; reuse the dormant module's logger, which is already bound to the original `app.services.species.speciation` category.

**Tech Stack:** Python 3.12, SQLModel-compatible species data shapes, pytest.

## Global Constraints

- Modify only the dormant-gene responsibility module, its compatibility facade, and its focused test file.
- Preserve list/type checks, skip order, float conversion and clamping, defaults, harmful-gene coercion, dictionary keys, insertion order, raw input list counts in logs, return values, logger category, and existing exceptions.
- Add no dependency, constructor argument, public interface, error translation, database/schema change, persisted-format change, AI/gameplay output change, or unrelated cleanup.
- Use one implementation pass, at most one repair pass, and no subagents.
- Run one backend full suite and one frontend test/build/lint gate after focused tests pass.

---

### Task 1: Extract LLM-generated dormant-gene construction

**Files:**
- Modify: `backend/app/services/species/speciation_dormant_genes.py`
- Modify: `backend/app/services/species/speciation.py:4267`
- Modify: `backend/app/services/species/tests/test_speciation_dormant_genes.py`

**Interfaces:**
- Consumes: a Species-compatible object, an LLM `new_dormant_genes` dictionary, and an integer turn index.
- Produces: `process_ai_new_dormant_genes(species: Species, new_genes_data: dict, turn_index: int) -> int`.
- Preserves: `SpeciationService._process_ai_new_dormant_genes(species, new_genes_data, turn_index) -> int`.

- [ ] **Step 1: Run the focused baseline**

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_dormant_genes.py -q
```

Expected: the existing seven dormant-gene tests pass.

- [ ] **Step 2: Add characterization tests before production code**

Extend the dormant-module import:

```python
from ..speciation_dormant_genes import (
    process_ai_activated_genes,
    process_ai_new_dormant_genes,
    summarize_dormant_genes,
)
```

Add this fixture helper and four tests:

```python
def _new_gene_species() -> SimpleNamespace:
    return SimpleNamespace(
        common_name="测试物种",
        abstract_traits={"现有特质": 8.0},
        dormant_genes={
            "traits": {"已有休眠": {"sentinel": True}},
            "organs": {"已有器官": {"sentinel": True}},
        },
    )


def test_ai_new_dormant_genes_preserve_normalization_and_shapes() -> None:
    species = _new_gene_species()
    new_genes_data = {
        "traits": [
            {
                "name": "耐寒增强",
                "potential_value": "20",
                "pressure_types": "cold",
                "dominance": "invalid",
                "mutation_effect": "invalid",
                "description": "更耐寒",
            },
            {
                "name": "脆弱性",
                "potential_value": "bad",
                "pressure_types": ["cold"],
                "dominance": "dominant",
                "mutation_effect": "harmful",
                "target_trait": "现有特质",
                "value_modifier": "-2.5",
            },
            {"name": "已有休眠"},
            {"name": "现有特质"},
            "invalid",
            {"name": ""},
        ],
        "organs": [
            {
                "name": "厚甲",
                "organ_data": {
                    "category": "defense",
                    "type": "shell",
                    "parameters": ["invalid"],
                },
                "pressure_types": "predation",
                "dominance": "invalid",
                "description": "防御结构",
            },
            {"name": "已有器官"},
            "invalid",
            {"name": ""},
        ],
    }

    result = process_ai_new_dormant_genes(species, new_genes_data, 9)

    assert result == 3
    assert species.dormant_genes["traits"]["已有休眠"] == {
        "sentinel": True
    }
    assert species.dormant_genes["traits"]["耐寒增强"] == {
        "potential_value": 15.0,
        "activation_threshold": 0.20,
        "pressure_types": ["competition"],
        "exposure_count": 0,
        "activated": False,
        "inherited_from": "llm_speciation",
        "dominance": "codominant",
        "mutation_effect": "beneficial",
        "description": "更耐寒",
        "created_turn": 9,
    }
    assert species.dormant_genes["traits"]["脆弱性"] == {
        "potential_value": 6.0,
        "activation_threshold": 0.20,
        "pressure_types": ["cold"],
        "exposure_count": 0,
        "activated": False,
        "inherited_from": "llm_speciation",
        "dominance": "recessive",
        "mutation_effect": "harmful",
        "description": "",
        "created_turn": 9,
        "target_trait": "现有特质",
        "value_modifier": -2.5,
    }
    assert "现有特质" not in species.dormant_genes["traits"]
    assert species.dormant_genes["organs"]["已有器官"] == {
        "sentinel": True
    }
    assert species.dormant_genes["organs"]["厚甲"] == {
        "organ_data": {
            "category": "defense",
            "type": "shell",
            "parameters": {},
        },
        "activation_threshold": 0.25,
        "pressure_types": ["competition", "predation"],
        "exposure_count": 0,
        "activated": False,
        "inherited_from": "llm_speciation",
        "dominance": "codominant",
        "development_stage": None,
        "stage_start_turn": None,
        "description": "防御结构",
        "created_turn": 9,
    }


def test_ai_new_dormant_genes_preserve_empty_input_initialization() -> None:
    species = SimpleNamespace(
        common_name="测试物种", abstract_traits={}, dormant_genes={}
    )

    assert process_ai_new_dormant_genes(species, {}, 4) == 0
    assert species.dormant_genes == {}

    assert process_ai_new_dormant_genes(species, {"traits": []}, 4) == 0
    assert species.dormant_genes == {"traits": {}, "organs": {}}


def test_ai_new_dormant_genes_preserve_logger_and_raw_list_counts(
    caplog,
) -> None:
    species = SimpleNamespace(
        common_name="测试物种", abstract_traits={}, dormant_genes={}
    )
    new_genes_data = {
        "traits": [{"name": "有效特质"}, "invalid"],
        "organs": [{"name": "眼点"}],
    }

    with caplog.at_level(
        logging.INFO, logger="app.services.species.speciation"
    ):
        result = process_ai_new_dormant_genes(species, new_genes_data, 5)

    assert result == 2
    assert [
        (record.name, record.getMessage()) for record in caplog.records
    ] == [
        (
            "app.services.species.speciation",
            "[LLM新基因] 测试物种 成功添加 2 个LLM生成的休眠基因 "
            "(特质: 2, 器官: 1)",
        )
    ]


def test_speciation_service_keeps_ai_new_dormant_genes_method() -> None:
    data = {"traits": [{"name": "新特质"}]}
    direct_species = _new_gene_species()
    service_species = copy.deepcopy(direct_species)
    service = object.__new__(SpeciationService)

    direct_result = process_ai_new_dormant_genes(direct_species, data, 9)
    service_result = service._process_ai_new_dormant_genes(
        service_species, data, 9
    )

    assert service_result == direct_result
    assert vars(service_species) == vars(direct_species)
```

- [ ] **Step 3: Run the focused test and verify the red state**

Run Step 1's command.

Expected: collection fails with `ImportError: cannot import name 'process_ai_new_dormant_genes'` because the new module boundary does not yet exist.

- [ ] **Step 4: Add the extracted function with the original executable body**

Add this function to `speciation_dormant_genes.py`; its control flow and dictionary values match the current service method:

```python
def process_ai_new_dormant_genes(
    species: Species,
    new_genes_data: dict,
    turn_index: int,
) -> int:
    """处理 AI 返回的新休眠基因并添加到物种基因库。"""
    if not new_genes_data:
        return 0

    if not species.dormant_genes:
        species.dormant_genes = {"traits": {}, "organs": {}}
    species.dormant_genes.setdefault("traits", {})
    species.dormant_genes.setdefault("organs", {})

    added_count = 0

    traits_list = new_genes_data.get("traits", [])
    if isinstance(traits_list, list):
        for trait_data in traits_list:
            if not isinstance(trait_data, dict):
                continue

            trait_name = trait_data.get("name")
            if not trait_name:
                continue

            if trait_name in species.dormant_genes["traits"]:
                continue
            if trait_name in (species.abstract_traits or {}):
                continue

            potential_value = trait_data.get("potential_value", 6.0)
            try:
                potential_value = float(potential_value)
                potential_value = max(0.0, min(15.0, potential_value))
            except (ValueError, TypeError):
                potential_value = 6.0

            pressure_types = trait_data.get(
                "pressure_types", ["competition"]
            )
            if not isinstance(pressure_types, list):
                pressure_types = ["competition"]

            dominance = trait_data.get("dominance", "codominant")
            valid_dominance = [
                "dominant",
                "codominant",
                "recessive",
                "overdominant",
            ]
            if dominance not in valid_dominance:
                dominance = "codominant"

            mutation_effect = trait_data.get(
                "mutation_effect", "beneficial"
            )
            valid_effects = [
                "beneficial",
                "neutral",
                "mildly_harmful",
                "harmful",
                "lethal",
            ]
            if mutation_effect not in valid_effects:
                mutation_effect = "beneficial"

            description = trait_data.get("description", "")
            dormant_gene = {
                "potential_value": potential_value,
                "activation_threshold": 0.20,
                "pressure_types": pressure_types,
                "exposure_count": 0,
                "activated": False,
                "inherited_from": "llm_speciation",
                "dominance": dominance,
                "mutation_effect": mutation_effect,
                "description": description,
                "created_turn": turn_index,
            }

            if mutation_effect in (
                "mildly_harmful",
                "harmful",
                "lethal",
            ):
                dormant_gene["dominance"] = "recessive"
                target_trait = trait_data.get("target_trait")
                if target_trait:
                    dormant_gene["target_trait"] = target_trait
                value_modifier = trait_data.get("value_modifier", -1.0)
                try:
                    dormant_gene["value_modifier"] = float(value_modifier)
                except (ValueError, TypeError):
                    dormant_gene["value_modifier"] = -1.0

            species.dormant_genes["traits"][trait_name] = dormant_gene
            added_count += 1

            effect_label = {
                "beneficial": "有益",
                "neutral": "中性",
                "mildly_harmful": "轻微有害",
                "harmful": "有害",
            }.get(mutation_effect, "")
            dom_label = {
                "dominant": "显",
                "codominant": "共显",
                "recessive": "隐",
                "overdominant": "超显",
            }.get(dominance, "")
            logger.debug(
                f"[LLM新基因] {species.common_name} 获得特质基因: "
                f"{trait_name} "
                f"(潜力{potential_value:.1f}, {dom_label}, {effect_label})"
            )

    organs_list = new_genes_data.get("organs", [])
    if isinstance(organs_list, list):
        for organ_data in organs_list:
            if not isinstance(organ_data, dict):
                continue

            organ_name = organ_data.get("name")
            if not organ_name:
                continue

            if organ_name in species.dormant_genes["organs"]:
                continue

            organ_info = organ_data.get("organ_data", {})
            if not isinstance(organ_info, dict):
                organ_info = {}

            category = organ_info.get("category", "sensory")
            organ_type = organ_info.get("type", organ_name)
            parameters = organ_info.get("parameters", {})
            if not isinstance(parameters, dict):
                parameters = {}

            pressure_types = organ_data.get(
                "pressure_types", ["competition", "predation"]
            )
            if not isinstance(pressure_types, list):
                pressure_types = ["competition", "predation"]

            dominance = organ_data.get("dominance", "codominant")
            valid_dominance = [
                "dominant",
                "codominant",
                "recessive",
                "overdominant",
            ]
            if dominance not in valid_dominance:
                dominance = "codominant"

            description = organ_data.get("description", "")
            dormant_organ = {
                "organ_data": {
                    "category": category,
                    "type": organ_type,
                    "parameters": parameters,
                },
                "activation_threshold": 0.25,
                "pressure_types": pressure_types,
                "exposure_count": 0,
                "activated": False,
                "inherited_from": "llm_speciation",
                "dominance": dominance,
                "development_stage": None,
                "stage_start_turn": None,
                "description": description,
                "created_turn": turn_index,
            }

            species.dormant_genes["organs"][organ_name] = dormant_organ
            added_count += 1

            dom_label = {
                "dominant": "显",
                "codominant": "共显",
                "recessive": "隐",
                "overdominant": "超显",
            }.get(dominance, "")
            logger.debug(
                f"[LLM新基因] {species.common_name} 获得器官原基: "
                f"{organ_name} ({category}, {dom_label})"
            )

    if added_count > 0:
        logger.info(
            f"[LLM新基因] {species.common_name} 成功添加 "
            f"{added_count} 个LLM生成的休眠基因 "
            f"(特质: {len(traits_list) if isinstance(traits_list, list) else 0}, "
            f"器官: {len(organs_list) if isinstance(organs_list, list) else 0})"
        )

    return added_count
```

- [ ] **Step 5: Replace the service body with a compatibility delegate**

Import `process_ai_new_dormant_genes` beside the other dormant functions, retain the current service signature and full docstring, and replace only its executable body:

```python
return process_ai_new_dormant_genes(species, new_genes_data, turn_index)
```

- [ ] **Step 6: Verify focused and directly related tests**

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_dormant_genes.py -q
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests -q
```

Expected: all tests pass.

- [ ] **Step 7: Review only this diff and prove structural preservation**

Verify the extracted function's executable AST matches the original method after excluding docstrings; the compatibility method keeps its normalized documentation; the new responsibility block is at most 250 lines; the logger remains `app.services.species.speciation`; `git diff --check` exits zero; and only the three listed implementation/test files changed.

- [ ] **Step 8: Run the single full quality gate**

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend -q
npm run test:run
npm run build
npm run lint
```

Expected: backend and frontend tests pass, build exits zero, and lint reports zero errors without exceeding its 162-warning ceiling.

- [ ] **Step 9: Create one implementation commit and update the existing PR**

Stage only the three implementation/test files and commit:

```text
refactor(backend): extract dormant gene construction
```

Ordinary-push `phase-2c-outbound-url-security` to the Fork, add one concise progress comment to `Pocketfans/Clade#15`, verify PR #15 remains open/draft/unmerged, and verify local/Fork/PR head equality plus a clean worktree. Do not force-push, merge, create another PR, publish, or modify tags.
