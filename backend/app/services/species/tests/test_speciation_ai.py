import asyncio
import json
from types import SimpleNamespace

import pytest

from app.ai.streaming_helper import StreamOutcome

from .. import speciation as speciation_module
from ..speciation import SpeciationService
from ..speciation_ai import (
    build_batch_payload,
    call_batch_ai,
    call_ai_wrapper,
    generate_rule_based_fallback,
    normalize_ai_content,
    parse_batch_results,
)


class _NamingHints:
    def __init__(self) -> None:
        self.seeds: list[int] = []
        self.sample_counts: list[int] = []

    def set_seed(self, seed: int) -> None:
        self.seeds.append(seed)

    def generate_naming_prompt(self, samples_per_category: int) -> str:
        self.sample_counts.append(samples_per_category)
        return "NAMING HINTS"


def _build_payload(
    monkeypatch,
    *,
    entries: list[dict],
    turn_index: int = 7,
    map_changes=None,
    major_events=None,
    is_plant=lambda _parent: False,
    get_stage_name=lambda stage: f"stage-{stage}",
    get_milestone_hints=lambda _parent: "MILESTONES",
    format_competition_context=lambda _parent, _parents: "COMPETITION",
    get_evolution_hint=lambda _code: None,
    naming_hint_generator=None,
    summarize_map_changes=lambda changes: f"MAP:{changes}",
    summarize_major_events=lambda events: f"EVENTS:{events}",
    get_tradeoff_ratio=lambda: 0.7,
) -> tuple[dict, _NamingHints]:
    monkeypatch.setattr(
        "app.simulation.constants.get_time_config",
        lambda turn: {
            "era_name": f"era-{turn}",
            "years_per_turn": 12_345,
            "evolution_guide": "guide",
        },
    )
    naming_hints = naming_hint_generator or _NamingHints()
    result = build_batch_payload(
        entries=entries,
        average_pressure=0.75,
        pressure_summary="PRESSURE",
        map_changes=["raised"] if map_changes is None else map_changes,
        major_events=["impact"] if major_events is None else major_events,
        turn_index=turn_index,
        is_plant=is_plant,
        get_stage_name=get_stage_name,
        get_milestone_hints=get_milestone_hints,
        format_competition_context=format_competition_context,
        get_evolution_hint=get_evolution_hint,
        naming_hint_generator=naming_hints,
        summarize_map_changes=summarize_map_changes,
        summarize_major_events=summarize_major_events,
        get_tradeoff_ratio=get_tradeoff_ratio,
    )
    return result, naming_hints


def test_batch_payload_preserves_animal_defaults_time_naming_and_order(
    monkeypatch,
) -> None:
    parent = SimpleNamespace(abstract_traits={})
    summary_calls: list[tuple[str, list]] = []

    payload, naming_hints = _build_payload(
        monkeypatch,
        entries=[
            {
                "payload": {
                    "parent_lineage": "PARENT",
                    "latin_name": "Animalia testus",
                    "common_name": "Test animal",
                    "habitat_type": "shore",
                    "traits": "curly {braces}",
                },
                "ctx": {"parent": parent, "new_code": "CHILD"},
            }
        ],
        turn_index=-3,
        summarize_map_changes=lambda changes: summary_calls.append(
            ("map", changes)
        )
        or "MAP SUMMARY",
        summarize_major_events=lambda events: summary_calls.append(
            ("events", events)
        )
        or "EVENT SUMMARY",
        get_tradeoff_ratio=lambda: 0.65,
    )

    assert list(payload) == [
        "average_pressure",
        "pressure_summary",
        "map_changes_summary",
        "major_events_summary",
        "major_events",
        "species_list",
        "batch_size",
        "time_context",
        "naming_hints",
        "max_increase",
        "single_max",
        "era_caps",
        "tradeoff_ratio",
        "parent_summary",
        "trigger_context",
    ]
    assert summary_calls == [
        ("map", ["raised"]),
        ("events", ["impact"]),
        ("events", ["impact"]),
    ]
    assert payload["time_context"] == (
        "\n=== ⏳ 时间尺度上下文 (Chronos Flow) ===\n"
        "当前地质年代：era-0\n"
        "时间流逝速度：12,345 年/回合\n"
        "演化指导原则：guide\n"
    )
    assert naming_hints.seeds == [
        abs(hash("batch--3-1")) % 1_000_000_007
    ]
    assert naming_hints.sample_counts == [2]
    assert payload["naming_hints"] == "NAMING HINTS"
    assert payload["batch_size"] == 1
    assert payload["tradeoff_ratio"] == 0.65
    assert payload["era_caps"] == "依时代上限"
    assert payload["parent_summary"] == payload["species_list"]
    assert payload["trigger_context"] == "PRESSURE"
    assert "【物种 1】🦎动物" in payload["species_list"]
    assert "- 生物类群: protist" in payload["species_list"]
    assert "- 营养级: T2.0（允许范围：1.5-2.5）" in payload["species_list"]
    assert "- 描述: curly {braces}" in payload["species_list"]
    assert "- 现有器官: 无已记录的器官系统" in payload["species_list"]
    assert "- 地理隔离: 否" in payload["species_list"]


