"""
Genetic Evolution Service - 遗传演化服务

处理物种的遗传变异和演化过程。
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)


class GeneticEvolutionService:
    """遗传演化服务
    
    处理物种的遗传变异，包括：
    - 突变
    - 基因重组
    - 自然选择
    """
    
    def __init__(
        self,
        mutation_rate: float = 0.01,
        selection_strength: float = 0.1,
    ):
        self.mutation_rate = mutation_rate
        self.selection_strength = selection_strength
    
    def apply_mutations(
        self,
        species: "Species",
        environmental_pressure: float = 0.0,
    ) -> Dict[str, Any]:
        """应用突变
        
        Args:
            species: 物种
            environmental_pressure: 环境压力强度
            
        Returns:
            突变结果
        """
        mutations = {}
        
        # 获取隐藏特征
        hidden_traits = getattr(species, 'hidden_traits', {}) or {}
        
        # 环境压力增加突变率
        effective_rate = self.mutation_rate * (1 + environmental_pressure)
        
        for trait_name, trait_value in hidden_traits.items():
            if random.random() < effective_rate:
                # 发生突变
                if isinstance(trait_value, (int, float)):
                    # 数值型特征：高斯突变
                    delta = random.gauss(0, 0.1)
                    new_value = trait_value * (1 + delta)
                    hidden_traits[trait_name] = new_value
                    mutations[trait_name] = {
                        "old": trait_value,
                        "new": new_value,
                        "delta": delta,
                    }
        
        if mutations:
            logger.debug(f"[遗传演化] {species.lineage_code} 发生 {len(mutations)} 个突变")
        
        return mutations
    
    def calculate_fitness(
        self,
        species: "Species",
        environment: Dict[str, float] | None = None,
    ) -> float:
        """计算适应度
        
        Args:
            species: 物种
            environment: 环境参数
            
        Returns:
            适应度 [0, 1]
        """
        fitness = 0.5  # 基础适应度
        
        # 基于种群规模
        population = species.morphology_stats.get("population", 0) or 0
        if population > 10000:
            fitness += 0.2
        elif population > 1000:
            fitness += 0.1
        elif population < 100:
            fitness -= 0.2
        
        # 基于遗传多样性
        hidden_traits = getattr(species, 'hidden_traits', {}) or {}
        diversity = len(hidden_traits) / 10.0
        fitness += min(0.2, diversity)
        
        # 环境匹配
        if environment:
            # 简单的环境匹配评估
            pass
        
        return max(0.0, min(1.0, fitness))
    
    def apply_natural_selection(
        self,
        species_list: List["Species"],
    ) -> Dict[str, float]:
        """应用自然选择
        
        Args:
            species_list: 物种列表
            
        Returns:
            各物种的选择压力 {lineage_code: selection_pressure}
        """
        selection_pressures = {}
        
        for species in species_list:
            if species.status != "alive":
                continue
            
            fitness = self.calculate_fitness(species)
            
            # 选择压力与适应度成反比
            pressure = (1 - fitness) * self.selection_strength
            selection_pressures[species.lineage_code] = pressure
        
        return selection_pressures








