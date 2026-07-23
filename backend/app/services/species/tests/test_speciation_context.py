from types import SimpleNamespace

from ..speciation import SpeciationService
from ..speciation_context import (
    summarize_food_chain_status,
    summarize_major_events,
    summarize_map_changes,
    summarize_organs,
)


def test_food_chain_summary_preserves_existing_messages() -> None:
    assert summarize_food_chain_status(None) == "食物链状态未知"
    assert summarize_food_chain_status({}) == "食物链状态未知"
    assert summarize_food_chain_status({"t2_scarcity": 0.0}) == (
        "食物链稳定，各营养级食物充足"
    )
    assert summarize_food_chain_status({"t2_scarcity": 0.75}) == (
        "生产者(T1)紧张，初级消费者(T2)面临食物压力"
    )

    cascade = summarize_food_chain_status(
        {"t2_scarcity": 1.6, "t3_scarcity": 1.1}
    )

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
    assert summarize_map_changes([{"change_type": []}]) == "地形变化"
    assert summarize_map_changes([]) == ""


def test_major_event_summary_preserves_first_event_rule() -> None:
    events = [
        {"description": "火山喷发", "severity": "严重"},
        SimpleNamespace(description="不应使用", severity="高"),
    ]

    assert summarize_major_events(events) == "严重级火山喷发"
    assert summarize_major_events(
        [SimpleNamespace(description="冰期", severity="高")]
    ) == "高级冰期"
    assert summarize_major_events(
        [{"description": "", "severity": "低"}]
    ) == "重大环境事件"
    assert summarize_major_events([]) == ""


def test_speciation_service_keeps_compatibility_methods() -> None:
    service = object.__new__(SpeciationService)
    interactions = {"t4_scarcity": 0.75}
    changes = [{"change_type": "subsidence"}]
    events = [{"description": "海退", "severity": "中"}]

    assert service._summarize_food_chain_status(
        interactions
    ) == summarize_food_chain_status(interactions)
    assert service._summarize_map_changes(changes) == summarize_map_changes(
        changes
    )
    assert service._summarize_major_events(events) == summarize_major_events(
        events
    )


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
