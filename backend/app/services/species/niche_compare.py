"""生态位对比计算模块

提供向量化的生态位相似度、重叠度、竞争强度计算。
三个指标有明确不同的生态学含义：

- 相似度 (similarity): 描述文本的语义相似程度（基于embedding）
- 重叠度 (overlap): 资源利用、栖息地、生态功能的实际重叠
- 竞争强度 (competition_intensity): 考虑种群压力和资源稀缺的真实竞争

【设计原则】
重叠度计算的主要数据来源优先级：
1. 结构化数据（营养级、habitat_type、体型、属性向量）- 最可靠
2. 描述语义相似度（embedding）- 补充结构化数据
3. 关键词匹配 - 仅作为小幅修正，不是主要依据
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

logger = logging.getLogger(__name__)

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species


@dataclass
class NicheCompareResult:
    """生态位对比结果"""
    similarity: float      # 特征相似度 (0-1)
    overlap: float         # 资源重叠度 (0-1)
    competition: float     # 竞争强度 (0-1)
    
    # 详细分解
    details: dict


def compute_niche_metrics(
    species_a: 'Species',
    species_b: 'Species',
    embedding_similarity: float | None = None,
    embedding_vectors: tuple[np.ndarray, np.ndarray] | None = None,
) -> NicheCompareResult:
    """计算两个物种间的生态位指标
    
    Args:
        species_a: 物种A
        species_b: 物种B
        embedding_similarity: 预计算的embedding相似度（基于描述文本）
        embedding_vectors: (vec_a, vec_b) embedding向量对，用于更细粒度的重叠计算
        
    Returns:
        NicheCompareResult 包含三个指标和详细分解
    """
    # ============ 1. 提取结构化特征 ============
    features_a = _extract_species_features(species_a)
    features_b = _extract_species_features(species_b)
    
    # ============ 2. 计算相似度 (Similarity) ============
    # 优先使用embedding相似度（基于描述），否则基于属性计算
    if embedding_similarity is not None:
        base_similarity = embedding_similarity
    else:
        base_similarity = _compute_trait_similarity(features_a, features_b)
    
    # ============ 3. 计算重叠度 (Overlap) ============
    # 主要基于结构化数据 + embedding语义相似度
    overlap, overlap_details = _compute_ecological_overlap(
        species_a, species_b, features_a, features_b,
        embedding_similarity=embedding_similarity
    )
    
    # ============ 4. 计算竞争强度 (Competition) ============
    competition, competition_details = _compute_competition_intensity(
        species_a, species_b, overlap, features_a, features_b
    )
    
    return NicheCompareResult(
        similarity=round(base_similarity, 4),
        overlap=round(overlap, 4),
        competition=round(competition, 4),
        details={
            "overlap_breakdown": overlap_details,
            "competition_breakdown": competition_details,
        }
    )


def _extract_species_features(species: 'Species') -> dict:
    """提取物种的结构化特征（不依赖关键词）"""
    
    # ============ 属性向量（核心数据）============
    trait_names = [
        "耐寒性", "耐热性", "耐旱性", "耐盐性", "光照需求",
        "运动能力", "繁殖速度", "社会性", "攻击性", "防御性"
    ]
    traits = np.array([
        species.abstract_traits.get(t, 5.0) for t in trait_names
    ])
    
    # ============ 形态特征 ============
    body_length = species.morphology_stats.get("body_length_cm", 1.0)
    body_weight = species.morphology_stats.get("body_weight_g", 1.0)
    generation_time = species.morphology_stats.get("generation_time_days", 365)
    metabolic_rate = species.morphology_stats.get("metabolic_rate", 3.0)
    
    # ============ 结构化生态数据（最可靠）============
    trophic_level = species.trophic_level
    habitat_type = getattr(species, 'habitat_type', 'unknown') or 'unknown'
    
    # 根据营养级推断功能群（比关键词更可靠）
    if trophic_level < 1.5:
        functional_group = "producer"
    elif trophic_level < 2.5:
        functional_group = "primary_consumer"
    elif trophic_level < 3.5:
        functional_group = "secondary_consumer"
    else:
        functional_group = "apex_predator"
    
    # 【新增】植物专属字段
    growth_form = getattr(species, 'growth_form', 'aquatic') or 'aquatic'
    life_form_stage = getattr(species, 'life_form_stage', 0) or 0
    
    return {
        "traits": traits,
        "trait_names": trait_names,
        "body_length": body_length,
        "body_weight": body_weight,
        "generation_time": generation_time,
        "metabolic_rate": metabolic_rate,
        "trophic_level": trophic_level,
        "habitat_type": habitat_type,
        "functional_group": functional_group,
        "population": int(species.morphology_stats.get("population", 0) or 0),
        # 植物专属
        "growth_form": growth_form,
        "life_form_stage": life_form_stage,
    }


def _compute_trait_similarity(features_a: dict, features_b: dict) -> float:
    """计算属性向量的余弦相似度（当没有embedding时的后备）"""
    traits_a = features_a["traits"]
    traits_b = features_b["traits"]
    
    norm_a = np.linalg.norm(traits_a)
    norm_b = np.linalg.norm(traits_b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.5
    
    similarity = np.dot(traits_a, traits_b) / (norm_a * norm_b)
    return float(np.clip(similarity, 0.0, 1.0))


def _compute_ecological_overlap(
    species_a: 'Species',
    species_b: 'Species', 
    features_a: dict,
    features_b: dict,
    embedding_similarity: float | None = None,
) -> tuple[float, dict]:
    """计算生态位重叠度
    
    【核心设计】
    重叠度主要基于：
    1. 结构化数据（营养级、栖息地类型、体型、属性）- 权重60%
    2. 描述语义相似度（embedding）- 权重40%
    
    与相似度的区别：
    - 相似度：两个物种"有多像"
    - 重叠度：两个物种"是否竞争相同资源"
    """
    details = {}
    
    # ============ 1. 营养级重叠 (0-1) - 权重25% ============
    # 同营养级物种争夺相同食物来源
    trophic_diff = abs(features_a["trophic_level"] - features_b["trophic_level"])
    if trophic_diff < 0.3:
        trophic_overlap = 1.0  # 几乎同一营养级
    elif trophic_diff < 1.0:
        trophic_overlap = 1.0 - trophic_diff  # 线性下降
    else:
        trophic_overlap = max(0.0, 0.3 - (trophic_diff - 1.0) * 0.15)  # 不同营养级低重叠
    details["trophic_overlap"] = round(trophic_overlap, 3)
    
    # ============ 2. 栖息地类型重叠 (0-1) - 权重20% ============
    # 基于结构化的 habitat_type 字段，不依赖关键词
    habitat_a = features_a["habitat_type"].lower()
    habitat_b = features_b["habitat_type"].lower()
    
    # 定义栖息地兼容性矩阵
    HABITAT_COMPATIBILITY = {
        ("marine", "marine"): 1.0,
        ("marine", "coastal"): 0.7,
        ("marine", "deep_sea"): 0.6,
        ("terrestrial", "terrestrial"): 1.0,
        ("freshwater", "freshwater"): 1.0,
        ("freshwater", "terrestrial"): 0.3,  # 两栖可能
        ("aerial", "terrestrial"): 0.4,
    }
    
    if habitat_a == habitat_b:
        habitat_overlap = 1.0
    else:
        # 查找兼容性（双向）
        key1 = (habitat_a, habitat_b)
        key2 = (habitat_b, habitat_a)
        habitat_overlap = HABITAT_COMPATIBILITY.get(key1, 
                         HABITAT_COMPATIBILITY.get(key2, 0.2))
    details["habitat_overlap"] = round(habitat_overlap, 3)
    
    # ============ 3. 体型重叠 (0-1) - 权重15% ============
    # 体型相近的物种竞争相同大小的食物/空间
    size_a = max(features_a["body_length"], 0.001)
    size_b = max(features_b["body_length"], 0.001)
    size_ratio = max(size_a, size_b) / min(size_a, size_b)
    
    # 使用连续函数而非阶梯
    # size_overlap = 1 / (1 + log2(size_ratio))
    size_overlap = 1.0 / (1.0 + np.log2(max(size_ratio, 1.0)))
    details["size_overlap"] = round(size_overlap, 3)
    
    # ============ 4. 属性需求重叠 (0-1) - 权重15% ============
    # 环境适应性相似的物种占据相似生态位
    trait_diff = np.abs(features_a["traits"] - features_b["traits"])
    # 使用均方根差异，对大差异更敏感
    rms_diff = np.sqrt(np.mean(trait_diff ** 2)) / 10.0
    trait_overlap = max(0.0, 1.0 - rms_diff)
    details["trait_overlap"] = round(trait_overlap, 3)
    
    # ============ 5. 代谢/生活史重叠 (0-1) - 权重5% ============
    # 代谢率和世代时间相近的物种生态位更重叠
    gen_a = max(features_a["generation_time"], 1)
    gen_b = max(features_b["generation_time"], 1)
    gen_ratio = max(gen_a, gen_b) / min(gen_a, gen_b)
    life_history_overlap = 1.0 / (1.0 + np.log10(max(gen_ratio, 1.0)))
    details["life_history_overlap"] = round(life_history_overlap, 3)
    
    # ============ 6. 描述语义重叠 (0-1) - 权重20% ============
    # 这是关键！使用embedding捕捉描述中的生态信息
    if embedding_similarity is not None:
        # 描述相似度可以捕捉到关键词无法覆盖的信息
        # 比如"以小型甲壳类为食"和"捕食浮游动物"语义相近
        semantic_overlap = embedding_similarity
    else:
        # 没有embedding时，使用属性相似度作为代理
        semantic_overlap = trait_overlap
    details["semantic_overlap"] = round(semantic_overlap, 3)
    
    # ============ 综合重叠度 ============
    # 权重分配：结构化数据60% + 语义20%
    overlap = (
        trophic_overlap * 0.25 +        # 营养级（最重要）
        habitat_overlap * 0.20 +        # 栖息地类型
        size_overlap * 0.15 +           # 体型
        trait_overlap * 0.15 +          # 属性需求
        life_history_overlap * 0.05 +   # 生活史
        semantic_overlap * 0.20         # 描述语义
    )
    
    return float(np.clip(overlap, 0.0, 1.0)), details


def _compute_competition_intensity(
    species_a: 'Species',
    species_b: 'Species',
    overlap: float,
    features_a: dict,
    features_b: dict
) -> tuple[float, dict]:
    """计算竞争强度
    
    竞争强度 = 重叠度 × 密度压力 × 资源稀缺度
    
    与重叠度不同，竞争强度反映的是"当前的实际竞争压力"。
    即使重叠度高，如果资源充足或种群稀疏，竞争也不激烈。
    
    【不依赖关键词，使用结构化数据】
    """
    details = {}
    
    pop_a = features_a["population"]
    pop_b = features_b["population"]
    
    # ============ 1. 种群密度因子 (0-1) ============
    # 两个物种种群都大时，竞争更激烈
    if pop_a > 0 and pop_b > 0:
        # 对数尺度，因为种群差异可能很大
        log_pop_a = np.log10(pop_a + 1)
        log_pop_b = np.log10(pop_b + 1)
        
        # 几何平均 / 参考值（10^8为中等种群）
        geo_mean = np.sqrt(log_pop_a * log_pop_b)
        density_factor = min(1.0, geo_mean / 8.0)
    else:
        density_factor = 0.0  # 任一物种种群为0，无竞争
    details["density_factor"] = round(density_factor, 3)
    
    # ============ 2. 种群平衡因子 (0-1) ============
    # 种群规模相近时竞争更激烈
    if pop_a > 0 and pop_b > 0:
        ratio = min(pop_a, pop_b) / max(pop_a, pop_b)
        # 使用平滑函数：sqrt(ratio) 使曲线更平滑
        balance_factor = np.sqrt(ratio)
    else:
        balance_factor = 0.0
    details["balance_factor"] = round(balance_factor, 3)
    
    # ============ 3. 营养级竞争修正 ============
    # 基于结构化的 trophic_level
    trophic_a = features_a["trophic_level"]
    trophic_b = features_b["trophic_level"]
    trophic_diff = abs(trophic_a - trophic_b)
    
    # 同营养级竞争最激烈
    trophic_modifier = max(0.2, 1.0 - trophic_diff * 0.4)
    details["trophic_modifier"] = round(trophic_modifier, 3)
    
    # ============ 4. 功能群竞争修正 ============
    # 基于结构化的 functional_group（由营养级推断）
    func_a = features_a["functional_group"]
    func_b = features_b["functional_group"]
    
    if func_a == func_b:
        if func_a == "producer":
            functional_modifier = 1.3  # 生产者竞争光/养分，资源有限
        elif func_a == "primary_consumer":
            functional_modifier = 1.2  # 初级消费者竞争植物
        else:
            functional_modifier = 1.1  # 高级消费者
    elif {func_a, func_b} == {"primary_consumer", "secondary_consumer"}:
        functional_modifier = 0.6  # 相邻营养级，部分竞争
    else:
        functional_modifier = 0.4  # 不同功能群，主要是捕食而非竞争
    details["functional_modifier"] = round(functional_modifier, 3)
    
    # ============ 5. 体型竞争修正 ============
    # 体型相近时竞争更直接
    size_a = max(features_a["body_length"], 0.001)
    size_b = max(features_b["body_length"], 0.001)
    size_ratio = max(size_a, size_b) / min(size_a, size_b)
    
    size_modifier = 1.0 / (1.0 + np.log2(max(size_ratio, 1.0)) * 0.3)
    details["size_modifier"] = round(size_modifier, 3)
    
    # ============ 【新增】6. 植物生长形式竞争修正 ============
    # 同生长形式的植物竞争更激烈（争夺相同生态位）
    plant_modifier = 1.0
    if func_a == "producer" and func_b == "producer":
        growth_a = features_a.get("growth_form", "aquatic")
        growth_b = features_b.get("growth_form", "aquatic")
        
        if growth_a == growth_b:
            # 同生长形式竞争激烈
            plant_modifier = 1.4
        elif {growth_a, growth_b} in [{"herb", "shrub"}, {"shrub", "tree"}]:
            # 相邻高度层竞争（遮蔽/被遮蔽）
            plant_modifier = 1.2
        else:
            # 不同生态位，竞争减弱
            plant_modifier = 0.8
    details["plant_modifier"] = round(plant_modifier, 3)
    
    # ============ 综合竞争强度 ============
    # 公式：overlap × density × balance × modifiers
    base_competition = overlap * density_factor * (0.3 + 0.7 * balance_factor)
    competition = base_competition * trophic_modifier * functional_modifier * size_modifier * plant_modifier
    
    # 限制在0-1范围
    competition = float(np.clip(competition, 0.0, 1.0))
    
    return competition, details


def compute_batch_niche_matrix(
    species_list: list['Species'],
    embedding_matrix: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """批量计算物种间的生态位矩阵（向量化）
    
    Args:
        species_list: 物种列表
        embedding_matrix: 预计算的embedding相似度矩阵 (N×N)，可选
        
    Returns:
        (similarity_matrix, overlap_matrix, competition_matrix)
        每个都是 N×N 的对称矩阵
    """
    n = len(species_list)
    if n == 0:
        return np.array([]), np.array([]), np.array([])
    
    # 预提取所有物种特征
    all_features = [_extract_species_features(sp) for sp in species_list]
    
    # 初始化矩阵
    similarity_matrix = np.eye(n)
    overlap_matrix = np.eye(n)
    competition_matrix = np.zeros((n, n))
    
    # 计算上三角
    for i in range(n):
        for j in range(i + 1, n):
            # 获取embedding相似度（如果提供了矩阵）
            emb_sim = None
            if embedding_matrix is not None:
                emb_sim = float(embedding_matrix[i, j])
            
            result = compute_niche_metrics(
                species_list[i], species_list[j],
                embedding_similarity=emb_sim
            )
            
            similarity_matrix[i, j] = result.similarity
            similarity_matrix[j, i] = result.similarity
            
            overlap_matrix[i, j] = result.overlap
            overlap_matrix[j, i] = result.overlap
            
            competition_matrix[i, j] = result.competition
            competition_matrix[j, i] = result.competition
    
    return similarity_matrix, overlap_matrix, competition_matrix


def compute_embedding_similarity_matrix(
    descriptions: Sequence[str],
    embedding_service
) -> np.ndarray:
    """批量计算描述文本的embedding相似度矩阵
    
    Args:
        descriptions: 物种描述列表
        embedding_service: EmbeddingService实例
        
    Returns:
        N×N 的余弦相似度矩阵
    """
    n = len(descriptions)
    if n == 0:
        return np.array([])
    
    try:
        # 批量获取embedding
        vectors = embedding_service.embed(list(descriptions), require_real=False)
        vectors = np.array(vectors, dtype=float)
        
        # 计算余弦相似度矩阵
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = vectors / norms
        similarity = normalized @ normalized.T
        similarity = np.clip(similarity, 0.0, 1.0)
        
        return similarity
    except Exception as e:
        logger.warning(f"[生态位] Embedding计算失败: {e}, 返回单位矩阵")
        return np.eye(n)