def test_batch_payload_preserves_plant_context_parent_list_and_ai_slice(
    monkeypatch,
) -> None:
    plant = SimpleNamespace(
        life_form_stage=2,
        growth_form="moss",
        abstract_traits={
            "光合效率": 4.25,
            "保水能力": 5.0,
            "ignored": 99.0,
        },
    )
    other_parent = SimpleNamespace(abstract_traits={})
    competition_calls: list[tuple[object, list[object]]] = []
    hint_codes: list[str | None] = []

    def evolution_hint(code: str | None) -> dict | None:
        hint_codes.append(code)
        if code == "PLANT":
            return {"ai_directions": ["a", "b", "c", "d", "e", "ignored"]}
        return None

    payload, _ = _build_payload(
        monkeypatch,
        entries=[
            {
                "payload": {
                    "parent_lineage": "PLANT",
                    "trait_budget_summary": "PLANT BUDGET",
                },
                "ctx": {"parent": plant, "new_code": "PLANT-CHILD"},
            },
            {
                "payload": {"parent_lineage": "ANIMAL"},
                "ctx": {"parent": other_parent, "new_code": "ANIMAL-CHILD"},
            },
        ],
        is_plant=lambda parent: parent is plant,
        get_stage_name=lambda stage: f"named-{stage}",
        get_milestone_hints=lambda parent: (
            "PLANT MILESTONES" if parent is plant else "wrong"
        ),
        format_competition_context=lambda parent, parents: competition_calls.append(
            (parent, parents)
        )
        or "PLANT COMPETITION",
        get_evolution_hint=evolution_hint,
    )

    assert competition_calls == [(plant, [plant, other_parent])]
    assert hint_codes == ["PLANT", "ANIMAL"]
    assert "【🌱植物演化信息】" in payload["species_list"]
    assert "当前阶段: 2 (named-2)" in payload["species_list"]
    assert "生长形式: moss" in payload["species_list"]
    assert "光合效率=4.2, 保水能力=5.0" in payload["species_list"]
    assert "ignored" not in payload["species_list"]
    assert "PLANT MILESTONES" in payload["species_list"]
    assert "PLANT COMPETITION" in payload["species_list"]
    assert "建议方向: a, b, c, d, e" in payload["species_list"]
    assert "ignored" not in payload["species_list"]
    assert payload["era_caps"] == "PLANT BUDGET"


def test_batch_payload_preserves_empty_batch_defaults(monkeypatch) -> None:
    ratio_calls: list[None] = []

    payload, naming_hints = _build_payload(
        monkeypatch,
        entries=[],
        map_changes=[],
        major_events=[],
        get_tradeoff_ratio=lambda: ratio_calls.append(None) or 0.8,
    )

    assert payload["map_changes_summary"] == "无显著地形变化"
    assert payload["major_events_summary"] == "无重大事件"
    assert payload["major_events"] == "无重大事件"
    assert payload["species_list"] == ""
    assert payload["batch_size"] == 0
    assert payload["era_caps"] == "依时代上限"
    assert payload["tradeoff_ratio"] == 0.8
    assert ratio_calls == [None]
    assert naming_hints.seeds == [
        abs(hash("batch-7-0")) % 1_000_000_007
    ]


def test_service_batch_payload_delegate_preserves_bound_overrides(
    monkeypatch,
) -> None:
    captured: dict = {}
    sentinel = {"delegated": True}

    def fake_build_batch_payload(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        speciation_module, "build_batch_payload", fake_build_batch_payload
    )
    service = object.__new__(SpeciationService)
    service.naming_hint_generator = _NamingHints()
    service.tradeoff_calculator = SimpleNamespace(tradeoff_ratio=0.91)
    service.tradeoff_ratio = 0.12
    service.get_evolution_hint = lambda code: {"code": code}
    service._summarize_map_changes = lambda changes: f"custom-map:{changes}"
    service._summarize_major_events = lambda events: f"custom-events:{events}"

    result = service._build_batch_payload(
        entries=[],
        average_pressure=0.5,
        pressure_summary="summary",
        map_changes=[],
        major_events=[],
        turn_index=4,
    )

    assert result is sentinel
    assert captured["entries"] == []
    assert captured["average_pressure"] == 0.5
    assert captured["pressure_summary"] == "summary"
    assert captured["map_changes"] == []
    assert captured["major_events"] == []
    assert captured["turn_index"] == 4
    assert captured["get_evolution_hint"]("X") == {"code": "X"}
    assert captured["summarize_map_changes"](["x"]) == "custom-map:['x']"
    assert captured["summarize_major_events"](["x"]) == "custom-events:['x']"
    assert captured["naming_hint_generator"] is service.naming_hint_generator
    assert captured["get_tradeoff_ratio"]() == 0.91


