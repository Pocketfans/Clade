from copy import deepcopy
from types import SimpleNamespace

import pytest

from ..plant_evolution import (
    PLANT_ORGANS,
    PLANT_ORGAN_CATEGORIES,
    plant_evolution_service,
)
from ..speciation import SpeciationService
from ..speciation_organs import (
    get_complexity_constraints,
    inherit_and_update_organs,
    infer_biological_domain,
    infer_complexity_by_embedding,
    infer_complexity_by_rules,
    normalize_organ_evolution,
    process_plant_organ_changes,
    update_capabilities,
    validate_gradual_evolution,
)


ORGAN_CATALOG = [
    {
        "organ_key": "vision_simple_eye",
        "category": "sensory",
        "default_name": "眼点",
    },
    {
        "organ_key": "vision_complex_eye",
        "category": "sensory",
        "default_name": "成像眼",
    },
    {
        "organ_key": "locomotion_fins",
        "category": "locomotion",
        "default_name": "鳍状运动",
    },
]

COMPLEXITY_REFERENCES = {
    0: "level zero",
    1: "level one",
    2: "level two",
}


class _EmbeddingVectors:
    def __init__(
        self,
        reference_vectors: list[list[float]],
        species_vector: list[float],
        *,
        fail_species: bool = False,
    ) -> None:
        self.reference_vectors = reference_vectors
        self.species_vector = species_vector
        self.fail_species = fail_species
        self.calls: list[tuple[list[str], bool]] = []

    def embed(self, texts: list[str], require_real: bool = False) -> list[list[float]]:
        self.calls.append((list(texts), require_real))
        if len(texts) > 1:
            return self.reference_vectors
        if self.fail_species:
            raise RuntimeError("species embedding failed")
        return [self.species_vector]


def test_capabilities_convert_legacy_labels_preserve_unknown_and_deduplicate() -> None:
    parent = SimpleNamespace(
        capabilities=["photosynthesis", "光合作用", "custom", "venom"]
    )

    result = update_capabilities(parent, {})

    assert set(result) == {"光合作用", "custom", "毒素"}


def test_capabilities_derive_labels_from_each_active_organ_category() -> None:
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


def test_capabilities_skip_inactive_organs_and_preserve_keyword_priority() -> None:
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


def test_service_capability_delegate_matches_direct_function() -> None:
    parent = SimpleNamespace(capabilities=["swimming"])
    organs = {
        "sensory": {"type": "chemoreceptor", "is_active": True},
    }
    service = object.__new__(SpeciationService)

    assert set(service._update_capabilities(parent, organs)) == set(
        update_capabilities(parent, organs)
    )


def _complexity_species(
    *,
    description: str = "",
    common_name: str = "",
    organs: dict | None = None,
    body_length_cm: float = 0.01,
) -> SimpleNamespace:
    return SimpleNamespace(
        description=description,
        common_name=common_name,
        organs=organs or {},
        morphology_stats={"body_length_cm": body_length_cm},
    )


def test_complexity_rules_preserve_keyword_priority_and_prokaryote_guard() -> None:
    assert infer_complexity_by_rules(
        _complexity_species(description="细菌与哺乳动物的对照描述")
    ) == 5
    assert infer_complexity_by_rules(
        _complexity_species(description="具有线粒体的细菌", body_length_cm=0.01)
    ) == 1


@pytest.mark.parametrize(
    ("organs", "body_length_cm", "expected"),
    [
        ({f"organ_{index}": {} for index in range(5)}, 0.01, 4),
        ({f"organ_{index}": {} for index in range(3)}, 0.01, 3),
        ({"active": {}, "inactive": {"is_active": False}}, 0.2, 2),
        ({"active": {}}, 0.1, 1),
    ],
)
def test_complexity_rules_count_only_active_organs(
    organs: dict, body_length_cm: float, expected: int
) -> None:
    assert infer_complexity_by_rules(
        _complexity_species(organs=organs, body_length_cm=body_length_cm)
    ) == expected


@pytest.mark.parametrize(
    ("body_length_cm", "expected"),
    [
        (0.0009, 0),
        (0.001, 1),
        (0.1, 2),
        (1.0, 3),
        (10.0, 4),
    ],
)
def test_complexity_rules_preserve_body_length_boundaries(
    body_length_cm: float, expected: int
) -> None:
    assert infer_complexity_by_rules(
        _complexity_species(body_length_cm=body_length_cm)
    ) == expected


