"""物种杂交服务"""
from __future__ import annotations

import random
from typing import Sequence

from ...models.species import Species
from .genetic_distance import GeneticDistanceCalculator


class HybridizationService:
    """处理物种杂交"""
    
    def __init__(self, genetic_calculator: GeneticDistanceCalculator):
        self.genetic_calculator = genetic_calculator
    
    def can_hybridize(self, sp1: Species, sp2: Species, genetic_distance: float = None) -> tuple[bool, float]:
        """判断两个物种能否杂交
        
        Args:
            sp1, sp2: 待杂交的物种
            genetic_distance: 预计算的遗传距离（可选）
            
        Returns:
            (是否可杂交, 预期可育性)
        """
        if sp1.genus_code != sp2.genus_code or not sp1.genus_code:
            return False, 0.0
        
        if sp1.lineage_code == sp2.lineage_code:
            return False, 0.0
        
        if genetic_distance is None:
            genetic_distance = self.genetic_calculator.calculate_distance(sp1, sp2)
        
        if genetic_distance >= 0.5:
            return False, 0.0
        
        fertility = max(0.0, 1.0 - genetic_distance * 2.0)
        
        return True, fertility
    
    def create_hybrid(
        self, 
        parent1: Species, 
        parent2: Species, 
        turn_index: int,
        genetic_distance: float = None
    ) -> Species | None:
        """创建杂交种
        
        Args:
            parent1, parent2: 杂交亲本
            turn_index: 当前回合
            genetic_distance: 预计算的遗传距离（可选）
            
        Returns:
            杂交种，如果杂交失败则返回None
        """
        can_hybrid, fertility = self.can_hybridize(parent1, parent2, genetic_distance)
        if not can_hybrid:
            return None
        
        hybrid_code = f"{parent1.lineage_code}×{parent2.lineage_code}"
        
        hybrid_traits = self._mix_traits(parent1, parent2)
        hybrid_organs = self._merge_organs(parent1, parent2)
        hybrid_morphology = self._mix_morphology(parent1, parent2)
        hybrid_trophic = max(parent1.trophic_level, parent2.trophic_level)
        hybrid_capabilities = list(set(parent1.capabilities + parent2.capabilities))
        
        p1_genus = parent1.latin_name.split()[0] if ' ' in parent1.latin_name else parent1.latin_name
        p2_species = parent2.latin_name.split()[1] if ' ' in parent2.latin_name else "hybrid"
        
        return Species(
            lineage_code=hybrid_code,
            latin_name=f"{p1_genus} × {p2_species}",
            common_name=f"{parent1.common_name}×{parent2.common_name}杂交种",
            description=self._generate_hybrid_description(parent1, parent2),
            morphology_stats=hybrid_morphology,
            abstract_traits=hybrid_traits,
            hidden_traits=self._mix_hidden_traits(parent1, parent2),
            ecological_vector=None,
            parent_code=None,
            status="alive",
            created_turn=turn_index,
            trophic_level=hybrid_trophic,
            organs=hybrid_organs,
            capabilities=hybrid_capabilities,
            genus_code=parent1.genus_code,
            taxonomic_rank="hybrid",
            hybrid_parent_codes=[parent1.lineage_code, parent2.lineage_code],
            hybrid_fertility=fertility,
        )
    
    def _mix_traits(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合属性：模拟显性/隐性遗传"""
        mixed = {}
        for trait_name in p1.abstract_traits:
            if trait_name not in p2.abstract_traits:
                mixed[trait_name] = p1.abstract_traits[trait_name]
                continue
            
            val1 = p1.abstract_traits[trait_name]
            val2 = p2.abstract_traits[trait_name]
            
            rand = random.random()
            if rand < 0.7:
                mixed[trait_name] = max(val1, val2)
            elif rand < 0.9:
                mixed[trait_name] = (val1 + val2) / 2
            else:
                mixed[trait_name] = min(val1, val2)
            
            mixed[trait_name] += random.uniform(-0.2, 0.2)
            mixed[trait_name] = max(0.0, min(15.0, mixed[trait_name]))
        
        return mixed
    
    def _merge_organs(self, p1: Species, p2: Species) -> dict:
        """合并器官：杂交种获得双亲器官"""
        merged = {}
        
        for category, organ_data in p1.organs.items():
            merged[category] = dict(organ_data)
        
        for category, organ_data in p2.organs.items():
            if category in merged:
                eff1 = merged[category].get("parameters", {}).get("efficiency", 1.0)
                eff2 = organ_data.get("parameters", {}).get("efficiency", 1.0)
                
                if eff2 > eff1:
                    merged[category] = dict(organ_data)
            else:
                merged[category] = dict(organ_data)
        
        return merged
    
    def _mix_morphology(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合形态学参数"""
        mixed = {}
        
        for key in p1.morphology_stats:
            if key not in p2.morphology_stats:
                mixed[key] = p1.morphology_stats[key]
                continue
            
            val1 = p1.morphology_stats[key]
            val2 = p2.morphology_stats[key]
            
            if key == "population":
                mixed[key] = min(val1, val2) * 0.5
            else:
                mixed[key] = (val1 + val2) / 2 * random.uniform(0.9, 1.1)
        
        return mixed
    
    def _mix_hidden_traits(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合隐藏属性"""
        mixed = {}
        
        for key in p1.hidden_traits:
            if key not in p2.hidden_traits:
                mixed[key] = p1.hidden_traits[key]
                continue
            
            val1 = p1.hidden_traits[key]
            val2 = p2.hidden_traits[key]
            
            mixed[key] = (val1 + val2) / 2
            
            if key == "gene_diversity":
                mixed[key] = min(1.0, mixed[key] * 1.1)
        
        return mixed
    
    def _generate_hybrid_description(self, p1: Species, p2: Species) -> str:
        """生成杂交种描述"""
        return (
            f"{p1.common_name}与{p2.common_name}的杂交后代。"
            f"继承了双亲的部分特征，形态介于两者之间。"
            f"杂交种通常表现出杂交优势或某些特征的中间型。"
        )