def _fallback_parent(**overrides):
    values = {
        "latin_name": "Testus parentus",
        "common_name": "亲本",
        "habitat_type": "marine",
        "trophic_level": 2.5,
        "diet_type": "carnivore",
        "prey_species": ("PREY-A", "PREY-B"),
        "prey_preferences": {"PREY-A": 0.7},
        "morphology_stats": {
            "body_length_cm": 20.0,
            "body_weight_g": 300.0,
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_rule_fallback_preserves_deterministic_default_budget_and_copies() -> None:
    parent = _fallback_parent()
    callback_calls: list[tuple] = []

    def preprocess_rules(**kwargs):
        callback_calls.append(("preprocess", kwargs))
        return {
            "evolution_direction": "活动强化型",
            "direction_description": "快速迁移",
            "suggested_increases": ["速度", "随机选择", "未使用"],
            "suggested_decreases": ["防御"],
        }

    def generate_name(**kwargs):
        callback_calls.append(("name", kwargs))
        return "疾岸兽"

    result = generate_rule_based_fallback(
        parent=parent,
        new_code="NEW.123",
        survivors=4321,
        speciation_type="地理隔离",
        average_pressure=0.82,
        environment_pressure={"temperature": 0.4},
        turn_index=17,
        preprocess_rules=preprocess_rules,
        generate_background_species_name=generate_name,
    )

    assert callback_calls[0] == (
        "preprocess",
        {
            "parent_species": parent,
            "offspring_index": 1,
            "total_offspring": 1,
            "environment_pressure": {"temperature": 0.4},
            "pressure_context": "地理隔离",
            "turn_index": 17,
        },
    )
    assert callback_calls[1][0] == "name"
    assert callback_calls[1][1]["parent"] is parent
    assert callback_calls[1][1]["evolution_direction"] == "活动强化型"
    assert callback_calls[1][1]["habitat_type"] == "marine"
    assert callback_calls[1][1]["trophic_level"] == 2.5
    assert result == {
        "latin_name": "Testus cursor_123",
        "common_name": "疾岸兽",
        "description": (
            "疾岸兽是从亲本分化而来的海洋肉食性物种。"
            "在地理隔离的选择压力下，该物种发展出快速迁移的演化策略。"
            "主要适应性变化包括速度增强、防御降低。"
        ),
        "habitat_type": "marine",
        "trophic_level": 2.5,
        "diet_type": "carnivore",
        "prey_species": ["PREY-A", "PREY-B"],
        "prey_preferences": {"PREY-A": 0.7},
        "key_innovations": ["地理隔离适应", "速度强化"],
        "trait_changes": {"速度": "+1.5", "防御": "-0.9"},
        "morphology_changes": {
            "body_length_cm": 0.9863118604476898,
            "body_weight_g": 0.9551457055184757,
        },
        "event_description": "因地理隔离从亲本分化，采用活动强化型策略",
        "speciation_type": "地理隔离",
        "reason": "在地理隔离条件下，通过快速迁移实现自然选择",
        "organ_evolution": [],
        "_is_rule_fallback": True,
        "_evolution_direction": "活动强化型",
    }
    assert result["prey_species"] is not parent.prey_species
    assert result["prey_preferences"] is not parent.prey_preferences


def test_rule_fallback_preserves_budget_organ_and_random_draw_order() -> None:
    parent = _fallback_parent()
    budget = SimpleNamespace(
        total_increase_allowed=2.0,
        total_decrease_required=1.0,
        single_trait_max=1.0,
    )
    organs = [
        SimpleNamespace(category="locomotion", current_stage=1, max_target_stage=2),
        SimpleNamespace(category="sensory", current_stage=2, max_target_stage=4),
    ]

    result = generate_rule_based_fallback(
        parent=parent,
        new_code="ORG.457",
        survivors=100,
        speciation_type="竞争分化",
        average_pressure=0.5,
        preprocess_rules=lambda **_kwargs: {
            "evolution_direction": "防御特化型",
            "direction_description": "结构防御",
            "suggested_increases": ["护甲", "耐力"],
            "suggested_decreases": ["速度", "繁殖"],
            "_trait_budget": budget,
            "_organ_constraints": organs,
        },
        generate_background_species_name=lambda **_kwargs: "甲感兽",
    )

    assert result["latin_name"] == "Testus coriaceus_457"
    assert result["trait_changes"] == {
        "护甲": "+0.9",
        "耐力": "+0.9",
        "速度": "-0.4",
        "繁殖": "-0.5",
    }
    assert result["organ_evolution"] == [
        {
            "category": "sensory",
            "current_stage": 2,
            "target_stage": 3,
            "description": "感觉器官发展至功能完善",
        }
    ]
    assert result["morphology_changes"] == {
        "body_length_cm": 1.1220982527500307,
        "body_weight_g": 1.4065023615055423,
    }
    assert result["description"].endswith("形态上，感觉器官发展至功能完善。")
    assert result["key_innovations"] == [
        "竞争分化适应",
        "感觉器官发展至功能完善",
        "护甲强化",
    ]


def test_rule_fallback_preserves_empty_defaults_and_fresh_environment() -> None:
    parent = _fallback_parent(
        latin_name=None,
        common_name=None,
        habitat_type=None,
        trophic_level=1.0,
        diet_type=None,
        prey_species=None,
        prey_preferences=None,
        morphology_stats=None,
    )
    environments: list[dict[str, float]] = []

    result = generate_rule_based_fallback(
        parent=parent,
        new_code="EMPTY.789",
        survivors=0,
        speciation_type="自然分化",
        average_pressure=0.0,
        preprocess_rules=lambda **kwargs: environments.append(
            kwargs["environment_pressure"]
        )
        or {},
        generate_background_species_name=lambda **_kwargs: "无名兽",
    )

    assert environments == [{"temperature": 0, "humidity": 0}]
    assert result["latin_name"] == "Species evolutus_789"
    assert result["prey_species"] == []
    assert result["prey_preferences"] == {}
    assert result["trait_changes"] == {}
    assert result["organ_evolution"] == []
    assert result["morphology_changes"] == {
        "body_length_cm": 1.0362646606813137,
        "body_weight_g": 1.1609732302348752,
    }
    assert result["description"] == (
        "无名兽是从None分化而来的未知杂食性物种。"
        "在自然分化的选择压力下，该物种发展出自然选择的演化策略。"
    )
    assert result["key_innovations"] == ["自然分化适应"]


def test_service_rule_fallback_delegate_preserves_bound_overrides(
    monkeypatch,
) -> None:
    captured: dict = {}
    sentinel = {"delegated": True}

    def fake_generate_rule_based_fallback(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        speciation_module,
        "generate_rule_based_fallback",
        fake_generate_rule_based_fallback,
    )
    service = object.__new__(SpeciationService)
    service.rules = SimpleNamespace(preprocess=lambda **kwargs: ("rules", kwargs))
    service._generate_background_species_name = lambda **kwargs: ("name", kwargs)
    parent = _fallback_parent()

    result = service._generate_rule_based_fallback(
        parent=parent,
        new_code="NEW",
        survivors=123,
        speciation_type="test",
        average_pressure=0.4,
        environment_pressure={"humidity": 0.2},
        turn_index=9,
    )

    assert result is sentinel
    assert captured["parent"] is parent
    assert captured["new_code"] == "NEW"
    assert captured["survivors"] == 123
    assert captured["speciation_type"] == "test"
    assert captured["average_pressure"] == 0.4
    assert captured["environment_pressure"] == {"humidity": 0.2}
    assert captured["turn_index"] == 9
    assert captured["preprocess_rules"](value=1) == (
        "rules",
        {"value": 1},
    )
    assert captured["generate_background_species_name"](value=2) == (
        "name",
        {"value": 2},
    )


def _batch_result_entries(count: int) -> list[dict]:
    return [
        {
            "ctx": {
                "parent": SimpleNamespace(code=f"PARENT-{idx}"),
                "new_code": f"CHILD-{idx}",
                "population": 100 + idx,
                "speciation_type": f"type-{idx}",
                **({"average_pressure": 1.25} if idx == 0 else {}),
            }
        }
        for idx in range(count)
    ]


def _fallback_recorder(calls: list[dict]):
    def generate_fallback(**kwargs):
        calls.append(kwargs)
        return {"fallback_code": kwargs["new_code"]}

    return generate_fallback


def test_batch_result_parser_pops_endosymbiosis_and_prioritizes_it_in_fallback(
) -> None:
    entries = _batch_result_entries(3)
    endosymbiosis = {"common_name": "内共生结果"}
    response = {
        "_use_fallback": True,
        "_endo_overrides": {1: endosymbiosis},
    }
    calls: list[dict] = []

    results = parse_batch_results(
        response,
        entries,
        generate_rule_based_fallback=_fallback_recorder(calls),
    )

    assert response == {"_use_fallback": True}
    assert results == [
        {"fallback_code": "CHILD-0", "_is_fallback": True},
        endosymbiosis,
        {"fallback_code": "CHILD-2", "_is_fallback": True},
    ]
    assert [call["new_code"] for call in calls] == ["CHILD-0", "CHILD-2"]
    assert calls[0] == {
        "parent": entries[0]["ctx"]["parent"],
        "new_code": "CHILD-0",
        "survivors": 100,
        "speciation_type": "type-0",
        "average_pressure": 1.25,
    }
    assert calls[1]["average_pressure"] == 3.0


def test_batch_result_parser_falls_back_for_non_dict_response() -> None:
    entries = _batch_result_entries(2)
    calls: list[dict] = []

    results = parse_batch_results(
        ["not", "a", "dict"],
        entries,
        generate_rule_based_fallback=_fallback_recorder(calls),
    )

    assert results == [
        {"fallback_code": "CHILD-0", "_is_fallback": True},
        {"fallback_code": "CHILD-1", "_is_fallback": True},
    ]
    assert [call["new_code"] for call in calls] == ["CHILD-0", "CHILD-1"]


def test_batch_result_parser_preserves_invalid_results_branch_behavior() -> None:
    entries = _batch_result_entries(2)
    ignored_endosymbiosis = {"common_name": "当前分支不会使用"}
    response = {
        "_endo_overrides": {0: ignored_endosymbiosis},
        "results": "not-a-list",
    }
    calls: list[dict] = []

    results = parse_batch_results(
        response,
        entries,
        generate_rule_based_fallback=_fallback_recorder(calls),
    )

    assert "_endo_overrides" not in response
    assert results == [
        {"fallback_code": "CHILD-0", "_is_fallback": True},
        {"fallback_code": "CHILD-1", "_is_fallback": True},
    ]
    assert ignored_endosymbiosis not in results


def test_batch_result_parser_matches_request_ids_then_position() -> None:
    entries = _batch_result_entries(3)
    mapped_one = {
        "request_id": "1",
        "latin_name": "One",
        "common_name": "一",
        "description": "mapped one",
    }
    mapped_zero = {
        "request_id": 0,
        "latin_name": "Zero",
        "common_name": "零",
        "description": "mapped zero",
    }
    positional_two = {
        "request_id": "not-an-index",
        "latin_name": "Two",
        "common_name": "二",
        "description": "position two",
    }
    calls: list[dict] = []

    results = parse_batch_results(
        {"results": [mapped_one, mapped_zero, positional_two]},
        entries,
        generate_rule_based_fallback=_fallback_recorder(calls),
    )

    assert results == [mapped_zero, mapped_one, positional_two]
    assert calls == []


def test_batch_result_parser_falls_back_for_missing_fields_and_matches() -> None:
    entries = _batch_result_entries(3)
    response = {
        "results": [
            {
                "request_id": 0,
                "latin_name": "Missing",
                "common_name": "缺描述",
                "description": "",
            },
            "not-a-dict",
        ]
    }
    calls: list[dict] = []

    results = parse_batch_results(
        response,
        entries,
        generate_rule_based_fallback=_fallback_recorder(calls),
    )

    assert results == [
        {"fallback_code": "CHILD-0", "_is_fallback": True},
        {"fallback_code": "CHILD-1", "_is_fallback": True},
        {"fallback_code": "CHILD-2", "_is_fallback": True},
    ]
    assert [call["new_code"] for call in calls] == [
        "CHILD-0",
        "CHILD-1",
        "CHILD-2",
    ]


def test_service_batch_result_parser_delegate_preserves_fallback_override(
    monkeypatch,
) -> None:
    captured: dict = {}
    sentinel = [{"delegated": True}]

    def fake_parse_batch_results(batch_response, entries, **kwargs):
        captured["batch_response"] = batch_response
        captured["entries"] = entries
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        speciation_module,
        "parse_batch_results",
        fake_parse_batch_results,
    )
    service = object.__new__(SpeciationService)
    service._generate_rule_based_fallback = lambda **kwargs: ("fallback", kwargs)
    response = {"results": []}
    entries = _batch_result_entries(1)

    result = service._parse_batch_results(response, entries)

    assert result is sentinel
    assert captured["batch_response"] is response
    assert captured["entries"] is entries
    assert captured["generate_rule_based_fallback"](value=3) == (
        "fallback",
        {"value": 3},
    )


@pytest.mark.asyncio
async def test_single_ai_wrapper_forwards_exact_invocation_without_callback(
    monkeypatch,
) -> None:
    router = object()
    payload = {"parent": "P"}
    content = {"result": "ok"}
    captured: dict = {}

    async def fake_invoke_with_heartbeat(**kwargs):
        captured.update(kwargs)
        return {"content": content}

    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    result = await call_ai_wrapper(router, payload, None)

    assert result is content
    assert captured == {
        "router": router,
        "capability": "speciation",
        "payload": payload,
        "task_name": "单物种分化",
        "heartbeat_interval": 2.0,
        "event_callback": None,
    }


@pytest.mark.asyncio
async def test_single_ai_wrapper_prefers_three_argument_callback(
    monkeypatch,
) -> None:
    events: list[tuple[str, str, str]] = []

    async def fake_invoke_with_heartbeat(**kwargs):
        kwargs["event_callback"]("heartbeat", "working", "speciation")
        return {"content": {"done": True}}

    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    result = await call_ai_wrapper(
        object(),
        {},
        lambda event_type, message, category: events.append(
            (event_type, message, category)
        ),
    )

    assert result == {"done": True}
    assert events == [("heartbeat", "working", "speciation")]


@pytest.mark.asyncio
async def test_single_ai_wrapper_falls_back_to_one_argument_callback(
    monkeypatch,
) -> None:
    messages: list[str] = []

    async def fake_invoke_with_heartbeat(**kwargs):
        kwargs["event_callback"]("heartbeat", "legacy message", "speciation")
        return {"content": {}}

    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    await call_ai_wrapper(object(), {}, lambda message: messages.append(message))

    assert messages == ["legacy message"]


@pytest.mark.asyncio
async def test_single_ai_wrapper_schedules_coroutine_callback_once(
    monkeypatch,
) -> None:
    scheduled = []

    def fake_create_task(coroutine):
        scheduled.append(coroutine)
        coroutine.close()
        return object()

    async def async_callback(
        _event_type: str,
        _message: str,
        _category: str,
    ) -> None:
        return None

    async def fake_invoke_with_heartbeat(**kwargs):
        kwargs["event_callback"]("heartbeat", "working", "speciation")
        return {"content": {}}

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    await call_ai_wrapper(object(), {}, async_callback)

    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_single_ai_wrapper_isolates_callback_errors(
    monkeypatch,
    caplog,
) -> None:
    def broken_callback(*_args):
        raise RuntimeError("callback failed")

    async def fake_invoke_with_heartbeat(**kwargs):
        kwargs["event_callback"]("heartbeat", "working", "speciation")
        return {"content": {"continued": True}}

    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    result = await call_ai_wrapper(object(), {}, broken_callback)

    assert result == {"continued": True}
    assert "[Speciation] 心跳回调失败: callback failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.TimeoutError(), RuntimeError("boom")])
async def test_single_ai_wrapper_returns_empty_for_invocation_errors(
    monkeypatch,
    error: Exception,
) -> None:
    async def fake_invoke_with_heartbeat(**_kwargs):
        raise error

    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    assert await call_ai_wrapper(object(), {}, None) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (["not", "a", "dict"], {}),
        ({"content": None}, None),
    ],
)
async def test_single_ai_wrapper_preserves_response_content_rules(
    monkeypatch,
    response,
    expected,
) -> None:
    async def fake_invoke_with_heartbeat(**_kwargs):
        return response

    monkeypatch.setattr(
        "app.ai.streaming_helper.invoke_with_heartbeat",
        fake_invoke_with_heartbeat,
    )

    assert await call_ai_wrapper(object(), {}, None) == expected