def test_complexity_constraints_preserve_prokaryote_and_eukaryote_rules() -> None:
    assert get_complexity_constraints("complexity_0") == {
        "origin_type": "prokaryote",
        "hard_forbidden": [
            "真核鞭毛",
            "纤毛",
            "线粒体",
            "叶绿体",
            "细胞核",
            "内质网",
            "高尔基体",
        ],
        "max_organ_stage": 4,
    }
    assert get_complexity_constraints("complexity_5") == {
        "origin_type": "eukaryote",
        "hard_forbidden": [],
        "max_organ_stage": 4,
    }
    assert get_complexity_constraints("unknown") == {
        "origin_type": "eukaryote",
        "hard_forbidden": [],
        "max_organ_stage": 4,
    }

    with pytest.raises(ValueError):
        get_complexity_constraints("complexity_invalid")


def test_service_complexity_delegates_match_direct_functions() -> None:
    species = _complexity_species(common_name="水母")
    service = object.__new__(SpeciationService)

    assert service._infer_complexity_by_rules(species) == infer_complexity_by_rules(
        species
    )
    assert service._get_complexity_constraints(
        "complexity_0"
    ) == get_complexity_constraints("complexity_0")


def test_gradual_validation_empty_input_skips_constraint_lookup() -> None:
    def unexpected_lookup(_domain: str) -> dict:
        raise AssertionError("empty input must not read constraints")

    assert validate_gradual_evolution([], {}, "complexity_1", unexpected_lookup) == (
        True,
        [],
    )


def test_gradual_validation_skips_non_dictionary_items() -> None:
    assert validate_gradual_evolution(
        [None, "bad"], {}, "complexity_1", get_complexity_constraints
    ) == (True, [])


def test_gradual_validation_applies_parent_stage_and_jump_rules_in_place() -> None:
    change = {
        "category": "sensory",
        "action": "enhance",
        "current_stage": 1,
        "target_stage": 4,
        "structure_name": "眼",
    }

    valid, result = validate_gradual_evolution(
        [change],
        {"sensory": {"evolution_stage": 2}},
        "complexity_1",
        get_complexity_constraints,
    )

    assert valid is True
    assert result == [change]
    assert result[0] is change
    assert change["current_stage"] == 2
    assert change["target_stage"] == 3


def test_gradual_validation_starts_new_organs_at_stage_one() -> None:
    change = {
        "category": "defense",
        "action": "initiate",
        "current_stage": 0,
        "target_stage": 4,
        "structure_name": "壳",
    }

    assert validate_gradual_evolution(
        [change], {}, "complexity_1", get_complexity_constraints
    ) == (True, [change])
    assert change["target_stage"] == 1


def test_gradual_validation_filters_prokaryote_forbidden_structures() -> None:
    forbidden = {
        "category": "metabolic",
        "action": "initiate",
        "target_stage": 1,
        "structure_name": "线粒体",
    }
    allowed = {
        "category": "defense",
        "action": "initiate",
        "target_stage": 1,
        "structure_name": "细胞壁",
    }

    assert validate_gradual_evolution(
        [forbidden, allowed], {}, "complexity_0", get_complexity_constraints
    ) == (True, [allowed])


def test_gradual_validation_converts_missing_parent_enhancement() -> None:
    change = {
        "category": "sensory",
        "action": "enhance",
        "current_stage": 3,
        "target_stage": 4,
        "structure_name": "眼",
    }

    assert validate_gradual_evolution(
        [change], {}, "complexity_1", get_complexity_constraints
    ) == (True, [change])
    assert change == {
        "category": "sensory",
        "action": "initiate",
        "current_stage": 0,
        "target_stage": 1,
        "structure_name": "眼",
    }


def test_gradual_validation_uses_constraint_callback() -> None:
    seen = []
    change = {
        "category": "defense",
        "action": "initiate",
        "current_stage": 0,
        "target_stage": 4,
        "structure_name": "壳",
    }

    def constraints(domain: str) -> dict:
        seen.append(domain)
        return {
            "origin_type": "eukaryote",
            "hard_forbidden": [],
            "max_organ_stage": 1,
        }

    assert validate_gradual_evolution(
        [change], {}, "custom_domain", constraints
    ) == (True, [change])
    assert seen == ["custom_domain"]
    assert change["target_stage"] == 1


