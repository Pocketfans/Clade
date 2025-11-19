from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from ..models.species import Species
from ..services.niche import NicheMetrics

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MortalityResult:
    species: Species
    initial_population: int
    deaths: int
    survivors: int
    death_rate: float
    notes: list[str]
    niche_overlap: float
    resource_pressure: float
    is_background: bool
    tier: str
    grazing_pressure: float = 0.0  # 新增：被捕食压力(T1受T2)
    predation_pressure: float = 0.0  # 新增：被捕食压力(T2受T3+)


class MortalityEngine:
    """Rule-driven mortality calculator for bulk species."""

    def __init__(self, batch_limit: int = 50) -> None:
        self.batch_limit = batch_limit

    def evaluate(
        self,
        species_batch: Iterable[Species],
        pressure_modifiers: dict[str, float],
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        trophic_interactions: dict[str, float] = None,  # 新增参数：营养级互动数据
    ) -> list[MortalityResult]:
        """计算物种死亡率，考虑体型、繁殖策略、生态位和营养级互动。
        
        引入营养级互动(Scheme B)：
        - T1 (生产者): 承受 T2 的啃食压力 (grazing_pressure)
        - T2+ (消费者): 承受 T(n+1) 的捕食压力 (predation_pressure)
        - 资源限制: T1 依赖 Abiotic Resources，T2+ 依赖 Prey Biomass
        """
        if trophic_interactions is None:
            trophic_interactions = {}
            
        logger.debug(f"Evaluating mortality for {len(species_batch)} species in tier {tier}")
            
        results: list[MortalityResult] = []
        for sp in species_batch:
            base_sensitivity = sp.hidden_traits.get("environment_sensitivity", 0.5)
            pressure_score = sum(pressure_modifiers.values()) / (len(pressure_modifiers) or 1)
            metrics = niche_metrics.get(
                sp.lineage_code, NicheMetrics(overlap=0.0, saturation=0.0)
            )
            
            # 获取营养级
            trophic_level = sp.trophic_level
            
            # 获取被捕食压力（来自上层营养级）
            # key格式: "predation_on_{lineage_code}"
            predation_key = f"predation_on_{sp.lineage_code}"
            predation_pressure = trophic_interactions.get(predation_key, 0.0)
            
            # 区分 T1 和 T2+ 的压力来源
            if trophic_level < 2.0:
                # T1 生产者：主要受环境和啃食影响
                grazing_pressure = predation_pressure  # T1的被捕食即为啃食
                predation_effect = 0.0 # 已经在grazing体现
                # T1 资源压力主要来自空间/阳光竞争 (Saturation)
                resource_factor = min(metrics.saturation * 0.3, 0.5) 
            else:
                # T2+ 消费者：受食物限制(resource)和捕食(predation)影响
                grazing_pressure = 0.0
                predation_effect = min(predation_pressure * 0.4, 0.6) # 捕食致死
                
                # 消费者资源压力 = 生态位饱和度 + 食物短缺(Scarcity)
                # 从 trophic_interactions 获取食物短缺系数
                scarcity = 0.0
                if trophic_level < 3.0: # T2
                    scarcity = trophic_interactions.get("t2_scarcity", 0.0)
                else: # T3+
                    scarcity = trophic_interactions.get("t3_scarcity", 0.0)
                
                # 综合资源压力：饱和度(空间/同类竞争) + 短缺(猎物不足)
                # 饱和度通常 0-2.0，短缺 0-2.0
                # 取较大值作为主要限制因素
                resource_factor = min(max(metrics.saturation * 0.4, scarcity), 0.8) 

            
            # 获取体型信息（cm）
            body_size = sp.morphology_stats.get("body_length_cm", 0.01)
            
            # 体型修正因子（小型生物抗性更强）
            if body_size < 0.1:  # 微米级（0.1cm = 1mm）
                size_resistance = 0.7  # 微生物有70%的抗性
            elif body_size < 1.0:  # 毫米到厘米级
                size_resistance = 0.5  # 小型生物有50%的抗性
            elif body_size < 10.0:  # 厘米级
                size_resistance = 0.3
            else:  # 大型生物
                size_resistance = 0.1
            
            # 繁殖策略修正（从种群数量推断）
            population = int(sp.morphology_stats.get("population", 0) or 0)
            if population > 500_000:  # r策略物种（高繁殖率）
                repro_resistance = 0.3
            elif population > 100_000:
                repro_resistance = 0.2
            else:  # K策略物种（低繁殖率）
                repro_resistance = 0.1
            
            # P1-4: 根据物种的环境适应性属性调整压力敏感度
            # 获取适应性属性（1-10，数值越高抗性越强）
            cold_resistance = sp.abstract_traits.get("耐寒性", 5) / 10.0  # 转为0-1
            heat_resistance = sp.abstract_traits.get("耐热性", 5) / 10.0
            drought_resistance = sp.abstract_traits.get("耐旱性", 5) / 10.0
            salinity_resistance = sp.abstract_traits.get("耐盐性", 5) / 10.0
            
            # 根据压力类型应用相应的抗性
            adjusted_sensitivity = base_sensitivity
            if "temperature" in pressure_modifiers:
                # 温度压力：使用耐寒性和耐热性的平均值
                temp_resistance = (cold_resistance + heat_resistance) / 2
                adjusted_sensitivity *= (1.0 - temp_resistance * 0.4)  # 最多降低40%敏感度
            if "drought" in pressure_modifiers:
                adjusted_sensitivity *= (1.0 - drought_resistance * 0.5)  # 最多降低50%敏感度
            if "flood" in pressure_modifiers:
                adjusted_sensitivity *= (1.0 - salinity_resistance * 0.3)  # 洪水可能改变盐度
            
            # 基础死亡率计算
            # 微生物虽然有抗性，但在强压力下仍会有显著死亡
            pressure_factor = (pressure_score / 20) * adjusted_sensitivity  # 使用调整后的敏感度
            overlap_factor = max(metrics.overlap, 0.0) * 0.5  # P1-3: 从0.3提高到0.5，增强竞争压力
            
            # 整合所有压力因子 (Scheme B)
            # Base Mortality = Environment + Competition + Resource + Predation(Grazing)
            base_mortality = (
                pressure_factor + 
                overlap_factor + 
                resource_factor + 
                grazing_pressure + 
                predation_effect
            )
            
            # 应用抗性修正（抗性降低死亡，但不能完全免疫）
            adjusted = base_mortality * (1.0 - size_resistance * 0.6) * (1.0 - repro_resistance * 0.5)
            
            # 【问题1-A】演化滞后debuff：分化后的亲代额外死亡率
            offspring_penalty = self._calculate_offspring_penalty(
                sp, species_batch, tier
            )
            adjusted += offspring_penalty
            
            # 【问题1-C】同属竞争：同谱系前缀物种间的竞争压力
            sibling_competition = self._calculate_sibling_competition(
                sp, species_batch, metrics.overlap
            )
            adjusted += sibling_competition
            
            # P3-4: 扩大死亡率范围，允许濒危物种出现
            # 最低3%（自然死亡），最高75%（濒危物种，有救赎演化机会）
            # 10-45%触发分化，45-60%高压力适应，60-75%濒危状态
            adjusted = min(0.75, max(0.03, adjusted))
            
            deaths = int(population * adjusted)
            survivors = max(population - deaths, 0)
            
            # 生成规则计算的死亡率分析文本（增强版，包含属性详情）
            analysis_parts = []
            if pressure_score > 3:
                analysis_parts.append(f"环境压力较高({pressure_score:.1f}/10)")
            if metrics.overlap > 0.3:
                analysis_parts.append(f"生态位竞争明显(重叠度{metrics.overlap:.2f})")
            if metrics.saturation > 1.0:
                analysis_parts.append(f"种群饱和(S={metrics.saturation:.2f})")
            if resource_factor > 0.2 and trophic_level >= 2.0:
                # 对于消费者，如果资源因子高，可能是食物短缺
                scarcity = trophic_interactions.get("t2_scarcity" if trophic_level < 3 else "t3_scarcity", 0.0)
                if scarcity > 0.2:
                    analysis_parts.append(f"食物短缺({scarcity:.1%})")
            if grazing_pressure > 0.1:
                analysis_parts.append(f"承受啃食压力({grazing_pressure:.1%})")
            if predation_effect > 0.1:
                analysis_parts.append(f"遭捕食({predation_effect:.1%})")
            if body_size < 0.01:
                analysis_parts.append("体型极小，对环境变化敏感")
            elif body_size > 100:
                analysis_parts.append("体型巨大，具有一定抗压能力")
            
            # 增加：显示关键属性值（当存在对应压力时）
            attr_info = []
            if "temperature" in pressure_modifiers:
                attr_info.append(f"耐寒{cold_resistance:.0f}/耐热{heat_resistance:.0f}")
            if "drought" in pressure_modifiers:
                attr_info.append(f"耐旱{drought_resistance:.0f}")
            if "flood" in pressure_modifiers or "volcano" in pressure_modifiers:
                attr_info.append(f"耐盐{salinity_resistance:.0f}")
            
            if attr_info:
                analysis_parts.append(f"属性[{'/'.join(attr_info)}]")
            
            if analysis_parts:
                mortality_reason = f"{sp.common_name}本回合死亡率{adjusted:.1%}：" + "；".join(analysis_parts) + "。"
            else:
                mortality_reason = f"{sp.common_name}死亡率{adjusted:.1%}，种群状况稳定，未受明显环境压力影响。"
            
            if adjusted > 0.5 and not extinction_triggered:
                logger.info(f"[高死亡率警告] {sp.common_name}: {adjusted:.1%} (原因: {mortality_reason})")
            
            notes = [mortality_reason]
            
            results.append(
                MortalityResult(
                    species=sp,
                    initial_population=population,
                    deaths=deaths,
                    survivors=survivors,
                    death_rate=adjusted,
                    notes=notes,
                    niche_overlap=metrics.overlap,
                    resource_pressure=metrics.saturation,
                    is_background=sp.is_background,
                    tier=tier,
                    grazing_pressure=grazing_pressure,  # 记录新字段
                    predation_pressure=predation_effect # 记录新字段
                )
            )
        return results
    
    def _calculate_offspring_penalty(
        self, species: Species, all_species: Sequence[Species], tier: str
    ) -> float:
        """计算演化滞后惩罚（亲代被子代竞争淘汰）
        
        检查该物种是否有近期分化出的子代，如果有则施加衰退惩罚。
        惩罚随时间衰减：第1回合后15%，第2回合10%，第3回合5%。
        
        Args:
            species: 目标物种
            all_species: 所有物种列表
            tier: 物种层级
            
        Returns:
            额外死亡率惩罚（0-0.15）
        """
        # 只对非background物种计算（background已经在低关注度）
        if tier == "background":
            return 0.0
        
        # 查找以该物种为parent的子代
        offspring = [
            s for s in all_species 
            if s.parent_code == species.lineage_code and s.status == "alive"
        ]
        
        if not offspring:
            return 0.0
        
        # 计算最年轻子代的年龄
        youngest_offspring = max(offspring, key=lambda s: s.created_turn)
        turns_since_speciation = max(0, youngest_offspring.created_turn - species.created_turn)
        
        # 衰减惩罚：0回合(刚分化)15%，1回合10%，2回合5%，3回合后0%
        if turns_since_speciation == 0:
            penalty = 0.15
        elif turns_since_speciation == 1:
            penalty = 0.10
        elif turns_since_speciation == 2:
            penalty = 0.05
        else:
            penalty = 0.0
        
        return penalty
    
    def _calculate_sibling_competition(
        self, species: Species, all_species: Sequence[Species], base_overlap: float
    ) -> float:
        """计算同属物种竞争压力
        
        同谱系前缀的物种（如A1与A1a1，A1a1与A1a1a1）之间存在更激烈的竞争。
        子代对亲代的竞争压力更大（体现演化优势）。
        
        Args:
            species: 目标物种
            all_species: 所有物种列表
            base_overlap: 基础生态位重叠度
            
        Returns:
            额外死亡率（0-0.25）
        """
        lineage = species.lineage_code
        population = int(species.morphology_stats.get("population", 0) or 0)
        
        if population == 0:
            return 0.0
        
        # 提取谱系前缀（去掉最后的分化标记）
        # 例如：A1a1a2 -> A1a1, B1 -> B1
        if len(lineage) > 2:
            prefix = lineage[:-2]
        else:
            prefix = lineage
        
        # 找所有同属物种（共享前缀）
        siblings = [
            s for s in all_species
            if s.lineage_code.startswith(prefix) 
            and s.lineage_code != lineage
            and s.status == "alive"
        ]
        
        if not siblings:
            return 0.0
        
        # 计算竞争强度
        total_competition = 0.0
        
        for sibling in siblings:
            sibling_pop = int(sibling.morphology_stats.get("population", 0) or 0)
            
            # 子代对亲代的压制（子代created_turn更大）
            if sibling.created_turn > species.created_turn:
                # 子代相对种群规模
                pop_ratio = sibling_pop / max(population, 1)
                # 竞争强度 = 生态位重叠 × 种群比例 × 压制系数
                competition = base_overlap * min(pop_ratio, 2.0) * 0.15  # 最多15%
                total_competition += competition
        
        # 上限25%
        return min(total_competition, 0.25)