@pytest.mark.asyncio
async def test_service_single_ai_wrapper_delegate_preserves_router(
    monkeypatch,
) -> None:
    captured: dict = {}
    sentinel = {"delegated": True}

    async def fake_call_ai_wrapper(router, payload, stream_callback):
        captured.update(
            {
                "router": router,
                "payload": payload,
                "stream_callback": stream_callback,
            }
        )
        return sentinel

    monkeypatch.setattr(
        speciation_module,
        "call_ai_wrapper",
        fake_call_ai_wrapper,
    )
    service = object.__new__(SpeciationService)
    service.router = object()
    payload = {"test": True}
    callback = lambda _message: None

    result = await service._call_ai_wrapper(payload, callback)

    assert result is sentinel
    assert captured == {
        "router": service.router,
        "payload": payload,
        "stream_callback": callback,
    }


@pytest.mark.asyncio
async def test_batch_ai_invocation_preserves_animal_tasks_and_endo_injection(
    monkeypatch,
) -> None:
    router = object()
    parents = [SimpleNamespace(name="first"), SimpleNamespace(name="second")]
    entries = [
        {
            "ctx": {
                "parent": parents[0],
                "turn_index": 8,
            }
        },
        {"ctx": {"parent": parents[1]}},
    ]
    payload = {
        "average_pressure": 4.5,
        "pressure_summary": "high pressure",
    }
    endosymbiosis = {"is_endosymbiosis": True, "common_name": "共生体"}
    endo_calls: list[tuple] = []
    invocation: dict = {}
    events: list[tuple[str, str, str]] = []

    async def attempt_endosymbiosis(parent, pressure, context, turn_index):
        endo_calls.append((parent, pressure, context, turn_index))
        if parent is parents[0]:
            return endosymbiosis
        raise RuntimeError("ignored endosymbiosis failure")

    async def fake_stream_invoke_with_heartbeat(**kwargs):
        invocation.update(kwargs)
        kwargs["event_callback"]("heartbeat", "streaming", "speciation")
        return StreamOutcome(
            content=json.dumps({"results": [{"request_id": 0}]}),
            completed=True,
        )

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    result = await call_batch_ai(
        router,
        payload,
        lambda event_type, message, category: events.append(
            (event_type, message, category)
        ),
        entries,
        attempt_endosymbiosis_async=attempt_endosymbiosis,
        is_plant=lambda _parent: False,
        get_organ_category_info_for_prompt=lambda _stage: pytest.fail(
            "animal batches must not request plant organ context"
        ),
    )

    assert invocation == {
        "router": router,
        "capability": "speciation_batch",
        "payload": payload,
        "task_name": "分化[动物×2]",
        "heartbeat_interval": 2.0,
        "event_callback": invocation["event_callback"],
    }
    assert callable(invocation["event_callback"])
    assert events == [("heartbeat", "streaming", "speciation")]
    assert endo_calls == [
        (parents[0], 4.5, "high pressure", 8),
        (parents[1], 4.5, "high pressure", 0),
    ]
    assert endosymbiosis["request_id"] == 0
    assert result == {
        "results": [{"request_id": 0}],
        "_endo_overrides": {0: endosymbiosis},
    }