def test_gradual_validation_keeps_only_first_three_valid_changes() -> None:
    changes = [
        {
            "category": str(index),
            "action": "initiate",
            "target_stage": 0,
            "structure_name": str(index),
        }
        for index in range(4)
    ]

    assert validate_gradual_evolution(
        changes, {}, "complexity_1", get_complexity_constraints
    ) == (True, changes[:3])


def test_service_gradual_validation_delegate_matches_direct_function() -> None:
    changes = [
        {
            "category": "sensory",
            "action": "enhance",
            "current_stage": 0,
            "target_stage": 4,
            "structure_name": "眼",
        }
    ]
    parent_organs = {"sensory": {"evolution_stage": 2}}
    service_changes = deepcopy(changes)
    direct_changes = deepcopy(changes)
    service = object.__new__(SpeciationService)

    assert service._validate_gradual_evolution(
        service_changes, parent_organs, "complexity_1"
    ) == validate_gradual_evolution(
        direct_changes,
        parent_organs,
        "complexity_1",
        get_complexity_constraints,
    )
    assert service_changes == direct_changes


def _process_plant_changes(
    organs: dict,
    changes: list,
    parent: SimpleNamespace,
    turn_index: int,
) -> dict:
    return process_plant_organ_changes(
        organs,
        changes,
        parent,
        turn_index,
        plant_evolution_service,
        PLANT_ORGANS,
        PLANT_ORGAN_CATEGORIES,
    )


def test_plant_changes_empty_input_returns_same_generic_organs() -> None:
    organs = {"legacy": {"type": "legacy"}}
    parent = SimpleNamespace(life_form_stage=0, plant_organs=None)

    result = _process_plant_changes(organs, [], parent, 4)

    assert result is organs
    assert result == {
        "legacy": {"type": "legacy"},
        "_plant_organs": {},
    }


def test_plant_changes_add_reference_milestone_from_legacy_parameters() -> None:
    organs = {}
    parent = SimpleNamespace(life_form_stage=1, plant_organs=None)
    change = {
        "category": "photosynthetic",
        "change_type": "new",
        "organ_name": "叶绿体",
        "parameter": "efficiency",
        "delta": 9.0,
    }

    result = _process_plant_changes(organs, [change], parent, 7)
    stored = result["_plant_organs"]["photosynthetic"]["叶绿体"]

    assert stored == {
        "efficiency": 5.0,
        "min_stage": 0,
        "acquired_turn": 7,
        "is_custom": False,
        "milestone_required": True,
        "milestone_id": "first_eukaryote",
    }
    assert result["photosynthetic"] == {
        "type": "叶绿体",
        "parameters": stored.copy(),
        "evolution_stage": 4,
        "evolution_progress": 1.0,
        "is_active": True,
    }


def test_plant_changes_skip_unknown_and_stage_locked_categories() -> None:
    parent = SimpleNamespace(life_form_stage=0, plant_organs=None)
    changes = [
        {
            "category": "unknown",
            "change_type": "new",
            "organ_name": "未知",
            "parameters": {},
        },
        {
            "category": "root_system",
            "change_type": "new",
            "organ_name": "假根",
            "parameters": {"depth_cm": 1, "absorption": 1},
        },
    ]

    assert _process_plant_changes({}, changes, parent, 1) == {
        "_plant_organs": {}
    }


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
        {
            "category": "photosynthetic",
            "change_type": "enhance",
            "organ_name": "自定义叶",
            "parameters": {"efficiency": 1.0},
        },
        {
            "category": "protection",
            "change_type": "degrade",
            "organ_name": "树脂层",
        },
    ]

    result = _process_plant_changes({}, changes, parent, 9)

    assert photosynthetic == {
        "efficiency": 5.0,
        "min_stage": 0,
        "modified_turn": 9,
    }
    assert protection == {
        "uv_resist": 1.0,
        "min_stage": 0,
        "is_degraded": True,
        "degraded_turn": 9,
    }
    assert result["photosynthetic"]["type"] == "自定义叶"
    assert "type" not in result["protection"]


def test_plant_changes_protect_milestones_and_keep_first_best_organ() -> None:
    first = {"efficiency": 2.0, "min_stage": 0}
    tied = {"efficiency": 2.0, "min_stage": 0}
    milestone = {"efficiency": 1.0, "min_stage": 0}
    parent = SimpleNamespace(
        life_form_stage=3,
        plant_organs={
            "photosynthetic": {
                "第一叶": first,
                "同值叶": tied,
                "叶绿体": milestone,
            }
        },
    )
    changes = [
        {
            "category": "photosynthetic",
            "change_type": "degrade",
            "organ_name": "叶绿体",
        }
    ]

    result = _process_plant_changes({}, changes, parent, 10)

    assert "is_degraded" not in milestone
    assert result["photosynthetic"]["type"] == "第一叶"


