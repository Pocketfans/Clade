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
from .trait_config import TraitConfig, PlantTraitConfig
from ...ai.model_router import ModelRouter, staggered_gather
from ...ai.prompts.species import SPECIES_PROMPTS
from ...core.config import get_settings
from ...simulation.constants import get_time_config

logger = logging.getLogger(__name__)

# 【新增】植物压力类型映射（环境压力 → 植物压力类型）
ENVIRONMENT_TO_PLANT_PRESSURE = {
    "temperature": None,  # 温度使用共享特质
    "drought": "drought",
    "humidity": "drought",  # 负值时映射到干旱
    "light": "light_reduction",
    "nutrient": "nutrient_poor",
    "herbivory": "herbivory",  # 食草压力
    "competition": "competition",
}

# 获取配置
_settings = get_settings()

# 高压力阈值：超过此值时使用LLM进行智能适应
HIGH_PRESSURE_THRESHOLD = 5.0


import numpy as np

class AdaptationService:
    """处理物种的渐进演化和器官退化
    
    【核心重构 v2.0】矩阵驱动的能量守恒演化系统
    1. 使用 Numpy 批量计算适应方向
    2. 引入 L2 范数归一化强制能量守恒 (Trade-off)
    3. 支持地质时代模长限制 (Era Cap)
    """
    
    def __init__(self, router: ModelRouter):
        self.router = router
        self.gradual_evolution_rate = 0.15
        self.regression_check_turns = 5
        self.drift_threshold = 3.0  # 累积漂移超过此值触发描述更新
        self.enable_llm_adaptation = True  # 是否启用LLM驱动的适应
        # 【修复】添加并发限制，防止一次性生成过多AI任务
        self.max_llm_adaptations_per_turn = 15
        self.max_description_updates_per_turn = 10
        
        # 【新增】地质时代模长上限配置 (Era Cap)
        self.era_trait_caps = {
            "Hadean": 20.0,      # 冥古宙：极简生物
            "Archean": 30.0,     # 太古宙：原核生物
            "Proterozoic": 45.0, # 元古宙：真核/多细胞
            "Paleozoic": 60.0,   # 古生代：复杂生命爆发
            "Mesozoic": 80.0,    # 中生代：巨型生物
            "Cenozoic": 100.0,   # 新生代：当前水平
        }
        
    def _normalize_traits(self, traits: dict[str, float], era: str = "Cenozoic") -> dict[str, float]:
        """执行特征向量归一化，强制能量守恒
        
        Args:
            traits: 特征字典
            era: 地质时代
            
        Returns:
            归一化后的特征字典
        """
        if not traits:
            return {}
            
        # 1. 转换为向量
        keys = list(traits.keys())
        values = np.array([traits[k] for k in keys], dtype=np.float64)
        
        # 2. 计算当前模长 (L2 Norm)
        current_magnitude = np.linalg.norm(values)
        
        # 3. 获取时代上限
        cap = self.era_trait_caps.get(era, 100.0)
        
        # 4. 归一化逻辑
        # 如果模长超过上限，强制缩放回上限
        # 这样新属性增加时，旧属性会被迫减少
        if current_magnitude > cap:
            scale_factor = cap / current_magnitude
            normalized_values = values * scale_factor
            
            # 更新字典
            new_traits = {}
            for k, v in zip(keys, normalized_values):
                new_traits[k] = round(float(v), 2)
            return new_traits
            
        return traits.copy()

    def _calculate_adaptation_vector(
        self, 
        species: Species, 
        env_pressure_matrix: np.ndarray, # (n_tiles, n_features)
        tile_indices: list[int],
        feature_map: dict[str, int] # pressure_name -> matrix_col_index
    ) -> dict[str, float]:
        """计算物种在特定区域的理想适应向量 (Numpy加速)
        
        基于区域内的环境压力，计算每个特征的理想调整方向和幅度。
        """
        if not tile_indices or env_pressure_matrix is None:
            return {}
            
        # 1. 提取区域子矩阵
        # region_pressures: (n_tiles_in_region, n_features)
        region_pressures = env_pressure_matrix[tile_indices]
        
        # 2. 计算区域平均压力 (简单的算术平均，后续可改为种群加权平均)
        # avg_pressures: (n_features,)
        avg_pressures = np.mean(region_pressures, axis=0)
        
        adaptation_vector = {}
        
        # 3. 遍历特征，计算适应方向
        # feature_map 示例: {"temperature": 0, "humidity": 1, "salinity": 2}
        for pressure_name, col_idx in feature_map.items():
            if col_idx >= len(avg_pressures):
                continue
                
            pressure_val = avg_pressures[col_idx]
            
            # 根据压力值推断需要的特征变化
            # 这里复用 PlantTraitConfig 或 TraitConfig 的映射逻辑
            # 但为了性能，最好将其预计算为矩阵运算
            
            # 简化示例：假设压力值直接对应需要的特征值偏移
            # 例如：温度压力 +5 -> 耐热性 +0.5
            
            # 获取关联的特征
            related_traits = self._get_traits_for_pressure(pressure_name, species)
            
            for trait in related_traits:
                # 简单的线性映射：压力 * 系数
                # 系数通常较小，表示渐进演化
                delta = pressure_val * 0.1 
                
                if trait not in adaptation_vector:
                    adaptation_vector[trait] = 0.0
                adaptation_vector[trait] += delta
                
        return adaptation_vector

    def _get_traits_for_pressure(self, pressure_name: str, species: Species) -> list[str]:
        """获取受特定压力影响的特征列表"""
        # 判断是否为植物
        is_plant = PlantTraitConfig.is_plant(species)
        
        # 简单的硬编码映射，后续应从配置加载
        # 注意：这里需要与 _apply_gradual_evolution 中的映射保持一致或更优
        if is_plant:
            mapping = {
                "temperature": ["耐热性", "耐寒性"],
                "drought": ["耐旱性", "保水能力"],
                "humidity": ["耐旱性"], # 负相关
                "light": ["光照需求", "光合效率"],
                "nutrient": ["耐贫瘠", "根系发达度"],
                "herbivory": ["物理防御", "化学防御", "再生能力"],
                "competition": ["生长速度", "高度"],
            }
        else:
            mapping = {
                "temperature": ["耐热性", "耐寒性"],
                "drought": ["耐旱性"],
                "predation": ["运动能力", "感知能力", "防御力"],
                "competition": ["攻击力", "体型"],
                "scarcity": ["代谢率", "消化效率"],
            }
            
        # 模糊匹配
        related = []
        for key, traits in mapping.items():
            if key in pressure_name.lower():
                related.extend(traits)
                
        return list(set(related))

    async def apply_adaptations_async(
        self,
        species_list: Sequence[Species],
        environment_pressure: dict[str, float],
        turn_index: int,
        pressures: Sequence = None,  # 新增：ParsedPressure 列表
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
        mortality_results: Sequence = None,  # 【新增】死亡率结果，用于提取植物压力
        event_callback: Callable[[str, str, str], None] | None = None,  # 【新增】事件回调
    ) -> list[dict]:
        """应用适应性变化（渐进演化+退化+描述同步+LLM智能适应）(Async)
        
        Args:
            species_list: 所有存活物种
            environment_pressure: 当前环境压力
            turn_index: 当前回合数
            pressures: ParsedPressure 列表，用于提供上下文
            stream_callback: (已废弃) 流式内容回调
            mortality_results: 死亡率结果列表，用于提取植物竞争压力等
            event_callback: 事件回调函数 (type, message, category)
            
        Returns:
            变化记录列表
        """
        # 【新增】获取时间配置
        time_config = get_time_config(turn_index)
        years_per_turn = time_config["years_per_turn"]
        scaling_factor = time_config["scaling_factor"]
        
        # 【新增】构建物种压力映射（从死亡率结果中提取）
        species_pressure_cache: dict[str, dict] = {}
        if mortality_results:
            for result in mortality_results:
                pressure_data = {
                    "plant_competition": getattr(result, 'plant_competition_pressure', 0.0),
                    "herbivory": getattr(result, 'herbivory_pressure', 0.0),
                    "light_competition": getattr(result, 'light_competition', 0.0),
                    "nutrient_competition": getattr(result, 'nutrient_competition', 0.0),
                    # 动物压力
                    "predation": getattr(result, 'predation_pressure', 0.0),
                    "grazing": getattr(result, 'grazing_pressure', 0.0),
                    "competition": getattr(result, 'niche_overlap', 0.0) * 10.0, # 归一化到0-10
                }
                species_pressure_cache[result.species.lineage_code] = pressure_data
                
        self._species_pressure_cache = species_pressure_cache
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
            # 计算经历了多少代 (使用动态年份)
            generation_time = species.morphology_stats.get("generation_time_days", 365)
            generations = (years_per_turn * 365) / max(1.0, generation_time)
            
            # 0. 应用表型可塑性缓冲 (Phenotypic Plasticity)
            # 必须在基因演化之前执行，因为缓冲状态会影响演化紧迫性
            plasticity_changes, urgency_score = self._apply_plasticity_buffer(
                species, environment_pressure, turn_index
            )
            species.accumulated_adaptation_score += urgency_score
            
            if plasticity_changes:
                # 记录但不作为主要演化事件，除非非常紧急
                if urgency_score > 1.0:
                    adaptation_events.append({
                        "lineage_code": species.lineage_code,
                        "common_name": species.common_name,
                        "changes": {"buffer": "critical_low"},
                        "type": "stress_response"
                    })

            # 1. 渐进演化
            # 传入 scaling_factor 调整演化速率
            gradual_changes, drift_score = self._apply_gradual_evolution(
                species, environment_pressure, turn_index, generations, scaling_factor
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
                species, environment_pressure, scaling_factor
            )
            species.accumulated_adaptation_score += organ_drift_score
            
            if organ_drift_changes:
                adaptation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "changes": organ_drift_changes,
                    "type": "organ_drift"
                })
            
            # 2.5 器官进度累积 (Organ Progress Accumulation)
            # 让发展中的器官逐渐成熟
            organ_progress_changes, organ_progress_score = self._apply_organ_progress_accumulation(
                species, environment_pressure, turn_index, scaling_factor
            )
            species.accumulated_adaptation_score += organ_progress_score
            
            if organ_progress_changes:
                adaptation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "changes": organ_progress_changes,
                    "type": "organ_development"
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
                    species, environment_pressure, turn_index, force_regression, scaling_factor
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
                        species, environment_pressure, pressure_context, stream_callback, time_config
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

        # 【优化】间隔并行执行描述更新
        if description_update_tasks:
            # 【限制】如果任务过多，进行截断
            if len(description_update_tasks) > self.max_description_updates_per_turn:
                logger.info(f"[适应性] 描述更新任务过多 ({len(description_update_tasks)}), 限制为 {self.max_description_updates_per_turn}")
                description_update_tasks = description_update_tasks[:self.max_description_updates_per_turn]
                species_to_update = species_to_update[:self.max_description_updates_per_turn]

            logger.info(f"[适应性] 开始间隔并行执行 {len(description_update_tasks)} 个物种的描述更新...")
            
            # 【优化】间隔并行执行，每2秒启动一个，最多同时3个
            results = await staggered_gather(
                description_update_tasks,
                interval=2.0,
                max_concurrent=3,
                task_name="描述更新",
                event_callback=event_callback,  # 【新增】传递心跳回调
            )
            
            for idx, (species, res) in enumerate(zip(species_to_update, results)):
                if isinstance(res, Exception):
                    logger.error(f"[描述更新失败] {species.common_name}: {res}")
                    continue
                    
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
            
            logger.info(f"[适应性] 描述更新完成")
        
        # 【优化】间隔并行执行LLM智能适应
        if llm_adaptation_tasks:
            # 【限制】限制最大适应数
            if len(llm_adaptation_tasks) > self.max_llm_adaptations_per_turn:
                logger.info(f"[适应性] LLM适应任务过多 ({len(llm_adaptation_tasks)}), 限制为 {self.max_llm_adaptations_per_turn}")
                llm_adaptation_tasks = llm_adaptation_tasks[:self.max_llm_adaptations_per_turn]
                llm_species_list = llm_species_list[:self.max_llm_adaptations_per_turn]

            logger.info(f"[适应性] 开始间隔并行执行 {len(llm_adaptation_tasks)} 个LLM智能适应任务...")
            
            # 【优化】间隔并行执行，每2秒启动一个，最多同时3个
            results = await staggered_gather(
                llm_adaptation_tasks,
                interval=2.0,
                max_concurrent=3,
                task_name="LLM适应",
                event_callback=event_callback,  # 【新增】传递心跳回调
            )
            
            for idx, (species, res) in enumerate(zip(llm_species_list, results)):
                if isinstance(res, Exception):
                    logger.warning(f"[LLM适应失败] {species.common_name}: {res}")
                    continue
                    
                if not isinstance(res, dict):
                    continue
                
                # 应用LLM建议的特质变化
                llm_changes = self._apply_llm_recommendations(species, res)
                if llm_changes:
                    # 【修复】提取并使用 priority 字段
                    priority = res.get("priority", "medium")
                    adaptation_events.append({
                        "lineage_code": species.lineage_code,
                        "common_name": species.common_name,
                        "changes": llm_changes,
                        "type": "llm_adaptation",
                        "priority": priority,  # high/medium/low
                        "analysis": res.get("analysis", ""),
                        "rationale": res.get("rationale", ""),
                    })
                    priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                    logger.info(f"[LLM适应] {priority_emoji} {species.common_name}: {llm_changes}")
            
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
        """创建描述更新的AI任务（非流式，更稳定）
        
        【改进】植物使用专用的描述更新Prompt
        """
        is_plant = PlantTraitConfig.is_plant(species)
        
        # 构建 trait diffs 文本
        high_traits = [
            f"{k}: {v:.1f}" 
            for k, v in species.abstract_traits.items() 
            if v > 7.0 or v < 2.0
        ]
        
        trait_diffs = f"显著特征: {', '.join(high_traits)}\n近期变化: {json.dumps(recent_changes, ensure_ascii=False)}"
        
        if is_plant:
            # 【新增】使用植物专用Prompt
            life_form_stage = getattr(species, 'life_form_stage', 0)
            growth_form = getattr(species, 'growth_form', 'aquatic')
            stage_name = PlantTraitConfig.get_stage_name(life_form_stage)
            
            # 构建植物器官摘要
            plant_organs_summary = ""
            if hasattr(species, 'plant_organs') and species.plant_organs:
                organs_lines = []
                for category, organ_data in species.plant_organs.items():
                    if organ_data:
                        organ_name = organ_data.get('name', category)
                        organs_lines.append(f"- {category}: {organ_name}")
                plant_organs_summary = "\n".join(organs_lines) if organs_lines else "无专用器官"
            else:
                plant_organs_summary = "无专用器官"
            
            # 获取植物竞争压力上下文
            cached_pressures = getattr(self, '_species_pressure_cache', {}).get(species.lineage_code, {})
            plant_context_lines = []
            if cached_pressures.get("plant_competition", 0) > 0.1:
                plant_context_lines.append(f"植物竞争压力: {cached_pressures['plant_competition']:.0%}")
            if cached_pressures.get("herbivory", 0) > 0.1:
                plant_context_lines.append(f"食草动物压力: {cached_pressures['herbivory']:.0%}")
            plant_context = "\n".join(plant_context_lines) if plant_context_lines else ""
            
            prompt = SPECIES_PROMPTS["plant_description_update"].format(
                latin_name=species.latin_name,
                common_name=species.common_name,
                life_form_stage_name=stage_name,
                growth_form=growth_form,
                old_description=species.description,
                trait_diffs=trait_diffs,
                pressure_context=pressure_context,
                plant_context=plant_context,
                plant_organs_summary=plant_organs_summary,
            )
        else:
            # 动物使用原有Prompt
            prompt = SPECIES_PROMPTS["species_description_update"].format(
                latin_name=species.latin_name,
                common_name=species.common_name,
                old_description=species.description,
                trait_diffs=trait_diffs,
                pressure_context=pressure_context
            )

        # 【优化】使用带心跳的调用
        from ...ai.streaming_helper import acall_with_heartbeat
        
        try:
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="narrative",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"描述更新[{species.common_name[:8]}]",
                timeout=60,
                heartbeat_interval=2.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"[描述更新] {species.common_name} 超时（60秒）")
            return {}
        except Exception as e:
            logger.error(f"[描述更新] AI调用失败: {e}")
            return {}
        
        return self.router._parse_content(full_content)

    def _apply_plasticity_buffer(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int
    ) -> tuple[dict, float]:
        """应用表型可塑性缓冲 (Phenotypic Plasticity Buffer)
        
        【新机制 v2.0】
        生物面对压力时，首先通过生理调节（消耗缓冲）来应对，
        只有当缓冲耗尽时，才会面临真正的死亡或被迫进行基因演化。
        
        - 压力高 -> 消耗缓冲
        - 压力低 -> 恢复缓冲
        - 缓冲低 -> 增加演化紧迫性 (Evolutionary Urgency)
        
        Returns:
            (changes_dict, urgency_score)
        """
        changes = {}
        urgency_score = 0.0
        
        # 1. 计算当前环境总压力
        # 忽略一些常规压力，关注极端值
        extreme_pressures = [abs(v) for k, v in environment_pressure.items() if abs(v) > 3.0]
        total_stress = sum(extreme_pressures)
        
        current_buffer = getattr(species, 'plasticity_buffer', 1.0)
        
        # 2. 缓冲动态变化
        if total_stress > 5.0:
            # 高压环境：消耗缓冲
            # 压力越大，消耗越快
            consumption = min(0.2, total_stress * 0.01)
            new_buffer = max(0.0, current_buffer - consumption)
            
            if new_buffer < current_buffer:
                species.plasticity_buffer = round(new_buffer, 3)
                # 缓冲下降不记录为显性Trait变化，但会影响演化紧迫性
                if new_buffer < 0.3:
                    changes["plasticity"] = "critical_low"
                    urgency_score += 2.0  # 增加演化紧迫性
                elif new_buffer < 0.6:
                    urgency_score += 0.5
                    
                logger.debug(f"[可塑性] {species.common_name} 缓冲消耗: {current_buffer:.2f} -> {new_buffer:.2f} (压力 {total_stress:.1f})")
        
        elif total_stress < 2.0:
            # 低压环境：恢复缓冲
            recovery = 0.05
            new_buffer = min(1.0, current_buffer + recovery)
            
            if new_buffer > current_buffer:
                species.plasticity_buffer = round(new_buffer, 3)
                logger.debug(f"[可塑性] {species.common_name} 缓冲恢复: {current_buffer:.2f} -> {new_buffer:.2f}")
                
        return changes, urgency_score

    def _apply_gradual_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
        generations: float = 1000.0,
        scaling_factor: float = 1.0,
    ) -> tuple[dict, float]:
        """渐进演化（支持动物和植物）
        
        【改进 v2.0】矩阵驱动 + 能量守恒 + 动态时间缩放
        """
        changes = {}
        drift_score = 0.0
        
        # 【新增】判断是否为植物
        is_plant = PlantTraitConfig.is_plant(species)
        
        # 0. 准备压力数据（合并环境压力和生物压力）
        # 复制一份，以免修改原字典
        combined_pressure = environment_pressure.copy()
        
        # 从缓存获取额外的生物压力 (Predation, Competition, Herbivory)
        cached_pressures = getattr(self, '_species_pressure_cache', {}).get(species.lineage_code, {})
        if cached_pressures:
            if is_plant:
                # 植物压力转换
                if cached_pressures.get("plant_competition", 0) > 0.1:
                    combined_pressure["competition"] = cached_pressures["plant_competition"] * 20
                if cached_pressures.get("herbivory", 0) > 0.1:
                    combined_pressure["herbivory"] = cached_pressures["herbivory"] * 15
                if cached_pressures.get("light_competition", 0) > 0.1:
                    combined_pressure["light_reduction"] = cached_pressures["light_competition"] * 15
                if cached_pressures.get("nutrient_competition", 0) > 0.1:
                    combined_pressure["nutrient_poor"] = cached_pressures["nutrient_competition"] * 15
            else:
                # 动物压力转换
                if cached_pressures.get("predation", 0) > 0.05:
                    # 捕食压力直接映射到 predation
                    combined_pressure["predation"] = cached_pressures["predation"] * 20 
                if cached_pressures.get("competition", 0) > 2.0:
                    combined_pressure["competition"] = cached_pressures["competition"]
        
        # 1. 提取当前特征向量
        # 过滤掉非数值特征
        trait_keys = list(species.abstract_traits.keys())
        if not trait_keys:
            return {}, 0.0
            
        V_traits = np.array([species.abstract_traits[k] for k in trait_keys], dtype=np.float64)
        
        # 2. 构建目标梯度向量 (Gradient)
        # 理想情况下，特质应该向抵抗压力的方向移动
        G_evo = np.zeros_like(V_traits)
        
        # 获取压力映射
        if is_plant:
            pressure_map_func = PlantTraitConfig.get_plant_pressure_mapping
        else:
            pressure_map_func = TraitConfig.get_pressure_mapping
            
        # 遍历每个特质，计算其受到的环境“拉力”
        for idx, trait_name in enumerate(trait_keys):
            mapping = pressure_map_func(trait_name)
            if not mapping:
                continue
                
            pressure_type, pressure_direction = mapping
            pressure_val = combined_pressure.get(pressure_type, 0.0)
            
            # 计算该特质的理想改变量
            force = 0.0
            
            if pressure_direction == "hot" and pressure_val > 0:
                force = pressure_val * 0.1
            elif pressure_direction == "cold" and pressure_val < 0:
                force = abs(pressure_val) * 0.1
            elif pressure_direction == "high" and pressure_val > 0:
                force = pressure_val * 0.1
            elif pressure_direction == "low" and pressure_val < 0:
                force = abs(pressure_val) * 0.1
            elif pressure_direction in ["drought", "dry"]: 
                 if pressure_val > 0: force = pressure_val * 0.1
            # 新增：捕食/竞争压力正向拉动
            elif pressure_type in ["predation", "competition", "herbivory", "light_reduction", "nutrient_poor"]:
                if pressure_val > 0: force = pressure_val * 0.1
                 
            G_evo[idx] = force

        # 3. 应用演化步长
        # 演化速率受世代数、可塑性缓冲和时间缩放因子影响
        buffer_val = getattr(species, 'plasticity_buffer', 1.0)
        urgency_factor = 1.0 + (1.0 - buffer_val) * 2.0  # 最多3倍速
        
        # 基础学习率 * 紧迫性 * 时间缩放 * 矩阵系数
        learning_rate = self.gradual_evolution_rate * urgency_factor * scaling_factor * 0.1 
        
        # V_new = V_traits + G_evo * lr
        # 添加随机噪音模拟基因漂变 (噪音也随时间尺度放大，但系数较小)
        noise_scale = 0.05 * max(1.0, scaling_factor * 0.5)
        noise = np.random.normal(0, noise_scale, size=len(V_traits))
        V_new = V_traits + (G_evo * learning_rate) + noise
        
        # 4. 能量守恒归一化 (Trade-off)
        # 将新向量映射回特征字典进行归一化
        temp_traits = {k: v for k, v in zip(trait_keys, V_new)}
        
        # 使用地质时代限制
        # 假设当前是 Cenozoic (需从某处获取，这里暂时硬编码或从 settings 获取)
        current_era = "Cenozoic" 
        normalized_traits = self._normalize_traits(temp_traits, era=current_era)
        
        # 5. 应用变化并记录
        for k, new_v in normalized_traits.items():
            old_v = species.abstract_traits[k]
            # 确保数值非负且在合理范围
            new_v = max(0.0, min(15.0, new_v))
            
            if abs(new_v - old_v) > 0.05:
                species.abstract_traits[k] = round(new_v, 2)
                delta = new_v - old_v
                changes[k] = f"{delta:+.2f}"
                drift_score += abs(delta)
        
        return changes, drift_score
    
    def _accumulate_plant_stage_progress(
        self,
        species: Species,
        changes: dict,
        turn_index: int
    ) -> None:
        """【新增】植物阶段进度累积
        
        当植物的关键特质增加时，累积向更高阶段发展的进度
        """
        from .plant_evolution import PLANT_MILESTONES, plant_evolution_service
        
        current_stage = getattr(species, 'life_form_stage', 0)
        if current_stage >= 6:  # 已达到最高阶段
            return
        
        # 查找下一个阶段的里程碑
        next_milestone = plant_evolution_service.get_next_milestone(species)
        if not next_milestone or next_milestone.from_stage != current_stage:
            return
        
        # 检查变化是否有助于里程碑
        requirements = next_milestone.requirements
        progress_boost = 0.0
        
        for trait_name, required_value in requirements.items():
            if trait_name in changes:
                change_str = changes[trait_name]
                if change_str.startswith("+"):
                    change_value = float(change_str[1:])
                    current_value = species.abstract_traits.get(trait_name, 0)
                    # 如果朝着目标进步，累积进度
                    if current_value < required_value:
                        progress_boost += change_value / required_value * 0.1
        
        if progress_boost > 0:
            # 记录进度（可以在后续回合检查是否满足条件）
            current_progress = species.morphology_stats.get("milestone_progress", 0.0)
            species.morphology_stats["milestone_progress"] = min(1.0, current_progress + progress_boost)
            logger.debug(
                f"[植物阶段进度] {species.common_name}: "
                f"向 '{next_milestone.name}' 进度 +{progress_boost:.1%}"
            )
    
    def _apply_organ_drift(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        scaling_factor: float = 1.0,
    ) -> tuple[dict, float]:
        """器官参数漂移：纯数值的微调
        
        【改进】支持植物专用的器官压力映射，支持时间缩放
        
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        
        # 【新增】判断是否为植物
        is_plant = PlantTraitConfig.is_plant(species)
        
        # 定义可漂移的参数白名单
        ANIMAL_DRIFTABLE_PARAMS = {"efficiency", "speed", "range", "strength", "defense", "rate", "cost"}
        PLANT_DRIFTABLE_PARAMS = {"efficiency", "capacity", "rate", "density", "resistance", "production", "absorption"}
        
        DRIFTABLE_PARAMS = PLANT_DRIFTABLE_PARAMS if is_plant else ANIMAL_DRIFTABLE_PARAMS
        
        # 【改进】定义压力驱动的参数倾向
        ANIMAL_PRESSURE_MAP = {
            "predation": ["speed", "defense", "range"],
            "scarcity": ["efficiency", "rate"],
            "competition": ["strength", "efficiency"],
            "temperature": ["efficiency"],
        }
        
        # 【新增】植物专用压力映射
        PLANT_PRESSURE_MAP = {
            "drought": ["efficiency", "capacity", "resistance"],     # 干旱 → 提高效率/储水能力
            "light": ["efficiency", "rate", "density"],             # 光照变化 → 提高光合效率
            "nutrient": ["absorption", "efficiency"],                # 养分压力 → 提高吸收效率
            "herbivory": ["resistance", "production"],               # 食草压力 → 提高防御
            "competition": ["efficiency", "density", "rate"],        # 竞争 → 提高生长速度
            "temperature": ["resistance", "efficiency"],
        }
        
        PRESSURE_MAP = PLANT_PRESSURE_MAP if is_plant else ANIMAL_PRESSURE_MAP
        
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
                    delta = random.uniform(0.01, 0.05) * scaling_factor
                elif random.random() < 0.05: # 5% 概率随机波动 (中性漂移)
                    delta = random.uniform(-0.02, 0.02) * scaling_factor
                
                if delta != 0.0:
                    new_val = max(0.1, param_value + delta) # 保持为正数
                    params[param_name] = round(new_val, 3)
                    drifted = True
                    drift_score += abs(delta) * 2.0 # 器官变化权重较高
                    changes[f"{organ_data['type']}.{param_name}"] = f"{delta:+.3f}"
            
            if drifted:
                organ_data["parameters"] = params # 更新回对象
        
        return changes, drift_score
    
    def _apply_organ_progress_accumulation(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
        scaling_factor: float = 1.0,
    ) -> tuple[dict, float]:
        """器官进度累积：让发展中的器官逐渐成熟
        
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        
        # 计算环境压力强度（用于调整进度增益）
        pressure_intensity = sum(abs(p) for p in environment_pressure.values()) / max(1, len(environment_pressure))
        pressure_multiplier = 1.0 + min(pressure_intensity / 10.0, 0.5)  # 最多1.5倍速
        
        # 世代时间影响：繁殖快的物种进化快
        generation_time = species.morphology_stats.get("generation_time_days", 365)
        # 使用 scaling_factor 调整回合年数
        total_days = 500_000 * scaling_factor * 365
        generations = total_days / max(1.0, generation_time)
        # 世代加成：log10(代数) * 0.01
        generation_multiplier = 1.0 + math.log10(max(10, generations)) * 0.01
        
        for category, organ_data in species.organs.items():
            current_stage = organ_data.get("evolution_stage", 4)
            current_progress = organ_data.get("evolution_progress", 1.0)
            
            # 只处理未完善的器官（阶段1-3）
            if current_stage >= 4:
                continue
            
            # 基础进度增益（经过 scaling_factor 调整）
            # 基准: 0.02-0.06 per 500k years
            base_progress_gain = random.uniform(0.02, 0.06) * scaling_factor
            
            # 应用倍率
            actual_gain = base_progress_gain * pressure_multiplier * generation_multiplier
            
            # 添加随机性：有时进度停滞，有时快速突破
            if random.random() < 0.1:  # 10% 概率停滞
                actual_gain = 0
            elif random.random() < 0.05:  # 5% 概率快速突破
                actual_gain *= 2.0
            
            # 更新进度
            new_progress = current_progress + actual_gain
            
            # 检查是否达到下一阶段
            stage_thresholds = {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}
            next_stage = current_stage + 1
            threshold = stage_thresholds.get(next_stage, 1.0)
            
            if new_progress >= threshold and next_stage <= 4:
                # 升级到下一阶段
                organ_data["evolution_stage"] = next_stage
                organ_data["evolution_progress"] = new_progress
                organ_data["modified_turn"] = turn_index
                
                # 阶段2+开始具有功能
                if next_stage >= 2:
                    organ_data["is_active"] = True
                
                # 记录演化历史
                if "evolution_history" not in organ_data:
                    organ_data["evolution_history"] = []
                organ_data["evolution_history"].append({
                    "turn": turn_index,
                    "from_stage": current_stage,
                    "to_stage": next_stage,
                    "description": f"器官发育成熟度提升"
                })
                
                stage_names = {1: "原基", 2: "初级", 3: "功能化", 4: "完善"}
                organ_type = organ_data.get("type", category)
                changes[f"{organ_type}"] = f"阶段{current_stage}({stage_names.get(current_stage, '未知')})→{next_stage}({stage_names.get(next_stage, '完善')})"
                drift_score += 2.0  # 阶段升级是重大变化
                
                logger.info(
                    f"[器官发育] {species.common_name} {organ_type}: "
                    f"阶段{current_stage}→{next_stage} (进度{new_progress:.0%})"
                )
            else:
                # 只更新进度，未达到升级阈值
                organ_data["evolution_progress"] = new_progress
                if actual_gain > 0:
                    organ_type = organ_data.get("type", category)
                    logger.debug(
                        f"[器官发育] {species.common_name} {organ_type}: "
                        f"进度 {current_progress:.0%}→{new_progress:.0%}"
                    )
        
        return changes, drift_score

    def _apply_regressive_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
        force_mode: bool = False,
        scaling_factor: float = 1.0,
    ) -> tuple[dict, float]:
        """退化演化 (Use it or Lose it & Entropy)
        
        Args:
            species: 目标物种
            environment_pressure: 环境压力
            turn_index: 当前回合
            force_mode: 是否强制执行
            scaling_factor: 时间缩放因子
            
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        
        # A. 随机熵增退化 (Maintenance Cost)
        # 当总属性过高时，随机降低某些属性以模拟能量守恒
        # 概率受 scaling_factor 影响 (时间越长，发生熵增概率越高)
        entropy_prob = 0.1 * scaling_factor
        if force_mode or random.random() < entropy_prob: 
            # 选择一个较高的属性进行削弱
            high_traits = [k for k, v in species.abstract_traits.items() if v > 3.0]
            if high_traits:
                trait_to_regress = random.choice(high_traits)
                current_val = species.abstract_traits[trait_to_regress]
                # 削弱幅度：越高削弱越狠，受时间缩放影响
                delta = random.uniform(0.1, 0.4) * (current_val / 5.0) * scaling_factor
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
                delta = random.uniform(0.15, 0.25) * scaling_factor
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
                delta = random.uniform(0.1, 0.2) * scaling_factor
                new_value = max(0.0, current_movement - delta)
                species.abstract_traits["运动能力"] = round(new_value, 2)
                changes["运动能力"] = f"-{delta:.2f} (附着生活退化)"
                drift_score += delta
                logger.debug(f"[退化] {species.common_name} 运动能力 -{delta:.2f}")
                
                # 同时检查运动器官是否需要退化
                if "locomotion" in species.organs:
                    if species.organs["locomotion"].get("is_active", True):
                        # 概率使器官失活，受时间缩放影响
                        deactivate_prob = 0.3 * min(1.0, scaling_factor)
                        if random.random() < deactivate_prob:
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
                    regression_prob = min(0.5, turns_in_darkness * 0.01 * scaling_factor)  # 最多50%
                    
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
                    if random.random() < 0.4 * min(1.0, scaling_factor):
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
            
            if is_mismatched and random.random() < 0.2 * scaling_factor:
                delta = random.uniform(0.05, 0.15) * scaling_factor
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
        stream_callback: Callable[[str], Awaitable[None] | None] | None,
        time_config: dict = None,
    ) -> dict:
        """创建LLM驱动的适应性演化任务（非流式，更稳定）
        
        Args:
            species: 目标物种
            environment_pressure: 环境压力字典
            pressure_context: 压力描述上下文
            stream_callback: 流式回调函数（已停用）
            time_config: 时间配置 (years_per_turn, era_name 等)
            
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
        
        # 准备时间上下文
        era_name = "Unknown"
        years_per_turn = 500000
        evolution_guide = "Standard"
        
        if time_config:
            era_name = time_config.get("era_name", era_name)
            years_per_turn = time_config.get("years_per_turn", years_per_turn)
            evolution_guide = time_config.get("evolution_guide", evolution_guide)
        
        time_context = f"""
=== ⏳ 时间尺度上下文 (Chronos Flow) ===
当前地质年代：{era_name}
时间流逝速度：{years_per_turn:,} 年/回合
演化指导原则：{evolution_guide}
"""

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
            time_context=time_context,  # 注入时间上下文
        )
        
        # 【优化】使用带心跳的调用
        from ...ai.streaming_helper import acall_with_heartbeat
        
        try:
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="pressure_adaptation",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"LLM适应[{species.common_name[:8]}]",
                timeout=90,
                heartbeat_interval=2.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"[LLM适应] {species.common_name} 超时（90秒）")
            return {}
        except Exception as e:
            logger.error(f"[LLM适应] 调用失败: {e}")
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