@pytest.mark.asyncio
async def test_batch_ai_invocation_preserves_plant_prompt_and_payload_mutation(
    monkeypatch,
) -> None:
    parents = [
        SimpleNamespace(life_form_stage=3),
        SimpleNamespace(life_form_stage=5),
    ]
    entries = [{"ctx": {"parent": parent}} for parent in parents]
    payload: dict = {}
    stages: list[int] = []
    invocation: dict = {}

    async def fake_stream_invoke_with_heartbeat(**kwargs):
        invocation.update(kwargs)
        return StreamOutcome(content="{}", completed=True)

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    result = await call_batch_ai(
        object(),
        payload,
        None,
        entries,
        attempt_endosymbiosis_async=lambda *_args: _async_none(),
        is_plant=lambda parent: parent in parents,
        get_organ_category_info_for_prompt=lambda stage: stages.append(stage)
        or "PLANT ORGANS",
    )

    assert result == {}
    assert stages == [3]
    assert payload["organ_categories_info"] == "PLANT ORGANS"
    assert invocation["capability"] == "plant_speciation_batch"
    assert invocation["task_name"] == "分化[植物×2]"
    assert invocation["event_callback"] is None


async def _async_none():
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            StreamOutcome(content="not-json", completed=True),
            {"_error": "invalid_response", "_use_fallback": True},
        ),
        (
            StreamOutcome(content="[]", completed=True),
            {"_error": "invalid_response", "_use_fallback": True},
        ),
        (
            StreamOutcome(
                content='{"partial": true}',
                completed=False,
                reason="outbound_timeout",
            ),
            {"_timeout": True, "_use_fallback": True},
        ),
        (
            StreamOutcome(content="", completed=False, reason="stream_error"),
            {"_error": "stream_error", "_use_fallback": True},
        ),
    ],
)
async def test_batch_ai_invocation_preserves_stream_outcome_branches(
    monkeypatch,
    outcome: StreamOutcome,
    expected: dict,
) -> None:
    async def fake_stream_invoke_with_heartbeat(**_kwargs):
        return outcome

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    result = await call_batch_ai(
        object(),
        {},
        None,
        [],
        attempt_endosymbiosis_async=lambda *_args: _async_none(),
        is_plant=lambda _parent: False,
        get_organ_category_info_for_prompt=lambda _stage: "",
    )

    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            asyncio.TimeoutError(),
            {"_timeout": True, "_use_fallback": True},
        ),
        (
            RuntimeError("stream failed"),
            {"_error": "stream_error", "_use_fallback": True},
        ),
    ],
)
async def test_batch_ai_invocation_preserves_task_exception_branches(
    monkeypatch,
    error: Exception,
    expected: dict,
) -> None:
    async def fake_stream_invoke_with_heartbeat(**_kwargs):
        raise error

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    result = await call_batch_ai(
        object(),
        {},
        None,
        [],
        attempt_endosymbiosis_async=lambda *_args: _async_none(),
        is_plant=lambda _parent: False,
        get_organ_category_info_for_prompt=lambda _stage: "",
    )

    assert result == expected


