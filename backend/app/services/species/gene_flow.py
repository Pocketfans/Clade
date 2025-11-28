"""基因流动服务

【核心改进】基因流动现在考虑地理隔离：
- 只有在同一地块或相邻地块的物种才能发生基因流动
- 地块重叠程度影响基因流动强度
- 完全地理隔离的物种无法基因交流

【平衡优化v2】调整阈值让分化更快独立：
- 降低遗传距离阈值（0.4→0.28），更快停止基因交流
- 放宽地理隔离判断（0.05→0.12），适度重叠仍可隔离
- 增加基础流速，让有交流时效果更明显
"""
from __future__ import annotations

import logging
from typing import Sequence

from ...core.config import get_settings
from ...models.genus import Genus
from ...models.species import Species
from ...models.environment import HabitatPopulation
from ...repositories.environment_repository import environment_repository

logger = logging.getLogger(__name__)


class GeneFlowService:
    """模拟同属物种间的基因流动
    
    【核心改进】现在考虑地理隔离：
    - 只有栖息地重叠的物种才能发生基因流动
    - 重叠程度影响基因流动强度
    """
    
    def __init__(self):
        self._habitat_cache: dict[int, set[int]] = {}  # {species_id: {tile_ids}}
    
    def _build_habitat_cache(self, species_list: Sequence[Species]) -> None:
        """构建物种栖息地缓存"""
        self._habitat_cache.clear()
        
        # 获取所有物种的ID
        species_ids = [sp.id for sp in species_list if sp.id is not None]
        if not species_ids:
            return
        
        # 获取栖息地数据
        habitats = environment_repository.latest_habitats(species_ids=species_ids)
        
        for habitat in habitats:
            sp_id = habitat.species_id
            if sp_id not in self._habitat_cache:
                self._habitat_cache[sp_id] = set()
            self._habitat_cache[sp_id].add(habitat.tile_id)
    
    def _calculate_habitat_overlap(self, sp1: Species, sp2: Species) -> float:
        """计算两个物种的栖息地重叠程度
        
        使用 Jaccard 系数：交集 / 并集
        
        Returns:
            0.0 = 完全隔离（无基因流动）
            1.0 = 完全重叠（最大基因流动）
        """
        tiles1 = self._habitat_cache.get(sp1.id, set()) if sp1.id else set()
        tiles2 = self._habitat_cache.get(sp2.id, set()) if sp2.id else set()
        
        if not tiles1 or not tiles2:
            # 没有栖息地数据，假设中等重叠
            return 0.5
        
        intersection = tiles1 & tiles2
        union = tiles1 | tiles2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def apply_gene_flow(self, genus: Genus, species_list: Sequence[Species]) -> int:
        """应用基因流动
        
        【核心改进】现在考虑地理隔离：
        - 只有栖息地重叠的物种才能发生基因流动
        - 重叠程度影响基因流动强度
        
        【平衡优化v2】使用配置参数：
        - 遗传距离阈值从0.4降到0.28，更快停止交流促进分化
        - 地理重叠阈值从0.05升到0.12，放宽隔离判断
        - 基础流速从0.02升到0.03，有交流时效果更显著
        
        Args:
            genus: 属对象（包含遗传距离矩阵）
            species_list: 该属下的物种列表
            
        Returns:
            发生基因流动的物种对数量
        """
        _settings = get_settings()
        distance_threshold = _settings.gene_flow_distance_threshold  # 默认0.28
        overlap_threshold = _settings.gene_flow_overlap_threshold    # 默认0.12
        
        flow_count = 0
        
        # 构建栖息地缓存
        self._build_habitat_cache(species_list)
        
        for i, sp1 in enumerate(species_list):
            for sp2 in species_list[i+1:]:
                # 1. 检查遗传距离（使用配置阈值）
                distance_key = self._make_distance_key(sp1.lineage_code, sp2.lineage_code)
                distance = genus.genetic_distances.get(distance_key, 0.5)
                
                if distance > distance_threshold:
                    continue
                
                # 2. 检查地理重叠（使用配置阈值）
                habitat_overlap = self._calculate_habitat_overlap(sp1, sp2)
                
                # 地理隔离：无基因流动
                if habitat_overlap < overlap_threshold:
                    logger.debug(
                        f"[基因流动] {sp1.common_name} 与 {sp2.common_name} "
                        f"地理隔离（重叠={habitat_overlap:.2f}<{overlap_threshold}），跳过"
                    )
                    continue
                
                # 3. 计算基因流动速率
                # 基础速率提高到0.03，让有交流时效果更明显
                base_rate = 0.03 * (1.0 - distance / distance_threshold)
                flow_rate = base_rate * habitat_overlap
                
                self._apply_flow_between(sp1, sp2, flow_rate)
                flow_count += 1
                
                logger.debug(
                    f"[基因流动] {sp1.common_name} ↔ {sp2.common_name}: "
                    f"遗传距离={distance:.2f}, 地理重叠={habitat_overlap:.2f}, 流速={flow_rate:.4f}"
                )
        
        if flow_count > 0:
            logger.info(f"[基因流动] {genus.genus_code}属内发生{flow_count}次基因流动")
        
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

