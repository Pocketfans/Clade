"""
Ecosystem Metrics Service - 生态系统指标服务

计算和追踪生态系统健康指标。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)


class EcosystemMetricsService:
    """生态系统指标服务
    
    计算生态系统的各项健康指标。
    """
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
    
    def calculate_biodiversity_index(
        self,
        species_list: List["Species"],
    ) -> float:
        """计算生物多样性指数
        
        使用 Shannon-Wiener 指数
        
        Args:
            species_list: 物种列表
            
        Returns:
            多样性指数
        """
        import math
        
        alive_species = [s for s in species_list if s.status == "alive"]
        if not alive_species:
            return 0.0
        
        total_pop = sum(
            s.morphology_stats.get("population", 0) or 0
            for s in alive_species
        )
        
        if total_pop <= 0:
            return 0.0
        
        # Shannon-Wiener 指数
        h = 0.0
        for species in alive_species:
            pop = species.morphology_stats.get("population", 0) or 0
            if pop > 0:
                p = pop / total_pop
                h -= p * math.log(p)
        
        return h
    
    def calculate_ecosystem_health(
        self,
        species_list: List["Species"],
    ) -> float:
        """计算生态系统健康度
        
        Args:
            species_list: 物种列表
            
        Returns:
            健康度 [0, 1]
        """
        alive_species = [s for s in species_list if s.status == "alive"]
        
        if not alive_species:
            return 0.0
        
        # 基于多个因素计算
        health = 0.5
        
        # 物种数量因素
        if len(alive_species) >= 10:
            health += 0.2
        elif len(alive_species) >= 5:
            health += 0.1
        else:
            health -= 0.1
        
        # 营养级分布因素
        trophic_levels = set()
        for sp in alive_species:
            tl = getattr(sp, 'trophic_level', 1.0) or 1.0
            trophic_levels.add(int(tl))
        
        if len(trophic_levels) >= 4:
            health += 0.2
        elif len(trophic_levels) >= 3:
            health += 0.1
        
        # 总种群规模因素
        total_pop = sum(
            s.morphology_stats.get("population", 0) or 0
            for s in alive_species
        )
        
        if total_pop >= 100000:
            health += 0.1
        elif total_pop < 1000:
            health -= 0.1
        
        return max(0.0, min(1.0, health))
    
    def get_trophic_distribution(
        self,
        species_list: List["Species"],
    ) -> Dict[int, int]:
        """获取营养级分布
        
        Args:
            species_list: 物种列表
            
        Returns:
            {营养级: 物种数量}
        """
        distribution = {}
        
        for species in species_list:
            if species.status != "alive":
                continue
            tl = int(getattr(species, 'trophic_level', 1.0) or 1.0)
            distribution[tl] = distribution.get(tl, 0) + 1
        
        return distribution


# 单例
_ecosystem_metrics_service: EcosystemMetricsService | None = None


def get_ecosystem_metrics_service() -> EcosystemMetricsService:
    """获取生态系统指标服务单例"""
    global _ecosystem_metrics_service
    if _ecosystem_metrics_service is None:
        _ecosystem_metrics_service = EcosystemMetricsService()
    return _ecosystem_metrics_service








