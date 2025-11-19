"""物种繁殖与种群增长系统。

一个回合代表50万年的演化时间，物种应该有显著的种群增长。
"""

from __future__ import annotations

import logging
import math
from typing import Sequence

from ..models.species import Species

logger = logging.getLogger(__name__)


class ReproductionService:
    """处理物种在回合间的自然繁殖和种群增长。
    
    增长模型基于：
    - 生态位竞争（重叠度越高，增长越慢）
    - 资源压力（饱和度越高，增长越慢）
    - 繁殖率（基于物种属性）
    - 承载力限制
    """
    
    def __init__(self, global_carrying_capacity: int = 100_000_000, turn_years: int = 500_000):
        """初始化繁殖服务。
        
        Args:
            global_carrying_capacity: 全球总承载力（提高到1亿，适应微生物大种群）
            turn_years: 每回合代表的年数（默认50万年）
        """
        self.global_carrying_capacity = global_carrying_capacity
        self.turn_years = turn_years
        # 50万年 = 182,500,000天
        # 微生物世代时间：1-5天，即可以经历10万-50万代
        # r策略物种在理想条件下每代可增长1.5-2倍
        # 但会受到承载力和竞争的限制
    
    def apply_reproduction(
        self,
        species_list: Sequence[Species],
        niche_metrics: dict[str, tuple[float, float]],  # {lineage_code: (overlap, saturation)}
        survival_rates: dict[str, float],  # {lineage_code: survival_rate}
    ) -> dict[str, int]:
        """计算所有物种的繁殖增长，返回新的种群数量。
        
        Args:
            species_list: 所有存活物种
            niche_metrics: 生态位重叠和资源饱和度
            survival_rates: 上一回合的存活率（1 - 死亡率）
            
        Returns:
            {lineage_code: new_population}
        """
        total_current = sum(int(sp.morphology_stats.get("population", 0)) for sp in species_list)
        
        # 如果总种群接近承载力，限制增长
        global_pressure = min(1.0, total_current / self.global_carrying_capacity)
        
        new_populations = {}
        
        for species in species_list:
            current_pop = int(species.morphology_stats.get("population", 0))
            
            if current_pop <= 0:
                new_populations[species.lineage_code] = 0
                continue
            
            # 获取生态位数据
            overlap, saturation = niche_metrics.get(species.lineage_code, (0.0, 0.0))
            survival_rate = survival_rates.get(species.lineage_code, 0.5)
            
            # 计算增长因子
            growth_factor = self._calculate_growth_factor(
                species=species,
                niche_overlap=overlap,
                resource_saturation=saturation,
                survival_rate=survival_rate,
                global_pressure=global_pressure,
            )
            
            # 应用增长
            new_pop = int(current_pop * growth_factor)
            
            # 确保合理范围（允许单个物种占据更多承载力）
            # 但最多不超过全球承载力的80%
            new_pop = max(100, min(new_pop, int(self.global_carrying_capacity * 0.8)))
            
            if abs(new_pop - current_pop) / max(current_pop, 1) > 0.5:
                logger.info(f"[种群变动] {species.common_name}: {current_pop} -> {new_pop} (factor={growth_factor:.2f})")
            else:
                logger.debug(f"[种群微调] {species.common_name}: {current_pop} -> {new_pop} (factor={growth_factor:.2f})")
            
            new_populations[species.lineage_code] = new_pop
        
        return new_populations
    
    def _calculate_growth_factor(
        self,
        species: Species,
        niche_overlap: float,
        resource_saturation: float,
        survival_rate: float,
        global_pressure: float,
    ) -> float:
        """计算物种的增长因子，基于世代时间和r/K策略。
        
        返回值 > 1.0 表示增长，< 1.0 表示衰退。
        微生物应该能在数回合内达到承载力。
        """
        # 1. 计算理论世代数
        generation_time_days = species.morphology_stats.get("generation_time_days", 10)
        total_days = self.turn_years * 365.25
        generations = total_days / generation_time_days
        
        # 2. 基于繁殖速度的每代增长率
        reproduction_speed = species.abstract_traits.get("繁殖速度", 5)  # 1-10
        # 高繁殖速度（9-10）= r策略，每代可增长1.5-2倍
        # 中等繁殖速度（5-8）= 每代增长1.2-1.5倍
        # 低繁殖速度（1-4）= K策略，每代增长1.05-1.2倍
        per_generation_growth = 1.0 + (reproduction_speed / 20.0)  # 1.05 到 1.5
        
        # 3. 理论最大增长（指数增长公式，但会被限制）
        # 对于微藻（繁殖速度9，1天世代）：50万年有50万代，理论上可增长(1.45^500000)
        # 但实际会很快达到承载力
        theoretical_max = per_generation_growth ** min(generations, 100)  # 限制指数，避免溢出
        
        # 将理论增长映射到合理范围（1.5 - 10倍/回合）
        # 微生物在理想条件下1回合应该能增长5-10倍
        if reproduction_speed >= 8:  # r策略，快速繁殖
            base_factor = min(theoretical_max, 8.0)
        elif reproduction_speed >= 5:  # 中等繁殖
            base_factor = min(theoretical_max, 4.0)
        else:  # K策略，慢速繁殖
            base_factor = min(theoretical_max, 2.0)
        
        # 4. 生存压力修正
        survival_modifier = 0.5 + survival_rate  # 0.5 到 1.5
        
        # 5. 生态位竞争修正（竞争激烈时增长大幅降低）
        competition_modifier = 1.0 - (niche_overlap * 0.7)  # 0.3 到 1.0
        
        # 6. 资源饱和修正（饱和度越高，增长越受限）
        # 当饱和度>1时，增长应该接近停滞
        if resource_saturation < 0.5:
            resource_modifier = 1.0  # 资源充足
        elif resource_saturation < 1.0:
            resource_modifier = 1.0 - (resource_saturation - 0.5) * 1.5  # 0.25 到 1.0
        else:
            resource_modifier = max(0.1, 1.0 - resource_saturation * 0.8)  # 饱和时大幅减速
        
        # 7. 全局压力修正（总种群接近承载力时）
        if global_pressure < 0.7:
            global_modifier = 1.0  # 承载力充足
        else:
            global_modifier = max(0.3, 1.0 - (global_pressure - 0.7) * 2.0)  # 接近承载力时强烈抑制
        
        # 8. 种群规模修正
        population = int(species.morphology_stats.get("population", 1000))
        if population < 100_000:
            size_modifier = 1.3  # 小种群快速恢复
        elif population < 1_000_000:
            size_modifier = 1.1
        elif population < 10_000_000:
            size_modifier = 1.0
        else:
            size_modifier = 0.85  # 大种群增长放缓
        
        # 综合计算
        growth_factor = (
            base_factor
            * survival_modifier
            * competition_modifier
            * resource_modifier
            * global_modifier
            * size_modifier
        )
        
        # 确保在合理范围内
        # 理想条件：8-10倍/回合（r策略物种）
        # 饱和条件：0.5-1.2倍/回合（维持种群）
        growth_factor = max(0.5, min(growth_factor, 10.0))
        
        # 添加随机波动（±15%）
        import random
        noise = random.uniform(0.85, 1.15)
        growth_factor *= noise
        
        return growth_factor

