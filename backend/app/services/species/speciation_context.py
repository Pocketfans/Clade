from __future__ import annotations


def summarize_food_chain_status(
    trophic_interactions: dict[str, float] | None,
) -> str:
    """总结食物链状态，供 AI 做演化决策参考。"""
    if not trophic_interactions:
        return "食物链状态未知"

    status_parts = []

    # scarcity: 0 = 充足, 1 = 紧张, 2 = 严重短缺
    t2_scarcity = trophic_interactions.get("t2_scarcity", 0.0)
    t3_scarcity = trophic_interactions.get("t3_scarcity", 0.0)
    t4_scarcity = trophic_interactions.get("t4_scarcity", 0.0)
    t5_scarcity = trophic_interactions.get("t5_scarcity", 0.0)

    if t2_scarcity > 0.5:
        status_parts.append(
            f"生产者(T1){'紧张' if t2_scarcity < 1.0 else '短缺'}，"
            "初级消费者(T2)面临食物压力"
        )

    if t3_scarcity > 0.5:
        status_parts.append(
            f"初级消费者(T2){'紧张' if t3_scarcity < 1.0 else '短缺'}，"
            "次级消费者(T3)面临食物压力"
        )

    if t4_scarcity > 0.5:
        status_parts.append(
            f"次级消费者(T3){'紧张' if t4_scarcity < 1.0 else '短缺'}，"
            "三级消费者(T4)面临食物压力"
        )

    if t5_scarcity > 0.5:
        status_parts.append(
            f"三级消费者(T4){'紧张' if t5_scarcity < 1.0 else '短缺'}，"
            "顶级捕食者(T5)面临食物压力"
        )

    if t2_scarcity > 1.5 and t3_scarcity > 1.0:
        status_parts.append("⚠️ 食物链底层崩溃，可能引发级联灭绝")

    if not status_parts:
        return "食物链稳定，各营养级食物充足"

    return "；".join(status_parts)


def summarize_map_changes(map_changes: list) -> str:
    """总结地图变化用于分化原因描述。"""
    if not map_changes:
        return ""

    change_types = []
    for change in map_changes[:3]:
        if isinstance(change, dict):
            change_type = change.get("change_type", "")
        else:
            change_type = getattr(change, "change_type", "")

        if change_type == "uplift":
            change_types.append("地壳抬升")
        elif change_type == "volcanic":
            change_types.append("火山活动")
        elif change_type == "glaciation":
            change_types.append("冰川推进")
        elif change_type == "subsidence":
            change_types.append("地壳下沉")

    return "、".join(change_types) if change_types else "地形变化"


def summarize_major_events(major_events: list) -> str:
    """总结重大事件用于分化原因描述。"""
    if not major_events:
        return ""

    for event in major_events[:1]:
        if isinstance(event, dict):
            description = event.get("description", "")
            severity = event.get("severity", "")
        else:
            description = getattr(event, "description", "")
            severity = getattr(event, "severity", "")

        if description:
            return f"{severity}级{description}"

    return "重大环境事件"


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
