from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable


logger = logging.getLogger(f"{__package__}.speciation")


def build_batch_payload(
    entries: list[dict],
    average_pressure: float,
    pressure_summary: str,
    map_changes: list,
    major_events: list,
    turn_index: int,
    *,
    is_plant: Callable[[Any], bool],
    get_stage_name: Callable[[int], str],
    get_milestone_hints: Callable[[Any], str],
    format_competition_context: Callable[[Any, list[Any]], str],
    get_evolution_hint: Callable[[str | None], dict | None],
    naming_hint_generator: Any,
    summarize_map_changes: Callable[[list], str],
    summarize_major_events: Callable[[list], str],
    get_tradeoff_ratio: Callable[[], float],
) -> dict:
    """构建批量分化请求的 payload。"""
    # 构建物种列表文本
    species_list_parts = []
    for idx, entry in enumerate(entries):
        payload = entry["payload"]
        ctx = entry["ctx"]

        # 获取生物类群和器官摘要（可能在单独调用时已添加）
        biological_domain = payload.get("biological_domain", "protist")
        organs_summary = payload.get(
            "current_organs_summary", "无已记录的器官系统"
        )

        # 【关键】获取规则引擎约束信息
        organ_constraints = payload.get(
            "organ_constraints_summary", "无器官约束"
        )
        trait_budget = payload.get(
            "trait_budget_summary", "增加上限: +3.0, 减少下限: -1.5"
        )
        trophic_range = payload.get("trophic_range", "1.5-2.5")
        parent_trophic = payload.get("parent_trophic_level", 2.0)

        # 【新增】获取地块级信息
        tile_context = payload.get("tile_context", "未知区域")
        region_mortality = payload.get("region_mortality", 0.5)
        region_pressure_level = payload.get("region_pressure_level", "中压")
        mortality_gradient = payload.get("mortality_gradient", 0.0)
        num_isolation_regions = payload.get("num_isolation_regions", 1)
        is_geographic_isolation = payload.get("is_geographic_isolation", False)

        # 【植物演化】为植物物种添加专有上下文
        parent_species = ctx["parent"]
        parent_is_plant = is_plant(parent_species)
        plant_context = ""

        if parent_is_plant:
            # 获取植物演化阶段信息
            life_form_stage = getattr(parent_species, "life_form_stage", 0)
            growth_form = getattr(parent_species, "growth_form", "aquatic")
            stage_name = get_stage_name(life_form_stage)

            # 获取里程碑提示
            milestone_hints = get_milestone_hints(parent_species)

            # 获取植物特质摘要
            traits = parent_species.abstract_traits or {}
            plant_trait_summary = ", ".join(
                [
                    f"{k}={v:.1f}"
                    for k, v in traits.items()
                    if k
                    in [
                        "光合效率",
                        "根系发达度",
                        "保水能力",
                        "木质化程度",
                        "种子化程度",
                        "多细胞程度",
                    ]
                ]
            )

            # 【新增】获取竞争上下文
            # 从entries中收集所有父代物种作为species_list
            all_parent_species = [e["ctx"]["parent"] for e in entries]
            competition_context = format_competition_context(
                parent_species, all_parent_species
            )

            plant_context = f"""
- 【🌱植物演化信息】:
  - 当前阶段: {life_form_stage} ({stage_name})
  - 生长形式: {growth_form}
  - 植物特质: {plant_trait_summary or '无'}
  - 里程碑提示:
{milestone_hints}
- {competition_context}
- 【植物阶段约束⚠️】:
  - 阶段只能升级1级（{life_form_stage} → {life_form_stage + 1}）
  - 登陆条件(阶段2→3): 保水能力>=5.0, 耐旱性>=4.0
  - 成为树木条件: 木质化程度>=7.0, 阶段>=5"""

        # 【新增】获取 AI 演化提示（来自生态智能体）
        parent_code = payload.get("parent_lineage")
        evolution_hint = get_evolution_hint(parent_code)
        ai_evolution_context = ""
        if evolution_hint:
            ai_directions = evolution_hint.get("ai_directions", [])
            if ai_directions:
                ai_evolution_context = f"""
- 【🧠AI演化建议】（来自生态智能体评估）:
  - 建议方向: {', '.join(ai_directions[:5])}
  - 请参考这些方向设计子代的特质变化！"""
                logger.debug(
                    f"[分化] {parent_code} 使用AI演化提示: {ai_directions}"
                )

        species_info = f"""
【物种 {idx + 1}】{'🌱植物' if parent_is_plant else '🦎动物'}
- request_id: {idx}
- 父系编码: {payload.get('parent_lineage')}
- 学名: {payload.get('latin_name')}
- 俗名: {payload.get('common_name')}
- 新编码: {ctx['new_code']}
- 栖息地: {payload.get('habitat_type')}
- 生物类群: {biological_domain}
- 营养级: T{parent_trophic:.1f}（允许范围：{trophic_range}）
- 描述: {payload.get('traits', '')[:200]}
- 现有器官: {organs_summary}
- 幸存者: {payload.get('survivors', 0):,}
- 分化类型: {payload.get('speciation_type')}
- 子代编号: 第{payload.get('offspring_index', 1)}个（共{payload.get('total_offspring', 1)}个）
- 【属性预算】: {trait_budget}
- 【器官约束⚠️必须遵守current_stage】:
{organ_constraints}{plant_context}{ai_evolution_context}
- 【地块背景】: {tile_context[:150]}
- 区域死亡率: {region_mortality:.1%}（{region_pressure_level}）
- 死亡率梯度: {mortality_gradient:.1%}
- 隔离区域数: {num_isolation_regions}
- 地理隔离: {'是' if is_geographic_isolation else '否'}"""
        species_list_parts.append(species_info)

    species_list = "\n".join(species_list_parts)

    # 【修复】不再转义 species_list 中的花括号
    # prompt format(**payload) 不会递归解析 value 中的花括号
    species_list_escaped = species_list

    from ...simulation.constants import get_time_config

    time_config = get_time_config(max(turn_index, 0))
    time_context = (
        "\n=== ⏳ 时间尺度上下文 (Chronos Flow) ===\n"
        f"当前地质年代：{time_config['era_name']}\n"
        f"时间流逝速度：{time_config['years_per_turn']:,} 年/回合\n"
        f"演化指导原则：{time_config.get('evolution_guide', 'Standard')}\n"
    )

    # 【命名提示】为批量分化生成随机命名参考
    batch_naming_seed = (
        abs(hash(f"batch-{turn_index}-{len(entries)}")) % 1_000_000_007
    )
    naming_hint_generator.set_seed(batch_naming_seed)
    naming_hints = naming_hint_generator.generate_naming_prompt(
        samples_per_category=2
    )

    payload_data = {
        "average_pressure": average_pressure,
        "pressure_summary": pressure_summary,
        "map_changes_summary": (
            summarize_map_changes(map_changes)
            if map_changes
            else "无显著地形变化"
        ),
        "major_events_summary": (
            summarize_major_events(major_events) if major_events else "无重大事件"
        ),
        # 【修复】同时提供 major_events 字段
        "major_events": (
            summarize_major_events(major_events) if major_events else "无重大事件"
        ),
        "species_list": species_list_escaped,
        "batch_size": len(entries),
        "time_context": time_context,
        "naming_hints": naming_hints,
    }
    first_payload = entries[0]["payload"] if entries else {}
    payload_data.update(
        {
            # 张量系统预先计算的预算约束，LLM 只需输出增益
            "max_increase": 3.0,
            "single_max": 2.0,
            "era_caps": first_payload.get("trait_budget_summary", "依时代上限"),
            "tradeoff_ratio": get_tradeoff_ratio(),
            # 为精简版prompt提供摘要
            "parent_summary": species_list_escaped,
            "trigger_context": pressure_summary,
        }
    )
    logger.debug(f"[分化批量] Payload keys: {list(payload_data.keys())}")
    return payload_data


