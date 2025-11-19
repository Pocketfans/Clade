from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..models.species import Species
from .embedding import EmbeddingService


@dataclass(slots=True)
class NicheMetrics:
    overlap: float
    saturation: float


class NicheAnalyzer:
    """计算生态位重叠和资源饱和度，用于平衡大量物种。"""

    def __init__(self, embeddings: EmbeddingService, carrying_capacity: int) -> None:
        self.embeddings = embeddings
        self.carrying_capacity = max(carrying_capacity, 1)

    def analyze(self, species_list: Sequence[Species]) -> dict[str, NicheMetrics]:
        if not species_list:
            return {}
        vectors = self._ensure_vectors(species_list)
        similarity = self._cosine_matrix(vectors)
        
        # 应用规则修正：基于功能群和栖息地的生态位重叠度补偿
        similarity = self._apply_ecological_rules(species_list, similarity)
        
        niche_data: dict[str, NicheMetrics] = {}
        total_slots = self.carrying_capacity or 1
        per_species_capacity = total_slots / max(len(species_list), 1)
        for idx, species in enumerate(species_list):
            population = float(species.morphology_stats.get("population", 0) or 0)
            if len(species_list) > 1:
                overlap = (similarity[idx].sum() - 1.0) / (len(species_list) - 1)
            else:
                overlap = 0.0
            saturation = min(2.0, population / max(per_species_capacity, 1.0))
            niche_data[species.lineage_code] = NicheMetrics(overlap=overlap, saturation=saturation)
        return niche_data

    def _ensure_vectors(self, species_list: Sequence[Species]) -> np.ndarray:
        """使用 embedding 服务统一计算所有物种的生态位向量。
        
        注意：不再使用 species.ecological_vector 字段，而是始终基于 description 计算 embedding。
        这确保了向量维度的一致性，并且能够捕捉物种描述中的所有生态位信息。
        """
        # 收集所有物种的描述
        descriptions = [species.description for species in species_list]
        
        # 批量计算 embedding
        vectors = self.embeddings.embed(descriptions)
        
        # 确保所有向量都有效
        validated_vectors: list[list[float]] = []
        for vector in vectors:
            if vector and len(vector) > 0:
                validated_vectors.append(vector)
            else:
                # 如果 embedding 失败，使用零向量（长度与第一个有效向量相同）
                dim = len(validated_vectors[0]) if validated_vectors else 128
                validated_vectors.append([0.0] * dim)
        
        return np.array(validated_vectors, dtype=float)

    def _cosine_matrix(self, vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = vectors / norms
        similarity = normalized @ normalized.T
        similarity = np.clip(similarity, -1.0, 1.0)
        return similarity
    
    def _apply_ecological_rules(self, species_list: Sequence[Species], similarity: np.ndarray) -> np.ndarray:
        """基于生态学规则修正生态位重叠度。
        
        修正原因：
        1. Embedding向量可能低估功能相似物种的重叠度
        2. 同营养级、同栖息地的物种应有更高重叠
        3. 体型相近的物种竞争更激烈
        
        规则：
        - 同功能群（如都是光合作用生产者）：+0.12
        - 同栖息地（如都在海洋）：+0.08
        - 体型相近（5倍以内）：+0.06
        - 同属物种（lineage_code前缀相同）：+0.15
        - 最大累积bonus：+0.30
        """
        n = len(species_list)
        adjusted = similarity.copy()
        
        for i in range(n):
            desc_i = species_list[i].description.lower()
            code_i = species_list[i].lineage_code
            size_i = species_list[i].morphology_stats.get("body_length_cm", 0.01)
            
            for j in range(i + 1, n):
                desc_j = species_list[j].description.lower()
                code_j = species_list[j].lineage_code
                size_j = species_list[j].morphology_stats.get("body_length_cm", 0.01)
                
                bonus = 0.0
                
                # 规则1：同功能群检测
                producers_i = any(kw in desc_i for kw in ["光合", "藻", "植物", "自养"])
                producers_j = any(kw in desc_j for kw in ["光合", "藻", "植物", "自养"])
                consumers_i = any(kw in desc_i for kw in ["捕食", "掠食", "异养", "滤食"])
                consumers_j = any(kw in desc_j for kw in ["捕食", "掠食", "异养", "滤食"])
                
                if (producers_i and producers_j) or (consumers_i and consumers_j):
                    bonus += 0.12
                
                # 规则2：同栖息地检测（降低bonus从0.15到0.08）
                habitats_i = set()
                habitats_j = set()
                for habitat in ["海洋", "浅海", "深海", "淡水", "陆地", "森林", "草原", "沙漠"]:
                    if habitat in desc_i:
                        habitats_i.add(habitat)
                    if habitat in desc_j:
                        habitats_j.add(habitat)
                
                if habitats_i & habitats_j:  # 有交集
                    bonus += 0.08
                
                # 规则3：体型相近检测
                if size_i > 0 and size_j > 0:
                    size_ratio = max(size_i, size_j) / min(size_i, size_j)
                    if size_ratio <= 5.0:  # 5倍以内认为体型相近
                        bonus += 0.06
                
                # 规则4：同属物种检测
                # A1a1 和 A1a2 应该有高重叠
                if len(code_i) >= 2 and len(code_j) >= 2:
                    # 至少共享前2个字符
                    common_prefix = 0
                    for ci, cj in zip(code_i, code_j):
                        if ci == cj:
                            common_prefix += 1
                        else:
                            break
                    if common_prefix >= 2:
                        bonus += 0.15
                
                # 应用修正
                bonus = min(bonus, 0.30)  # 限制总bonus上限
                adjusted[i, j] = min(1.0, adjusted[i, j] + bonus)
                adjusted[j, i] = adjusted[i, j]  # 对称矩阵
        
        return adjusted