def test_service_plant_change_delegate_matches_direct_function() -> None:
    parent = SimpleNamespace(life_form_stage=1, plant_organs=None)
    changes = [
        {
            "category": "photosynthetic",
            "change_type": "new",
            "organ_name": "光合泡",
            "parameters": {"efficiency": 1.2},
        }
    ]
    service_organs = {}
    direct_organs = {}
    service = object.__new__(SpeciationService)

    assert service._process_plant_organ_changes(
        service_organs, deepcopy(changes), parent, 3
    ) == _process_plant_changes(
        direct_organs, deepcopy(changes), parent, 3
    )
    assert service_organs == direct_organs


def _normalize_organ_changes(
    changes: list,
    parent: SimpleNamespace,
    radius: float,
) -> list:
    return normalize_organ_evolution(changes, parent, 8, radius, ORGAN_CATALOG)


def test_organ_normalization_empty_input_returns_empty_list() -> None:
    parent = SimpleNamespace(organs={})

    assert _normalize_organ_changes([], parent, 0.4) == []


def test_organ_normalization_filters_invalid_items_and_unknown_keys() -> None:
    parent = SimpleNamespace(organs={})
    changes = [
        None,
        "bad",
        {"organ_key": "unknown", "structure_name": "未知"},
    ]

    assert _normalize_organ_changes(changes, parent, 0.4) == []


def test_organ_normalization_guesses_key_and_overwrites_category_in_place() -> None:
    parent = SimpleNamespace(organs={})
    change = {
        "organ_key": "unknown",
        "category": "wrong",
        "action": "initiate",
        "structure_name": "强化-眼点!",
        "target_stage": 1,
    }

    assert _normalize_organ_changes([change], parent, 0.4) == [change]
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

    assert _normalize_organ_changes([change], parent, 0.0) == [change]
    assert change["action"] == "enhance"
    assert change["category"] == "sensory"


def test_organ_normalization_radius_boundary_converts_or_drops_new_organs() -> None:
    existing_category_parent = SimpleNamespace(
        organs={"sensory": {"type": "不同名称"}}
    )
    missing_category_parent = SimpleNamespace(organs={})
    converted = {
        "organ_key": "vision_simple_eye",
        "action": "initiate",
        "target_stage": 1,
    }
    dropped = {
        "organ_key": "vision_simple_eye",
        "action": "initiate",
        "target_stage": 1,
    }

    assert _normalize_organ_changes(
        [converted], existing_category_parent, 0.39
    ) == [converted]
    assert converted["action"] == "enhance"
    assert _normalize_organ_changes([dropped], missing_category_parent, 0.39) == []


def test_organ_normalization_allows_only_first_new_key_at_boundary() -> None:
    parent = SimpleNamespace(organs={})
    first = {
        "organ_key": "vision_simple_eye",
        "action": "initiate",
        "target_stage": 1,
    }
    second = {
        "organ_key": "locomotion_fins",
        "action": "initiate",
        "target_stage": 1,
    }

    assert _normalize_organ_changes([first, second], parent, 0.4) == [first]


def test_organ_normalization_deduplicates_by_key_into_first_item() -> None:
    parent = SimpleNamespace(organs={})
    first = {
        "organ_key": "vision_simple_eye",
        "action": "enhance",
        "target_stage": 2,
        "description": "first",
    }
    duplicate = {
        "organ_key": "vision_simple_eye",
        "action": "enhance",
        "target_stage": 4,
        "description": "second",
    }

    result = _normalize_organ_changes([first, duplicate], parent, 0.4)

    assert result == [first]
    assert result[0] is first
    assert first["target_stage"] == 4
    assert first["description"] == "first"


def test_service_organ_normalization_delegate_matches_direct_function() -> None:
    parent = SimpleNamespace(organs={})
    service = object.__new__(SpeciationService)
    service._organ_catalog = deepcopy(ORGAN_CATALOG)
    service_changes = [
        {
            "organ_key": "vision_simple_eye",
            "action": "initiate",
            "target_stage": 1,
        }
    ]
    direct_changes = deepcopy(service_changes)

    assert service._normalize_organ_evolution(
        service_changes, parent, 8, 0.4
    ) == normalize_organ_evolution(
        direct_changes,
        parent,
        8,
        0.4,
        service._organ_catalog,
    )
    assert service_changes == direct_changes