def generate_rule_based_fallback(
    parent: Any,
    new_code: str,
    survivors: int,
    speciation_type: str,
    average_pressure: float,
    environment_pressure: dict[str, float] | None = None,
    turn_index: int = 0,
    *,
    preprocess_rules: Callable[..., dict],
    generate_background_species_name: Callable[..., str],
) -> dict:
    """当 AI 持续失败时，使用规则引擎生成新物种内容。"""
    import random
    import hashlib

    # 使用 new_code 作为随机种子，确保相同物种生成一致的内容
    seed = int(hashlib.md5(new_code.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    # ========== 0. 使用规则引擎获取约束 ==========
    env_pressure = environment_pressure or {"temperature": 0, "humidity": 0}
    constraints = preprocess_rules(
        parent_species=parent,
        offspring_index=1,
        total_offspring=1,
        environment_pressure=env_pressure,
        pressure_context=speciation_type,
        turn_index=turn_index,
    )

    # ========== 1. 生成名称（优化：避免累加截断）==========
    parent_latin = parent.latin_name or "Species unknown"
    latin_parts = parent_latin.split()
    genus = latin_parts[0] if latin_parts else "Genus"

    # 根据分化类型和演化方向选择后缀
    evolution_direction = constraints.get("evolution_direction", "自然分化")

    suffix_map = {
        "环境适应型": ["robustus", "tolerans", "resistens", "durans", "fortis"],
        "活动强化型": ["velox", "agilis", "cursor", "celer", "mobilis"],
        "繁殖策略型": ["fecundus", "prolifer", "fertilis", "abundans", "vivax"],
        "防御特化型": ["armatus", "spinosus", "coriaceus", "tectus", "protectus"],
        "极端特化型": ["extremus", "ultimus", "maximus", "supremus", "insignis"],
    }
    suffixes = suffix_map.get(evolution_direction, ["novus", "adaptus", "evolutus", "mutatus", "diversus"])

    # 添加编码后缀避免重名
    code_suffix = new_code.replace(".", "").lower()[-3:]
    new_species_name = f"{genus} {rng.choice(suffixes)}_{code_suffix}"

    # 中文俗名：【优化】使用独立的名字系统，避免累加截断
    new_common_name = generate_background_species_name(
        parent=parent,
        evolution_direction=evolution_direction,
        habitat_type=parent.habitat_type,
        trophic_level=parent.trophic_level,
        rng=rng,
    )

    # ========== 2. 使用规则引擎生成特质变化 ==========
    trait_changes = {}

    # 从规则引擎获取建议的增强/减弱属性
    suggested_increases = constraints.get("suggested_increases", [])
    suggested_decreases = constraints.get("suggested_decreases", [])

    # 增强属性（使用规则引擎的预算）
    trait_budget = constraints.get("_trait_budget")
    if trait_budget:
        max_increase = trait_budget.total_increase_allowed
        max_decrease = trait_budget.total_decrease_required
        single_max = trait_budget.single_trait_max
    else:
        max_increase, max_decrease, single_max = 3.0, 1.5, 2.0

    # 分配增强点数
    total_increase = 0
    for trait in suggested_increases[:2]:  # 最多增强2个属性
        if trait and "随机" not in trait:
            change = rng.uniform(
                0.5, min(single_max, max_increase - total_increase)
            )
            trait_changes[trait] = f"+{change:.1f}"
            total_increase += change
            if total_increase >= max_increase:
                break

    # 分配减弱点数（权衡）
    total_decrease = 0
    for trait in suggested_decreases[:2]:  # 最多减弱2个属性
        if trait:
            change = rng.uniform(
                0.3, min(single_max * 0.5, max_decrease - total_decrease)
            )
            trait_changes[trait] = f"-{change:.1f}"
            total_decrease += change
            if total_decrease >= max_decrease:
                break

    # ========== 3. 生成器官演化（使用约束）==========
    organ_evolution = []
    organ_constraints = constraints.get("_organ_constraints", [])

    # 随机选择一个器官进行演化
    evolvable_organs = [
        oc
        for oc in organ_constraints
        if oc.max_target_stage > oc.current_stage
    ]

    if evolvable_organs and rng.random() > 0.3:  # 70% 概率进行器官演化
        chosen = rng.choice(evolvable_organs)
        new_stage = min(chosen.max_target_stage, chosen.current_stage + 1)

        organ_names = {
            "locomotion": "运动器官",
            "sensory": "感觉器官",
            "metabolic": "代谢系统",
            "digestive": "消化系统",
            "defense": "防御结构",
            "reproduction": "繁殖系统",
        }
        stage_names = {
            1: "原基形成",
            2: "初级结构",
            3: "功能完善",
            4: "高度特化",
        }

        organ_evolution.append(
            {
                "category": chosen.category,
                "current_stage": chosen.current_stage,
                "target_stage": new_stage,
                "description": (
                    f"{organ_names.get(chosen.category, chosen.category)}"
                    f"发展至{stage_names.get(new_stage, '新阶段')}"
                ),
            }
        )

    # ========== 4. 生成形态变化 ==========
    parent_morph = parent.morphology_stats or {}
    morphology_changes = {}

    # 体长变化（±20%）
    base_length = parent_morph.get("body_length_cm", 10.0)
    length_ratio = rng.uniform(0.85, 1.15)
    morphology_changes["body_length_cm"] = length_ratio

    # 体重变化（与体长相关，但有独立变异）
    base_weight = parent_morph.get("body_weight_g", 100.0)
    weight_ratio = length_ratio**2.5 * rng.uniform(0.9, 1.1)  # 体重与体长的立方近似
    morphology_changes["body_weight_g"] = weight_ratio

    # ========== 5. 生成描述（更详细）==========
    habitat_map = {
        "marine": "海洋",
        "freshwater": "淡水",
        "terrestrial": "陆地",
        "amphibious": "两栖",
        "aerial": "空中",
        "deep_sea": "深海",
        "coastal": "沿岸",
    }
    diet_map = {
        "herbivore": "植食性",
        "carnivore": "肉食性",
        "omnivore": "杂食性",
        "detritivore": "腐食性",
        "autotroph": "自养型",
    }

    habitat_str = habitat_map.get(
        parent.habitat_type, parent.habitat_type or "未知"
    )
    diet_str = diet_map.get(parent.diet_type, parent.diet_type or "杂食性")
    direction_desc = constraints.get("direction_description", "自然选择")

    # 构建详细描述
    description_parts = [
        f"{new_common_name}是从{parent.common_name}分化而来的{habitat_str}{diet_str}物种。",
        f"在{speciation_type}的选择压力下，该物种发展出{direction_desc}的演化策略。",
    ]

    # 添加关键特质描述
    if trait_changes:
        changes_desc = []
        for trait, change in trait_changes.items():
            if change.startswith("+"):
                changes_desc.append(f"{trait}增强")
            else:
                changes_desc.append(f"{trait}降低")
        description_parts.append(f"主要适应性变化包括{'、'.join(changes_desc)}。")

    # 添加器官演化描述
    if organ_evolution:
        organ_desc = organ_evolution[0].get("description", "器官结构优化")
        description_parts.append(f"形态上，{organ_desc}。")

    description = "".join(description_parts)

    # ========== 6. 生成关键创新 ==========
    key_innovations = [f"{speciation_type}适应"]
    if organ_evolution:
        key_innovations.append(
            organ_evolution[0].get("description", "器官演化")
        )
    if suggested_increases:
        key_innovations.append(f"{suggested_increases[0]}强化")

    # ========== 7. 返回完整内容 ==========
    logger.info(
        f"[规则Fallback] 为 {new_code} 生成规则物种: "
        f"{new_common_name} ({evolution_direction})"
    )

    return {
        "latin_name": new_species_name,
        "common_name": new_common_name,
        "description": description,
        "habitat_type": parent.habitat_type,
        "trophic_level": parent.trophic_level,
        "diet_type": parent.diet_type,
        "prey_species": (
            list(parent.prey_species) if parent.prey_species else []
        ),
        "prey_preferences": (
            dict(parent.prey_preferences) if parent.prey_preferences else {}
        ),
        "key_innovations": key_innovations,
        "trait_changes": trait_changes,
        "morphology_changes": morphology_changes,
        "event_description": (
            f"因{speciation_type}从{parent.common_name}分化，"
            f"采用{evolution_direction}策略"
        ),
        "speciation_type": speciation_type,
        "reason": (
            f"在{speciation_type}条件下，通过{direction_desc}实现自然选择"
        ),
        "organ_evolution": organ_evolution,
        "_is_rule_fallback": True,  # 标记为规则生成
        "_evolution_direction": evolution_direction,  # 记录演化方向供后续使用
    }


async def call_batch_ai(
    router: Any,
    payload: dict,
    stream_callback: Callable[[str], Awaitable[None] | None] | None,
    entries: list[dict] | None = None,
    *,
    attempt_endosymbiosis_async: Callable[..., Awaitable[dict | None]],
    is_plant: Callable[[Any], bool],
    get_organ_category_info_for_prompt: Callable[[int], str],
) -> dict:
    """调用批量分化 AI 接口（带心跳检测）。"""
    from ...ai.streaming_helper import (
        StreamOutcome,
        stream_invoke_with_heartbeat,
    )
    import asyncio
    import json

    # === 【新增】内共生并发检测 ===
    endosymbiosis_tasks = []
    endosymbiosis_indices = []  # 记录对应的 entries 索引

    if entries:
        pressure = payload.get("average_pressure", 0.0)
        pressure_context = payload.get("pressure_summary", "")

        for i, entry in enumerate(entries):
            parent = entry["ctx"]["parent"]
            turn_index = entry["ctx"].get("turn_index", 0)

            # 并发启动内共生尝试（不阻塞主流程）
            task = asyncio.create_task(
                attempt_endosymbiosis_async(
                    parent, pressure, pressure_context, turn_index
                )
            )
            endosymbiosis_tasks.append(task)
            endosymbiosis_indices.append(i)

    # 【植物混合模式】检测是否为纯植物批次
    prompt_name = "speciation_batch"  # 默认
    batch_type = "动物"
    if entries:
        is_all_plants = all(is_plant(e["ctx"]["parent"]) for e in entries)
        if is_all_plants:
            prompt_name = "plant_speciation_batch"
            batch_type = "植物"
            # 为植物批次添加器官类别信息
            if entries:
                first_parent = entries[0]["ctx"]["parent"]
                current_stage = getattr(first_parent, "life_form_stage", 0)
                payload["organ_categories_info"] = (
                    get_organ_category_info_for_prompt(current_stage)
                )
            logger.debug(
                f"[分化批量] 使用植物专用Prompt，批次大小: {len(entries)}"
            )

    # 【优化】使用流式调用 + 智能空闲超时（只要AI在输出就不会超时）
    # 【修复】正确传递 event_type 和 category，不再丢失事件类型
    def heartbeat_callback(event_type: str, message: str, category: str):
        if stream_callback:
            try:
                result = stream_callback(event_type, message, category)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                pass

    batch_size = len(entries) if entries else 0

    # 启动 Batch AI Task
    batch_ai_task = asyncio.create_task(
        stream_invoke_with_heartbeat(
            router=router,
            capability=prompt_name,
            payload=payload,
            task_name=f"分化[{batch_type}×{batch_size}]",
            heartbeat_interval=2.0,
            event_callback=heartbeat_callback if stream_callback else None,
        )
    )

    # 等待所有任务 (Batch + Endosymbiosis)
    # 注意：我们允许内共生失败（返回None），也允许Batch失败（异常）
    all_tasks = [batch_ai_task] + endosymbiosis_tasks
    results = await asyncio.gather(*all_tasks, return_exceptions=True)

    batch_result = results[0]
    endo_results = results[1:]

    # 处理 Batch 结果
    final_content = {}
    if isinstance(batch_result, StreamOutcome):
        if batch_result.completed:
            try:
                parsed_content = json.loads(batch_result.content)
            except (TypeError, ValueError):
                logger.warning(
                    "[分化批量] AI返回内容不是有效JSON，将使用规则fallback"
                )
                final_content = {
                    "_error": "invalid_response",
                    "_use_fallback": True,
                }
            else:
                if isinstance(parsed_content, dict):
                    final_content = parsed_content
                else:
                    logger.warning(
                        "[分化批量] AI返回内容不是JSON对象，将使用规则fallback"
                    )
                    final_content = {
                        "_error": "invalid_response",
                        "_use_fallback": True,
                    }
        elif batch_result.reason == "outbound_timeout":
            logger.warning("[分化批量] AI流式请求中断，将使用规则fallback")
            final_content = {"_timeout": True, "_use_fallback": True}
        else:
            logger.warning("[分化批量] AI流式请求失败，将使用规则fallback")
            final_content = {
                "_error": "stream_error",
                "_use_fallback": True,
            }
    elif isinstance(batch_result, Exception):
        # Batch 失败处理
        if isinstance(batch_result, asyncio.TimeoutError):
            logger.warning("[分化批量] AI请求超时，将使用规则fallback")
            final_content = {"_timeout": True, "_use_fallback": True}
        else:
            logger.error(
                "[分化批量] 请求异常 (%s)，将使用规则fallback",
                type(batch_result).__name__,
            )
            final_content = {
                "_error": "stream_error",
                "_use_fallback": True,
            }

    if not isinstance(final_content, dict):
        final_content = {}

    # === 注入内共生结果 ===
    # 将成功的内共生结果暂存到 _endo_overrides 字段
    # 后续 _parse_batch_results 会优先使用这些结果

    valid_endo_overrides = {}
    for idx, res in zip(endosymbiosis_indices, endo_results):
        if isinstance(res, dict) and res.get("is_endosymbiosis"):
            res["request_id"] = idx  # 确保 ID 匹配
            valid_endo_overrides[idx] = res

    if valid_endo_overrides:
        final_content["_endo_overrides"] = valid_endo_overrides
        logger.info(
            f"[内共生] 成功捕获 {len(valid_endo_overrides)} 个内共生事件，准备注入"
        )

    return final_content


def parse_batch_results(
    batch_response: Any,
    entries: list[dict],
    *,
    generate_rule_based_fallback: Callable[..., dict],
) -> list[dict | Exception]:
    """解析批量响应，返回与 entries 对应的结果列表。"""
    results = []

    # 【新增】提取内共生覆盖结果
    endo_overrides = {}
    if isinstance(batch_response, dict):
        endo_overrides = batch_response.pop("_endo_overrides", {})

    # 【修复】检测是否需要使用fallback（AI超时或错误）
    if isinstance(batch_response, dict) and batch_response.get("_use_fallback"):
        logger.info(
            f"[分化批量] 检测到fallback标记，为 {len(entries)} 个物种生成规则fallback"
        )
        for idx, entry in enumerate(entries):
            # 【新增】即使是 fallback，如果内共生成功了，也优先使用内共生
            if idx in endo_overrides:
                results.append(endo_overrides[idx])
                continue

            ctx = entry["ctx"]
            fallback_result = generate_rule_based_fallback(
                parent=ctx["parent"],
                new_code=ctx["new_code"],
                survivors=ctx["population"],
                speciation_type=ctx["speciation_type"],
                average_pressure=ctx.get("average_pressure", 3.0),
            )
            # 标记为fallback结果
            fallback_result["_is_fallback"] = True
            results.append(fallback_result)
        return results

    if not isinstance(batch_response, dict):
        logger.warning(f"[分化批量] 响应不是字典类型: {type(batch_response)}")
        # 【修复】改为生成fallback而不是返回异常
        for idx, entry in enumerate(entries):
            if idx in endo_overrides:
                results.append(endo_overrides[idx])
                continue

            ctx = entry["ctx"]
            fallback_result = generate_rule_based_fallback(
                parent=ctx["parent"],
                new_code=ctx["new_code"],
                survivors=ctx["population"],
                speciation_type=ctx["speciation_type"],
                average_pressure=ctx.get("average_pressure", 3.0),
            )
            fallback_result["_is_fallback"] = True
            results.append(fallback_result)
        return results

    # 尝试从响应中提取 results 数组
    ai_results = batch_response.get("results", [])
    if not isinstance(ai_results, list):
        # 可能响应本身就是结果数组
        if isinstance(batch_response, list):
            ai_results = batch_response
        else:
            logger.warning(f"[分化批量] 响应中没有 results 数组，使用规则fallback")
            # 【修复】使用fallback而不是返回异常
            for entry in entries:
                ctx = entry["ctx"]
                fallback_result = generate_rule_based_fallback(
                    parent=ctx["parent"],
                    new_code=ctx["new_code"],
                    survivors=ctx["population"],
                    speciation_type=ctx["speciation_type"],
                    average_pressure=ctx.get("average_pressure", 3.0),
                )
                fallback_result["_is_fallback"] = True
                results.append(fallback_result)
            return results

    # 建立 request_id 到结果的映射
    result_map = {}
    for item in ai_results:
        if isinstance(item, dict):
            req_id = item.get("request_id")
            if req_id is not None:
                try:
                    result_map[int(req_id)] = item
                except (ValueError, TypeError):
                    result_map[str(req_id)] = item

    # 按顺序匹配结果
    for idx, entry in enumerate(entries):
        # 【新增】检查是否有内共生覆盖（优先使用）
        if idx in endo_overrides:
            results.append(endo_overrides[idx])
            continue

        # 尝试多种方式匹配
        matched_result = result_map.get(idx) or result_map.get(str(idx))

        if matched_result is None and idx < len(ai_results):
            # 如果没有 request_id，按顺序匹配
            matched_result = (
                ai_results[idx] if isinstance(ai_results[idx], dict) else None
            )

        if matched_result:
            # 验证必要字段
            required_fields = ["latin_name", "common_name", "description"]
            if all(matched_result.get(f) for f in required_fields):
                results.append(matched_result)
                logger.debug(
                    f"[分化批量] 成功匹配结果 {idx}: "
                    f"{matched_result.get('common_name')}"
                )
            else:
                logger.warning(
                    f"[分化批量] 结果 {idx} 缺少必要字段，使用规则fallback"
                )
                # 【修复】使用fallback而不是返回异常
                ctx = entry["ctx"]
                fallback_result = generate_rule_based_fallback(
                    parent=ctx["parent"],
                    new_code=ctx["new_code"],
                    survivors=ctx["population"],
                    speciation_type=ctx["speciation_type"],
                    average_pressure=ctx.get("average_pressure", 3.0),
                )
                fallback_result["_is_fallback"] = True
                results.append(fallback_result)
        else:
            logger.warning(
                f"[分化批量] 无法匹配结果 {idx}，使用规则fallback"
            )
            # 【修复】使用fallback而不是返回异常
            ctx = entry["ctx"]
            fallback_result = generate_rule_based_fallback(
                parent=ctx["parent"],
                new_code=ctx["new_code"],
                survivors=ctx["population"],
                speciation_type=ctx["speciation_type"],
                average_pressure=ctx.get("average_pressure", 3.0),
            )
            fallback_result["_is_fallback"] = True
            results.append(fallback_result)

    return results


async def call_ai_wrapper(
    router: Any,
    payload: dict,
    stream_callback: (
        Callable[[str], Awaitable[None] | None]
        | Callable[[str, str, str], None]
        | None
    ),
) -> dict:
    """AI调用包装器（带心跳检测）"""
    from ...ai.streaming_helper import invoke_with_heartbeat
    import asyncio

    def heartbeat_callback(event_type: str, message: str, category: str):
        if stream_callback:
            try:
                # 尝试以3参数方式调用 (event_type, message, category)
                # 这是为了兼容 SpeciationStage 传入的完整事件回调
                try:
                    result = stream_callback(event_type, message, category)
                except TypeError:
                    # 如果失败，回退到1参数方式 (message only)
                    # 用于兼容旧的仅接收消息的回调
                    result = stream_callback(message)

                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                # 避免回调错误中断主流程，但记录日志
                logger.warning(f"[Speciation] 心跳回调失败: {e}")

    try:
        response = await invoke_with_heartbeat(
            router=router,
            capability="speciation",
            payload=payload,
            task_name="单物种分化",
            heartbeat_interval=2.0,
            event_callback=heartbeat_callback if stream_callback else None,
        )
    except asyncio.TimeoutError:
        logger.error("[分化] 单个请求超时")
        return {}
    except Exception as e:
        logger.error(f"[分化] 请求异常: {e}")
        return {}
    return response.get("content") if isinstance(response, dict) else {}


def normalize_ai_content(ai_content: Any) -> Any:
    """将新格式的AI输出规范化为内部通用字段。

    - 如果提供了 innovations/gains，则汇总为 trait_changes
    - 缺少 key_innovations 时从 innovations 中提取
    """
    if not isinstance(ai_content, dict):
        return ai_content

    if not ai_content.get("trait_changes"):
        aggregated: dict[str, float] = {}
        key_innovations = list(ai_content.get("key_innovations") or [])
        innovations = ai_content.get("innovations") or []

        if isinstance(innovations, list):
            for inv in innovations:
                if not isinstance(inv, dict):
                    continue
                name = inv.get("name")
                if name and name not in key_innovations:
                    key_innovations.append(name)

                gains = inv.get("gains") or {}
                if isinstance(gains, dict):
                    for trait, delta in gains.items():
                        try:
                            val = float(str(delta).replace("+", ""))
                        except (ValueError, TypeError):
                            continue
                        aggregated[trait] = aggregated.get(trait, 0.0) + val

        if aggregated:
            ai_content["trait_changes"] = aggregated
        if key_innovations and not ai_content.get("key_innovations"):
            ai_content["key_innovations"] = key_innovations

    return ai_content
