"""生态位共存系统 - 模拟多物种共存与微生态位分化

【核心设计哲学】
一个8万平方公里的地块可以容纳非常多物种共存！
竞争排斥只发生在**生态位高度重叠**的物种之间。

【性能优化 v4】
1. 使用Embedding相似度矩阵（批量计算所有物种对）
2. 使用numpy矩阵运算（批量计算所有地块）
3. 特征相似度 + 语义相似度混合计算

【Embedding集成】
生态位相似度 = 特征相似度 × 0.6 + Embedding语义相似度 × 0.4
- 特征相似度：基于营养级、体型、栖息地、特质的结构化计算
- 语义相似度：基于物种描述的embedding向量余弦相似度

【矩阵化计算】
1. 物种相似度矩阵 (n_species × n_species)：预计算所有物种对的相似度
2. 种群矩阵 (n_tiles × n_species)：每个地块每个物种的种群
3. 占据度矩阵 (n_tiles × n_species)：每个地块每个物种的占据度
4. 竞争压力矩阵 (n_tiles × n_species)：每个地块每个物种受到的竞争压力

【竞争规则 v3】
1. 同层+生态位相似度>70%：强竞争（互相排斥）
2. 同层+生态位相似度50-70%：弱竞争（共存但有压力）
3. 同层+生态位相似度<50%：可完全共存（微生态位分化）
4. 不同层：完全共存（捕食关系另算）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.environment import HabitatPopulation, MapTile
    from ...models.species import Species
    from ..system.embedding import EmbeddingService

from ...repositories.environment_repository import environment_repository

logger = logging.getLogger(__name__)


# ==================== 矩阵化工具函数 ====================

def compute_feature_similarity_matrix(
    species_list: Sequence['Species']
) -> np.ndarray:
    """批量计算所有物种对的特征相似度矩阵
    
    【矩阵化计算】一次性计算 n_species × n_species 的相似度矩阵
    
    Returns:
        (n_species, n_species) 相似度矩阵，对角线为1
    """
    n = len(species_list)
    if n == 0:
        return np.array([])
    
    # 提取特征向量 (n_species, n_features)
    # 特征：[营养级, log体型, 栖息地编码, 耐热性, 耐寒性, 耐旱性]
    features = np.zeros((n, 6), dtype=np.float32)
    
    # 栖息地类型编码
    habitat_encoding = {
        'terrestrial': 0, 'marine': 1, 'freshwater': 2,
        'coastal': 3, 'aerial': 4, 'deep_sea': 5
    }
    
    for i, sp in enumerate(species_list):
        features[i, 0] = getattr(sp, 'trophic_level', 1.0) / 5.0  # 归一化营养级
        
        body_size = sp.morphology_stats.get("body_length_cm", 10.0) or 10.0
        features[i, 1] = np.log10(max(body_size, 0.01)) / 4.0  # 归一化对数体型
        
        habitat = getattr(sp, 'habitat_type', 'terrestrial')
        features[i, 2] = habitat_encoding.get(habitat, 0) / 5.0
        
        traits = sp.abstract_traits or {}
        features[i, 3] = traits.get("耐热性", 5) / 10.0
        features[i, 4] = traits.get("耐寒性", 5) / 10.0
        features[i, 5] = traits.get("耐旱性", 5) / 10.0
    
    # 计算欧几里得距离矩阵 (n × n)
    # dist[i,j] = ||features[i] - features[j]||
    diff = features[:, np.newaxis, :] - features[np.newaxis, :, :]  # (n, n, 6)
    distances = np.sqrt((diff ** 2).sum(axis=2))  # (n, n)
    
    # 转换为相似度（距离越小越相似）
    max_dist = np.sqrt(6)  # 最大可能距离
    similarity = 1.0 - (distances / max_dist)
    
    # 确保对角线为1
    np.fill_diagonal(similarity, 1.0)
    
    return np.clip(similarity, 0.0, 1.0)


def compute_layer_mask_matrix(
    species_list: Sequence['Species']
) -> np.ndarray:
    """计算同层掩码矩阵
    
    只有同一生态层的物种才会竞争
    
    Returns:
        (n_species, n_species) 布尔矩阵，同层为True
    """
    n = len(species_list)
    if n == 0:
        return np.array([])
    
    # 获取每个物种的生态层
    layers = np.array([get_ecological_layer(getattr(sp, 'trophic_level', 1.0)) for sp in species_list])
    
    # 同层掩码
    same_layer = layers[:, np.newaxis] == layers[np.newaxis, :]
    
    return same_layer


# 生态层定义（基于营养级）
ECOLOGICAL_LAYERS = {
    1: {"name": "生产者", "trophic_min": 1.0, "trophic_max": 1.5},
    2: {"name": "初级消费者", "trophic_min": 1.5, "trophic_max": 2.5},
    3: {"name": "次级消费者", "trophic_min": 2.5, "trophic_max": 3.5},
    4: {"name": "三级消费者", "trophic_min": 3.5, "trophic_max": 4.5},
    5: {"name": "顶级捕食者", "trophic_min": 4.5, "trophic_max": 10.0},
}

# 生态位相似度阈值
NICHE_STRONG_COMPETITION = 0.70   # >70%：强竞争，互相排斥
NICHE_WEAK_COMPETITION = 0.50     # 50-70%：弱竞争，共存但有压力
NICHE_COEXISTENCE = 0.50          # <50%：可完全共存


def get_ecological_layer(trophic_level: float) -> int:
    """根据营养级获取所属生态层"""
    for layer_id, layer_info in ECOLOGICAL_LAYERS.items():
        if layer_info["trophic_min"] <= trophic_level < layer_info["trophic_max"]:
            return layer_id
    return 5  # 默认顶级


def compute_niche_similarity(
    species_a: 'Species',
    species_b: 'Species'
) -> float:
    """计算两个物种的生态位相似度
    
    【核心函数】决定两个物种是否会竞争
    
    维度：
    1. 营养级差异（25%）- 差异越小越竞争
    2. 体型差异（20%）- 体型相近更竞争
    3. 栖息地类型（20%）- 同栖息地更竞争
    4. 特质相似度（20%）- 属性相近更竞争
    5. 功能群（15%）- 同功能群更竞争
    
    Returns:
        0.0-1.0 的相似度，越高越竞争
    """
    # 1. 营养级相似度 (25%)
    trophic_a = getattr(species_a, 'trophic_level', 1.0)
    trophic_b = getattr(species_b, 'trophic_level', 1.0)
    trophic_diff = abs(trophic_a - trophic_b)
    trophic_sim = max(0.0, 1.0 - trophic_diff / 2.0)  # 差2级以上=0
    
    # 2. 体型相似度 (20%)
    size_a = species_a.morphology_stats.get("body_length_cm", 10.0) or 10.0
    size_b = species_b.morphology_stats.get("body_length_cm", 10.0) or 10.0
    # 使用对数比较（体型差10倍才是显著差异）
    log_ratio = abs(np.log10(max(size_a, 0.01)) - np.log10(max(size_b, 0.01)))
    size_sim = max(0.0, 1.0 - log_ratio / 2.0)  # 差100倍=0
    
    # 3. 栖息地相似度 (20%)
    habitat_a = getattr(species_a, 'habitat_type', 'terrestrial')
    habitat_b = getattr(species_b, 'habitat_type', 'terrestrial')
    if habitat_a == habitat_b:
        habitat_sim = 1.0
    elif {habitat_a, habitat_b} in [{'marine', 'coastal'}, {'freshwater', 'coastal'}]:
        habitat_sim = 0.6  # 相邻栖息地
    else:
        habitat_sim = 0.2  # 不同栖息地
    
    # 4. 特质相似度 (20%)
    traits_a = species_a.abstract_traits or {}
    traits_b = species_b.abstract_traits or {}
    
    trait_keys = ["耐热性", "耐寒性", "耐旱性", "繁殖策略", "群居性"]
    trait_diffs = []
    for key in trait_keys:
        val_a = traits_a.get(key, 5)
        val_b = traits_b.get(key, 5)
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            trait_diffs.append(abs(val_a - val_b) / 10.0)
    
    if trait_diffs:
        trait_sim = 1.0 - (sum(trait_diffs) / len(trait_diffs))
    else:
        trait_sim = 0.5  # 默认中等相似
    
    # 5. 功能群相似度 (15%)
    # 检查是否是同一类生物（如都是哺乳动物、都是鸟类等）
    desc_a = species_a.description.lower() if species_a.description else ""
    desc_b = species_b.description.lower() if species_b.description else ""
    
    functional_keywords = [
        ("哺乳", "mammal"), ("鸟", "bird", "avian"),
        ("爬行", "reptile"), ("两栖", "amphibian"),
        ("鱼", "fish"), ("昆虫", "insect"),
        ("植物", "plant"), ("藻", "algae")
    ]
    
    func_a = None
    func_b = None
    for keywords in functional_keywords:
        if any(kw in desc_a for kw in keywords):
            func_a = keywords[0]
        if any(kw in desc_b for kw in keywords):
            func_b = keywords[0]
    
    if func_a and func_b:
        func_sim = 1.0 if func_a == func_b else 0.3
    else:
        func_sim = 0.5  # 无法判断
    
    # 综合计算
    total_similarity = (
        trophic_sim * 0.25 +
        size_sim * 0.20 +
        habitat_sim * 0.20 +
        trait_sim * 0.20 +
        func_sim * 0.15
    )
    
    return float(np.clip(total_similarity, 0.0, 1.0))


@dataclass
class TerritoryStatus:
    """物种在特定地块的领地状态"""
    tile_id: int
    species_id: int
    lineage_code: str
    ecological_layer: int = 1  # 【新增】所属生态层
    
    # 控制度 (0-1): 0=无控制, 1=完全控制
    control_level: float = 0.0
    
    # 领地类型
    territory_type: str = "none"  # "core" | "frontier" | "contested" | "none"
    
    # 竞争对手信息（只记录同层竞争者）
    top_competitor: str | None = None  # 同层最大竞争对手的lineage_code
    competitor_control: float = 0.0     # 竞争对手的控制度
    
    # 历史信息
    turns_held: int = 0               # 连续控制回合数
    peak_control: float = 0.0          # 历史最高控制度


@dataclass
class TerritoryUpdate:
    """领地更新结果"""
    lineage_code: str
    ecological_layer: int = 1  # 【新增】所属生态层
    tiles_gained: list[int] = field(default_factory=list)      # 新获得的地块
    tiles_lost: list[int] = field(default_factory=list)        # 失去的地块
    core_tiles: list[int] = field(default_factory=list)        # 核心领地（根据地）
    frontier_tiles: list[int] = field(default_factory=list)    # 边疆地块
    contested_tiles: list[int] = field(default_factory=list)   # 争议地块
    
    total_control: float = 0.0         # 总控制度
    average_control: float = 0.0       # 平均控制度
    is_layer_dominant: bool = False    # 【新增】是否为该层主导物种


class TerritorySystem:
    """生态位共存系统（矩阵化版本）
    
    【核心改进】
    1. 使用numpy矩阵批量计算所有地块和物种
    2. 集成Embedding服务计算语义相似度
    3. 特征相似度+语义相似度混合计算
    
    关键概念：
    - 生态位占据度：物种在地块的"存在强度"（0-1）
    - 生态位相似度：决定两个物种是否竞争（相似度>70%才强竞争）
    - 多物种共存：同一地块同一层可以有多个成功物种
    """
    
    # 占据度阈值
    ESTABLISHED_THRESHOLD = 0.60   # >60%为稳定栖息地
    PRESENT_THRESHOLD = 0.30       # 30-60%为存在但不稳定
    MARGINAL_THRESHOLD = 0.10      # 10-30%为边缘存在
    
    # 占据度变化速率
    SUITABILITY_GAIN_RATE = 0.12   # 适宜度加成
    POPULATION_GAIN_RATE = 0.08    # 种群加成
    COMPETITION_LOSS_RATE = 0.10   # 竞争损失（只对高相似度物种）
    DECAY_RATE = 0.04              # 无种群衰减
    
    # 竞争影响系数（基于生态位相似度）
    STRONG_COMPETITION_FACTOR = 0.8   # 相似度>70%：80%竞争强度
    WEAK_COMPETITION_FACTOR = 0.3     # 相似度50-70%：30%竞争强度
    NO_COMPETITION_FACTOR = 0.0       # 相似度<50%：不竞争
    
    # 相似度权重
    FEATURE_SIMILARITY_WEIGHT = 0.6   # 特征相似度权重
    EMBEDDING_SIMILARITY_WEIGHT = 0.4  # Embedding相似度权重
    
    # 排斥效应（只对高度相似的竞争者）
    MAX_EXCLUSION_MORTALITY = 0.10   # 最大额外死亡率10%
    
    def __init__(self, embedding_service: 'EmbeddingService | None' = None):
        self.repo = environment_repository
        self.embeddings = embedding_service
        
        # ========== 矩阵缓存 ==========
        # 相似度矩阵 (n_species × n_species)
        self._similarity_matrix: np.ndarray | None = None
        self._similarity_codes: list[str] = []  # 对应的lineage_code顺序
        
        # 占据度矩阵 (n_tiles × n_species)
        self._occupancy_np: np.ndarray | None = None
        self._tile_ids: list[int] = []     # 对应的tile_id顺序
        self._species_ids: list[int] = []  # 对应的species_id顺序
        
        # ========== 字典缓存（用于快速查找） ==========
        # 占据度 {(tile_id, species_id): occupancy_level}
        self._occupancy_dict: dict[tuple[int, int], float] = {}
        
        # 领地状态 {(tile_id, species_id): status}
        self._presence_status: dict[tuple[int, int], str] = {}
        
        # 历史记录 {(tile_id, species_id): turns_present}
        self._turns_present: dict[tuple[int, int], int] = {}
        
        # 物种生态层缓存 {species_id: layer}
        self._species_layer: dict[int, int] = {}
        
        # 每地块每层的物种列表 {(tile_id, layer): [species_ids]}
        self._tile_layer_species: dict[tuple[int, int], list[int]] = {}
        
        # 索引映射
        self._tile_idx_map: dict[int, int] = {}    # tile_id -> matrix_index
        self._species_idx_map: dict[int, int] = {}  # species_id -> matrix_index
        self._code_idx_map: dict[str, int] = {}     # lineage_code -> matrix_index
    
    def get_species_layer(self, species: 'Species') -> int:
        """获取物种所属的生态层"""
        if species.id and species.id in self._species_layer:
            return self._species_layer[species.id]
        trophic = getattr(species, 'trophic_level', 1.0)
        layer = get_ecological_layer(trophic)
        if species.id:
            self._species_layer[species.id] = layer
        return layer
    
    def build_similarity_matrix(
        self,
        species_list: Sequence['Species']
    ) -> None:
        """构建物种相似度矩阵
        
        【矩阵化】一次性计算所有物种对的相似度
        
        相似度 = 特征相似度 × 0.6 + Embedding相似度 × 0.4
        """
        n = len(species_list)
        if n == 0:
            self._similarity_matrix = None
            return
        
        # 1. 计算特征相似度矩阵 (n × n)
        feature_sim = compute_feature_similarity_matrix(species_list)
        
        # 2. 计算同层掩码矩阵 (n × n)
        layer_mask = compute_layer_mask_matrix(species_list)
        
        # 3. 获取Embedding相似度矩阵 (n × n)
        embedding_sim = np.zeros((n, n), dtype=np.float32)
        
        if self.embeddings:
            try:
                lineage_codes = [sp.lineage_code for sp in species_list]
                emb_matrix, emb_codes = self.embeddings.compute_species_similarity_matrix(lineage_codes)
                
                if len(emb_matrix) > 0 and len(emb_codes) == n:
                    embedding_sim = emb_matrix
                    logger.debug(f"[生态位] 使用Embedding相似度矩阵 ({n}×{n})")
            except Exception as e:
                logger.warning(f"[生态位] Embedding相似度计算失败: {e}")
        
        # 4. 混合相似度
        combined_sim = (
            feature_sim * self.FEATURE_SIMILARITY_WEIGHT +
            embedding_sim * self.EMBEDDING_SIMILARITY_WEIGHT
        )
        
        # 5. 应用同层掩码（不同层相似度设为0）
        combined_sim = np.where(layer_mask, combined_sim, 0.0)
        
        # 6. 对角线设为0（自己不与自己竞争）
        np.fill_diagonal(combined_sim, 0.0)
        
        self._similarity_matrix = combined_sim
        self._similarity_codes = [sp.lineage_code for sp in species_list]
        self._code_idx_map = {code: i for i, code in enumerate(self._similarity_codes)}
        
        logger.info(f"[生态位] 构建相似度矩阵完成: {n}×{n}")
    
    def get_niche_similarity(
        self,
        species_a: 'Species',
        species_b: 'Species'
    ) -> float:
        """获取两个物种的生态位相似度
        
        优先从预计算的矩阵中查找
        """
        if not species_a.id or not species_b.id:
            return 0.0
        
        # 尝试从矩阵获取
        if self._similarity_matrix is not None:
            idx_a = self._code_idx_map.get(species_a.lineage_code)
            idx_b = self._code_idx_map.get(species_b.lineage_code)
            if idx_a is not None and idx_b is not None:
                return float(self._similarity_matrix[idx_a, idx_b])
        
        # 回退到单独计算
        return compute_niche_similarity(species_a, species_b)
    
    def get_occupancy_level(self, tile_id: int, species_id: int) -> float:
        """获取物种在特定地块的占据度"""
        # 优先从矩阵获取（更快）
        if self._occupancy_np is not None:
            tile_idx = self._tile_idx_map.get(tile_id)
            sp_idx = self._species_idx_map.get(species_id)
            if tile_idx is not None and sp_idx is not None:
                return float(self._occupancy_np[tile_idx, sp_idx])
        
        # 回退到字典
        return self._occupancy_dict.get((tile_id, species_id), 0.0)
    
    def get_presence_status(self, tile_id: int, species_id: int) -> str:
        """获取物种在特定地块的存在状态
        
        Returns:
            "established" | "present" | "marginal" | "absent"
        """
        return self._presence_status.get((tile_id, species_id), "absent")
    
    def get_tile_species(self, tile_id: int, layer: int | None = None) -> list[int]:
        """获取地块上的所有物种（可按层筛选）
        
        【关键】一个地块可以有多个成功物种！
        """
        if layer is not None:
            return self._tile_layer_species.get((tile_id, layer), [])
        
        # 返回所有层的物种
        all_species = []
        for l in range(1, 6):
            all_species.extend(self._tile_layer_species.get((tile_id, l), []))
        return all_species
    
    def get_species_established_tiles(self, species_id: int) -> list[int]:
        """获取物种的稳定栖息地列表（占据度>60%）"""
        tiles = []
        for (tid, sid), status in self._presence_status.items():
            if sid == species_id and status == "established":
                tiles.append(tid)
        return tiles
    
    def get_competition_mortality_modifier(
        self,
        species: 'Species',
        tile_id: int,
        all_species: list['Species']
    ) -> float:
        """计算竞争带来的额外死亡率
        
        【核心改进】只有生态位高度相似的物种才会造成排斥！
        
        计算逻辑：
        1. 找出该地块上所有同层物种
        2. 计算与每个物种的生态位相似度
        3. 只有相似度>70%的物种才造成竞争压力
        4. 竞争压力 = 相似度 × 对方占据度 × 竞争系数
        """
        if not species.id:
            return 0.0
        
        my_occupancy = self.get_occupancy_level(tile_id, species.id)
        my_layer = self.get_species_layer(species)
        
        # 如果自己占据度很高，不受排斥
        if my_occupancy >= self.ESTABLISHED_THRESHOLD:
            return 0.0
        
        total_competition_pressure = 0.0
        
        # 检查同层物种
        same_layer_ids = self._tile_layer_species.get((tile_id, my_layer), [])
        
        for other in all_species:
            if not other.id or other.id == species.id:
                continue
            if other.id not in same_layer_ids:
                continue
            if other.status != 'alive':
                continue
            
            # 计算生态位相似度
            similarity = self.get_niche_similarity(species, other)
            other_occupancy = self.get_occupancy_level(tile_id, other.id)
            
            # 根据相似度决定竞争强度
            if similarity >= NICHE_STRONG_COMPETITION:
                # 强竞争：相似度>70%
                comp_factor = self.STRONG_COMPETITION_FACTOR
            elif similarity >= NICHE_WEAK_COMPETITION:
                # 弱竞争：50-70%
                comp_factor = self.WEAK_COMPETITION_FACTOR
            else:
                # 不竞争：<50%，生态位分化足够
                comp_factor = self.NO_COMPETITION_FACTOR
            
            if comp_factor > 0 and other_occupancy > my_occupancy:
                # 对方占据度更高，造成压力
                pressure = comp_factor * (other_occupancy - my_occupancy) * similarity
                total_competition_pressure += pressure
        
        # 限制最大额外死亡率
        return min(self.MAX_EXCLUSION_MORTALITY, total_competition_pressure * 0.15)
    
    def _get_competition_factor(
        self,
        species_a: 'Species',
        species_b: 'Species'
    ) -> float:
        """获取两个物种之间的竞争系数
        
        【核心改进】基于生态位相似度，而不是简单的同层判断
        
        Returns:
            0.0-1.0 的竞争系数，越高竞争越激烈
        """
        # 不同层完全不竞争
        layer_a = self.get_species_layer(species_a)
        layer_b = self.get_species_layer(species_b)
        if layer_a != layer_b:
            return 0.0
        
        # 计算生态位相似度
        similarity = self.get_niche_similarity(species_a, species_b)
        
        # 根据相似度返回竞争系数
        if similarity >= NICHE_STRONG_COMPETITION:
            return self.STRONG_COMPETITION_FACTOR
        elif similarity >= NICHE_WEAK_COMPETITION:
            return self.WEAK_COMPETITION_FACTOR
        else:
            return self.NO_COMPETITION_FACTOR
    
    def update_occupancy_matrix(
        self,
        species_list: Sequence['Species'],
        all_tiles: list['MapTile'],
        all_habitats: list['HabitatPopulation'],
        suitability_matrix: np.ndarray | None = None,
        turn_index: int = 0
    ) -> dict[str, TerritoryUpdate]:
        """更新所有物种的占据度矩阵（矩阵化版本）
        
        【性能优化】使用numpy矩阵批量计算
        
        Args:
            species_list: 所有存活物种
            all_tiles: 所有地块
            all_habitats: 当前栖息地分布
            suitability_matrix: (n_species, n_tiles) 适宜度矩阵（可选）
            turn_index: 当前回合
            
        Returns:
            {lineage_code: TerritoryUpdate} 领地变化结果
        """
        if not species_list or not all_tiles:
            return {}
        
        alive_species = [sp for sp in species_list if sp.status == 'alive' and sp.id]
        n_species = len(alive_species)
        n_tiles = len(all_tiles)
        
        if n_species == 0:
            return {}
        
        # ========== 1. 构建索引映射 ==========
        self._tile_ids = [t.id for t in all_tiles if t.id]
        self._species_ids = [sp.id for sp in alive_species]
        self._tile_idx_map = {tid: i for i, tid in enumerate(self._tile_ids)}
        self._species_idx_map = {sid: i for i, sid in enumerate(self._species_ids)}
        
        # 预计算每个物种的生态层
        for sp in alive_species:
            if sp.id:
                self._species_layer[sp.id] = self.get_species_layer(sp)
        
        # ========== 2. 构建相似度矩阵 (n_species × n_species) ==========
        self.build_similarity_matrix(alive_species)
        
        # ========== 3. 构建种群矩阵 (n_tiles × n_species) ==========
        population_matrix = np.zeros((n_tiles, n_species), dtype=np.float32)
        for hab in all_habitats:
            sp_idx = self._species_idx_map.get(hab.species_id)
            tile_idx = self._tile_idx_map.get(hab.tile_id)
            if sp_idx is not None and tile_idx is not None:
                population_matrix[tile_idx, sp_idx] = hab.population
        
        # ========== 4. 构建旧占据度矩阵 (n_tiles × n_species) ==========
        old_occupancy = np.zeros((n_tiles, n_species), dtype=np.float32)
        for (tid, sid), occ in self._occupancy_dict.items():
            tile_idx = self._tile_idx_map.get(tid)
            sp_idx = self._species_idx_map.get(sid)
            if tile_idx is not None and sp_idx is not None:
                old_occupancy[tile_idx, sp_idx] = occ
        
        # ========== 5. 构建适宜度矩阵 (n_tiles × n_species) ==========
        if suitability_matrix is None:
            suit_matrix = np.ones((n_tiles, n_species), dtype=np.float32) * 0.5
        elif suitability_matrix.shape == (n_species, n_tiles):
            suit_matrix = suitability_matrix.T  # 转置为 (n_tiles × n_species)
        else:
            suit_matrix = np.ones((n_tiles, n_species), dtype=np.float32) * 0.5
        
        # ========== 6. 矩阵化计算占据度变化 ==========
        
        # 种群存在掩码 (n_tiles × n_species)
        has_population = population_matrix > 0
        
        # 6.1 适宜度加成 (n_tiles × n_species)
        suitability_gain = np.where(
            suit_matrix > 0.4,
            self.SUITABILITY_GAIN_RATE * suit_matrix,
            0.0
        )
        
        # 6.2 种群占比加成
        tile_total_pop = population_matrix.sum(axis=1, keepdims=True)
        tile_total_pop = np.maximum(tile_total_pop, 1)
        pop_ratio = population_matrix / tile_total_pop
        population_gain = self.POPULATION_GAIN_RATE * np.minimum(1.0, pop_ratio * 3)
        
        # 6.3 【核心】矩阵化竞争计算
        # 竞争压力 = Σ (相似度 × 竞争系数 × (对方占据度 - 我的占据度))
        
        if self._similarity_matrix is not None:
            # 获取竞争系数矩阵 (n_species × n_species)
            sim = self._similarity_matrix
            comp_factor = np.where(
                sim >= NICHE_STRONG_COMPETITION, self.STRONG_COMPETITION_FACTOR,
                np.where(sim >= NICHE_WEAK_COMPETITION, self.WEAK_COMPETITION_FACTOR, 0.0)
            )
            
            # 对每个地块计算竞争压力
            # competition_loss[t, s] = Σ_j (comp_factor[s,j] × max(0, occ[t,j] - occ[t,s]) × (pop[t,j] > pop[t,s]))
            
            competition_loss = np.zeros((n_tiles, n_species), dtype=np.float32)
            
            for t in range(n_tiles):
                # 该地块的占据度和种群
                occ_t = old_occupancy[t, :]  # (n_species,)
                pop_t = population_matrix[t, :]  # (n_species,)
                
                # 占据度差异矩阵 (n_species × n_species)
                # occ_diff[i,j] = occ[j] - occ[i]
                occ_diff = occ_t[np.newaxis, :] - occ_t[:, np.newaxis]
                occ_diff = np.maximum(occ_diff, 0)  # 只考虑对方更高的情况
                
                # 种群优势掩码 (n_species × n_species)
                # pop_stronger[i,j] = pop[j] > pop[i]
                pop_stronger = pop_t[np.newaxis, :] > pop_t[:, np.newaxis]
                
                # 竞争损失 (n_species,)
                loss = (comp_factor * occ_diff * pop_stronger).sum(axis=1)
                competition_loss[t, :] = loss * self.COMPETITION_LOSS_RATE
            
            # 限制最大竞争损失
            competition_loss = np.minimum(competition_loss, 0.15)
        else:
            competition_loss = np.zeros((n_tiles, n_species), dtype=np.float32)
        
        # 6.4 时间累积加成（需要逐个处理）
        time_bonus = np.zeros((n_tiles, n_species), dtype=np.float32)
        for t, tid in enumerate(self._tile_ids):
            for s, sid in enumerate(self._species_ids):
                key = (tid, sid)
                turns = self._turns_present.get(key, 0)
                if has_population[t, s]:
                    if turns > 2:
                        time_bonus[t, s] = 0.015 * min(turns - 2, 8)
                    self._turns_present[key] = turns + 1
                else:
                    self._turns_present[key] = 0
        
        # 6.5 计算总变化
        delta = np.where(
            has_population,
            suitability_gain + population_gain - competition_loss + time_bonus,
            -self.DECAY_RATE
        )
        
        # ========== 7. 应用变化，更新矩阵 ==========
        new_occupancy = np.clip(old_occupancy + delta, 0.0, 1.0)
        self._occupancy_np = new_occupancy
        
        # 更新字典缓存
        self._occupancy_dict.clear()
        self._presence_status.clear()
        self._tile_layer_species.clear()
        
        for t, tid in enumerate(self._tile_ids):
            for s, sid in enumerate(self._species_ids):
                occ = float(new_occupancy[t, s])
                key = (tid, sid)
                self._occupancy_dict[key] = occ
                
                # 更新存在状态
                if occ >= self.ESTABLISHED_THRESHOLD:
                    status = "established"
                elif occ >= self.PRESENT_THRESHOLD:
                    status = "present"
                elif occ >= self.MARGINAL_THRESHOLD:
                    status = "marginal"
                else:
                    status = "absent"
                self._presence_status[key] = status
                
                # 更新地块-层-物种列表
                if status != "absent":
                    layer = self._species_layer.get(sid, 1)
                    layer_key = (tid, layer)
                    if layer_key not in self._tile_layer_species:
                        self._tile_layer_species[layer_key] = []
                    self._tile_layer_species[layer_key].append(sid)
        
        # ========== 8. 构建返回结果 ==========
        updates: dict[str, TerritoryUpdate] = {}
        
        for s, sp in enumerate(alive_species):
            layer = self._species_layer.get(sp.id, 1)
            update = TerritoryUpdate(
                lineage_code=sp.lineage_code,
                ecological_layer=layer
            )
            
            for t, tid in enumerate(self._tile_ids):
                new_occ = float(new_occupancy[t, s])
                old_occ = float(old_occupancy[t, s])
                status = self._presence_status.get((tid, sp.id), "absent")
                
                old_status = "absent"
                if old_occ >= self.ESTABLISHED_THRESHOLD:
                    old_status = "established"
                elif old_occ >= self.PRESENT_THRESHOLD:
                    old_status = "present"
                elif old_occ >= self.MARGINAL_THRESHOLD:
                    old_status = "marginal"
                
                if status == "established":
                    update.core_tiles.append(tid)
                elif status == "present":
                    update.frontier_tiles.append(tid)
                elif status == "marginal":
                    update.contested_tiles.append(tid)
                
                if old_status == "absent" and status != "absent":
                    update.tiles_gained.append(tid)
                elif old_status != "absent" and status == "absent":
                    update.tiles_lost.append(tid)
                
                update.total_control += new_occ
            
            occupied = len(update.core_tiles) + len(update.frontier_tiles) + len(update.contested_tiles)
            if occupied > 0:
                update.average_control = update.total_control / occupied
            
            updates[sp.lineage_code] = update
        
        # ========== 9. 统计日志 ==========
        layer_counts = {i: 0 for i in range(1, 6)}
        for update in updates.values():
            layer_counts[update.ecological_layer] += 1
        
        coexist_count = sum(1 for sp_list in self._tile_layer_species.values() if len(sp_list) > 1)
        
        layer_info = ", ".join([f"L{l}:{c}" for l, c in layer_counts.items() if c > 0])
        
        logger.info(
            f"[生态位系统] 回合{turn_index}: "
            f"矩阵计算完成 ({n_tiles}×{n_species}), "
            f"物种分布 ({layer_info}), "
            f"{coexist_count}个地块-层有多物种共存"
        )
        
        return updates
    
    def get_territory_summary(
        self,
        species: 'Species'
    ) -> dict:
        """获取物种的领地概况"""
        if not species.id:
            return {}
        
        layer = self._species_layer.get(species.id, self.get_species_layer(species))
        layer_name = ECOLOGICAL_LAYERS.get(layer, {}).get("name", "未知")
        
        established_count = 0
        present_count = 0
        marginal_count = 0
        total_occupancy = 0.0
        
        for (tid, sid), status in self._presence_status.items():
            if sid == species.id:
                if status == "established":
                    established_count += 1
                elif status == "present":
                    present_count += 1
                elif status == "marginal":
                    marginal_count += 1
                total_occupancy += self._occupancy_matrix.get((tid, sid), 0.0)
        
        total_tiles = established_count + present_count + marginal_count
        
        return {
            "ecological_layer": layer,
            "layer_name": layer_name,
            "established_tiles": established_count,  # 稳定栖息地
            "present_tiles": present_count,          # 存在的地块
            "marginal_tiles": marginal_count,        # 边缘存在
            "total_tiles": total_tiles,
            "total_occupancy": round(total_occupancy, 2),
            "average_occupancy": round(total_occupancy / max(1, total_tiles), 2),
            "territory_strength": "strong" if established_count >= 3 else "moderate" if established_count >= 1 else "weak"
        }
    
    def get_tile_layer_summary(self, tile_id: int) -> dict:
        """获取地块的分层概况
        
        【改进】展示每层的所有物种（支持多物种共存）
        """
        summary = {}
        for layer in range(1, 6):
            layer_info = ECOLOGICAL_LAYERS[layer]
            species_list = self._tile_layer_species.get((tile_id, layer), [])
            
            species_data = []
            for sp_id in species_list:
                occupancy = self.get_occupancy_level(tile_id, sp_id)
                status = self.get_presence_status(tile_id, sp_id)
                if status != "absent":
                    species_data.append({
                        "species_id": sp_id,
                        "occupancy": round(occupancy, 2),
                        "status": status
                    })
            
            # 按占据度排序
            species_data.sort(key=lambda x: x["occupancy"], reverse=True)
            
            summary[layer] = {
                "layer_name": layer_info["name"],
                "species_count": len(species_data),
                "species": species_data[:5]  # 只返回前5个
            }
        
        return summary
    
    def get_coexistence_stats(self) -> dict:
        """获取共存统计数据
        
        用于分析生态系统的多样性
        """
        # 统计每层的平均共存物种数
        layer_coexist: dict[int, list[int]] = {i: [] for i in range(1, 6)}
        
        for (tid, layer), sp_list in self._tile_layer_species.items():
            layer_coexist[layer].append(len(sp_list))
        
        stats = {}
        for layer in range(1, 6):
            counts = layer_coexist[layer]
            if counts:
                stats[layer] = {
                    "layer_name": ECOLOGICAL_LAYERS[layer]["name"],
                    "avg_species_per_tile": round(sum(counts) / len(counts), 2),
                    "max_species_per_tile": max(counts),
                    "tiles_with_species": len(counts)
                }
            else:
                stats[layer] = {
                    "layer_name": ECOLOGICAL_LAYERS[layer]["name"],
                    "avg_species_per_tile": 0,
                    "max_species_per_tile": 0,
                    "tiles_with_species": 0
                }
        
        return stats
    
    def clear_caches(self) -> None:
        """清空所有缓存（存档切换时调用）"""
        # 矩阵缓存
        self._similarity_matrix = None
        self._similarity_codes.clear()
        self._occupancy_np = None
        self._tile_ids.clear()
        self._species_ids.clear()
        
        # 字典缓存
        self._occupancy_dict.clear()
        self._presence_status.clear()
        self._turns_present.clear()
        self._species_layer.clear()
        self._tile_layer_species.clear()
        
        # 索引映射
        self._tile_idx_map.clear()
        self._species_idx_map.clear()
        self._code_idx_map.clear()
    
    def export_state(self) -> dict:
        """导出状态用于存档"""
        return {
            "occupancy_dict": {f"{t}_{s}": v for (t, s), v in self._occupancy_dict.items()},
            "presence_status": {f"{t}_{s}": v for (t, s), v in self._presence_status.items()},
            "turns_present": {f"{t}_{s}": v for (t, s), v in self._turns_present.items()},
            "species_layer": self._species_layer.copy()
        }
    
    def import_state(self, state: dict) -> None:
        """从存档导入状态"""
        self.clear_caches()
        
        for key, value in state.get("occupancy_dict", {}).items():
            parts = key.split("_")
            if len(parts) == 2:
                self._occupancy_dict[(int(parts[0]), int(parts[1]))] = value
        
        for key, value in state.get("presence_status", {}).items():
            parts = key.split("_")
            if len(parts) == 2:
                self._presence_status[(int(parts[0]), int(parts[1]))] = value
        
        for key, value in state.get("turns_present", {}).items():
            parts = key.split("_")
            if len(parts) == 2:
                self._turns_present[(int(parts[0]), int(parts[1]))] = value
        
        self._species_layer = {int(k): v for k, v in state.get("species_layer", {}).items()}


# 全局实例
territory_system = TerritorySystem()

