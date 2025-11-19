"""遗传距离计算服务"""
from __future__ import annotations

import math
from typing import Sequence

from ..models.species import Species


class GeneticDistanceCalculator:
    """计算物种间遗传距离"""
    
    def calculate_distance(self, sp1: Species, sp2: Species) -> float:
        """基于多维度计算遗传距离
        
        Args:
            sp1, sp2: 待比较的物种
            
        Returns:
            遗传距离 0.0-1.0，0表示同种，1表示完全隔离
        """
        morphology_diff = self._morphology_difference(sp1, sp2)
        trait_diff = self._trait_difference(sp1, sp2)
        organ_diff = self._organ_difference(sp1, sp2)
        time_diff = self._time_divergence(sp1, sp2)
        
        distance = (
            morphology_diff * 0.30 +
            trait_diff * 0.25 +
            organ_diff * 0.25 +
            time_diff * 0.20
        )
        
        return min(1.0, distance)
    
    def _morphology_difference(self, sp1: Species, sp2: Species) -> float:
        """形态学差异"""
        try:
            length1 = sp1.morphology_stats.get("body_length_cm", 1.0)
            length2 = sp2.morphology_stats.get("body_length_cm", 1.0)
            length_ratio = min(length1, length2) / max(length1, length2)
            length_diff = 1.0 - length_ratio
            
            weight1 = sp1.morphology_stats.get("body_weight_g", 1.0)
            weight2 = sp2.morphology_stats.get("body_weight_g", 1.0)
            weight_ratio = min(weight1, weight2) / max(weight1, weight2)
            weight_diff = 1.0 - weight_ratio
            
            return (length_diff + weight_diff) / 2
        except (ZeroDivisionError, KeyError):
            return 0.5
    
    def _trait_difference(self, sp1: Species, sp2: Species) -> float:
        """属性差异（归一化欧氏距离）"""
        total_diff = 0.0
        count = 0
        
        for trait_name in sp1.abstract_traits:
            if trait_name not in sp2.abstract_traits:
                continue
            
            diff = abs(sp1.abstract_traits[trait_name] - sp2.abstract_traits[trait_name])
            total_diff += (diff / 15.0) ** 2
            count += 1
        
        if count == 0:
            return 0.0
        
        return math.sqrt(total_diff / count)
    
    def _organ_difference(self, sp1: Species, sp2: Species) -> float:
        """器官差异"""
        organs1 = set(sp1.organs.keys())
        organs2 = set(sp2.organs.keys())
        
        unique_organs = organs1.symmetric_difference(organs2)
        total_organs = len(organs1.union(organs2))
        
        if total_organs == 0:
            return 0.0
        
        return len(unique_organs) / total_organs
    
    def _time_divergence(self, sp1: Species, sp2: Species) -> float:
        """基于分化时间估算遗传距离
        
        假设每50回合遗传距离增加0.1
        """
        common_ancestor_turn = self._find_common_ancestor_turn(sp1, sp2)
        current_turn = max(sp1.created_turn, sp2.created_turn)
        
        divergence_turns = current_turn - common_ancestor_turn
        time_distance = min(1.0, divergence_turns / 500)
        
        return time_distance
    
    def _find_common_ancestor_turn(self, sp1: Species, sp2: Species) -> int:
        """查找共同祖先的回合数"""
        codes1 = self._get_lineage_path(sp1.lineage_code)
        codes2 = self._get_lineage_path(sp2.lineage_code)
        
        for i, (c1, c2) in enumerate(zip(codes1, codes2)):
            if c1 != c2:
                if i == 0:
                    return 0
                return min(sp1.created_turn, sp2.created_turn)
        
        return min(sp1.created_turn, sp2.created_turn)
    
    def _get_lineage_path(self, lineage_code: str) -> list[str]:
        """获取谱系路径
        
        例如: "A1a1b" -> ["A", "A1", "A1a", "A1a1", "A1a1b"]
        """
        path = []
        current = ""
        
        for char in lineage_code:
            current += char
            if char.isalpha() and len(current) == 1:
                path.append(current)
            elif char.isdigit():
                path.append(current)
            elif char.isalpha() and len(current) > 1:
                path.append(current)
        
        return path
    
    def batch_calculate(self, species_list: Sequence[Species]) -> dict[str, float]:
        """批量计算同属物种间的遗传距离
        
        Args:
            species_list: 同属物种列表
            
        Returns:
            距离字典 {"code1-code2": distance}
        """
        distances = {}
        
        for i, sp1 in enumerate(species_list):
            for sp2 in species_list[i+1:]:
                key = f"{sp1.lineage_code}-{sp2.lineage_code}"
                distances[key] = self.calculate_distance(sp1, sp2)
        
        return distances