def _embedding_species() -> SimpleNamespace:
    return SimpleNamespace(
        common_name="test species",
        description="test description",
        abstract_traits={"speed": 8.0, "armor": 2.0},
    )


def _infer_with_cache(
    embedding_service: _EmbeddingVectors,
    state: dict,
    *,
    effective: dict[int, list[float]] | None = None,
) -> int | None:
    return infer_complexity_by_embedding(
        _embedding_species(),
        embedding_service,
        COMPLEXITY_REFERENCES,
        lambda: state["base"],
        lambda value: state.__setitem__("base", value),
        lambda: state["base"] if effective is None else effective,
    )


def test_domain_selection_prefers_embedding_and_skips_rules() -> None:
    calls = []
    species = _embedding_species()

    result = infer_biological_domain(
        species,
        lambda current: calls.append(("embedding", current)) or 4,
        lambda current: calls.append(("rules", current)) or 2,
    )

    assert result == "complexity_4"
    assert calls == [("embedding", species)]


def test_domain_selection_falls_back_to_rules_only_for_none() -> None:
    species = _embedding_species()
    calls = []

    result = infer_biological_domain(
        species,
        lambda current: calls.append(("embedding", current)),
        lambda current: calls.append(("rules", current)) or 2,
    )

    assert result == "complexity_2"
    assert calls == [("embedding", species), ("rules", species)]


def test_embedding_complexity_initializes_cache_and_selects_best_level() -> None:
    embedding_service = _EmbeddingVectors(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        [0.0, 2.0],
    )
    state = {"base": None}

    assert _infer_with_cache(embedding_service, state) == 1
    assert state["base"] == {
        0: [1.0, 0.0],
        1: [0.0, 1.0],
        2: [-1.0, 0.0],
    }
    assert embedding_service.calls[0] == (
        list(COMPLEXITY_REFERENCES.values()),
        False,
    )
    assert embedding_service.calls[1][1] is False


def test_embedding_complexity_uses_effective_cache_without_reembedding_references() -> None:
    embedding_service = _EmbeddingVectors([], [0.0, 1.0])
    state = {"base": {0: [1.0, 0.0]}}
    effective = {4: [0.0, 1.0]}

    assert _infer_with_cache(
        embedding_service, state, effective=effective
    ) == 4
    assert len(embedding_service.calls) == 1


def test_embedding_complexity_returns_none_for_zero_species_vector() -> None:
    embedding_service = _EmbeddingVectors([], [0.0, 0.0])
    state = {"base": {0: [1.0, 0.0]}}

    assert _infer_with_cache(embedding_service, state) is None


def test_embedding_complexity_skips_zero_references_and_keeps_default_level() -> None:
    embedding_service = _EmbeddingVectors([], [1.0, 0.0])
    state = {"base": {0: [0.0, 0.0], 5: [0.0, 0.0]}}

    assert _infer_with_cache(embedding_service, state) == 1


def test_embedding_complexity_keeps_first_level_on_similarity_tie() -> None:
    embedding_service = _EmbeddingVectors([], [1.0, 0.0])
    state = {"base": {3: [1.0, 0.0], 4: [2.0, 0.0]}}

    assert _infer_with_cache(embedding_service, state) == 3


def test_embedding_complexity_preserves_cache_when_species_embed_fails() -> None:
    embedding_service = _EmbeddingVectors(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        [0.0, 1.0],
        fail_species=True,
    )
    state = {"base": None}

    assert _infer_with_cache(embedding_service, state) is None
    assert state["base"] == {
        0: [1.0, 0.0],
        1: [0.0, 1.0],
        2: [-1.0, 0.0],
    }


def test_service_embedding_delegate_lazily_uses_router_and_class_cache(
    monkeypatch,
) -> None:
    embedding_service = _EmbeddingVectors(
        [[1.0, 0.0] for _ in SpeciationService._COMPLEXITY_REFERENCES],
        [1.0, 0.0],
    )
    service = object.__new__(SpeciationService)
    service.router = SimpleNamespace(embedding_service=embedding_service)
    monkeypatch.setattr(SpeciationService, "_complexity_embeddings", None)

    assert service._infer_complexity_by_embedding(_embedding_species()) == 0
    assert service._embedding_service is embedding_service
    assert SpeciationService._complexity_embeddings is not None


