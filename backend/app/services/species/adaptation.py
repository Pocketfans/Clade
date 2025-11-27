"""物种适应服务：渐进演化和退化机制

实现P0和P1改进：
- P0: 退化机制（用进废退）
- P1: 渐进演化（非分化的逐代适应）
- P2: 描述同步（当数值漂移过大时重写描述）
- P3: LLM驱动的智能适应（高压力情况下使用AI决策）
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from typing import Sequence, Callable, Awaitable

from ...models.species import Species
from .trait_config import TraitConfig
from ...ai.model_router import ModelRouter
from ...ai.prompts.species import SPECIES_PROMPTS
from ...core.config import get_settings

logger = logging.getLogger(__name__)

# 获取配置
_settings = get_settings()

# 高压力阈值：超过此值时使用LLM进行智能适应
HIGH_PRESSURE_THRESHOLD = 5.0


class AdaptationService:
    """处理物种的渐进演化和器官退化"""
    
    def __init__(self, router: ModelRouter):
        self.router = router
        self.gradual_evolution_rate = 0.15
        self.regression_check_turns = 5
        self.drift_threshold = 3.0  # 累积漂移超过此值触发描述更新
        self.enable_llm_adaptation = True  # 是否启用LLM驱动的适应
        # 【修复】添加并发限制，防止一次性生成过多AI任务
        self.max_llm_adaptations_per_turn = 15
        self.max_description_updates_per_turn = 10
        
    async def apply_adaptations_async(
        self,
        species_list: Sequence[Species],
        environment_pressure: dict[str, float],
        turn_index: int,
        pressures: Sequence = None,  # 新增：ParsedPressure 列表
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> list[dict]:
        """应用适应性变化（渐进演化+退化+描述同步+LLM智能适应）(Async)
        
        Args:
            species_list: 所有存活物种
            environment_pressure: 当前环境压力
            turn_index: 当前回合数
            pressures: ParsedPressure 列表，用于提供上下文
            
        Returns:
            变化记录列表
        """
        adaptation_events = []
        description_update_tasks = []
        species_to_update = []
        llm_adaptation_tasks = []
        llm_species_list = []
        
        # 提取压力描述摘要
        pressure_context = "环境稳定"
        if pressures:
            narratives = sorted(list(set(p.narrative for p in pressures)))
            pressure_context = "; ".join(narratives)
        
        # 计算总压力强度
        total_pressure = sum(abs(v) for v in environment_pressure.values())
        use_llm_adaptation = (
            self.enable_llm_adaptation 
            and total_pressure >= HIGH_PRESSURE_THRESHOLD 
            and self.router is not None
        )
        
        if use_llm_adaptation:
            logger.info(f"[适应性] 检测到高压力环境 ({total_pressure:.1f})，启用LLM智能适应")
        
        for species in species_list:
            # 计算经历了多少代
            generation_time = species.morphology_stats.get("generation_time_days", 365)
            generations = (500_000 * 365) / max(1.0, generation_time)
            
            # 1. 渐进演化
            gradual_changes, drift_score = self._apply_gradual_evolution(
                species, environment_pressure, turn_index, generations
            )
            
            # 更新累积漂移分数
            species.accumulated_adaptation_score += drift_score
            
            if gradual_changes:
                adaptation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "changes": gradual_changes,
                    "type": "gradual_evolution"
                })
            
            # 2. 器官参数漂移 (Organ Parameter Drift)
            organ_drift_changes, organ_drift_score = self._apply_organ_drift(
                species, environment_pressure
            )
            species.accumulated_adaptation_score += organ_drift_score
            
            if organ_drift_changes:
                adaptation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "changes": organ_drift_changes,
                    "type": "organ_drift"
                })
            
            # 3. 熵增与退化检查 (Enhanced Regression)
            # 基础退化概率每5回合一次
            is_regression_turn = (turn_index % self.regression_check_turns == 0)
            # 计算总属性负担（Maintenance Cost）
            total_traits = sum(species.abstract_traits.values())
            maintenance_threshold = 40.0 + (species.trophic_level * 5.0) # 营养级越高，允许的属性总和越高
            
            # 如果属性总和过高，即使不是退化回合也强制触发退化检查
            force_regression = total_traits > (maintenance_threshold * 1.2)
            
            if is_regression_turn or force_regression:
                regression_changes, reg_drift = self._apply_regressive_evolution(
                    species, environment_pressure, turn_index, force_regression
                )
                species.accumulated_adaptation_score += reg_drift
                
                if regression_changes:
                    adaptation_events.append({
                        "lineage_code": species.lineage_code,
                        "common_name": species.common_name,
                        "changes": regression_changes,
                        "type": "regression"
                    })
            
            # 4. LLM驱动的智能适应（高压力情况下）
            # 只对部分关键物种使用LLM，避免token消耗过大
            if use_llm_adaptation and not species.is_background:
                # 选择性地使用LLM：高压力、非背景物种、每3回合一次
                should_use_llm = (
                    turn_index % 3 == 0 
                    or total_pressure >= HIGH_PRESSURE_THRESHOLD * 1.5
                )
                if should_use_llm:
                    task = self._create_llm_adaptation_task(
                        species, environment_pressure, pressure_context, stream_callback
                    )
                    llm_adaptation_tasks.append(task)
                    llm_species_list.append(species)
            
            # 5. 检查是否需要更新描述
            # 只有 Critical 或 Focus 物种，且漂移超过阈值时才更新（节省Token）
            # 或者每隔 20 回合强制检查一次
            should_update_desc = (
                species.accumulated_adaptation_score >= self.drift_threshold
                and (turn_index - species.last_description_update_turn) > 10
            )
            
            if should_update_desc:
                # 准备上下文
                task = self._create_description_update_task(species, gradual_changes, pressure_context, stream_callback)
                description_update_tasks.append(task)
                species_to_update.append(species)
                
                # 重置分数
                species.accumulated_adaptation_score = 0.0
                species.last_description_update_turn = turn_index

        # 【修改】顺序执行描述更新（避免并发请求过多）
        if description_update_tasks:
            # 【限制】如果任务过多，进行截断
            if len(description_update_tasks) > self.max_description_updates_per_turn:
                logger.info(f"[适应性] 描述更新任务过多 ({len(description_update_tasks)}), 限制为 {self.max_description_updates_per_turn}")
                description_update_tasks = description_update_tasks[:self.max_description_updates_per_turn]
                species_to_update = species_to_update[:self.max_description_updates_per_turn]

            logger.info(f"[适应性] 开始顺序执行 {len(description_update_tasks)} 个物种的描述更新...")
            
            # 【修改】顺序执行，逐个处理，避免并发
            for idx, (species, task) in enumerate(zip(species_to_update, description_update_tasks)):
                logger.info(f"[描述更新] 处理 {idx + 1}/{len(description_update_tasks)}: {species.common_name}")
                try:
                    res = await task
                    
                    new_desc = res.get("new_description") if isinstance(res, dict) else None
                    if new_desc and len(new_desc) > 50:
                        old_desc_preview = species.description[:20]
                        species.description = new_desc
                        logger.info(f"[描述更新] {species.common_name}: {old_desc_preview}... -> {new_desc[:20]}...")
                        
                        adaptation_events.append({
                            "lineage_code": species.lineage_code,
                            "common_name": species.common_name,
                            "changes": {"description": "re-written based on traits"},
                            "type": "description_update"
                        })
                except Exception as e:
                    logger.error(f"[描述更新失败] {species.common_name}: {e}")
            
            logger.info(f"[适应性] 描述更新完成")
        
        # 【修改】顺序执行LLM智能适应（避免并发请求过多）
        if llm_adaptation_tasks:
            # 【限制】限制最大适应数
            if len(llm_adaptation_tasks) > self.max_llm_adaptations_per_turn:
                logger.info(f"[适应性] LLM适应任务过多 ({len(llm_adaptation_tasks)}), 限制为 {self.max_llm_adaptations_per_turn}")
                llm_adaptation_tasks = llm_adaptation_tasks[:self.max_llm_adaptations_per_turn]
                llm_species_list = llm_species_list[:self.max_llm_adaptations_per_turn]

            logger.info(f"[适应性] 开始顺序执行 {len(llm_adaptation_tasks)} 个LLM智能适应任务...")
            
            # 【修改】顺序执行，逐个处理，避免并发
            for idx, (species, task) in enumerate(zip(llm_species_list, llm_adaptation_tasks)):
                logger.info(f"[LLM适应] 处理 {idx + 1}/{len(llm_adaptation_tasks)}: {species.common_name}")
                try:
                    res = await task
                    
                    if not isinstance(res, dict):
                        continue
                    
                    # 应用LLM建议的特质变化
                    llm_changes = self._apply_llm_recommendations(species, res)
                    if llm_changes:
                        adaptation_events.append({
                            "lineage_code": species.lineage_code,
                            "common_name": species.common_name,
                            "changes": llm_changes,
                            "type": "llm_adaptation",
                            "analysis": res.get("analysis", ""),
                            "rationale": res.get("rationale", ""),
                        })
                        logger.info(f"[LLM适应] {species.common_name}: {llm_changes}")
                except Exception as e:
                    logger.warning(f"[LLM适应失败] {species.common_name}: {e}")
            
            logger.info(f"[适应性] LLM智能适应完成")

        return adaptation_events
    
    def apply_adaptations(self, *args, **kwargs):
        """同步方法已废弃"""
        raise NotImplementedError("Use apply_adaptations_async instead")

    async def _create_description_update_task(
        self, 
        species: Species, 
        recent_changes: dict, 
        pressure_context: str,
        stream_callback: Callable[[str], Awaitable[None] | None] | None
    ) -> dict:
        """创建描述更新的AI任务"""
        # 构建 trait diffs 文本
        # 这里简单列出数值较高的 trait，提示 AI 关注
        high_traits = [
            f"{k}: {v:.1f}" 
            for k, v in species.abstract_traits.items() 
            if v > 7.0 or v < 2.0
        ]
        
        trait_diffs = f"显著特征: {', '.join(high_traits)}\n近期变化: {json.dumps(recent_changes, ensure_ascii=False)}"
        
        prompt = SPECIES_PROMPTS["species_description_update"].format(
            latin_name=species.latin_name,
            common_name=species.common_name,
            old_description=species.description,
            trait_diffs=trait_diffs,
            pressure_context=pressure_context  # 传入环境上下文
        )

        full_content = ""
        try:
            if stream_callback:
                 async for chunk in self.router.astream_capability(
                    capability="narrative",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                 ):
                    if isinstance(chunk, dict) and chunk.get("type") in ("status", "error"):
                         continue
                    if isinstance(chunk, str):
                        full_content += chunk
                        if asyncio.iscoroutinefunction(stream_callback):
                            await stream_callback(chunk)
                        else:
                            stream_callback(chunk)
            else:
                full_content = await self.router.acall_capability(
                    capability="narrative",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
        except Exception as e:
            logger.error(f"[描述更新] 流式调用失败: {e}")
            if not full_content:
                full_content = await self.router.acall_capability(
                    capability="narrative",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
        
        return self.router._parse_content(full_content)

    def _apply_gradual_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
        generations: float = 1000.0,
    ) -> tuple[dict, float]:
        """渐进演化
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        limits = TraitConfig.get_trophic_limits(species.trophic_level)
        current_total = sum(species.abstract_traits.values())
        
        # ========== 【世代感知模型】增强突变强度计算 ==========
        # 基于代数的演化速度修正（对数尺度）
        # 1000代 -> log10(1000)=3 -> 0.375
        # 10万代 -> log10(100000)=5 -> 0.625
        # 1亿代 -> log10(1e8)=8 -> 1.0
        generation_factor = math.log10(max(10, generations)) / _settings.generation_scale_factor
        
        # 计算选择压力强度（高压力下有益突变更容易固定）
        pressure_intensity = sum(abs(p) for p in environment_pressure.values()) / max(1, len(environment_pressure))
        selection_factor = 1.0 + (min(pressure_intensity / 10.0, 1.0) * 0.5)  # 最多1.5倍
        
        # 综合突变强度
        mutation_strength = generation_factor * selection_factor
        
        logger.debug(
            f"[突变强度] {species.common_name}: {generations:.0f}代, "
            f"generation_factor={generation_factor:.3f}, selection={selection_factor:.3f}, "
            f"总强度={mutation_strength:.3f}"
        )
        
        for trait_name, current_value in species.abstract_traits.items():
            mapping = TraitConfig.get_pressure_mapping(trait_name)
            if not mapping:
                continue
            
            pressure_type, pressure_direction = mapping
            pressure_value = environment_pressure.get(pressure_type, 0.0)
            
            should_evolve = False
            if pressure_direction == "hot" and pressure_value > 6.0:
                should_evolve = True
            elif pressure_direction == "cold" and pressure_value < -6.0:
                should_evolve = True
            elif pressure_direction == "high" and pressure_value > 5.0:
                should_evolve = True
            elif pressure_direction == "low" and pressure_value < -5.0:
                should_evolve = True
            
            if should_evolve and random.random() < self.gradual_evolution_rate:
                # ========== 【世代感知模型】应用突变强度 ==========
                # 基础幅度 0.1-0.3，乘以突变强度
                # 上限3.0（防止单次变化过大）
                base_delta = random.uniform(0.1, 0.3)
                delta = min(3.0, base_delta * mutation_strength)
                new_value = current_value + delta
                
                if new_value <= limits["specialized"] and current_total + delta <= limits["total"]:
                    species.abstract_traits[trait_name] = round(new_value, 2)
                    changes[trait_name] = f"+{delta:.2f}"
                    current_total += delta
                    drift_score += abs(delta)
                    logger.debug(f"[渐进演化] {species.common_name} {trait_name} +{delta:.2f} (压力{pressure_value:.1f})")
                    
                    if trait_name in ["耐热性", "耐极寒"]:
                        species.morphology_stats["metabolic_rate"] = species.morphology_stats.get("metabolic_rate", 1.0) * 1.02
        
        return changes, drift_score
    
    def _apply_organ_drift(
        self,
        species: Species,
        environment_pressure: dict[str, float],
    ) -> tuple[dict, float]:
        """器官参数漂移：纯数值的微调
        
        不改变器官类型，只改变 parameters 中的数值 (efficiency, speed, range, strength等)。
        
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        
        # 定义可漂移的参数白名单
        DRIFTABLE_PARAMS = {"efficiency", "speed", "range", "strength", "defense", "rate", "cost"}
        
        # 定义压力驱动的参数倾向 (Pressure -> Target Param to Increase)
        PRESSURE_MAP = {
            "predation": ["speed", "defense", "range"],
            "scarcity": ["efficiency", "rate"],
            "competition": ["strength", "efficiency"],
            "temperature": ["efficiency"], # 极端温度下需要更高效的代谢
        }
        
        # 找出当前的主要压力
        active_pressures = [k for k, v in environment_pressure.items() if abs(v) > 4.0]
        target_params = set()
        for p in active_pressures:
            # 简单的模糊匹配
            for key, params in PRESSURE_MAP.items():
                if key in p.lower():
                    target_params.update(params)
        
        # 如果没有显著压力，随机漂移
        if not target_params:
            if random.random() < 0.2: # 20% 概率发生随机漂移
                target_params.add(random.choice(list(DRIFTABLE_PARAMS)))
        
        for category, organ_data in species.organs.items():
            if not organ_data.get("is_active", True):
                continue
            
            params = organ_data.get("parameters", {})
            if not params:
                continue
            
            # 检查该器官是否有可漂移的参数
            drifted = False
            for param_name, param_value in params.items():
                if param_name not in DRIFTABLE_PARAMS:
                    continue
                
                # 必须是数字
                if not isinstance(param_value, (int, float)):
                    continue
                
                # 决定漂移方向
                # 如果该参数在目标列表中，倾向于增加
                # 否则，微小随机波动
                delta = 0.0
                if param_name in target_params and random.random() < 0.3: # 30% 概率适应性增强
                    delta = random.uniform(0.01, 0.05)
                elif random.random() < 0.05: # 5% 概率随机波动 (中性漂移)
                    delta = random.uniform(-0.02, 0.02)
                
                if delta != 0.0:
                    new_val = max(0.1, param_value + delta) # 保持为正数
                    params[param_name] = round(new_val, 3)
                    drifted = True
                    drift_score += abs(delta) * 2.0 # 器官变化权重较高
                    changes[f"{organ_data['type']}.{param_name}"] = f"{delta:+.3f}"
            
            if drifted:
                organ_data["parameters"] = params # 更新回对象
        
        return changes, drift_score

    def _apply_regressive_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
        force_mode: bool = False
    ) -> tuple[dict, float]:
        """退化演化 (Use it or Lose it & Entropy)
        
        Args:
            species: 目标物种
            environment_pressure: 环境压力
            turn_index: 当前回合
            force_mode: 是否强制执行（用于高熵状态）
            
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        
        # A. 随机熵增退化 (Maintenance Cost)
        # 当总属性过高时，随机降低某些属性以模拟能量守恒
        if force_mode or random.random() < 0.1: # 即使非强制模式，也有10%概率发生熵增
            # 选择一个较高的属性进行削弱
            high_traits = [k for k, v in species.abstract_traits.items() if v > 3.0]
            if high_traits:
                trait_to_regress = random.choice(high_traits)
                current_val = species.abstract_traits[trait_to_regress]
                # 削弱幅度：越高削弱越狠
                delta = random.uniform(0.1, 0.4) * (current_val / 5.0)
                new_value = max(1.0, current_val - delta)
                
                species.abstract_traits[trait_to_regress] = round(new_value, 2)
                changes[trait_to_regress] = f"-{delta:.2f} (熵增/维持成本)"
                drift_score += delta
                logger.debug(f"[退化] {species.common_name} {trait_to_regress} -{delta:.2f} (熵增)")

        # B. 环境驱动的定向退化 (Use it or Lose it)
        
        # 1. 光照需求退化（深海/洞穴生物）
        light_level = environment_pressure.get("light_level", 1.0)
        if light_level < 0.1:
            current_light_need = species.abstract_traits.get("光照需求", 5.0)
            if current_light_need > 1.0:
                # 每5回合降低0.2
                delta = random.uniform(0.15, 0.25)
                new_value = max(0.0, current_light_need - delta)
                species.abstract_traits["光照需求"] = round(new_value, 2)
                changes["光照需求"] = f"-{delta:.2f} (长期黑暗退化)"
                drift_score += delta
                logger.debug(f"[退化] {species.common_name} 光照需求 -{delta:.2f}")
        
        # 2. 运动能力退化（附着型生物）
        desc_lower = species.description.lower()
        if any(kw in desc_lower for kw in ["附着", "固着", "sessile", "attached"]):
            current_movement = species.abstract_traits.get("运动能力", 5.0)
            if current_movement > 0.5:
                delta = random.uniform(0.1, 0.2)
                new_value = max(0.0, current_movement - delta)
                species.abstract_traits["运动能力"] = round(new_value, 2)
                changes["运动能力"] = f"-{delta:.2f} (附着生活退化)"
                drift_score += delta
                logger.debug(f"[退化] {species.common_name} 运动能力 -{delta:.2f}")
                
                # 同时检查运动器官是否需要退化
                if "locomotion" in species.organs:
                    if species.organs["locomotion"].get("is_active", True):
                        # 30%概率使器官失活
                        if random.random() < 0.3:
                            species.organs["locomotion"]["is_active"] = False
                            species.organs["locomotion"]["deactivated_turn"] = turn_index
                            changes["器官退化"] = f"{species.organs['locomotion']['type']}失活"
                            drift_score += 2.0 # 器官变化算大漂移
                            logger.info(f"[退化] {species.common_name} 运动器官失活")
        
        # 3. 视觉器官退化（洞穴生物）
        if light_level < 0.05 and "sensory" in species.organs:
            sensory_organ = species.organs["sensory"]
            if sensory_organ.get("type") in ["eyespot", "simple_eye", "compound_eye"]:
                if sensory_organ.get("is_active", True):
                    # 判断退化概率：取决于在黑暗环境中的时间
                    turns_in_darkness = turn_index - species.created_turn
                    regression_prob = min(0.5, turns_in_darkness * 0.01)  # 最多50%
                    
                    if random.random() < regression_prob:
                        species.organs["sensory"]["is_active"] = False
                        species.organs["sensory"]["deactivated_turn"] = turn_index
                        changes["器官退化"] = f"视觉器官失活（{turns_in_darkness}回合黑暗）"
                        drift_score += 2.0
                        logger.info(f"[退化] {species.common_name} 视觉器官失活")
        
        # 4. 消化系统退化（寄生生物）
        if any(kw in desc_lower for kw in ["寄生", "parasite", "宿主", "host"]):
            if "digestive" in species.organs:
                if species.organs["digestive"].get("is_active", True):
                    # 寄生生物有40%概率退化消化系统
                    if random.random() < 0.4:
                        species.organs["digestive"]["is_active"] = False
                        species.organs["digestive"]["deactivated_turn"] = turn_index
                        changes["器官退化"] = "消化系统退化（寄生生活）"
                        drift_score += 2.0
                        logger.info(f"[退化] {species.common_name} 消化系统退化")
        
        # 5. 不匹配环境的属性缓慢降低（动态检查所有trait）
        for trait_name, current_value in species.abstract_traits.items():
            mapping = TraitConfig.get_pressure_mapping(trait_name)
            if not mapping:
                continue
            
            pressure_type, pressure_direction = mapping
            pressure_value = environment_pressure.get(pressure_type, 0.0)
            
            is_mismatched = False
            if pressure_direction == "hot" and pressure_value < -3.0 and current_value > 8.0:
                is_mismatched = True
            elif pressure_direction == "cold" and pressure_value > 3.0 and current_value > 8.0:
                is_mismatched = True
            elif pressure_direction == "high" and pressure_value < 2.0 and current_value > 8.0:
                is_mismatched = True
            
            if is_mismatched and random.random() < 0.2:
                delta = random.uniform(0.05, 0.15)
                new_value = max(5.0, current_value - delta)
                species.abstract_traits[trait_name] = round(new_value, 2)
                changes[trait_name] = f"-{delta:.2f} (环境不需要)"
                drift_score += delta
                logger.debug(f"[退化] {species.common_name} {trait_name} -{delta:.2f}")
        
        return changes, drift_score
    
    def get_organ_summary(self, species: Species) -> dict:
        """获取物种器官摘要（用于API返回）
        
        Returns:
            {
                "active_organs": [...],
                "inactive_organs": [...],
                "capabilities": [...]
            }
        """
        active = []
        inactive = []
        
        for category, organ_data in species.organs.items():
            organ_info = {
                "category": category,
                "type": organ_data.get("type", "unknown"),
                "acquired_turn": organ_data.get("acquired_turn", 0)
            }
            
            if organ_data.get("is_active", True):
                active.append(organ_info)
            else:
                organ_info["deactivated_turn"] = organ_data.get("deactivated_turn", 0)
                inactive.append(organ_info)
        
        return {
            "active_organs": active,
            "inactive_organs": inactive,
            "capabilities": species.capabilities
        }
    
    async def _create_llm_adaptation_task(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        pressure_context: str,
        stream_callback: Callable[[str], Awaitable[None] | None] | None
    ) -> dict:
        """创建LLM驱动的适应性演化任务
        
        Args:
            species: 目标物种
            environment_pressure: 环境压力字典
            pressure_context: 压力描述上下文
            stream_callback: 流式回调函数
            
        Returns:
            LLM返回的适应建议
        """
        # 构建特质摘要
        traits_summary = "\n".join([
            f"- {k}: {v:.1f}" 
            for k, v in sorted(species.abstract_traits.items(), key=lambda x: -x[1])
        ])
        
        # 构建器官摘要
        organs_summary = ""
        for category, organ_data in species.organs.items():
            if organ_data.get("is_active", True):
                organ_type = organ_data.get("type", "unknown")
                params = organ_data.get("parameters", {})
                param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
                organs_summary += f"- {category}: {organ_type} ({param_str})\n"
        
        if not organs_summary:
            organs_summary = "无已记录器官"
        
        # 构建prompt
        prompt = SPECIES_PROMPTS["pressure_adaptation"].format(
            pressure_context=pressure_context,
            latin_name=species.latin_name,
            common_name=species.common_name,
            habitat_type=getattr(species, 'habitat_type', 'unknown'),
            trophic_level=species.trophic_level,
            description=species.description,
            traits_summary=traits_summary,
            organs_summary=organs_summary,
        )
        
        full_content = ""
        try:
            if stream_callback:
                async for chunk in self.router.astream_capability(
                    capability="pressure_adaptation",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                ):
                    if isinstance(chunk, dict) and chunk.get("type") in ("status", "error"):
                        continue
                    if isinstance(chunk, str):
                        full_content += chunk
                        if asyncio.iscoroutinefunction(stream_callback):
                            await stream_callback(chunk)
                        else:
                            stream_callback(chunk)
            else:
                full_content = await self.router.acall_capability(
                    capability="pressure_adaptation",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
        except Exception as e:
            logger.error(f"[LLM适应] 调用失败: {e}")
            if not full_content:
                # 回退到空结果
                return {}
        
        return self.router._parse_content(full_content)
    
    def _apply_llm_recommendations(self, species: Species, llm_result: dict) -> dict:
        """应用LLM推荐的适应性变化
        
        Args:
            species: 目标物种
            llm_result: LLM返回的建议
            
        Returns:
            实际应用的变化字典
        """
        applied_changes = {}
        
        # 1. 应用特质变化
        recommended_changes = llm_result.get("recommended_changes", {})
        if isinstance(recommended_changes, dict):
            for trait_name, change_str in recommended_changes.items():
                if trait_name not in species.abstract_traits:
                    continue
                
                try:
                    # 解析变化值 (格式: "+0.3" 或 "-0.2")
                    if isinstance(change_str, str):
                        delta = float(change_str.replace("+", ""))
                    else:
                        delta = float(change_str)
                    
                    # 限制单次变化幅度
                    delta = max(-0.8, min(0.8, delta))
                    
                    current_value = species.abstract_traits[trait_name]
                    new_value = TraitConfig.clamp_trait(current_value + delta)
                    
                    species.abstract_traits[trait_name] = round(new_value, 2)
                    applied_changes[trait_name] = f"{delta:+.2f}"
                    
                except (ValueError, TypeError) as e:
                    logger.warning(f"[LLM适应] 无法解析特质变化 {trait_name}: {change_str}, {e}")
        
        # 2. 应用器官变化
        organ_changes = llm_result.get("organ_changes", [])
        if isinstance(organ_changes, list):
            for change in organ_changes:
                if not isinstance(change, dict):
                    continue
                
                category = change.get("category")
                change_type = change.get("change_type")
                parameter = change.get("parameter")
                delta = change.get("delta", 0)
                
                if not category or not change_type:
                    continue
                
                if category in species.organs and change_type == "enhance":
                    # 增强现有器官参数
                    if parameter and parameter in species.organs[category].get("parameters", {}):
                        try:
                            current = species.organs[category]["parameters"][parameter]
                            new_val = current + float(delta)
                            species.organs[category]["parameters"][parameter] = round(new_val, 3)
                            applied_changes[f"{category}.{parameter}"] = f"{delta:+.3f}"
                        except (ValueError, TypeError):
                            pass
                elif change_type == "degrade" and category in species.organs:
                    # 退化器官
                    species.organs[category]["is_active"] = False
                    applied_changes[f"{category}"] = "deactivated"
        
        # 3. 更新累积适应分数
        if applied_changes:
            species.accumulated_adaptation_score += len(applied_changes) * 0.5
        
        return applied_changes
