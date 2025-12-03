"""
Trophic Interaction Service - 营养级互动服务

处理物种之间的捕食关系和能量传递计算。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)


class TrophicInteractionService:
    """营养级互动服务
    
    计算物种之间的捕食关系和能量传递。
    """
    
    def __init__(self):
        self._cache: Dict[str, float] = {}
    
    def calculate(
        self,
        species_list: List["Species"],
    ) -> Dict[str, float]:
        """计算营养级互动
        
        Args:
            species_list: 物种列表
            
        Returns:
            lineage_code -> 互动强度 的映射
        """
        interactions = {}
        
        # 按营养级分组
        producers = []
        herbivores = []
        carnivores = []
        
        for sp in species_list:
            if sp.status != "alive":
                continue
            tl = getattr(sp, 'trophic_level', 1.0) or 1.0
            if tl < 2.0:
                producers.append(sp)
            elif tl < 3.0:
                herbivores.append(sp)
            else:
                carnivores.append(sp)
        
        # 计算生产者-草食动物互动
        total_producer_biomass = sum(
            s.morphology_stats.get("population", 0) or 0
            for s in producers
        )
        
        for herb in herbivores:
            # 草食动物受生产者丰度影响
            if total_producer_biomass > 0:
                interactions[herb.lineage_code] = min(1.0, total_producer_biomass / 100000)
            else:
                interactions[herb.lineage_code] = 0.1
        
        # 计算草食动物-肉食动物互动
        total_herbivore_biomass = sum(
            s.morphology_stats.get("population", 0) or 0
            for s in herbivores
        )
        
        for carn in carnivores:
            if total_herbivore_biomass > 0:
                interactions[carn.lineage_code] = min(1.0, total_herbivore_biomass / 50000)
            else:
                interactions[carn.lineage_code] = 0.1
        
        return interactions
    
    def get_predators(
        self,
        species: "Species",
        all_species: List["Species"],
    ) -> List["Species"]:
        """获取指定物种的捕食者"""
        target_tl = getattr(species, 'trophic_level', 1.0) or 1.0
        predators = []
        
        for sp in all_species:
            if sp.status != "alive" or sp.lineage_code == species.lineage_code:
                continue
            sp_tl = getattr(sp, 'trophic_level', 1.0) or 1.0
            # 捕食者营养级比猎物高 0.5-2.0
            if 0.5 <= sp_tl - target_tl <= 2.0:
                predators.append(sp)
        
        return predators
    
    def get_prey(
        self,
        species: "Species",
        all_species: List["Species"],
    ) -> List["Species"]:
        """获取指定物种的猎物"""
        target_tl = getattr(species, 'trophic_level', 1.0) or 1.0
        prey = []
        
        if target_tl < 2.0:
            return []  # 生产者没有猎物
        
        for sp in all_species:
            if sp.status != "alive" or sp.lineage_code == species.lineage_code:
                continue
            sp_tl = getattr(sp, 'trophic_level', 1.0) or 1.0
            # 猎物营养级比捕食者低 0.5-2.0
            if 0.5 <= target_tl - sp_tl <= 2.0:
                prey.append(sp)
        
        return prey


# 单例模式
_trophic_service: TrophicInteractionService | None = None


def get_trophic_service() -> TrophicInteractionService:
    """获取营养级互动服务单例"""
    global _trophic_service
    if _trophic_service is None:
        _trophic_service = TrophicInteractionService()
    return _trophic_service








