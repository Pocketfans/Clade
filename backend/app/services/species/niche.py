from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ...models.species import Species
from ...models.environment import HabitatPopulation
from ..system.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NicheMetrics:
    overlap: float
    saturation: float


class NicheAnalyzer:
    """计算生态位重叠和资源饱和度，用于平衡大量物种。
    
    【重要改进】竞争计算现在考虑地块重叠：
    - 只有在同一地块上的物种才会真正竞争
    - 不同地块上的物种即使生态位相似也不竞争
    """

    def __init__(self, embeddings: EmbeddingService, carrying_capacity: int) -> None:
        self.embeddings = embeddings
        self.carrying_capacity = max(carrying_capacity, 1)
        self._habitat_cache: dict[int, set[int]] = {}  # {species_id: {tile_ids}}

    def analyze(
        self, 
        species_list: Sequence[Species],
        habitat_data: list[HabitatPopulation] | None = None
    ) -> dict[str, NicheMetrics]:
        """分析所有物种的生态位重叠和资源饱和度。
        
        【关键改进】现在考虑地块重叠：
        - 如果两个物种不在同一地块，它们的竞争强度会大幅降低
        - 只有真正共享地块的物种才会产生完全的竞争
        
        Args:
            species_list: 物种列表
            habitat_data: 栖息地分布数据（可选，如果不提供会自动获取）
        """
        if not species_list:
            return {}
        
        try:
            # 构建物种地块映射（用于计算地块重叠）
            self._build_habitat_cache(species_list, habitat_data)
            
            vectors = self._ensure_vectors(species_list)
            similarity = self._cosine_matrix(vectors)
            
            # 应用规则修正：基于功能群和栖息地的生态位重叠度补偿
            similarity = self._apply_ecological_rules(species_list, similarity)
            
            # 【新增】应用地块重叠因子
            similarity = self._apply_tile_overlap_factor(species_list, similarity)
            
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
            logger.error(f"[生态位分析错误] {str(e)}", exc_info=True)
            # 降级：返回默认的低重叠度、低饱和度
            logger.warning(f"[生态位分析] 使用降级策略，为{len(species_list)}个物种生成默认指标")
            return {
                species.lineage_code: NicheMetrics(overlap=0.3, saturation=0.5)
                for species in species_list
            }
    
    def _build_habitat_cache(
        self, 
        species_list: Sequence[Species],
        habitat_data: list[HabitatPopulation] | None = None
    ) -> None:
        """构建物种→地块映射缓存"""
        self._habitat_cache.clear()
        
        if habitat_data is None:
            # 如果没有传入，从数据库获取
            try:
                from ...repositories.environment_repository import environment_repository
                habitat_data = environment_repository.latest_habitats()
            except Exception:
                habitat_data = []
        
        # 构建映射
        for habitat in habitat_data:
            species_id = habitat.species_id
            if species_id not in self._habitat_cache:
                self._habitat_cache[species_id] = set()
            self._habitat_cache[species_id].add(habitat.tile_id)
    
    def _apply_tile_overlap_factor(
        self, 
        species_list: Sequence[Species], 
        similarity: np.ndarray
    ) -> np.ndarray:
        """【关键新增】应用地块重叠因子
        
        只有在同一地块上的物种才会真正竞争。
        
        地块重叠因子计算：
        - overlap_factor = |共享地块数| / |两物种地块总数|
        - 如果没有共享地块，factor = 0.1（保留少量潜在竞争）
        - 如果完全重叠，factor = 1.0
        
        最终相似度 = 原始相似度 × 地块重叠因子
        """
        n = len(species_list)
        if n <= 1:
            return similarity.copy()
        
        species_list = list(species_list)
        adjusted = similarity.copy()
        
        for i in range(n):
            sp_i = species_list[i]
            tiles_i = self._habitat_cache.get(sp_i.id, set()) if sp_i.id else set()
            
            for j in range(i + 1, n):
                sp_j = species_list[j]
                tiles_j = self._habitat_cache.get(sp_j.id, set()) if sp_j.id else set()
                
                # 计算地块重叠
                if tiles_i and tiles_j:
                    shared_tiles = tiles_i & tiles_j
                    total_tiles = tiles_i | tiles_j
                    
                    if total_tiles:
                        # Jaccard 系数：共享地块 / 总地块
                        overlap_factor = len(shared_tiles) / len(total_tiles)
                    else:
                        overlap_factor = 0.1
                    
                    # 如果没有共享地块，保留少量"潜在竞争"（可能会迁徙到同一地块）
                    if len(shared_tiles) == 0:
                        overlap_factor = 0.1  # 10%的潜在竞争
                else:
                    # 没有栖息地数据，假设中等重叠
                    overlap_factor = 0.5
                
                # 应用地块重叠因子
                adjusted[i, j] *= overlap_factor
                adjusted[j, i] *= overlap_factor
        
        return adjusted

    def _ensure_vectors(self, species_list: Sequence[Species]) -> np.ndarray:
        """获取物种的生态位向量
        
        【优化】优先从已有索引获取向量，只对未索引的物种调用embed：
        1. 首先尝试从 EmbeddingService 的物种索引获取已存在的向量
        2. 对于未索引的物种，使用统一的描述文本构建方法生成 embedding
        3. 完善的后备逻辑确保总是返回有效向量
        """
        species_list = list(species_list)
        n = len(species_list)
        
        if n == 0:
            return np.array([])
        
        try:
            # 【优化】先尝试从索引批量获取已存在的向量
            lineage_codes = [sp.lineage_code for sp in species_list]
            indexed_vectors, indexed_codes = self.embeddings.get_species_vectors(lineage_codes)
            
            # 构建代码到向量的映射
            code_to_vector = dict(zip(indexed_codes, indexed_vectors))
            
            # 收集需要新生成向量的物种
            vectors = []
            missing_species = []
            missing_indices = []
            
            for i, sp in enumerate(species_list):
                if sp.lineage_code in code_to_vector:
                    vectors.append(code_to_vector[sp.lineage_code])
                else:
                    vectors.append(None)
                    missing_species.append(sp)
                    missing_indices.append(i)
            
            # 对未索引的物种生成向量
            if missing_species:
                # 使用统一的描述文本构建方法
                from ..system.embedding import EmbeddingService
                descriptions = [
                    EmbeddingService.build_species_text(sp, include_traits=True, include_names=True)
                    for sp in missing_species
                ]
                
                new_vectors = self.embeddings.embed(descriptions, require_real=False)
                
                for i, idx in enumerate(missing_indices):
                    vectors[idx] = new_vectors[i]
            
            # 验证向量并确保维度一致
            if not vectors or any(v is None for v in vectors):
                logger.warning(f"[生态位向量] 部分向量无效，使用默认向量")
                return self._generate_fallback_vectors(species_list)
            
            # 检查维度一致性
            valid_dim = len(vectors[0]) if vectors else 0
            for i, vector in enumerate(vectors):
                if len(vector) != valid_dim:
                    logger.warning(f"[生态位向量] 维度不一致：期望{valid_dim}，得到{len(vector)}")
                    return self._generate_fallback_vectors(species_list)
            
            return np.array(vectors, dtype=float)
        
        except Exception as e:
            logger.error(f"[生态位向量错误] {str(e)}", exc_info=True)
            return self._generate_fallback_vectors(species_list)
    
    def _generate_fallback_vectors(self, species_list: Sequence[Species]) -> np.ndarray:
        """生成基于物种属性的后备向量（当embedding完全失败时使用）。
        
        使用物种的形态和生态属性生成确定性的向量。
        """
        logger.debug(f"[生态位向量] 使用基于属性的后备向量，物种数={len(species_list)}")
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
        """基于生态学规则修正生态位重叠度（向量化优化版）。
        
        【设计原则】主要使用结构化数据，不依赖关键词：
        - 营养级 (trophic_level) - 判断功能群
        - 栖息地类型 (habitat_type) - 判断空间重叠
        - 体型 (body_length_cm) - 判断资源分区
        - 谱系代码 (lineage_code) - 判断亲缘关系
        
        规则：
        - 同营养级（差异<0.5）：+0.12
        - 同栖息地类型：+0.10
        - 体型相近（5倍以内）：+0.06
        - 同属物种（lineage_code前缀相同）：+0.15
        - 最大累积bonus：+0.30
        
        【性能优化】使用NumPy向量化计算，避免嵌套循环。
        """
        n = len(species_list)
        if n <= 1:
            return similarity.copy()
        
        species_list = list(species_list)  # 确保可索引
        
        # ============ 阶段1: 预提取结构化特征（不依赖关键词）============
        trophic_levels = np.array([sp.trophic_level for sp in species_list])
        habitat_types = [getattr(sp, 'habitat_type', 'unknown') or 'unknown' for sp in species_list]
        sizes = np.array([sp.morphology_stats.get("body_length_cm", 0.01) for sp in species_list])
        lineage_codes = [sp.lineage_code for sp in species_list]
        
        # ============ 阶段2: 向量化计算各规则的bonus矩阵 ============
        
        # 规则1：同营养级（基于 trophic_level，不用关键词）
        # 营养级差异 < 0.5 认为是同功能群
        trophic_diff = np.abs(trophic_levels[:, np.newaxis] - trophic_levels[np.newaxis, :])
        functional_bonus = np.where(trophic_diff < 0.5, 0.12, 0.0)
        # 差异0.5-1.0给部分bonus
        functional_bonus = np.where(
            (trophic_diff >= 0.5) & (trophic_diff < 1.0), 
            0.06, 
            functional_bonus
        )
        
        # 规则2：同栖息地类型（基于 habitat_type，不用关键词）
        # 构建栖息地类型矩阵
        habitat_bonus = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                if habitat_types[i] == habitat_types[j]:
                    habitat_bonus[i, j] = 0.10
                elif self._habitats_compatible(habitat_types[i], habitat_types[j]):
                    habitat_bonus[i, j] = 0.05  # 兼容栖息地给部分bonus
                habitat_bonus[j, i] = habitat_bonus[i, j]
        
        # 规则3：体型相近（5倍以内）
        sizes = np.maximum(sizes, 0.001)  # 防止除零
        size_min = np.minimum.outer(sizes, sizes)
        size_max = np.maximum.outer(sizes, sizes)
        size_ratio = size_max / size_min
        # 使用连续函数而非阶梯
        size_bonus = np.where(size_ratio <= 2.0, 0.06, 0.0)
        size_bonus = np.where((size_ratio > 2.0) & (size_ratio <= 5.0), 0.03, size_bonus)
        
        # 规则4：同属物种（前缀匹配>=2）
        lineage_bonus = self._compute_lineage_bonus_matrix(lineage_codes)
        
        # ============ 阶段3: 组合并应用bonus ============
        total_bonus = functional_bonus + habitat_bonus + size_bonus + lineage_bonus
        total_bonus = np.minimum(total_bonus, 0.30)  # 限制上限
        
        # 只取上三角（避免重复计算）
        adjusted = similarity.copy()
        upper_mask = np.triu(np.ones((n, n), dtype=bool), k=1)
        
        adjusted = np.where(upper_mask, np.minimum(1.0, adjusted + total_bonus), adjusted)
        # 对称化
        adjusted = np.triu(adjusted, k=1) + np.triu(adjusted, k=1).T + np.diag(np.diag(adjusted))
        
        return adjusted
    
    def _habitats_compatible(self, h1: str, h2: str) -> bool:
        """检查两个栖息地类型是否兼容"""
        h1, h2 = h1.lower(), h2.lower()
        
        # 定义兼容组
        compatible_groups = [
            {"marine", "coastal", "deep_sea"},  # 海洋相关
            {"freshwater", "terrestrial"},       # 淡水-陆地（两栖）
            {"terrestrial", "aerial"},           # 陆地-空中
        ]
        
        for group in compatible_groups:
            if h1 in group and h2 in group:
                return True
        return False
    
    def _compute_lineage_bonus_matrix(self, lineage_codes: list[str]) -> np.ndarray:
        """计算谱系前缀匹配的bonus矩阵
        
        如果两个物种共享>=2个前缀字符，bonus=0.15
        """
        n = len(lineage_codes)
        bonus = np.zeros((n, n))
        
        for i in range(n):
            code_i = lineage_codes[i]
            if len(code_i) < 2:
                continue
            for j in range(i + 1, n):
                code_j = lineage_codes[j]
                if len(code_j) < 2:
                    continue
                
                # 计算共同前缀长度
                common_len = 0
                for ci, cj in zip(code_i, code_j):
                    if ci == cj:
                        common_len += 1
                    else:
                        break
                
                if common_len >= 2:
                    bonus[i, j] = 0.15
                    bonus[j, i] = 0.15
        
        return bonus
