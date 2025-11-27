"""遗传距离计算服务

【性能优化】使用NumPy向量化计算批量遗传距离。
【embedding支持】可选使用描述文本的语义距离作为遗传距离的一个维度。
"""
from __future__ import annotations

import math
from typing import Sequence, TYPE_CHECKING

import numpy as np

from ...models.species import Species

if TYPE_CHECKING:
    from ..system.embedding import EmbeddingService


# 标准属性列表（用于向量化计算）
STANDARD_TRAITS = [
    "耐寒性", "耐热性", "耐旱性", "耐盐性", "光照需求",
    "运动能力", "繁殖速度", "社会性", "攻击性", "防御性"
]


class GeneticDistanceCalculator:
    """计算物种间遗传距离
    
    【向量化优化】batch_calculate_vectorized 使用NumPy批量计算，
    在物种数量较多时（>10）显著提升性能。
    
    【embedding支持】可传入embedding_service来使用描述语义距离。
    """
    
    def __init__(self, embedding_service: 'EmbeddingService | None' = None):
        """初始化遗传距离计算器
        
        Args:
            embedding_service: 可选的embedding服务，用于计算描述语义距离
        """
        self.embedding_service = embedding_service
    
    def calculate_distance(
        self, 
        sp1: Species, 
        sp2: Species,
        embedding_distance: float | None = None
    ) -> float:
        """基于多维度计算遗传距离（单对物种）
        
        Args:
            sp1, sp2: 待比较的物种
            embedding_distance: 预计算的描述语义距离（可选）
            
        Returns:
            遗传距离 0.0-1.0，0表示同种，1表示完全隔离
        """
        morphology_diff = self._morphology_difference(sp1, sp2)
        trait_diff = self._trait_difference(sp1, sp2)
        organ_diff = self._organ_difference(sp1, sp2)
        time_diff = self._time_divergence(sp1, sp2)
        
        # 如果有embedding距离，使用新的权重分配
        if embedding_distance is not None:
            # 描述语义距离反映了表型/生态差异
            distance = (
                morphology_diff * 0.20 +      # 降低形态权重
                trait_diff * 0.20 +           # 降低属性权重
                organ_diff * 0.20 +           # 降低器官权重
                time_diff * 0.20 +            # 保持时间权重
                embedding_distance * 0.20     # 新增描述语义距离
            )
        else:
            # 原始权重
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
    
    def batch_calculate(
        self, 
        species_list: Sequence[Species],
        use_embedding: bool = True
    ) -> dict[str, float]:
        """批量计算同属物种间的遗传距离（自动选择优化方法）
        
        当物种数量>10时使用向量化方法，否则使用逐对计算。
        
        Args:
            species_list: 同属物种列表
            use_embedding: 是否使用embedding计算描述语义距离
            
        Returns:
            距离字典 {"code1-code2": distance}
        """
        n = len(species_list)
        
        # 计算embedding距离矩阵（如果可用）
        embedding_matrix = None
        if use_embedding and self.embedding_service is not None and n > 1:
            embedding_matrix = self._compute_embedding_distance_matrix(species_list)
        
        # 小规模使用原方法，大规模使用向量化
        if n <= 10:
            return self._batch_calculate_simple(species_list, embedding_matrix)
        else:
            return self._batch_calculate_vectorized(species_list, embedding_matrix)
    
    def _batch_calculate_simple(
        self, 
        species_list: Sequence[Species],
        embedding_matrix: np.ndarray | None = None
    ) -> dict[str, float]:
        """原始逐对计算方法"""
        distances = {}
        species_list = list(species_list)
        
        for i, sp1 in enumerate(species_list):
            for j, sp2 in enumerate(species_list[i+1:], start=i+1):
                key = f"{sp1.lineage_code}-{sp2.lineage_code}"
                
                # 获取embedding距离（如果有）
                emb_dist = None
                if embedding_matrix is not None:
                    emb_dist = float(embedding_matrix[i, j])
                
                distances[key] = self.calculate_distance(sp1, sp2, embedding_distance=emb_dist)
        
        return distances
    
    def _batch_calculate_vectorized(
        self, 
        species_list: Sequence[Species],
        embedding_matrix: np.ndarray | None = None
    ) -> dict[str, float]:
        """向量化批量计算遗传距离
        
        使用NumPy广播计算成对差异，显著提升性能。
        
        Args:
            species_list: 物种列表
            embedding_matrix: 预计算的描述语义距离矩阵（可选）
        """
        n = len(species_list)
        species_list = list(species_list)  # 确保可索引
        
        # ============ 提取特征矩阵 ============
        # 形态特征
        lengths = np.array([
            sp.morphology_stats.get("body_length_cm", 1.0) for sp in species_list
        ], dtype=float)
        weights = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0) for sp in species_list
        ], dtype=float)
        
        # 确保非零（防止除零）
        lengths = np.maximum(lengths, 0.001)
        weights = np.maximum(weights, 0.001)
        
        # 属性矩阵 (n x k)
        trait_matrix = np.zeros((n, len(STANDARD_TRAITS)))
        for i, sp in enumerate(species_list):
            for j, trait_name in enumerate(STANDARD_TRAITS):
                trait_matrix[i, j] = sp.abstract_traits.get(trait_name, 5.0)
        
        # 器官集合（用于 Jaccard 距离）
        organ_sets = [set(sp.organs.keys()) for sp in species_list]
        
        # 时间信息
        created_turns = np.array([sp.created_turn for sp in species_list], dtype=float)
        lineage_paths = [self._get_lineage_path(sp.lineage_code) for sp in species_list]
        
        # ============ 向量化计算形态差异 ============
        length_min = np.minimum.outer(lengths, lengths)
        length_max = np.maximum.outer(lengths, lengths)
        length_ratio = length_min / length_max
        length_diff = 1.0 - length_ratio
        
        weight_min = np.minimum.outer(weights, weights)
        weight_max = np.maximum.outer(weights, weights)
        weight_ratio = weight_min / weight_max
        weight_diff = 1.0 - weight_ratio
        
        morphology_diff_matrix = (length_diff + weight_diff) / 2
        
        # ============ 向量化计算属性差异 ============
        trait_diff_raw = trait_matrix[:, np.newaxis, :] - trait_matrix[np.newaxis, :, :]
        trait_diff_sq = (trait_diff_raw / 15.0) ** 2
        trait_diff_matrix = np.sqrt(np.mean(trait_diff_sq, axis=2))
        
        # ============ 计算器官差异（需要逐对）============
        organ_diff_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                union = organ_sets[i] | organ_sets[j]
                if len(union) == 0:
                    organ_diff_matrix[i, j] = 0.0
                else:
                    symmetric = organ_sets[i] ^ organ_sets[j]
                    organ_diff_matrix[i, j] = len(symmetric) / len(union)
                organ_diff_matrix[j, i] = organ_diff_matrix[i, j]
        
        # ============ 计算时间差异（需要逐对）============
        time_diff_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                common_turn = self._find_common_ancestor_turn_by_paths(
                    lineage_paths[i], lineage_paths[j],
                    int(created_turns[i]), int(created_turns[j])
                )
                current_turn = max(created_turns[i], created_turns[j])
                divergence = current_turn - common_turn
                time_diff_matrix[i, j] = min(1.0, divergence / 500)
                time_diff_matrix[j, i] = time_diff_matrix[i, j]
        
        # ============ 组合距离（根据是否有embedding调整权重）============
        if embedding_matrix is not None:
            # 有embedding时，使用新权重
            distance_matrix = (
                morphology_diff_matrix * 0.20 +
                trait_diff_matrix * 0.20 +
                organ_diff_matrix * 0.20 +
                time_diff_matrix * 0.20 +
                embedding_matrix * 0.20  # 描述语义距离
            )
        else:
            # 无embedding时，使用原权重
            distance_matrix = (
                morphology_diff_matrix * 0.30 +
                trait_diff_matrix * 0.25 +
                organ_diff_matrix * 0.25 +
                time_diff_matrix * 0.20
            )
        
        distance_matrix = np.minimum(distance_matrix, 1.0)
        
        # ============ 提取上三角结果 ============
        distances = {}
        for i in range(n):
            for j in range(i + 1, n):
                key = f"{species_list[i].lineage_code}-{species_list[j].lineage_code}"
                distances[key] = float(distance_matrix[i, j])
        
        return distances
    
    def _compute_embedding_distance_matrix(self, species_list: Sequence[Species]) -> np.ndarray:
        """计算描述文本的语义距离矩阵
        
        使用embedding服务计算物种描述的语义相似度，然后转换为距离。
        
        Returns:
            N×N 的距离矩阵（1 - 余弦相似度）
        """
        n = len(species_list)
        if n == 0 or self.embedding_service is None:
            return np.zeros((n, n))
        
        try:
            # 收集描述
            descriptions = [sp.description for sp in species_list]
            
            # 批量获取embedding
            vectors = self.embedding_service.embed(descriptions, require_real=False)
            vectors = np.array(vectors, dtype=float)
            
            # 计算余弦相似度矩阵
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            normalized = vectors / norms
            similarity = normalized @ normalized.T
            similarity = np.clip(similarity, 0.0, 1.0)
            
            # 转换为距离：distance = 1 - similarity
            distance = 1.0 - similarity
            
            return distance
            
        except Exception as e:
            print(f"[遗传距离] Embedding计算失败: {e}")
            return np.zeros((n, n))
    
    def _find_common_ancestor_turn_by_paths(
        self, path1: list[str], path2: list[str],
        turn1: int, turn2: int
    ) -> int:
        """使用预计算的谱系路径查找共同祖先回合"""
        for i, (c1, c2) in enumerate(zip(path1, path2)):
            if c1 != c2:
                if i == 0:
                    return 0
                return min(turn1, turn2)
        return min(turn1, turn2)
    
    def get_distance_matrix(self, species_list: Sequence[Species]) -> tuple[np.ndarray, list[str]]:
        """返回完整的距离矩阵和物种代码列表
        
        用于需要矩阵形式数据的场景（如聚类分析）。
        
        Args:
            species_list: 物种列表
            
        Returns:
            (distance_matrix, lineage_codes) - n×n距离矩阵和对应的谱系代码列表
        """
        species_list = list(species_list)
        n = len(species_list)
        
        if n == 0:
            return np.array([]), []
        
        lineage_codes = [sp.lineage_code for sp in species_list]
        
        # 使用向量化方法计算
        distances_dict = self._batch_calculate_vectorized(species_list) if n > 1 else {}
        
        # 构建对称矩阵
        matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                key = f"{lineage_codes[i]}-{lineage_codes[j]}"
                dist = distances_dict.get(key, 0.0)
                matrix[i, j] = dist
                matrix[j, i] = dist
        
        return matrix, lineage_codes