def test_service_embedding_delegate_returns_none_without_available_service() -> None:
    service = object.__new__(SpeciationService)
    service.router = SimpleNamespace()

    assert service._infer_complexity_by_embedding(_embedding_species()) is None


def test_service_domain_delegate_preserves_method_overrides() -> None:
    calls = []

    class _OverriddenService(SpeciationService):
        def _infer_complexity_by_embedding(self, species):
            calls.append("embedding")
            return None

        def _infer_complexity_by_rules(self, species):
            calls.append("rules")
            return 5

    service = object.__new__(_OverriddenService)

    assert service._infer_biological_domain(
        _embedding_species()
    ) == "complexity_5"
    assert calls == ["embedding", "rules"]


def _unexpected_organ_callback(*args, **kwargs):
    raise AssertionError(f"unexpected callback: {args!r} {kwargs!r}")


def test_organ_update_inherits_category_defaults_and_preserves_nested_sharing() -> None:
    parameters = {"focus": 0.8}
    history = [{"turn": 1}]
    parent = SimpleNamespace(
        organs={
            "sensory": {
                "type": "眼点",
                "parameters": parameters,
                "evolution_history": history,
            }
        },
        gene_diversity_radius=0.35,
    )

    result = inherit_and_update_organs(
        parent,
        {},
        8,
        lambda current: False,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
    )

    assert result["sensory"] is not parent.organs["sensory"]
    assert result["sensory"]["evolution_stage"] == 4
    assert result["sensory"]["evolution_progress"] == 1.0
    assert "evolution_stage" not in parent.organs["sensory"]
    assert result["sensory"]["parameters"] is parameters
    assert result["sensory"]["evolution_history"] is history


def test_organ_update_uses_plant_changes_before_animal_formats() -> None:
    calls = []
    plant_result = {"plant": {"type": "叶绿体"}}
    parent = SimpleNamespace(
        organs={"photosynthetic": {"type": "光合泡"}},
        gene_diversity_radius=0.35,
    )
    changes = [{"action": "initiate", "organ_name": "叶绿体"}]

    def process_plant(organs, organ_changes, current_parent, turn_index):
        calls.append(("plant", organs, organ_changes, current_parent, turn_index))
        return plant_result

    result = inherit_and_update_organs(
        parent,
        {
            "organ_changes": changes,
            "organ_evolution": [{"action": "initiate"}],
            "structural_innovations": [{"category": "legacy"}],
        },
        9,
        lambda current: calls.append(("is_plant", current)) or True,
        process_plant,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
    )

    assert result is plant_result
    assert [call[0] for call in calls] == ["is_plant", "plant"]
    _, inherited, passed_changes, passed_parent, passed_turn = calls[1]
    assert inherited["photosynthetic"]["evolution_stage"] == 4
    assert passed_changes is changes
    assert passed_parent is parent
    assert passed_turn == 9


def test_organ_update_applies_normalized_gradual_evolution_in_callback_order() -> None:
    history = [{"turn": 2, "from_stage": 1, "to_stage": 2}]
    parent = SimpleNamespace(
        organs={
            "sensory": {
                "type": "眼点",
                "evolution_stage": 2,
                "evolution_progress": 0.5,
                "evolution_history": history,
            }
        },
        gene_diversity_radius=0,
    )
    raw = [{"action": "raw"}]
    valid = [{"action": "validated"}]
    normalized = [
        {
            "category": "locomotion",
            "action": "initiate",
            "target_stage": 1,
            "structure_name": "鳍芽",
            "description": "开始形成鳍",
        },
        {
            "category": "sensory",
            "action": "enhance",
            "target_stage": 3,
            "structure_name": "复眼",
            "description": "视觉增强",
        },
    ]
    calls = []

    def infer_domain(current_parent):
        calls.append(("domain", current_parent))
        return "complexity_3"

    def validate(evolutions, parent_organs, domain):
        calls.append(("validate", evolutions, parent_organs, domain))
        return False, valid

    def normalize(evolutions, current_parent, turn_index, radius):
        calls.append(("normalize", evolutions, current_parent, turn_index, radius))
        return normalized

    result = inherit_and_update_organs(
        parent,
        {"organ_evolution": raw},
        12,
        lambda current: False,
        _unexpected_organ_callback,
        infer_domain,
        validate,
        normalize,
    )

    assert [call[0] for call in calls] == ["domain", "validate", "normalize"]
    assert calls[1][1:] == (raw, parent.organs, "complexity_3")
    assert calls[2][1:] == (valid, parent, 12, 0.35)
    assert result["locomotion"] == {
        "type": "鳍芽",
        "parameters": {},
        "evolution_stage": 1,
        "evolution_progress": 0.25,
        "acquired_turn": 12,
        "is_active": False,
        "evolution_history": [
            {
                "turn": 12,
                "from_stage": 0,
                "to_stage": 1,
                "description": "开始形成鳍",
            }
        ],
    }
    assert result["sensory"]["type"] == "复眼"
    assert result["sensory"]["evolution_stage"] == 3
    assert result["sensory"]["evolution_progress"] == 0.75
    assert result["sensory"]["modified_turn"] == 12
    assert result["sensory"]["is_active"] is True
    assert result["sensory"]["evolution_history"] is history
    assert parent.organs["sensory"]["evolution_history"][-1] == {
        "turn": 12,
        "from_stage": 2,
        "to_stage": 3,
        "description": "视觉增强",
    }


