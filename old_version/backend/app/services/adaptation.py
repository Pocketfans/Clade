"""物种适应服务：渐进演化和退化机制

实现P0和P1改进：
- P0: 退化机制（用进废退）
- P1: 渐进演化（非分化的逐代适应）
"""
from __future__ import annotations

import logging
import random
from typing import Sequence

from ..models.species import Species
from .trait_config import TraitConfig

logger = logging.getLogger(__name__)


class AdaptationService:
    """处理物种的渐进演化和器官退化"""
    
    def __init__(self):
        self.gradual_evolution_rate = 0.15
        self.regression_check_turns = 5
        
    def apply_adaptations(
        self,
        species_list: Sequence[Species],
        environment_pressure: dict[str, float],
        turn_index: int,
    ) -> list[dict]:
        """应用适应性变化（渐进演化+退化）
        
        Args:
            species_list: 所有存活物种
            environment_pressure: 当前环境压力 {"temperature": 8.0, "drought": 5.0, ...}
            turn_index: 当前回合数
            
        Returns:
            变化记录列表 [{"lineage_code": "A1", "changes": {...}, "type": "gradual/regression"}]
        """
        adaptation_events = []
        
        for species in species_list:
            # 1. 渐进演化（每回合都可能发生）
            gradual_changes = self._apply_gradual_evolution(
                species, environment_pressure, turn_index
            )
            if gradual_changes:
                adaptation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "changes": gradual_changes,
                    "type": "gradual_evolution"
                })
            
            # 2. 退化检查（每5回合检查一次）
            if turn_index % self.regression_check_turns == 0:
                regression_changes = self._apply_regressive_evolution(
                    species, environment_pressure, turn_index
                )
                if regression_changes:
                    adaptation_events.append({
                        "lineage_code": species.lineage_code,
                        "common_name": species.common_name,
                        "changes": regression_changes,
                        "type": "regression"
                    })
        
        return adaptation_events
    
    def _apply_gradual_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
    ) -> dict:
        """渐进演化：动态处理所有trait对压力的响应，考虑营养级限制"""
        changes = {}
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
                    logger.debug(f"[渐进演化] {species.common_name} {trait_name} +{delta:.2f} (压力{pressure_value:.1f})")
                    
                    if trait_name in ["耐热性", "耐极寒"]:
                        species.morphology_stats["metabolic_rate"] = species.morphology_stats.get("metabolic_rate", 1.0) * 1.02
        
        return changes
    
    def _apply_regressive_evolution(
        self,
        species: Species,
        environment_pressure: dict[str, float],
        turn_index: int,
    ) -> dict:
        """退化演化：长期不使用的能力会逐渐退化（用进废退）
        """
        changes = {}
        
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
                logger.debug(f"[退化] {species.common_name} 运动能力 -{delta:.2f}")
                
                # 同时检查运动器官是否需要退化
                if "locomotion" in species.organs:
                    if species.organs["locomotion"].get("is_active", True):
                        # 30%概率使器官失活
                        if random.random() < 0.3:
                            species.organs["locomotion"]["is_active"] = False
                            species.organs["locomotion"]["deactivated_turn"] = turn_index
                            changes["器官退化"] = f"{species.organs['locomotion']['type']}失活"
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
                logger.debug(f"[退化] {species.common_name} {trait_name} -{delta:.2f}")
        
        return changes
    
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

