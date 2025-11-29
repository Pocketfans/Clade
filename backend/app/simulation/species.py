from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from ..models.species import Species
from ..services.species.niche import NicheMetrics
from ..core.config import get_settings

logger = logging.getLogger(__name__)

# 获取配置
_settings = get_settings()


# ============ 向量化辅助函数 ============

def _extract_species_arrays(species_list: list[Species], niche_metrics: dict[str, NicheMetrics]) -> dict[str, np.ndarray]:
    """批量提取物种属性为NumPy数组，用于向量化计算。
    
    Returns:
        包含各属性数组的字典
    """
    n = len(species_list)
    
    # 预分配数组
    base_sensitivity = np.zeros(n)
    trophic_level = np.zeros(n)
    body_size = np.zeros(n)
    population = np.zeros(n, dtype=np.int64)
    generation_time = np.zeros(n)
    
    # 抗性属性
    cold_resistance = np.zeros(n)
    heat_resistance = np.zeros(n)
    drought_resistance = np.zeros(n)
    salinity_resistance = np.zeros(n)
    
    # 生态位指标
    overlap = np.zeros(n)
    saturation = np.zeros(n)
    
    # 干预状态
    is_protected = np.zeros(n, dtype=bool)
    protection_turns = np.zeros(n, dtype=np.int32)
    is_suppressed = np.zeros(n, dtype=bool)
    suppression_turns = np.zeros(n, dtype=np.int32)
    
    # 批量提取
    for i, sp in enumerate(species_list):
        base_sensitivity[i] = sp.hidden_traits.get("environment_sensitivity", 0.5)
        trophic_level[i] = sp.trophic_level
        body_size[i] = sp.morphology_stats.get("body_length_cm", 0.01)
        population[i] = int(sp.morphology_stats.get("population", 0) or 0)
        generation_time[i] = sp.morphology_stats.get("generation_time_days", 365)
        
        cold_resistance[i] = sp.abstract_traits.get("耐寒性", 5) / 10.0
        heat_resistance[i] = sp.abstract_traits.get("耐热性", 5) / 10.0
        drought_resistance[i] = sp.abstract_traits.get("耐旱性", 5) / 10.0
        salinity_resistance[i] = sp.abstract_traits.get("耐盐性", 5) / 10.0
        
        metrics = niche_metrics.get(sp.lineage_code, NicheMetrics(overlap=0.0, saturation=0.0))
        overlap[i] = metrics.overlap
        saturation[i] = metrics.saturation
        
        is_protected[i] = getattr(sp, 'is_protected', False) or False
        protection_turns[i] = getattr(sp, 'protection_turns', 0) or 0
        is_suppressed[i] = getattr(sp, 'is_suppressed', False) or False
        suppression_turns[i] = getattr(sp, 'suppression_turns', 0) or 0
    
    return {
        'base_sensitivity': base_sensitivity,
        'trophic_level': trophic_level,
        'body_size': body_size,
        'population': population,
        'generation_time': generation_time,
        'cold_resistance': cold_resistance,
        'heat_resistance': heat_resistance,
        'drought_resistance': drought_resistance,
        'salinity_resistance': salinity_resistance,
        'overlap': overlap,
        'saturation': saturation,
        'is_protected': is_protected,
        'protection_turns': protection_turns,
        'is_suppressed': is_suppressed,
        'suppression_turns': suppression_turns,
    }


def _vectorized_size_resistance(body_size: np.ndarray) -> np.ndarray:
    """向量化计算体型抗性"""
    resistance = np.ones_like(body_size) * 0.1  # 默认大型生物
    resistance = np.where(body_size < 10.0, 0.3, resistance)
    resistance = np.where(body_size < 1.0, 0.5, resistance)
    resistance = np.where(body_size < 0.1, 0.7, resistance)
    return resistance


def _vectorized_repro_resistance(population: np.ndarray) -> np.ndarray:
    """向量化计算繁殖策略抗性"""
    resistance = np.ones_like(population, dtype=float) * 0.1  # 默认K策略
    resistance = np.where(population > 100_000, 0.2, resistance)
    resistance = np.where(population > 500_000, 0.3, resistance)
    return resistance


