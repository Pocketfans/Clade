import copy
import logging
from types import SimpleNamespace

from ..speciation import SpeciationService
from ..speciation_dormant_genes import (
    process_ai_activated_genes,
    process_ai_new_dormant_genes,
    summarize_dormant_genes,
)


def _species_with(dormant_genes: dict) -> SimpleNamespace:
    return SimpleNamespace(dormant_genes=dormant_genes)


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


def _new_gene_species() -> SimpleNamespace:
    return SimpleNamespace(
        common_name="测试物种",
        abstract_traits={"现有特质": 8.0},
        dormant_genes={
            "traits": {"已有休眠": {"sentinel": True}},
            "organs": {"已有器官": {"sentinel": True}},
        },
    )


def test_dormant_gene_summary_reports_empty_library() -> None:
    assert summarize_dormant_genes(_species_with({})) == "无休眠基因"


def test_dormant_gene_summary_reports_no_available_genes() -> None:
    species = _species_with(
        {
            "traits": {"已激活特质": {"activated": True}},
            "organs": {
                "成熟器官": {"activated": True, "development_stage": 3}
            },
        }
    )

    assert summarize_dormant_genes(species) == "无可激活基因"


def test_dormant_gene_summary_preserves_scoring_and_text() -> None:
    species = _species_with(
        {
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

    assert summarize_dormant_genes(species, ["cold"], 8) == (
        "推荐特质: ⭐耐寒增强[显](10), 普通代谢[隐](15)\n"
        "推荐器官: 厚甲(defense)[初级]\n"
        "⚠️ 遗传负荷: 有害甲, 有害乙 (避免激活)\n"
        "(⭐=匹配当前压力优先激活; [显]=显性易表达; "
        "[隐]=隐性需高压激活)"
    )


def test_speciation_service_keeps_dormant_gene_summary_method() -> None:
    species = _species_with({})
    service = object.__new__(SpeciationService)

    assert service._summarize_dormant_genes(species) == summarize_dormant_genes(
        species
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