@pytest.mark.asyncio
async def test_batch_ai_invocation_preserves_unexpected_batch_result(
    monkeypatch,
) -> None:
    async def fake_stream_invoke_with_heartbeat(**_kwargs):
        return {"content": "not a StreamOutcome"}

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    result = await call_batch_ai(
        object(),
        {},
        None,
        [],
        attempt_endosymbiosis_async=lambda *_args: _async_none(),
        is_plant=lambda _parent: False,
        get_organ_category_info_for_prompt=lambda _stage: "",
    )

    assert result == {}


@pytest.mark.asyncio
async def test_batch_ai_invocation_schedules_async_heartbeat_callback(
    monkeypatch,
) -> None:
    callback_completed = asyncio.Event()

    async def callback(
        _event_type: str,
        _message: str,
        _category: str,
    ) -> None:
        callback_completed.set()

    async def fake_stream_invoke_with_heartbeat(**kwargs):
        kwargs["event_callback"]("heartbeat", "streaming", "speciation")
        await asyncio.sleep(0)
        return StreamOutcome(content="{}", completed=True)

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    await call_batch_ai(
        object(),
        {},
        callback,
        [],
        attempt_endosymbiosis_async=lambda *_args: _async_none(),
        is_plant=lambda _parent: False,
        get_organ_category_info_for_prompt=lambda _stage: "",
    )

    assert callback_completed.is_set()