def _vectorized_generational_mortality(
    base_risk: np.ndarray,
    num_generations: np.ndarray,
    size_resistance: np.ndarray,
    repro_resistance: np.ndarray
) -> np.ndarray:
    """向量化计算世代累积死亡率"""
    num_generations = np.maximum(1.0, num_generations)
    
    # 每代死亡风险
    per_gen_risk = base_risk / num_generations
    per_gen_survival = np.clip(1.0 - per_gen_risk, 0.0, 1.0)
    
    # 累积存活率（使用对数变换避免数值问题）
    # 处理边界情况
    cumulative_survival = np.ones_like(per_gen_survival)
    
    # 正常情况：0 < survival < 1
    normal_mask = (per_gen_survival > 0) & (per_gen_survival < 1.0)
    log_survival = np.zeros_like(per_gen_survival)
    log_survival[normal_mask] = np.log(per_gen_survival[normal_mask])
    cumulative_log = num_generations * log_survival
    
    # 防止下溢
    cumulative_log = np.maximum(cumulative_log, -700)
    cumulative_survival = np.where(normal_mask, np.exp(cumulative_log), cumulative_survival)
    cumulative_survival = np.where(per_gen_survival <= 0, 0.0, cumulative_survival)
    
    # 转换为死亡率
    cumulative_mortality = 1.0 - cumulative_survival
    
    # 应用抗性修正
    resistance_factor = (1.0 - size_resistance * 0.6) * (1.0 - repro_resistance * 0.5)
    adjusted = cumulative_mortality * resistance_factor
    
    return np.clip(adjusted, 0.0, 0.98)


def _vectorized_density_penalty(total_count: int, trophic_levels: np.ndarray) -> np.ndarray:
    """向量化计算物种密度惩罚（达尔文式淘汰强化版）
    
    【核心理念】物种越多，竞争越激烈，淘汰压力越大
    这确保了"大量分化"后会有"大量淘汰"，筛选出最适者
    """
    n = len(trophic_levels)
    
    # 【强化】降低触发阈值从30到20
    if total_count <= 20:
        return np.zeros(n)
    
    # 【强化】增加惩罚力度
    if total_count <= 40:
        # 20-40种：每多5种增加3%（原10种增加2%）
        penalty = (total_count - 20) / 5 * 0.03
    elif total_count <= 70:
        # 40-70种：每多5种增加4%
        penalty = 0.12 + (total_count - 40) / 5 * 0.04
    elif total_count <= 100:
        # 70-100种：每多5种增加5%
        penalty = 0.36 + (total_count - 70) / 5 * 0.05
    else:
        # >100种：每多5种增加6%（生态系统超载）
        penalty = 0.66 + (total_count - 100) / 5 * 0.06
    
    # 营养级修正（高营养级物种对密度更敏感）
    multiplier = np.ones(n)
    multiplier = np.where(trophic_levels < 2.0, 0.6, multiplier)  # T1: 生产者
    multiplier = np.where((trophic_levels >= 2.0) & (trophic_levels < 3.0), 1.0, multiplier)  # T2
    multiplier = np.where((trophic_levels >= 3.0) & (trophic_levels < 4.0), 1.3, multiplier)  # T3
    multiplier = np.where((trophic_levels >= 4.0) & (trophic_levels < 5.0), 1.7, multiplier)  # T4
    multiplier = np.where(trophic_levels >= 5.0, 2.2, multiplier)  # T5: 顶级捕食者
    
    # 【强化】上限从0.30提高到0.45
    return np.minimum(penalty * multiplier, 0.45)


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
    
    # 新增：AI评估结果字段
    ai_status_eval: object | None = None  # SpeciesStatusEval
    ai_narrative: str = ""
    ai_headline: str = ""
    ai_mood: str = ""
    death_causes: str = ""  # 主要死因描述
    
    # 【新增v3】繁殖数据（在engine.py计算完繁殖后填充）
    births: int = 0  # 本回合新出生的个体数量
    final_population: int = 0  # 回合结束时的最终种群


