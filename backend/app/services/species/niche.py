from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ...models.species import Species
from ..system.embedding import EmbeddingService


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
        """分析所有物种的生态位重叠和资源饱和度。
        
        这个方法非常关键，任何错误都会中断模拟进程，因此需要完善的异常处理。
        """
        if not species_list:
            return {}
        
        try:
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
        except Exception as e:
            print(f"[生态位分析错误] {str(e)}")
            import traceback
            print(traceback.format_exc())
            # 降级：返回默认的低重叠度、低饱和度
            print(f"[生态位分析] 使用降级策略，为{len(species_list)}个物种生成默认指标")
            return {
                species.lineage_code: NicheMetrics(overlap=0.3, saturation=0.5)
                for species in species_list
            }

    def _ensure_vectors(self, species_list: Sequence[Species]) -> np.ndarray:
        """使用 embedding 服务统一计算所有物种的生态位向量。
        
        注意：不再使用 species.ecological_vector 字段，而是始终基于 description 计算 embedding。
        这确保了向量维度的一致性，并且能够捕捉物种描述中的所有生态位信息。
        
        关键改进：
        1. 不要求真实embedding（require_real=False），允许使用fake向量
        2. 完善的向量验证和降级逻辑
        3. 确保维度一致性
        """
        try:
            # 收集所有物种的描述
            descriptions = [species.description for species in species_list]
            
            # 批量计算 embedding (不要求真实向量，允许降级)
            vectors = self.embeddings.embed(descriptions, require_real=False)
            
            # 验证向量并确保维度一致
            if not vectors or len(vectors) != len(species_list):
                print(f"[生态位向量] Embedding返回向量数量不匹配，使用默认向量")
                return self._generate_fallback_vectors(species_list)
            
            # 检查所有向量是否有效且维度一致
            valid_dim = None
            for i, vector in enumerate(vectors):
                if not vector or len(vector) == 0:
                    print(f"[生态位向量] 物种 {species_list[i].common_name} 的向量无效")
                    return self._generate_fallback_vectors(species_list)
                if valid_dim is None:
                    valid_dim = len(vector)
                elif len(vector) != valid_dim:
                    print(f"[生态位向量] 维度不一致：期望{valid_dim}，得到{len(vector)}")
                    return self._generate_fallback_vectors(species_list)
            
            return np.array(vectors, dtype=float)
        
        except Exception as e:
            print(f"[生态位向量错误] {str(e)}")
            import traceback
            print(traceback.format_exc())
            return self._generate_fallback_vectors(species_list)
    
    def _generate_fallback_vectors(self, species_list: Sequence[Species]) -> np.ndarray:
        """生成基于物种属性的后备向量（当embedding完全失败时使用）。
        
        使用物种的形态和生态属性生成确定性的向量。
        """
        print(f"[生态位向量] 使用基于属性的后备向量，物种数={len(species_list)}")
        vectors = []
        for species in species_list:
            # 基于物种属性生成64维向量
            feature_vector = []
            
            # 1-10: 形态特征 (10维)
            feature_vector.append(np.log10(species.morphology_stats.get("body_length_cm", 1.0) + 1))
            feature_vector.append(np.log10(species.morphology_stats.get("body_weight_g", 1.0) + 1))
            feature_vector.append(species.morphology_stats.get("metabolic_rate", 3.0) / 10.0)
            feature_vector.append(species.morphology_stats.get("lifespan_days", 365) / 36500.0)
            feature_vector.append(species.morphology_stats.get("generation_time_days", 365) / 3650.0)
            feature_vector.extend([0.0] * 5)  # 预留形态特征
            
            # 11-20: 抽象特征 (10维)
            trait_names = ["耐寒性", "耐热性", "耐旱性", "耐盐性", "光照需求", 
                          "氧气需求", "繁殖速度", "运动能力", "社会性", "耐酸碱性"]
            for trait_name in trait_names:
                feature_vector.append(species.abstract_traits.get(trait_name, 5.0) / 10.0)
            
            # 21-30: 生态特征 (10维)
            feature_vector.append(species.trophic_level / 5.0)
            feature_vector.append(float(species.habitat_type == "marine"))
            feature_vector.append(float(species.habitat_type == "terrestrial"))
            feature_vector.append(float(species.habitat_type == "freshwater"))
            feature_vector.append(float(species.habitat_type == "aerial"))
            feature_vector.append(len(species.capabilities) / 10.0)
            feature_vector.extend([0.0] * 4)  # 预留生态特征
            
            # 31-64: 描述文本的简单特征 (34维)
            desc_lower = species.description.lower()
            keywords = ["光合", "捕食", "滤食", "腐食", "寄生", "共生", "群居", "独居",
                       "日行", "夜行", "迁徙", "冬眠", "变温", "恒温", "卵生", "胎生",
                       "水生", "陆生", "飞行", "游泳", "奔跑", "攀爬", "挖掘", "跳跃",
                       "视觉", "嗅觉", "听觉", "触觉", "电感", "磁感", "回声", "发光",
                       "毒性", "伪装"]
            for keyword in keywords:
                feature_vector.append(1.0 if keyword in desc_lower else 0.0)
            
            # 归一化
            vector_array = np.array(feature_vector, dtype=float)
            norm = np.linalg.norm(vector_array)
            if norm > 0:
                vector_array = vector_array / norm
            vectors.append(vector_array)
        
        return np.array(vectors, dtype=float)

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