@pytest.mark.asyncio
async def test_batch_ai_invocation_isolates_heartbeat_callback_errors(
    monkeypatch,
) -> None:
    def broken_callback(
        _event_type: str,
        _message: str,
        _category: str,
    ) -> None:
        raise RuntimeError("ignored callback error")

    async def fake_stream_invoke_with_heartbeat(**kwargs):
        kwargs["event_callback"]("heartbeat", "streaming", "speciation")
        return StreamOutcome(content="{}", completed=True)

    monkeypatch.setattr(
        "app.ai.streaming_helper.stream_invoke_with_heartbeat",
        fake_stream_invoke_with_heartbeat,
    )

    assert (
        await call_batch_ai(
            object(),
            {},
            broken_callback,
            [],
            attempt_endosymbiosis_async=lambda *_args: _async_none(),
            is_plant=lambda _parent: False,
            get_organ_category_info_for_prompt=lambda _stage: "",
        )
        == {}
    )


@pytest.mark.asyncio
async def test_service_batch_ai_delegate_preserves_runtime_dependencies(
    monkeypatch,
) -> None:
    captured: dict = {}
    sentinel = {"delegated": True}

    async def fake_call_batch_ai(
        router,
        payload,
        stream_callback,
        entries,
        **kwargs,
    ):
        captured.update(
            {
                "router": router,
                "payload": payload,
                "stream_callback": stream_callback,
                "entries": entries,
                **kwargs,
            }
        )
        return sentinel

    monkeypatch.setattr(speciation_module, "call_batch_ai", fake_call_batch_ai)
    service = object.__new__(SpeciationService)
    service.router = object()
    service._attempt_endosymbiosis_async = lambda *_args: _async_none()
    payload = {"test": True}
    entries = _batch_result_entries(1)
    callback = lambda *_args: None

    result = await service._call_batch_ai(payload, callback, entries)

    assert result is sentinel
    assert captured["router"] is service.router
    assert captured["payload"] is payload
    assert captured["stream_callback"] is callback
    assert captured["entries"] is entries
    assert (
        captured["attempt_endosymbiosis_async"]
        is service._attempt_endosymbiosis_async
    )
    assert callable(captured["is_plant"])
    assert callable(captured["get_organ_category_info_for_prompt"])


