"""基因流动服务"""
from __future__ import annotations

import logging
from typing import Sequence

from ..models.genus import Genus
from ..models.species import Species

logger = logging.getLogger(__name__)


class GeneFlowService:
    """模拟同属物种间的基因流动"""
    
    def apply_gene_flow(self, genus: Genus, species_list: Sequence[Species]) -> int:
        """应用基因流动
        
        在近缘物种间产生微小的属性趋同
        
        Args:
            genus: 属对象（包含遗传距离矩阵）
            species_list: 该属下的物种列表
            
        Returns:
            发生基因流动的物种对数量
        """
        flow_count = 0
        
        for i, sp1 in enumerate(species_list):
            for sp2 in species_list[i+1:]:
                distance_key = self._make_distance_key(sp1.lineage_code, sp2.lineage_code)
                distance = genus.genetic_distances.get(distance_key, 0.5)
                
                if distance > 0.4:
                    continue
                
                flow_rate = 0.02 * (1.0 - distance / 0.4)
                
                self._apply_flow_between(sp1, sp2, flow_rate)
                flow_count += 1
        
        if flow_count > 0:
            logger.debug(f"[基因流动] {genus.genus_code}属内发生{flow_count}次基因流动")
        
        return flow_count
    
    def _apply_flow_between(self, sp1: Species, sp2: Species, base_flow_rate: float):
        """在两个物种间应用基因流动（非对称）"""
        pop1 = sp1.morphology_stats.get("population", 1000)
        pop2 = sp2.morphology_stats.get("population", 1000)
        total_pop = pop1 + pop2 + 1  # prevent div by zero

        # 非对称基因流动：大种群对小种群的影响更大
        # flow_1_to_2: sp1 影响 sp2 (权重取决于 sp1 的相对占比)
        # 如果 sp1 占 90%, sp2 占 10%, 则 sp1 对 sp2 的影响很大，sp2 对 sp1 的影响很小
        weight_1 = pop1 / total_pop
        weight_2 = pop2 / total_pop
        
        # 放大因子：确保基础流速有效
        # 如果是 50/50 分布，双方各受 1.0 * base_rate 影响
        rate_impact_on_2 = base_flow_rate * weight_1 * 2.0
        rate_impact_on_1 = base_flow_rate * weight_2 * 2.0

        for trait_name in sp1.abstract_traits:
            if trait_name not in sp2.abstract_traits:
                continue
            
            val1 = sp1.abstract_traits[trait_name]
            val2 = sp2.abstract_traits[trait_name]
            diff = val2 - val1
            
            # sp1 受到 sp2 的影响 (rate_impact_on_1) -> 移向 val2
            # val1 += (val2 - val1) * rate
            sp1.abstract_traits[trait_name] += diff * rate_impact_on_1
            
            # sp2 受到 sp1 的影响 (rate_impact_on_2) -> 移向 val1
            # val2 -= (val2 - val1) * rate = val2 + (val1 - val2) * rate
            sp2.abstract_traits[trait_name] -= diff * rate_impact_on_2
            
            # 钳制范围
            sp1.abstract_traits[trait_name] = max(0.0, min(15.0, sp1.abstract_traits[trait_name]))
            sp2.abstract_traits[trait_name] = max(0.0, min(15.0, sp2.abstract_traits[trait_name]))
    
    def _make_distance_key(self, code1: str, code2: str) -> str:
        """生成距离键（保证顺序一致性）"""
        if code1 < code2:
            return f"{code1}-{code2}"
        return f"{code2}-{code1}"

