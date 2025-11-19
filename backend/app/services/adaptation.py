"""物种适应服务：渐进演化和退化机制

实现P0和P1改进：
- P0: 退化机制（用进废退）
- P1: 渐进演化（非分化的逐代适应）
- P2: 描述同步（当数值漂移过大时重写描述）
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Sequence

from ..models.species import Species
from .trait_config import TraitConfig
from ..ai.model_router import ModelRouter
from ..ai.prompts.species import SPECIES_PROMPTS

logger = logging.getLogger(__name__)


class AdaptationService:
    """处理物种的渐进演化和器官退化"""
    
    def __init__(self, router: ModelRouter):
        self.router = router
        self.gradual_evolution_rate = 0.15
        self.regression_check_turns = 5
        self.drift_threshold = 3.0  # 累积漂移超过此值触发描述更新
        
    async def apply_adaptations_async(
        self,
        species_list: Sequence[Species],
        environment_pressure: dict[str, float],
        turn_index: int,
    ) -> list[dict]:
        """应用适应性变化（渐进演化+退化+描述同步）(Async)
        
        Args:
            species_list: 所有存活物种
            environment_pressure: 当前环境压力
            turn_index: 当前回合数
            
        Returns:
            变化记录列表
        """
        adaptation_events = []
        description_update_tasks = []
        species_to_update = []
        
        for species in species_list:
            # 1. 渐进演化
            gradual_changes, drift_score = self._apply_gradual_evolution(
                species, environment_pressure, turn_index
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
            
            # 3. 退化检查
            if turn_index % self.regression_check_turns == 0:
                regression_changes, reg_drift = self._apply_regressive_evolution(
                    species, environment_pressure, turn_index
                )
                species.accumulated_adaptation_score += reg_drift
                
                if regression_changes:
                    adaptation_events.append({
                        "lineage_code": species.lineage_code,
                        "common_name": species.common_name,
                        "changes": regression_changes,
                        "type": "regression"
                    })
            
            # 3. 检查是否需要更新描述
            # 只有 Critical 或 Focus 物种，且漂移超过阈值时才更新（节省Token）
            # 或者每隔 20 回合强制检查一次
            should_update_desc = (
                species.accumulated_adaptation_score >= self.drift_threshold
                and (turn_index - species.last_description_update_turn) > 10
            )
            
            if should_update_desc:
                # 准备上下文
                task = self._create_description_update_task(species, gradual_changes)
                description_update_tasks.append(task)
                species_to_update.append(species)
                
                # 重置分数
                species.accumulated_adaptation_score = 0.0
                species.last_description_update_turn = turn_index

        # 并发执行描述更新
        if description_update_tasks:
            logger.info(f"[适应性] 触发 {len(description_update_tasks)} 个物种的描述更新...")
            results = await asyncio.gather(*description_update_tasks, return_exceptions=True)
            
            for species, res in zip(species_to_update, results):
                if isinstance(res, Exception):
                    logger.error(f"[描述更新失败] {species.common_name}: {res}")
                    continue
                
                new_desc = res.get("new_description")
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

        return adaptation_events
    
    def apply_adaptations(self, *args, **kwargs):
        """同步方法已废弃"""
        raise NotImplementedError("Use apply_adaptations_async instead")

    def _create_description_update_task(self, species: Species, recent_changes: dict):
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
            trait_diffs=trait_diffs
        )
        
        return self.router.acall_capability(
            capability="narrative", # 使用 narrative 能力通常更便宜或更擅长文本
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

    def _apply_gradual_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
    ) -> tuple[dict, float]:
        """渐进演化
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        limits = TraitConfig.get_trophic_limits(species.trophic_level)
        current_total = sum(species.abstract_traits.values())
        
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
                delta = random.uniform(0.1, 0.3)
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
    ) -> tuple[dict, float]:
        """退化演化
        Returns: (changes_dict, drift_score)
        """
        changes = {}
        drift_score = 0.0
        
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