def test_ai_normalization_preserves_non_dict_identity() -> None:
    content = ["not", "a", "dict"]

    assert normalize_ai_content(content) is content


def test_ai_normalization_skips_truthy_existing_trait_changes() -> None:
    content = {
        "trait_changes": {"speed": 1.0},
        "innovations": [{"name": "wing", "gains": {"armor": 2.0}}],
    }

    assert normalize_ai_content(content) is content
    assert content == {
        "trait_changes": {"speed": 1.0},
        "innovations": [{"name": "wing", "gains": {"armor": 2.0}}],
    }


def test_ai_normalization_aggregates_mixed_gains_and_deduplicates_names() -> None:
    content = {
        "trait_changes": {},
        "innovations": [
            {"name": "wing", "gains": {"speed": "+1.5", "armor": "bad"}},
            {"name": "wing", "gains": {"speed": 2, "social": None}},
            "invalid",
            {"name": "shell", "gains": ["not", "a", "dict"]},
        ],
    }

    assert normalize_ai_content(content) is content
    assert content["trait_changes"] == {"speed": 3.5}
    assert content["key_innovations"] == ["wing", "shell"]


def test_ai_normalization_preserves_existing_key_innovations() -> None:
    existing = ["existing"]
    content = {
        "key_innovations": existing,
        "innovations": [
            {"name": "wing", "gains": {"speed": 1.0}},
        ],
    }

    normalize_ai_content(content)

    assert content["trait_changes"] == {"speed": 1.0}
    assert content["key_innovations"] is existing
    assert content["key_innovations"] == ["existing"]


def test_ai_normalization_adds_names_even_without_valid_gains() -> None:
    content = {
        "innovations": [
            {"name": "shell", "gains": {"armor": object()}},
        ],
    }

    normalize_ai_content(content)

    assert "trait_changes" not in content
    assert content["key_innovations"] == ["shell"]


def test_service_ai_normalization_delegate_matches_direct_function() -> None:
    service = object.__new__(SpeciationService)
    service_content = {
        "innovations": [{"name": "wing", "gains": {"speed": "+1.0"}}]
    }
    direct_content = {
        "innovations": [{"name": "wing", "gains": {"speed": "+1.0"}}]
    }

    assert service._normalize_ai_content(service_content) == normalize_ai_content(
        direct_content
    )