class MortalityEngine:
    """Rule-driven mortality calculator for bulk species.
    
    【性能优化】使用NumPy向量化计算核心死亡率，显著提升大量物种时的性能。
    """

    def __init__(self, batch_limit: int = 50) -> None:
        self.batch_limit = batch_limit

    def evaluate(
        self,
        species_batch: Iterable[Species],
        pressure_modifiers: dict[str, float],
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        trophic_interactions: dict[str, float] = None,
        extinct_codes: set[str] = None,
    ) -> list[MortalityResult]:
        """计算物种死亡率（向量化优化版）。
        
        使用NumPy批量计算核心死亡率因子，然后逐个处理需要物种间交互的部分。
        """
        if trophic_interactions is None:
            trophic_interactions = {}
        if extinct_codes is None:
            extinct_codes = set()
        
        # 转换为列表以便多次迭代和索引
        species_list = list(species_batch)
        n = len(species_list)
        
        if n == 0:
            return []
        
        logger.debug(f"Evaluating mortality for {n} species in tier {tier} (vectorized)")
        
        # ============ 阶段1: 批量提取属性 ============
        arrays = _extract_species_arrays(species_list, niche_metrics)
        
        # ============ 阶段2: 向量化计算核心死亡率 ============
        # 【修复】正向修饰符不应计入压力分数
        # 这些修饰符表示有利条件，不应增加死亡率
        positive_modifiers = {
            'resource_boost', 'productivity', 'competition',  # 资源繁盛期
            'habitat_expansion', 'regeneration_opportunity',   # 中性/正向变化
            'metabolic_boost', 'body_size_potential',          # 高氧环境优势
            'oxygen', 'freshwater_input', 'nutrient_redistribution',
            'upwelling_change', 'sea_level', 'seasonality', 'humidity',
            'continental_shelf_exposure'
        }
        # 只累加负面压力（正值且非正向修饰符）
        negative_pressure_sum = sum(
            max(0, v) for k, v in pressure_modifiers.items() 
            if k not in positive_modifiers
        )
        pressure_count = len([k for k in pressure_modifiers if k not in positive_modifiers]) or 1
        pressure_score = negative_pressure_sum / pressure_count
        
        # 计算调整后的敏感度
        adjusted_sensitivity = arrays['base_sensitivity'].copy()
        if "temperature" in pressure_modifiers:
            temp_resistance = (arrays['cold_resistance'] + arrays['heat_resistance']) / 2
            adjusted_sensitivity *= (1.0 - temp_resistance * 0.4)
        if "drought" in pressure_modifiers:
            adjusted_sensitivity *= (1.0 - arrays['drought_resistance'] * 0.5)
        if "flood" in pressure_modifiers:
            adjusted_sensitivity *= (1.0 - arrays['salinity_resistance'] * 0.3)
        
        # 压力因子和竞争因子
        # 【强化v2】大幅提高压力影响系数，确保高强度压力有明显效果
        # 10级压力应该产生显著死亡率（~40-60%基础）
        pressure_factor = (pressure_score / 12) * adjusted_sensitivity  # 从/25改为/12，提升2倍多
        overlap_factor = np.maximum(arrays['overlap'], 0.0) * 0.55  # 从0.4提高到0.55
        
        # 【新增】灾难类压力直接死亡率加成
        # 火山、地震、极端天气等灾难类型需要更高的直接死亡率
        disaster_modifiers = {
            'volcano': 0.08,        # 火山喷发：每级+8%死亡率
            'volcanic': 0.08,       # 同上（兼容两种写法）
            'mortality_spike': 0.10, # 直接死亡率事件：每级+10%
            'sulfide': 0.12,        # 硫化事件：每级+12%（剧毒）
            'toxin_level': 0.06,    # 毒素：每级+6%
            'wildfire': 0.07,       # 野火：每级+7%
        }
        disaster_mortality = np.zeros(n)
        for modifier_key, rate_per_level in disaster_modifiers.items():
            modifier_value = pressure_modifiers.get(modifier_key, 0.0)
            if modifier_value > 0:
                # 灾难死亡率 = 修饰符值 × 每级死亡率 × (1 - 相关抗性)
                # 对于火山，使用耐热性作为部分抗性
                if modifier_key in ('volcano', 'volcanic', 'wildfire'):
                    resistance = arrays['heat_resistance'] * 0.3
                elif modifier_key in ('sulfide', 'toxin_level'):
                    resistance = arrays['salinity_resistance'] * 0.2  # 化学抗性近似
                else:
                    resistance = 0.0
                disaster_mortality += modifier_value * rate_per_level * (1.0 - resistance)
        
        # 营养级相关压力（需要逐个处理因为有条件分支）
        grazing_pressure = np.zeros(n)
        predation_effect = np.zeros(n)
        resource_factor = np.zeros(n)
        
        for i, sp in enumerate(species_list):
            predation_key = f"predation_on_{sp.lineage_code}"
            pred_pressure = trophic_interactions.get(predation_key, 0.0)
            region_label = self._resolve_region_label(sp)
            
            if arrays['trophic_level'][i] < 2.0:
                # T1 生产者
                grazing_pressure[i] = pred_pressure
                resource_factor[i] = min(arrays['saturation'][i] * 0.3, 0.5)
            else:
                # T2+ 消费者
                predation_effect[i] = min(pred_pressure * 0.3, 0.5)
                
                # 根据营养级选择对应的稀缺性压力
                # T2: 受T1（生产者）数量影响
                # T3: 受T2（草食动物）数量影响
                # T4: 受T3（小型捕食者）数量影响
                # T5: 受T4（中型捕食者）数量影响
                t_level = arrays['trophic_level'][i]
                if t_level < 3.0:
                    # T2: 初级消费者
                    key = f"t2_scarcity_{region_label}"
                    scarcity = trophic_interactions.get(key, trophic_interactions.get("t2_scarcity", 0.0))
                elif t_level < 4.0:
                    # T3: 次级消费者
                    key = f"t3_scarcity_{region_label}"
                    scarcity = trophic_interactions.get(key, trophic_interactions.get("t3_scarcity", 0.0))
                elif t_level < 5.0:
                    # T4: 三级消费者
                    key = f"t4_scarcity_{region_label}"
                    scarcity = trophic_interactions.get(key, trophic_interactions.get("t4_scarcity", 0.0))
                else:
                    # T5: 顶级捕食者
                    key = f"t5_scarcity_{region_label}"
                    scarcity = trophic_interactions.get(key, trophic_interactions.get("t5_scarcity", 0.0))
                
                # 资源因子 = max(饱和度影响, 食物稀缺影响)
                # 【调整】缓和稀缺性的影响，避免第一回合就崩溃
                # scarcity = 2.0（最大）时，resource_factor = 0.6
                saturation_effect = arrays['saturation'][i] * 0.3
                scarcity_effect = scarcity * 0.30  # 稀缺性最大影响 2.0 * 0.30 = 0.6
                resource_factor[i] = min(max(saturation_effect, scarcity_effect), 0.6)
        
        # 向量化计算复合存活率
        # 每个因子都有上限，防止单一因子导致100%死亡
        # 但多个因子叠加可以导致极高死亡率，实现"大量淘汰"
        survival_pressure = 1.0 - np.minimum(0.8, pressure_factor)
        survival_competition = 1.0 - np.minimum(0.70, overlap_factor)  # 从0.6提高到0.70
        # 【调整】资源/食物稀缺上限从0.85降到0.65，避免过早崩溃
        survival_resource = 1.0 - np.minimum(0.65, resource_factor)
        survival_grazing = 1.0 - np.minimum(0.7, grazing_pressure)
        survival_predation = 1.0 - np.minimum(0.7, predation_effect)
        # 【新增】灾难存活率（火山、毒气等直接杀伤）
        survival_disaster = 1.0 - np.minimum(0.85, disaster_mortality)
        
        compound_survival = (
            survival_pressure * 
            survival_competition * 
            survival_resource * 
            survival_grazing * 
            survival_predation *
            survival_disaster  # 新增灾难因子
        )
        
        base_mortality = 1.0 - compound_survival
        
        # ============ 阶段3: 向量化世代累积死亡率 ============
        size_resistance = _vectorized_size_resistance(arrays['body_size'])
        repro_resistance = _vectorized_repro_resistance(arrays['population'])
        
        if _settings.enable_generational_mortality:
            num_generations = (_settings.turn_years * 365) / np.maximum(1.0, arrays['generation_time'])
            adjusted = _vectorized_generational_mortality(
                base_mortality, num_generations, size_resistance, repro_resistance
            )
        else:
            adjusted = base_mortality * (1.0 - size_resistance * 0.6) * (1.0 - repro_resistance * 0.5)
        
        # ============ 阶段4: 向量化密度惩罚 ============
        density_penalty = _vectorized_density_penalty(n, arrays['trophic_level'])
        adjusted = adjusted + density_penalty
        
        # ============ 阶段5: 向量化干预修正 ============
        # 保护状态
        protected_mask = arrays['is_protected'] & (arrays['protection_turns'] > 0)
        adjusted = np.where(protected_mask, adjusted * 0.5, adjusted)
        
        # 压制状态
        suppressed_mask = arrays['is_suppressed'] & (arrays['suppression_turns'] > 0)
        adjusted = np.where(suppressed_mask, np.minimum(0.95, adjusted + 0.30), adjusted)
        
        # ============ 阶段6: 逐个处理需要物种间交互的部分 ============
        results: list[MortalityResult] = []
        
        for i, sp in enumerate(species_list):
            adj = adjusted[i]
            
            # 演化滞后惩罚（需要查找子代）
            offspring_penalty = self._calculate_offspring_penalty(sp, species_list, tier)
            adj += offspring_penalty
            
            # 同属竞争（需要谱系比较）
            sibling_competition = self._calculate_sibling_competition(
                sp, species_list, arrays['overlap'][i]
            )
            adj += sibling_competition
            
            # 共生依赖惩罚
            dependency_penalty = self._calculate_dependency_penalty(sp, extinct_codes)
            adj += dependency_penalty
            
            # 边界约束
            adj = min(0.98, max(0.03, adj))
            
            population = int(arrays['population'][i])
            deaths = int(population * adj)
            survivors = max(population - deaths, 0)
            
            # 生成分析文本
            notes = [self._generate_mortality_notes(
                sp, adj, pressure_score, arrays, i, 
                resource_factor[i], grazing_pressure[i], predation_effect[i],
                pressure_modifiers, trophic_interactions
            )]
            
            if adj > 0.5:
                logger.info(f"[高死亡率警告] {sp.common_name}: {adj:.1%}")
            
            results.append(
                MortalityResult(
                    species=sp,
                    initial_population=population,
                    deaths=deaths,
                    survivors=survivors,
                    death_rate=adj,
                    notes=notes,
                    niche_overlap=arrays['overlap'][i],
                    resource_pressure=arrays['saturation'][i],
                    is_background=sp.is_background,
                    tier=tier,
                    grazing_pressure=grazing_pressure[i],
                    predation_pressure=predation_effect[i]
                )
            )
        
        return results
    
    def _generate_mortality_notes(
        self, sp: Species, adjusted: float, pressure_score: float,
        arrays: dict, idx: int, resource_factor: float,
        grazing_pressure: float, predation_effect: float,
        pressure_modifiers: dict, trophic_interactions: dict
    ) -> str:
        """生成死亡率分析文本"""
        analysis_parts = []
        
        if pressure_score > 3:
            analysis_parts.append(f"环境压力较高({pressure_score:.1f}/10)")
        if arrays['overlap'][idx] > 0.3:
            analysis_parts.append(f"生态位竞争明显(重叠度{arrays['overlap'][idx]:.2f})")
        if arrays['saturation'][idx] > 1.0:
            analysis_parts.append(f"种群饱和(S={arrays['saturation'][idx]:.2f})")
        
        trophic_level = arrays['trophic_level'][idx]
        if resource_factor > 0.2 and trophic_level >= 2.0:
            scarcity = trophic_interactions.get("t2_scarcity" if trophic_level < 3 else "t3_scarcity", 0.0)
            if scarcity > 0.2:
                analysis_parts.append(f"食物短缺({scarcity:.1%})")
        
        if grazing_pressure > 0.1:
            analysis_parts.append(f"承受啃食压力({grazing_pressure:.1%})")
        if predation_effect > 0.1:
            analysis_parts.append(f"遭捕食({predation_effect:.1%})")
        
        body_size = arrays['body_size'][idx]
        if body_size < 0.01:
            analysis_parts.append("体型极小，对环境变化敏感")
        elif body_size > 100:
            analysis_parts.append("体型巨大，具有一定抗压能力")
        
        attr_info = []
        if "temperature" in pressure_modifiers:
            attr_info.append(f"耐寒{arrays['cold_resistance'][idx]:.0f}/耐热{arrays['heat_resistance'][idx]:.0f}")
        if "drought" in pressure_modifiers:
            attr_info.append(f"耐旱{arrays['drought_resistance'][idx]:.0f}")
        if "flood" in pressure_modifiers or "volcano" in pressure_modifiers:
            attr_info.append(f"耐盐{arrays['salinity_resistance'][idx]:.0f}")
        
        if attr_info:
            analysis_parts.append(f"属性[{'/'.join(attr_info)}]")
        
        if analysis_parts:
            return f"{sp.common_name}本回合死亡率{adjusted:.1%}：" + "；".join(analysis_parts) + "。"
        else:
            return f"{sp.common_name}死亡率{adjusted:.1%}，种群状况稳定，未受明显环境压力影响。"
    
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
        """计算同属物种竞争压力（达尔文式淘汰强化版）
        
        【核心设计理念】大量分化→激烈竞争→不适者淘汰→筛选最适者
        
        同谱系前缀的物种（如A1与A1a1，A1a1与A1a1a1）之间存在激烈的竞争。
        子代对亲代的竞争压力更大（体现演化优势）。
        
        【强化淘汰】增强所有竞争来源：
        1. 子代对亲代的压制（强化）- 新物种淘汰旧物种
        2. 同级兄弟竞争（强化）- 同代物种间生存竞争
        3. 近亲竞争（强化）- 物种数量越多，竞争越激烈
        4. 【新增】适应度竞争 - 属性更优的物种压制属性较差的
        
        Args:
            species: 目标物种
            all_species: 所有物种列表
            base_overlap: 基础生态位重叠度
            
        Returns:
            额外死亡率（0-0.55）
        """
        lineage = species.lineage_code
        population = int(species.morphology_stats.get("population", 0) or 0)
        
        if population == 0:
            return 0.0
        
        # 提取不同级别的谱系前缀
        if len(lineage) > 2:
            parent_prefix = lineage[:-2] if len(lineage) > 2 else lineage
        else:
            parent_prefix = lineage
        
        genus_prefix = lineage[:2] if len(lineage) >= 2 else lineage
        
        # 找所有相关物种
        siblings = []  # 同一父系的直接兄弟
        cousins = []   # 同属但非直接兄弟
        
        for s in all_species:
            if s.lineage_code == lineage or s.status != "alive":
                continue
            
            if s.lineage_code.startswith(parent_prefix):
                siblings.append(s)
            elif s.lineage_code.startswith(genus_prefix):
                cousins.append(s)
        
        total_competition = 0.0
        
        # 1. 子代对亲代的压制（强化：新物种淘汰旧物种）
        for sibling in siblings:
            sibling_pop = int(sibling.morphology_stats.get("population", 0) or 0)
            
            if sibling.created_turn > species.created_turn:
                pop_ratio = sibling_pop / max(population, 1)
                # 【强化】压制系数从0.20提高到0.28，体现"新物种更适应"
                competition = base_overlap * min(pop_ratio, 2.5) * 0.28
                total_competition += competition
        
        # 2. 同级兄弟竞争（强化：同代物种的生存竞争）
        my_parent = getattr(species, 'parent_code', None)
        for sibling in siblings:
            sibling_parent = getattr(sibling, 'parent_code', None)
            if sibling_parent and sibling_parent == my_parent:
                sibling_pop = int(sibling.morphology_stats.get("population", 0) or 0)
                pop_ratio = sibling_pop / max(population, 1)
                # 【强化】兄弟竞争系数从0.15提高到0.22
                competition = base_overlap * min(pop_ratio, 2.0) * 0.22
                total_competition += competition
        
        # 3. 近亲竞争（强化：物种数量越多，竞争越激烈）
        cousin_count = len(cousins)
        if cousin_count > 2:  # 降低触发阈值
            # 【强化】每多2个表亲增加7%竞争压力（原3个增加5%）
            cousin_penalty = min(0.25, (cousin_count - 2) * 0.07)
            total_competition += cousin_penalty * max(base_overlap, 0.3)  # 保证最小生态位重叠
        
        # 4.【新增】适应度竞争：属性更优的物种压制属性较差的
        # 比较核心属性（适应性、繁殖力、竞争力）
        my_fitness = self._calculate_fitness_score(species)
        for relative in siblings + cousins[:5]:  # 只比较前5个近亲
            relative_fitness = self._calculate_fitness_score(relative)
            if relative_fitness > my_fitness:
                fitness_gap = (relative_fitness - my_fitness) / max(my_fitness, 1.0)
                # 适应度差距转化为竞争压力
                total_competition += min(0.12, fitness_gap * 0.15)
        
        # 【强化】上限从40%提高到55%，允许更激烈的淘汰
        return min(total_competition, 0.55)
    
    def _calculate_fitness_score(self, species: Species) -> float:
        """计算物种的适应度分数（用于竞争比较）
        
        综合考虑：
        - 繁殖效率（世代时间越短越有优势）
        - 环境适应性（各种抗性的平均值）
        - 竞争能力（营养级和捕食能力）
        """
        traits = species.abstract_traits
        morph = species.morphology_stats
        
        # 繁殖效率：世代时间越短越好（log缩放）
        gen_time = morph.get("generation_time_days", 365)
        repro_score = 10.0 / (1.0 + math.log10(max(1, gen_time)))
        
        # 环境适应性：各种抗性的平均值
        adaptability = (
            traits.get("适应性", 5) +
            traits.get("耐寒性", 5) +
            traits.get("耐热性", 5) +
            traits.get("耐旱性", 5)
        ) / 4.0
        
        # 竞争能力：种群和营养级
        population = morph.get("population", 1000) or 1000
        pop_score = min(5.0, math.log10(max(1, population)) / 2)
        
        return repro_score + adaptability + pop_score
    
    def _calculate_generational_mortality(
        self,
        base_risk_per_turn: float,
        num_generations: float,
        size_resistance: float,
        repro_resistance: float
    ) -> float:
        """【新方法】计算世代累积死亡率
        
        原理：
        - 将回合级死亡风险分摊到每一代
        - 按世代数累积（避免微生物瞬间灭绝）
        - 应用抗性修正
        
        公式：
        1. 每代死亡风险 = base_risk_per_turn / num_generations
        2. 每代存活率 = 1 - per_gen_risk
        3. 多代存活率 = per_gen_survival ^ num_generations
        4. 累积死亡率 = 1 - multi_gen_survival
        
        示例：
        - 微生物（1亿代）：瞬时30%死亡→每代0.0000003%死亡→累积28%
        - 大象（1.7万代）：瞬时30%死亡→每代0.0018%死亡→累积26%
        
        Args:
            base_risk_per_turn: 瞬时死亡风险（当前模型计算的复合死亡率）
            num_generations: 经历的世代数
            size_resistance: 体型抗性（0-0.7）
            repro_resistance: 繁殖策略抗性（0-0.3）
            
        Returns:
            累积死亡率（0-0.98）
        """
        # 防止除零
        num_generations = max(1.0, num_generations)
        
        # 1. 计算每代死亡风险
        # 注意：对于极少代数（如大象），风险分摊可能导致每代风险很高
        # 对于极多代数（如微生物），风险分摊后每代风险极低
        per_generation_risk = base_risk_per_turn / num_generations
        
        # 2. 计算每代存活率
        per_generation_survival = 1.0 - per_generation_risk
        per_generation_survival = max(0.0, min(1.0, per_generation_survival))
        
        # 3. 累积存活率（指数衰减模型）
        # 为了性能，使用对数变换: S_total = S_gen^n = e^(n * ln(S_gen))
        if per_generation_survival <= 0:
            cumulative_survival = 0.0
        elif per_generation_survival >= 1.0:
            cumulative_survival = 1.0
        else:
            log_survival = math.log(per_generation_survival)
            cumulative_log_survival = num_generations * log_survival
            
            # 防止数值下溢（当num_generations很大时）
            if cumulative_log_survival < -700:  # e^-700 ≈ 0
                cumulative_survival = 0.0
            else:
                cumulative_survival = math.exp(cumulative_log_survival)
        
        # 4. 转换为累积死亡率
        cumulative_mortality = 1.0 - cumulative_survival
        
        # 5. 应用抗性修正（在累积后应用，避免重复应用）
        # 抗性主要影响基础风险，但对累积效应也有一定缓解
        resistance_factor = (1.0 - size_resistance * 0.6) * (1.0 - repro_resistance * 0.5)
        adjusted_mortality = cumulative_mortality * resistance_factor
        
        # 6. 边界检查
        adjusted_mortality = max(0.0, min(0.98, adjusted_mortality))
        
        return adjusted_mortality
    
    def _calculate_dependency_penalty(
        self, species: Species, extinct_codes: set[str]
    ) -> float:
        """计算共生依赖惩罚
        
        当物种依赖的其他物种灭绝时，增加额外死亡率。
        
        Args:
            species: 目标物种
            extinct_codes: 已灭绝物种代码集合
            
        Returns:
            额外死亡率惩罚（0-0.5）
        """
        # 获取依赖关系
        dependencies = getattr(species, 'symbiotic_dependencies', []) or []
        dep_strength = getattr(species, 'dependency_strength', 0.0) or 0.0
        
        if not dependencies or dep_strength == 0:
            return 0.0
        
        # 计算有多少依赖物种已灭绝
        extinct_deps = [d for d in dependencies if d in extinct_codes]
        
        if not extinct_deps:
            return 0.0
        
        # 依赖灭绝比例
        extinction_ratio = len(extinct_deps) / len(dependencies)
        
        # 惩罚 = 依赖强度 × 灭绝比例 × 基础惩罚系数
        # 最大惩罚50%（给物种留一些适应机会）
        penalty = dep_strength * extinction_ratio * 0.5
        
        if penalty > 0.05:
            logger.info(
                f"[共生惩罚] {species.common_name}: "
                f"{len(extinct_deps)}/{len(dependencies)}个依赖物种已灭绝, "
                f"额外死亡率+{penalty:.1%}"
            )
        
        return min(0.5, penalty)
    
    def _apply_intervention_modifiers(
        self, species: Species, base_mortality: float
    ) -> float:
        """应用玩家干预修正（保护/压制）
        
        Args:
            species: 目标物种
            base_mortality: 基础死亡率
            
        Returns:
            修正后的死亡率
        """
        adjusted = base_mortality
        
        # 保护状态：降低死亡率
        is_protected = getattr(species, 'is_protected', False) or False
        protection_turns = getattr(species, 'protection_turns', 0) or 0
        
        if is_protected and protection_turns > 0:
            # 保护效果：死亡率降低50%
            adjusted *= 0.5
            logger.debug(f"[保护] {species.common_name}: 死亡率从{base_mortality:.1%}降至{adjusted:.1%}")
        
        # 压制状态：提高死亡率
        is_suppressed = getattr(species, 'is_suppressed', False) or False
        suppression_turns = getattr(species, 'suppression_turns', 0) or 0
        
        if is_suppressed and suppression_turns > 0:
            # 压制效果：死亡率提高30%
            adjusted = min(0.95, adjusted + 0.30)
            logger.debug(f"[压制] {species.common_name}: 死亡率从{base_mortality:.1%}升至{adjusted:.1%}")
        
        return adjusted
    
    def _calculate_density_penalty(
        self, total_species_count: int, trophic_level: float
    ) -> float:
        """计算物种密度惩罚
        
        当生态系统中物种数量过多时，资源竞争加剧，
        所有物种的死亡率都会增加。
        
        惩罚公式：
        - 物种数 <= 30：无惩罚
        - 物种数 30-60：每多10种增加2%死亡率
        - 物种数 60-100：每多10种增加3%死亡率
        - 物种数 > 100：每多10种增加5%死亡率
        
        营养级修正：
        - 高营养级物种（T3+）受密度惩罚更严重（资源更稀缺）
        
        Args:
            total_species_count: 当前物种总数
            trophic_level: 物种营养级
            
        Returns:
            额外死亡率（0-0.30）
        """
        if total_species_count <= 30:
            return 0.0
        
        penalty = 0.0
        
        if total_species_count <= 60:
            # 30-60种：每多10种增加2%
            excess = total_species_count - 30
            penalty = (excess / 10) * 0.02
        elif total_species_count <= 100:
            # 60-100种：前30种的惩罚 + 每多10种增加3%
            penalty = 0.06  # 30-60种的惩罚
            excess = total_species_count - 60
            penalty += (excess / 10) * 0.03
        else:
            # >100种：前70种的惩罚 + 每多10种增加5%
            penalty = 0.06 + 0.12  # 30-60和60-100种的惩罚
            excess = total_species_count - 100
            penalty += (excess / 10) * 0.05
        
        # 营养级修正：高营养级受更严重的密度惩罚
        # T1: ×0.8, T2: ×1.0, T3: ×1.2, T4+: ×1.5
        if trophic_level < 2.0:
            trophic_multiplier = 0.8
        elif trophic_level < 3.0:
            trophic_multiplier = 1.0
        elif trophic_level < 4.0:
            trophic_multiplier = 1.2
        else:
            trophic_multiplier = 1.5
        
        penalty *= trophic_multiplier
        
        # 上限30%
        return min(penalty, 0.30)

    def _resolve_region_label(self, species: Species) -> str:
        habitat = (getattr(species, "habitat_type", "") or "").lower()
        marine_types = {"marine", "deep_sea", "coastal"}
        if habitat in marine_types:
            return "marine"
        return "terrestrial"