def test_organ_update_non_list_gradual_payload_falls_through_to_legacy() -> None:
    parent = SimpleNamespace(
        organs={
            "sensory": {
                "type": "眼点",
                "evolution_stage": 4,
                "evolution_progress": 1.0,
            }
        },
        gene_diversity_radius=0.35,
    )

    result = inherit_and_update_organs(
        parent,
        {
            "organ_evolution": {"action": "enhance"},
            "structural_innovations": [
                "invalid",
                {
                    "category": "sensory",
                    "type": "复眼",
                    "parameters": {"acuity": 0.9},
                },
                {
                    "category": "defense",
                    "type": "甲壳",
                    "parameters": {"hardness": 0.6},
                },
            ],
        },
        15,
        lambda current: False,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
    )

    assert result["sensory"] == {
        "type": "复眼",
        "parameters": {"acuity": 0.9},
        "evolution_stage": 4,
        "evolution_progress": 1.0,
        "modified_turn": 15,
        "is_active": True,
    }
    assert result["defense"] == {
        "type": "甲壳",
        "parameters": {"hardness": 0.6},
        "evolution_stage": 1,
        "evolution_progress": 0.25,
        "acquired_turn": 15,
        "is_active": False,
        "evolution_history": [
            {
                "turn": 15,
                "from_stage": 0,
                "to_stage": 1,
                "description": "开始发展甲壳原基",
            }
        ],
    }


def test_organ_update_returns_inherited_organs_for_non_list_legacy_payload() -> None:
    parent = SimpleNamespace(
        organs={"sensory": {"type": "眼点"}},
        gene_diversity_radius=0.35,
    )

    result = inherit_and_update_organs(
        parent,
        {"structural_innovations": {"category": "sensory"}},
        16,
        lambda current: False,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
        _unexpected_organ_callback,
    )

    assert result == {
        "sensory": {
            "type": "眼点",
            "evolution_stage": 4,
            "evolution_progress": 1.0,
        }
    }


def test_service_organ_update_delegate_preserves_method_overrides(
    monkeypatch,
) -> None:
    calls = []
    parent = SimpleNamespace(organs={}, gene_diversity_radius=0.4)
    evolution = [{"action": "enhance"}]

    class _OverriddenService(SpeciationService):
        def _infer_biological_domain(self, current_parent):
            calls.append(("domain", current_parent))
            return "complexity_2"

        def _validate_gradual_evolution(
            self, evolutions, parent_organs, biological_domain
        ):
            calls.append(
                ("validate", evolutions, parent_organs, biological_domain)
            )
            return True, evolutions

        def _normalize_organ_evolution(
            self, evolutions, current_parent, turn_index, radius
        ):
            calls.append(
                ("normalize", evolutions, current_parent, turn_index, radius)
            )
            return []

    monkeypatch.setattr(
        "app.services.species.speciation.PlantTraitConfig.is_plant",
        lambda current: calls.append(("is_plant", current)) or False,
    )
    service = object.__new__(_OverriddenService)

    assert service._inherit_and_update_organs(
        parent, {"organ_evolution": evolution}, 17
    ) == {}
    assert [call[0] for call in calls] == [
        "is_plant",
        "domain",
        "validate",
        "normalize",
    ]
