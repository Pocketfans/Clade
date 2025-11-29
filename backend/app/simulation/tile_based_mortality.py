"""基于地块的死亡率计算引擎

【核心改进】
每个地块独立计算物种死亡率，而不是全局统一计算。
这更符合生态学现实：不同区域的物种面临不同的环境压力。

【设计原理】
1. 构建地块-物种种群矩阵 (num_tiles × num_species)
2. 每个地块独立计算：
   - 地块环境压力
   - 地块内营养级互动
   - 地块内生态位竞争
3. 汇总各地块结果得到物种总体死亡率

【性能优化】
使用 NumPy 矩阵运算批量处理所有地块，避免逐个循环。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..models.environment import HabitatPopulation, MapTile
from ..models.species import Species
from ..services.species.niche import NicheMetrics
from ..services.species.predation import PredationService
from ..core.config import get_settings

logger = logging.getLogger(__name__)

# 获取配置
_settings = get_settings()


@dataclass(slots=True)
class TileMortalityResult:
    """单个地块上单个物种的死亡率结果"""
    species: Species
    tile_id: int
    tile_population: float      # 该地块上的种群数量(按适宜度分配)
    tile_death_rate: float      # 该地块的死亡率
    tile_deaths: int            # 该地块的死亡数
    tile_survivors: int         # 该地块的存活数
    
    # 分解因素
    pressure_factor: float      # 环境压力因子
    competition_factor: float   # 竞争因子
    trophic_factor: float       # 营养级互动因子
    resource_factor: float      # 资源因子


@dataclass(slots=True) 
class AggregatedMortalityResult:
    """汇总后的物种死亡率结果（兼容原有 MortalityResult）"""
    species: Species
    initial_population: int
    deaths: int
    survivors: int
    death_rate: float
    notes: list[str]
    niche_overlap: float
    resource_pressure: float
    is_background: bool
    tier: str
    grazing_pressure: float = 0.0
    predation_pressure: float = 0.0
    
    # 新增：地块级别详情
    tile_details: list[TileMortalityResult] | None = None
    
    # 新增：AI评估结果字段
    ai_status_eval: object | None = None  # SpeciesStatusEval
    ai_narrative: str = ""
    ai_headline: str = ""
    ai_mood: str = ""
    death_causes: str = ""  # 主要死因描述
    
    # 【新增】植物专用压力字段
    plant_competition_pressure: float = 0.0  # 植物竞争压力（光照+养分）
    light_competition: float = 0.0           # 光照竞争程度
    nutrient_competition: float = 0.0        # 养分竞争程度
    herbivory_pressure: float = 0.0          # 食草压力
    
    # 【新增v2】地块分布统计
    total_tiles: int = 0              # 分布的总地块数
    healthy_tiles: int = 0            # 健康地块数（死亡率<25%）
    warning_tiles: int = 0            # 警告地块数（死亡率25%-50%）
    critical_tiles: int = 0           # 危机地块数（死亡率>50%）
    best_tile_rate: float = 0.0       # 最低死亡率（最佳地块）
    worst_tile_rate: float = 1.0      # 最高死亡率（最差地块）
    has_refuge: bool = True           # 是否有避难所（至少1个地块死亡率<20%）
    
    def get_distribution_status(self) -> str:
        """返回分布状态描述"""
        if self.total_tiles == 0:
            return "无分布"
        if self.critical_tiles == self.total_tiles:
            return "全域危机"
        elif self.critical_tiles > self.total_tiles * 0.5:
            return "部分危机"
        elif self.healthy_tiles >= self.total_tiles * 0.5:
            return "稳定"
        else:
            return "警告"
    
    def get_distribution_summary(self) -> str:
        """返回分布摘要字符串"""
        if self.total_tiles == 0:
            return "无分布数据"
        return f"分布{self.total_tiles}块(🟢{self.healthy_tiles}/🟡{self.warning_tiles}/🔴{self.critical_tiles})"


class TileBasedMortalityEngine:
    """基于地块的死亡率计算引擎
    
    【核心特性】
    - 每个地块独立计算环境压力
    - 地块内物种竞争（只有同地块的物种才真正竞争）
    - 地块内营养级互动
    - 矩阵化批量计算
    - 【新增】集成Embedding相似度计算生态位竞争
    
    【性能】
    使用稀疏矩阵表示种群分布，避免处理空白地块。
    预计算物种相似度矩阵，避免重复计算。
    """
    
    def __init__(self, batch_limit: int = 50) -> None:
        self.batch_limit = batch_limit
        
        # 缓存地块信息
        self._tiles: list[MapTile] = []
        self._tile_id_to_idx: dict[int, int] = {}
        
        # 缓存物种信息
        self._species_id_to_idx: dict[int, int] = {}
        self._species_list: list[Species] = []
        
        # 种群分布矩阵 (num_tiles × num_species)
        self._population_matrix: np.ndarray | None = None
        # 适宜度矩阵 (num_tiles × num_species)
        self._suitability_matrix: np.ndarray | None = None
        # 地块环境矩阵 (num_tiles × num_features)
        self._tile_env_matrix: np.ndarray | None = None
        
        # 【新增】地块死亡率缓存（供其他服务使用）
        self._last_mortality_matrix: np.ndarray | None = None
        self._last_species_lineage_to_idx: dict[str, int] = {}
        
        # 【新增】地块邻接关系
        self._tile_adjacency: dict[int, set[int]] = {}
        
        # 【新增】捕食网服务
        self._predation_service = PredationService()
        
        # 【新增】植物压力缓存（用于结果汇总）
        self._last_plant_competition_matrix: np.ndarray | None = None
        self._last_herbivory_pressure: dict[str, float] = {}  # {lineage_code: pressure}
        
        # 【新增v3】物种相似度矩阵缓存（Embedding + 特征）
        self._species_similarity_matrix: np.ndarray | None = None
        self._embedding_service = None  # 由外部注入
    
    def build_matrices(
        self,
        species_list: Sequence[Species],
        tiles: list[MapTile],
        habitats: list[HabitatPopulation],
    ) -> None:
        """构建计算所需的矩阵
        
        Args:
            species_list: 物种列表
            tiles: 地块列表
            habitats: 栖息地分布数据
        """
        self._species_list = list(species_list)
        self._tiles = tiles
        
        n_species = len(species_list)
        n_tiles = len(tiles)
        
        if n_species == 0 or n_tiles == 0:
            logger.warning("物种或地块列表为空，跳过矩阵构建")
            return
        
        # 构建索引映射
        self._tile_id_to_idx = {tile.id: idx for idx, tile in enumerate(tiles) if tile.id is not None}
        self._species_id_to_idx = {sp.id: idx for idx, sp in enumerate(species_list) if sp.id is not None}
        
        # 构建地块邻接关系（基于地块坐标）
        self._build_tile_adjacency(tiles)
        
        # 初始化矩阵
        self._population_matrix = np.zeros((n_tiles, n_species), dtype=np.float64)
        self._suitability_matrix = np.zeros((n_tiles, n_species), dtype=np.float64)
        
        # 填充栖息地数据
        for habitat in habitats:
            tile_idx = self._tile_id_to_idx.get(habitat.tile_id)
            species_idx = self._species_id_to_idx.get(habitat.species_id)
            
            if tile_idx is not None and species_idx is not None:
                self._suitability_matrix[tile_idx, species_idx] = habitat.suitability
        
        # 根据适宜度分配种群到各地块
        self._distribute_population()
        
        # 构建地块环境矩阵
        self._build_tile_environment_matrix()
        
        # 【新增v3】构建物种相似度矩阵（用于生态位竞争）
        self._build_species_similarity_matrix(list(species_list))
        
        logger.info(f"[地块死亡率] 矩阵构建完成: {n_tiles}地块 × {n_species}物种")
    
    def _distribute_population(self) -> None:
        """根据适宜度将物种总种群分配到各地块
        
        分配公式：tile_pop = total_pop × (tile_suitability / sum_suitability)
        """
        if self._suitability_matrix is None or self._population_matrix is None:
            return
        
        for sp_idx, species in enumerate(self._species_list):
            total_pop = species.morphology_stats.get("population", 0) or 0
            if total_pop <= 0:
                continue
            
            # 获取该物种在所有地块的适宜度
            suitability_col = self._suitability_matrix[:, sp_idx]
            sum_suit = suitability_col.sum()
            
            if sum_suit > 0:
                # 按适宜度比例分配种群
                self._population_matrix[:, sp_idx] = total_pop * (suitability_col / sum_suit)
    
    def set_embedding_service(self, embedding_service) -> None:
        """设置Embedding服务（用于计算物种语义相似度）
        
        由 SimulationEngine 在初始化时调用
        """
        self._embedding_service = embedding_service
    
    def _build_species_similarity_matrix(self, species_list: list[Species]) -> None:
        """构建物种相似度矩阵（特征 + Embedding 混合）
        
        【核心优化】预计算所有物种对的相似度，避免每个地块重复计算
        
        相似度 = 特征相似度 × 0.5 + Embedding语义相似度 × 0.5
        
        这里的相似度表示生态位重叠程度：
        - 高相似度 → 竞争激烈
        - 低相似度 → 可共存
        """
        n = len(species_list)
        if n == 0:
            self._species_similarity_matrix = None
            return
        
        # ======== 1. 计算特征相似度矩阵 (n × n) ========
        # 提取特征向量：[营养级, log体型, 栖息地编码, 耐热性, 耐寒性, 耐旱性]
        features = np.zeros((n, 6), dtype=np.float32)
        
        habitat_encoding = {
            'terrestrial': 0, 'marine': 1, 'freshwater': 2,
            'coastal': 3, 'aerial': 4, 'deep_sea': 5, 'amphibious': 3.5
        }
        
        for i, sp in enumerate(species_list):
            features[i, 0] = getattr(sp, 'trophic_level', 1.0) / 5.0
            body_size = sp.morphology_stats.get("body_length_cm", 10.0) or 10.0
            features[i, 1] = np.log10(max(body_size, 0.01)) / 4.0
            habitat = getattr(sp, 'habitat_type', 'terrestrial')
            features[i, 2] = habitat_encoding.get(habitat, 0) / 5.0
            traits = sp.abstract_traits or {}
            features[i, 3] = traits.get("耐热性", 5) / 10.0
            features[i, 4] = traits.get("耐寒性", 5) / 10.0
            features[i, 5] = traits.get("耐旱性", 5) / 10.0
        
        # 欧几里得距离 → 相似度
        diff = features[:, np.newaxis, :] - features[np.newaxis, :, :]
        distances = np.sqrt((diff ** 2).sum(axis=2))
        max_dist = np.sqrt(6)
        feature_sim = 1.0 - (distances / max_dist)
        np.fill_diagonal(feature_sim, 1.0)
        feature_sim = np.clip(feature_sim, 0.0, 1.0)
        
        # ======== 2. 获取Embedding相似度矩阵 (n × n) ========
        embedding_sim = np.eye(n, dtype=np.float32)  # 默认单位矩阵
        
        if self._embedding_service is not None:
            try:
                lineage_codes = [sp.lineage_code for sp in species_list]
                emb_matrix, emb_codes = self._embedding_service.compute_species_similarity_matrix(lineage_codes)
                
                if len(emb_matrix) > 0 and len(emb_codes) == n:
                    embedding_sim = emb_matrix.astype(np.float32)
                    logger.debug(f"[地块竞争] 使用Embedding相似度矩阵 ({n}×{n})")
            except Exception as e:
                logger.warning(f"[地块竞争] Embedding相似度计算失败: {e}，使用纯特征相似度")
        
        # ======== 3. 混合相似度 ========
        # 特征相似度权重0.5 + Embedding权重0.5
        self._species_similarity_matrix = (
            feature_sim * 0.5 + embedding_sim * 0.5
        ).astype(np.float32)
        
        # 对角线设为0（自己与自己不竞争）
        np.fill_diagonal(self._species_similarity_matrix, 0.0)
        
        logger.debug(f"[地块竞争] 物种相似度矩阵构建完成 ({n}×{n})")
    
    def _get_habitat_type_mask(self, habitat_type: str) -> np.ndarray:
        """获取适合某种栖息地类型的地块掩码"""
        n_tiles = len(self._tiles)
        mask = np.zeros(n_tiles, dtype=bool)
        
        for idx, tile in enumerate(self._tiles):
            biome = tile.biome.lower()
            
            if habitat_type == "marine":
                if "浅海" in biome or "中层" in biome or "海" in biome:
                    mask[idx] = True
            elif habitat_type == "deep_sea":
                if "深海" in biome:
                    mask[idx] = True
            elif habitat_type == "coastal":
                if "海岸" in biome or "浅海" in biome:
                    mask[idx] = True
            elif habitat_type in ("terrestrial", "amphibious", "aerial"):
                if "海" not in biome:
                    mask[idx] = True
            else:
                # 默认陆地
                if "海" not in biome:
                    mask[idx] = True
        
        return mask
    
    def _build_tile_adjacency(self, tiles: list[MapTile]) -> None:
        """构建地块邻接关系
        
        基于地块的 row/col 坐标判断相邻（8邻域）
        """
        self._tile_adjacency = {}
        
        # 构建坐标到tile_id的映射
        coord_to_tile: dict[tuple[int, int], int] = {}
        for tile in tiles:
            row = getattr(tile, 'row', None)
            col = getattr(tile, 'col', None)
            if row is not None and col is not None and tile.id is not None:
                coord_to_tile[(row, col)] = tile.id
        
        # 8邻域偏移
        neighbors_offset = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)
        ]
        
        # 为每个地块找邻居
        for tile in tiles:
            if tile.id is None:
                continue
            
            row = getattr(tile, 'row', None)
            col = getattr(tile, 'col', None)
            
            if row is None or col is None:
                # 没有坐标信息，假设孤立
                self._tile_adjacency[tile.id] = set()
                continue
            
            neighbors = set()
            for dr, dc in neighbors_offset:
                neighbor_coord = (row + dr, col + dc)
                if neighbor_coord in coord_to_tile:
                    neighbors.add(coord_to_tile[neighbor_coord])
            
            self._tile_adjacency[tile.id] = neighbors
        
        logger.debug(f"[地块邻接] 构建了 {len(self._tile_adjacency)} 个地块的邻接关系")
    
    def get_tile_adjacency(self) -> dict[int, set[int]]:
        """获取地块邻接关系（供其他服务使用）"""
        return self._tile_adjacency
    
    def get_species_tile_mortality(self, lineage_code: str) -> dict[int, float]:
        """获取指定物种在各地块的死亡率
        
        Args:
            lineage_code: 物种谱系编码
            
        Returns:
            {tile_id: death_rate} 字典
        """
        if self._last_mortality_matrix is None:
            return {}
        
        species_idx = self._last_species_lineage_to_idx.get(lineage_code)
        if species_idx is None:
            return {}
        
        result = {}
        for tile_id, tile_idx in self._tile_id_to_idx.items():
            death_rate = self._last_mortality_matrix[tile_idx, species_idx]
            if death_rate > 0:  # 只返回有种群的地块
                result[tile_id] = float(death_rate)
        
        return result
    
    def get_all_species_tile_mortality(self) -> dict[str, dict[int, float]]:
        """获取所有物种在各地块的死亡率
        
        Returns:
            {lineage_code: {tile_id: death_rate}} 嵌套字典
        """
        if self._last_mortality_matrix is None:
            return {}
        
        result = {}
        for lineage_code, species_idx in self._last_species_lineage_to_idx.items():
            tile_rates = {}
            for tile_id, tile_idx in self._tile_id_to_idx.items():
                death_rate = self._last_mortality_matrix[tile_idx, species_idx]
                if death_rate > 0:
                    tile_rates[tile_id] = float(death_rate)
            if tile_rates:
                result[lineage_code] = tile_rates
        
        return result
    
    def get_species_tile_population(self, lineage_code: str) -> dict[int, float]:
        """获取指定物种在各地块的种群分布
        
        Args:
            lineage_code: 物种谱系编码
            
        Returns:
            {tile_id: population} 字典
        """
        if self._population_matrix is None:
            return {}
        
        species_idx = self._last_species_lineage_to_idx.get(lineage_code)
        if species_idx is None:
            return {}
        
        result = {}
        for tile_id, tile_idx in self._tile_id_to_idx.items():
            pop = self._population_matrix[tile_idx, species_idx]
            if pop > 0:
                result[tile_id] = float(pop)
        
        return result
    
    def get_all_species_tile_population(self) -> dict[str, dict[int, float]]:
        """获取所有物种在各地块的种群分布
        
        Returns:
            {lineage_code: {tile_id: population}} 嵌套字典
        """
        if self._population_matrix is None:
            return {}
        
        result = {}
        for lineage_code, species_idx in self._last_species_lineage_to_idx.items():
            tile_pops = {}
            for tile_id, tile_idx in self._tile_id_to_idx.items():
                pop = self._population_matrix[tile_idx, species_idx]
                if pop > 0:
                    tile_pops[tile_id] = float(pop)
            if tile_pops:
                result[lineage_code] = tile_pops
        
        return result
    
    def get_all_species_tile_survivors(self) -> dict[str, dict[int, int]]:
        """【新增】获取所有物种在各地块的存活数（死亡率计算后）
        
        这是关键方法：返回每个地块的实际存活数量，用于更新栖息地种群。
        计算公式：survivors = population * (1 - mortality_rate)
        
        Returns:
            {lineage_code: {tile_id: survivors}} 嵌套字典
        """
        if self._population_matrix is None or self._last_mortality_matrix is None:
            return {}
        
        result: dict[str, dict[int, int]] = {}
        
        for lineage_code, species_idx in self._last_species_lineage_to_idx.items():
            tile_survivors: dict[int, int] = {}
            
            for tile_id, tile_idx in self._tile_id_to_idx.items():
                pop = self._population_matrix[tile_idx, species_idx]
                if pop > 0:
                    mortality_rate = self._last_mortality_matrix[tile_idx, species_idx]
                    # 计算存活数（取整）
                    survivors = int(pop * (1.0 - mortality_rate))
                    if survivors > 0:
                        tile_survivors[tile_id] = survivors
            
            if tile_survivors:
                result[lineage_code] = tile_survivors
        
        return result
    
    def get_speciation_candidates(
        self, 
        min_tile_population: int = 100,
        mortality_threshold: tuple[float, float] = (0.03, 0.70),
        min_mortality_gradient: float = 0.15,
    ) -> dict[str, dict]:
        """获取适合分化的物种及其候选地块
        
        【核心功能】基于地块级数据筛选分化候选：
        - 在特定地块上种群达到阈值
        - 地块死亡率在适宜范围内
        - 存在地块间死亡率梯度（地理/生态隔离）
        
        Args:
            min_tile_population: 地块最小种群门槛
            mortality_threshold: 死亡率范围 (min, max)
            min_mortality_gradient: 最小死亡率梯度（隔离判定）
            
        Returns:
            {lineage_code: {
                "candidate_tiles": set[int],  # 可分化的地块
                "tile_populations": dict[int, float],  # 各地块种群
                "tile_mortality": dict[int, float],  # 各地块死亡率
                "mortality_gradient": float,  # 死亡率梯度
                "is_isolated": bool,  # 是否存在隔离
                "clusters": list[set[int]],  # 隔离区域
            }}
        """
        if self._population_matrix is None or self._last_mortality_matrix is None:
            return {}
        
        min_rate, max_rate = mortality_threshold
        result = {}
        
        for lineage_code, species_idx in self._last_species_lineage_to_idx.items():
            # 获取地块级数据
            tile_pops = {}
            tile_rates = {}
            candidate_tiles = set()
            
            for tile_id, tile_idx in self._tile_id_to_idx.items():
                pop = self._population_matrix[tile_idx, species_idx]
                rate = self._last_mortality_matrix[tile_idx, species_idx]
                
                if pop > 0:
                    tile_pops[tile_id] = float(pop)
                    tile_rates[tile_id] = float(rate)
                    
                    # 检查是否为候选地块
                    if pop >= min_tile_population and min_rate <= rate <= max_rate:
                        candidate_tiles.add(tile_id)
            
            if not candidate_tiles:
                continue
            
            # 计算死亡率梯度
            if len(tile_rates) >= 2:
                rates = list(tile_rates.values())
                mortality_gradient = max(rates) - min(rates)
            else:
                mortality_gradient = 0.0
            
            # 检测隔离区域
            clusters = self._find_population_clusters(set(tile_pops.keys()))
            is_isolated = len(clusters) >= 2 or mortality_gradient >= min_mortality_gradient
            
            result[lineage_code] = {
                "candidate_tiles": candidate_tiles,
                "tile_populations": tile_pops,
                "tile_mortality": tile_rates,
                "mortality_gradient": mortality_gradient,
                "is_isolated": is_isolated,
                "clusters": clusters,
                "total_candidate_population": sum(tile_pops.get(t, 0) for t in candidate_tiles),
            }
        
        return result
    
    def _find_population_clusters(self, tile_ids: set[int]) -> list[set[int]]:
        """使用并查集找出连通的地块群"""
        if not tile_ids:
            return []
        
        if not self._tile_adjacency:
            return [tile_ids]
        
        parent = {t: t for t in tile_ids}
        
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
        for tile_id in tile_ids:
            neighbors = self._tile_adjacency.get(tile_id, set())
            for neighbor in neighbors:
                if neighbor in tile_ids:
                    union(tile_id, neighbor)
        
        clusters_map: dict[int, set[int]] = {}
        for tile_id in tile_ids:
            root = find(tile_id)
            if root not in clusters_map:
                clusters_map[root] = set()
            clusters_map[root].add(tile_id)
        
        return list(clusters_map.values())
    
    def _build_tile_environment_matrix(self) -> None:
        """构建地块环境特征矩阵
        
        特征包括：
        - 温度 (0)
        - 湿度 (1)
        - 资源 (2)
        - 海拔 (3)
        - 盐度 (4)
        """
        n_tiles = len(self._tiles)
        self._tile_env_matrix = np.zeros((n_tiles, 5), dtype=np.float64)
        
        for idx, tile in enumerate(self._tiles):
            self._tile_env_matrix[idx, 0] = tile.temperature
            self._tile_env_matrix[idx, 1] = tile.humidity
            self._tile_env_matrix[idx, 2] = tile.resources
            self._tile_env_matrix[idx, 3] = tile.elevation
            self._tile_env_matrix[idx, 4] = getattr(tile, 'salinity', 35.0)
    
    def evaluate(
        self,
        species_batch: Sequence[Species],
        pressure_modifiers: dict[str, float],
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        trophic_interactions: dict[str, float] | None = None,
        extinct_codes: set[str] | None = None,
    ) -> list[AggregatedMortalityResult]:
        """计算物种死亡率（按地块计算后汇总）
        
        Args:
            species_batch: 物种列表
            pressure_modifiers: 全局压力修饰符
            niche_metrics: 生态位指标（全局）
            tier: 物种层级
            trophic_interactions: 营养级互动（全局）
            extinct_codes: 已灭绝物种代码集合
            
        Returns:
            汇总后的死亡率结果列表
        """
        if trophic_interactions is None:
            trophic_interactions = {}
        if extinct_codes is None:
            extinct_codes = set()
        
        species_list = list(species_batch)
        n = len(species_list)
        
        if n == 0:
            return []
        
        if self._population_matrix is None or self._tile_env_matrix is None:
            logger.warning("[地块死亡率] 矩阵未初始化，降级为全局计算")
            return self._fallback_global_evaluate(
                species_list, pressure_modifiers, niche_metrics, tier,
                trophic_interactions, extinct_codes
            )
        
        logger.debug(f"[地块死亡率] 按地块计算 {n} 个物种的死亡率 (tier={tier})")
        
        # ========== 【关键修复】创建当前批次对应的population子矩阵 ==========
        # 当前批次的物种可能是build_matrices时全部物种的子集
        # 需要正确映射以避免矩阵维度不匹配
        n_tiles = len(self._tiles)
        batch_population_matrix = np.zeros((n_tiles, n), dtype=np.float64)
        
        for sp_idx, sp in enumerate(species_list):
            if sp.id is not None and sp.id in self._species_id_to_idx:
                # 物种在原始矩阵中，提取对应的列
                global_idx = self._species_id_to_idx[sp.id]
                batch_population_matrix[:, sp_idx] = self._population_matrix[:, global_idx]
            # else: 新分化的物种，保持零值（没有历史种群数据）
        
        # ========== 阶段1: 提取物种属性为向量 ==========
        species_arrays = self._extract_species_arrays(species_list, niche_metrics)
        
        # ========== 阶段2: 计算各地块的死亡率矩阵 ==========
        # 死亡率矩阵 (num_tiles × num_species)
        mortality_matrix = self._compute_tile_mortality_matrix(
            species_list, species_arrays, pressure_modifiers, trophic_interactions,
            batch_population_matrix  # 传递正确维度的population矩阵
        )
        
        # 【新增】保存死亡率矩阵供其他服务使用
        self._last_mortality_matrix = mortality_matrix.copy()
        self._last_species_lineage_to_idx = {
            sp.lineage_code: i for i, sp in enumerate(species_list)
        }
        
        # ========== 阶段3: 汇总各地块结果 ==========
        results = self._aggregate_tile_results(
            species_list, species_arrays, mortality_matrix, 
            niche_metrics, tier, extinct_codes
        )
        
        return results
    
    def _extract_species_arrays(
        self,
        species_list: list[Species],
        niche_metrics: dict[str, NicheMetrics]
    ) -> dict[str, np.ndarray]:
        """批量提取物种属性为NumPy数组"""
        n = len(species_list)
        
        arrays = {
            'base_sensitivity': np.zeros(n),
            'trophic_level': np.zeros(n),
            'body_size': np.zeros(n),
            'population': np.zeros(n, dtype=np.int64),
            'generation_time': np.zeros(n),
            'cold_resistance': np.zeros(n),
            'heat_resistance': np.zeros(n),
            'drought_resistance': np.zeros(n),
            'salinity_resistance': np.zeros(n),
            'overlap': np.zeros(n),
            'saturation': np.zeros(n),
            'is_protected': np.zeros(n, dtype=bool),
            'protection_turns': np.zeros(n, dtype=np.int32),
            'is_suppressed': np.zeros(n, dtype=bool),
            'suppression_turns': np.zeros(n, dtype=np.int32),
        }
        
        for i, sp in enumerate(species_list):
            arrays['base_sensitivity'][i] = sp.hidden_traits.get("environment_sensitivity", 0.5)
            arrays['trophic_level'][i] = sp.trophic_level
            arrays['body_size'][i] = sp.morphology_stats.get("body_length_cm", 0.01)
            arrays['population'][i] = int(sp.morphology_stats.get("population", 0) or 0)
            arrays['generation_time'][i] = sp.morphology_stats.get("generation_time_days", 365)
            
            arrays['cold_resistance'][i] = sp.abstract_traits.get("耐寒性", 5) / 10.0
            arrays['heat_resistance'][i] = sp.abstract_traits.get("耐热性", 5) / 10.0
            arrays['drought_resistance'][i] = sp.abstract_traits.get("耐旱性", 5) / 10.0
            arrays['salinity_resistance'][i] = sp.abstract_traits.get("耐盐性", 5) / 10.0
            
            metrics = niche_metrics.get(sp.lineage_code, NicheMetrics(overlap=0.0, saturation=0.0))
            arrays['overlap'][i] = metrics.overlap
            arrays['saturation'][i] = metrics.saturation
            
            arrays['is_protected'][i] = getattr(sp, 'is_protected', False) or False
            arrays['protection_turns'][i] = getattr(sp, 'protection_turns', 0) or 0
            arrays['is_suppressed'][i] = getattr(sp, 'is_suppressed', False) or False
            arrays['suppression_turns'][i] = getattr(sp, 'suppression_turns', 0) or 0
        
        return arrays
    
    def _compute_tile_mortality_matrix(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        pressure_modifiers: dict[str, float],
        trophic_interactions: dict[str, float],
        batch_population_matrix: np.ndarray | None = None,
    ) -> np.ndarray:
        """计算每个地块上每个物种的死亡率
        
        【平衡修复】使用混合模型替代纯乘法，添加微生物抗性
        
        Args:
            species_list: 当前批次的物种列表
            species_arrays: 物种属性数组
            pressure_modifiers: 压力修饰符
            trophic_interactions: 营养级互动
            batch_population_matrix: 当前批次对应的population子矩阵
        
        Returns:
            (num_tiles × num_species) 的死亡率矩阵
        """
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        if batch_population_matrix is None:
            batch_population_matrix = self._population_matrix
        
        # 初始化死亡率矩阵
        mortality = np.zeros((n_tiles, n_species), dtype=np.float64)
        
        # ========== 1. 计算地块环境压力 ==========
        env_pressure = self._compute_tile_environment_pressure(
            species_list, species_arrays, pressure_modifiers
        )
        
        # ========== 2. 计算地块内竞争压力 ==========
        competition_pressure = self._compute_tile_competition_pressure(
            species_list, species_arrays, batch_population_matrix
        )
        
        # ========== 3. 计算地块内营养级互动 ==========
        trophic_pressure = self._compute_tile_trophic_pressure(
            species_list, species_arrays, trophic_interactions, batch_population_matrix
        )
        
        # ========== 4. 计算地块资源压力 ==========
        resource_pressure = self._compute_tile_resource_pressure(
            species_list, species_arrays, batch_population_matrix
        )
        
        # ========== 5. 计算捕食网压力 ==========
        predation_network_pressure = self._compute_predation_network_pressure(
            species_list, species_arrays, batch_population_matrix
        )
        
        # ========== 【新增】6. 计算植物竞争压力（光照+养分）==========
        plant_competition_pressure = self._compute_plant_competition_pressure(
            species_list, species_arrays, batch_population_matrix
        )
        
        # 【新增】缓存植物竞争压力矩阵（用于结果汇总）
        self._last_plant_competition_matrix = plant_competition_pressure
        
        # 【新增】计算并缓存食草压力（供结果汇总使用）
        self._compute_and_cache_herbivory_pressure(species_list)
        
        # ========== 【平衡修复v2】提高压力敏感度，减少过度减免 ==========
        # 问题诊断：原方案压力上限太低 + 抗性减免太多，导致高压力下死亡率仍然很低
        # 
        # 修复方向：
        # 1. 提高各压力因素的上限
        # 2. 减少抗性减免的幅度
        # 3. 让高压力环境真正产生高死亡率
        
        # 【修复1】提高压力上限，让极端环境真正危险
        env_capped = np.minimum(0.65, env_pressure)          # 从0.50提高到0.65
        competition_capped = np.minimum(0.50, competition_pressure)  # 从0.40提高到0.50
        trophic_capped = np.minimum(0.60, trophic_pressure)  # 从0.50提高到0.60
        resource_capped = np.minimum(0.55, resource_pressure)  # 从0.45提高到0.55
        predation_capped = np.minimum(0.60, predation_network_pressure)  # 从0.50提高到0.60
        plant_competition_capped = np.minimum(0.40, plant_competition_pressure)  # 从0.35提高到0.40
        
        # 【修复2】大幅降低体型/繁殖抗性
        # 原方案抗性太高（微生物0.4+0.35），导致死亡率被减少60%以上
        body_size = species_arrays['body_size']
        generation_time = species_arrays['generation_time']
        
        # 体型抗性：降低所有档位
        # body_size < 0.01cm (微生物) -> 0.20 抗性（原0.40）
        # body_size 0.01-0.1cm -> 0.15 抗性（原0.30）
        # body_size 0.1-1cm -> 0.10 抗性（原0.20）
        # body_size > 1cm -> 0.05 抗性（原0.10）
        size_resistance = np.where(
            body_size < 0.01, 0.20,
            np.where(body_size < 0.1, 0.15,
                np.where(body_size < 1.0, 0.10, 0.05))
        )
        
        # 繁殖速度抗性：同样降低
        # generation_time < 7天 -> 0.18 抗性（原0.35）
        # generation_time 7-30天 -> 0.12 抗性（原0.25）
        # generation_time 30-365天 -> 0.08 抗性（原0.15）
        # generation_time > 365天 -> 0.03 抗性（原0.05）
        repro_resistance = np.where(
            generation_time < 7, 0.18,
            np.where(generation_time < 30, 0.12,
                np.where(generation_time < 365, 0.08, 0.03))
        )
        
        # 【修复3】降低综合抗性上限
        # 最大抗性从约38%降到约20%
        total_resistance = size_resistance * 0.5 + repro_resistance * 0.5
        # 广播到矩阵形状 (n_tiles, n_species)
        resistance_matrix = total_resistance[np.newaxis, :]
        
        # 【修复4】提高加权和系数，让压力更容易导致高死亡率
        # 各因素权重提高，使得中等压力就能产生30-50%死亡率
        weighted_sum = (
            env_capped * 0.60 +           # 从0.50提高到0.60
            competition_capped * 0.45 +   # 从0.35提高到0.45
            trophic_capped * 0.55 +       # 从0.45提高到0.55
            resource_capped * 0.50 +      # 从0.40提高到0.50
            predation_capped * 0.50 +     # 从0.40提高到0.50
            plant_competition_capped * 0.35  # 从0.30提高到0.35
        )  # 总权重 = 2.95（原2.4）
        
        # 【修复5】提高乘法模型的压力系数
        survival_product = (
            (1.0 - env_capped * 0.70) *        # 从0.6提高到0.70
            (1.0 - competition_capped * 0.60) * # 从0.5提高到0.60
            (1.0 - trophic_capped * 0.70) *    # 从0.6提高到0.70
            (1.0 - resource_capped * 0.60) *   # 从0.5提高到0.60
            (1.0 - predation_capped * 0.70) *  # 从0.6提高到0.70
            (1.0 - plant_competition_capped * 0.50)  # 从0.4提高到0.50
        )
        multiplicative_mortality = 1.0 - survival_product
        
        # 【修复6】调整混合比例，增加乘法模型权重让高压力更致命
        # 加权和占60%，乘法占40%（原70%/30%）
        raw_mortality = weighted_sum * 0.60 + multiplicative_mortality * 0.40
        
        # 【修复7】降低抗性减免幅度
        # 抗性最多减少25%死亡率（原40%）
        mortality = raw_mortality * (1.0 - resistance_matrix * 0.6)
        
        # ========== 7. 应用世代累积死亡率 ==========
        if _settings.enable_generational_mortality:
            mortality = self._apply_generational_mortality(species_arrays, mortality)
        
        # ========== 8. 边界约束 ==========
        # 【修复】最低死亡率从3%降到2%，给快繁殖物种更多生存空间
        # 最高死亡率保持98%
        mortality = np.clip(mortality, 0.02, 0.98)
        
        return mortality
    
    def _compute_tile_environment_pressure(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        pressure_modifiers: dict[str, float],
    ) -> np.ndarray:
        """计算每个地块对每个物种的环境压力
        
        【生物学依据】
        环境压力基于物种特质与环境条件的匹配度计算：
        - 温度压力：基于物种耐热/耐寒特质
        - 水分压力：基于物种耐旱/耐湿特质
        - 特殊事件：疾病、火灾、紫外辐射等
        
        考虑：
        - 地块温度 vs 物种耐热/耐寒性
        - 地块湿度 vs 物种耐旱性
        - 全局压力修饰符（疾病、火灾、毒素等）
        """
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        # 初始化压力矩阵
        pressure = np.zeros((n_tiles, n_species), dtype=np.float64)
        
        # 地块温度 (n_tiles,)
        tile_temps = self._tile_env_matrix[:, 0]
        # 地块湿度 (n_tiles,)
        tile_humidity = self._tile_env_matrix[:, 1]
        
        # 物种耐性 (n_species,)
        cold_res = species_arrays['cold_resistance']
        heat_res = species_arrays['heat_resistance']
        drought_res = species_arrays['drought_resistance']
        salinity_res = species_arrays['salinity_resistance']
        base_sens = species_arrays['base_sensitivity']
        
        # ========== 温度压力 ==========
        # 全局温度修饰（来自冰河期/温室效应等）
        temp_modifier = pressure_modifiers.get('temperature', 0.0)
        adjusted_temps = tile_temps + temp_modifier * 3.0  # 每单位修饰器=3°C
        
        temp_deviation = np.abs(adjusted_temps[:, np.newaxis] - 15.0)
        
        # 高温/低温检测
        high_temp_mask = adjusted_temps[:, np.newaxis] > 20.0
        low_temp_mask = adjusted_temps[:, np.newaxis] < 10.0
        
        temp_pressure = np.zeros((n_tiles, n_species))
        temp_pressure = np.where(
            high_temp_mask,
            (temp_deviation / 30.0) * (1.0 - heat_res[np.newaxis, :]),
            temp_pressure
        )
        temp_pressure = np.where(
            low_temp_mask,
            (temp_deviation / 30.0) * (1.0 - cold_res[np.newaxis, :]),
            temp_pressure
        )
        
        # ========== 水分压力（干旱/洪水） ==========
        drought_modifier = pressure_modifiers.get('drought', 0.0)
        flood_modifier = pressure_modifiers.get('flood', 0.0)
        
        # 干旱压力
        adjusted_humidity = tile_humidity - drought_modifier * 0.1
        drought_base = np.maximum(0, 0.5 - adjusted_humidity[:, np.newaxis]) * 2.0
        drought_pressure = drought_base * (1.0 - drought_res[np.newaxis, :])
        
        # 洪水压力（陆生生物受影响）
        flood_pressure = np.zeros((n_tiles, n_species))
        if flood_modifier > 0:
            # 只有陆生生物受洪水影响
            for sp_idx, sp in enumerate(species_list):
                habitat = getattr(sp, 'habitat_type', 'terrestrial')
                if habitat in ('terrestrial', 'aerial'):
                    flood_pressure[:, sp_idx] = flood_modifier * 0.05
        
        # ========== 特殊事件压力 ==========
        special_pressure = np.zeros((n_tiles, n_species))
        
        # 疾病压力 - 社会性越高越容易传播
        disease_mod = pressure_modifiers.get('disease', 0.0)
        if disease_mod > 0:
            for sp_idx, sp in enumerate(species_list):
                sociality = sp.abstract_traits.get('社会性', 3.0)
                immunity = sp.abstract_traits.get('免疫力', 5.0) / 15.0
                # 社会性高的物种更易感染，免疫力提供保护
                disease_risk = (sociality / 10.0) * disease_mod * 0.08 * (1.0 - immunity)
                special_pressure[:, sp_idx] += disease_risk
        
        # 野火压力 - 陆生生物受影响，挖掘能力提供保护
        wildfire_mod = pressure_modifiers.get('wildfire', 0.0)
        if wildfire_mod > 0:
            for sp_idx, sp in enumerate(species_list):
                habitat = getattr(sp, 'habitat_type', 'terrestrial')
                if habitat in ('terrestrial', 'aerial', 'amphibious'):
                    fire_res = sp.abstract_traits.get('耐火性', 0.0) / 15.0
                    burrow = sp.abstract_traits.get('挖掘能力', 0.0) / 15.0
                    fire_risk = wildfire_mod * 0.07 * (1.0 - max(fire_res, burrow))
                    special_pressure[:, sp_idx] += fire_risk
        
        # 紫外辐射压力 - 表层生物受影响
        uv_mod = pressure_modifiers.get('uv_radiation', 0.0)
        if uv_mod > 0:
            for sp_idx, sp in enumerate(species_list):
                uv_res = sp.abstract_traits.get('抗紫外线', 0.0) / 15.0
                uv_risk = uv_mod * 0.06 * (1.0 - uv_res)
                special_pressure[:, sp_idx] += uv_risk
        
        # 硫化物/毒素压力
        sulfide_mod = pressure_modifiers.get('sulfide', 0.0) + pressure_modifiers.get('toxin_level', 0.0)
        if sulfide_mod > 0:
            for sp_idx, sp in enumerate(species_list):
                detox = sp.abstract_traits.get('解毒能力', 0.0) / 15.0
                toxin_risk = sulfide_mod * 0.08 * (1.0 - detox)
                special_pressure[:, sp_idx] += toxin_risk
        
        # 盐度变化压力 - 主要影响水生生物
        salinity_mod = abs(pressure_modifiers.get('salinity_change', 0.0))
        if salinity_mod > 0:
            salinity_pressure = salinity_mod * 0.05 * (1.0 - salinity_res[np.newaxis, :])
            for sp_idx, sp in enumerate(species_list):
                habitat = getattr(sp, 'habitat_type', 'terrestrial')
                if habitat in ('marine', 'coastal', 'freshwater', 'deep_sea'):
                    special_pressure[:, sp_idx] += salinity_pressure[0, sp_idx]
        
        # 直接死亡率修饰（风暴、地震等）
        mortality_spike = pressure_modifiers.get('mortality_spike', 0.0)
        if mortality_spike > 0:
            special_pressure += mortality_spike * 0.03  # 直接增加基础死亡率
        
        # ========== 基础环境敏感度 ==========
        # 计算剩余未特化处理的压力的综合影响
        handled_modifiers = {
            'temperature', 'drought', 'flood', 'disease', 'wildfire', 
            'uv_radiation', 'sulfide', 'toxin_level', 'salinity_change', 
            'mortality_spike', 'volcano', 'volcanic'
        }
        # 【修复】正向/中性修饰符不应计入死亡压力
        # 这些修饰符表示有利条件或中性变化，不应增加死亡率
        positive_modifiers = {
            'resource_boost',        # 资源丰富（资源繁盛期）
            'productivity',          # 生产力（资源繁盛期）
            'competition',           # 竞争变化（负值=减弱，不应计入）
            'habitat_expansion',     # 栖息地扩展
            'regeneration_opportunity',  # 再生机会（野火后）
            'metabolic_boost',       # 代谢增强（高氧）
            'body_size_potential',   # 大型化潜力（高氧）
            'continental_shelf_exposure',  # 大陆架暴露（中性）
            'oxygen',                # 氧气变化（正值=有利）
            'freshwater_input',      # 淡水输入（中性）
            'nutrient_redistribution',  # 营养重分布（中性）
            'upwelling_change',      # 上升流变化（中性）
            'sea_level',             # 海平面变化（中性，正负意义不同）
            'seasonality',           # 季节性变化（中性）
            'humidity',              # 湿度变化（中性，高湿度不一定有害）
        }
        excluded_modifiers = handled_modifiers | positive_modifiers
        
        # 只累加明确有害的未处理压力（正值部分）
        other_pressure = sum(
            max(0, v) for k, v in pressure_modifiers.items() 
            if k not in excluded_modifiers
        )
        global_pressure = (other_pressure / 30.0) * base_sens[np.newaxis, :]
        
        # ========== 组合压力 ==========
        # 【优化】调整各压力因素权重
        pressure = (
            temp_pressure * 0.25 +      # 温度是基础影响
            drought_pressure * 0.15 +   # 水分次之
            flood_pressure * 0.10 +     # 洪水影响较小
            special_pressure * 0.30 +   # 特殊事件影响显著
            global_pressure * 0.20      # 其他综合影响
        )
        
        return np.clip(pressure, 0.0, 1.0)
    
    def _compute_tile_competition_pressure(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        batch_population_matrix: np.ndarray,
    ) -> np.ndarray:
        """计算每个地块内的竞争压力（Embedding增强版）
        
        【核心改进v3】
        1. 使用预计算的物种相似度矩阵（特征+Embedding混合）
        2. 只有同一地块上的物种才会竞争
        3. 相似度越高，竞争越激烈（生态位重叠）
        4. 向量化批量计算所有地块
        
        竞争强度 = 生态位相似度 × 种群压力比 × 营养级系数
        
        Args:
            species_list: 当前批次的物种列表
            species_arrays: 物种属性数组
            batch_population_matrix: 当前批次对应的population子矩阵
        """
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        if batch_population_matrix is None:
            return np.zeros((n_tiles, n_species))
        
        # ======== 1. 获取或构建相似度矩阵 ========
        if self._species_similarity_matrix is not None and self._species_similarity_matrix.shape[0] == n_species:
            # 使用预计算的相似度矩阵
            similarity_matrix = self._species_similarity_matrix
        else:
            # 回退：重新构建（处理新分化物种的情况）
            self._build_species_similarity_matrix(species_list)
            if self._species_similarity_matrix is not None:
                similarity_matrix = self._species_similarity_matrix
            else:
                # 最终回退：只用营养级
                trophic_levels = species_arrays['trophic_level']
                trophic_diff = np.abs(trophic_levels[:, np.newaxis] - trophic_levels[np.newaxis, :])
                similarity_matrix = np.where(trophic_diff < 0.5, 0.8, 
                                             np.where(trophic_diff < 1.0, 0.4, 0.1))
                np.fill_diagonal(similarity_matrix, 0.0)
        
        # ======== 2. 营养级系数矩阵 ========
        # 同营养级竞争最激烈，相邻层次次之
        trophic_levels = species_arrays['trophic_level']
        trophic_diff = np.abs(trophic_levels[:, np.newaxis] - trophic_levels[np.newaxis, :])
        
        # 营养级系数：同级1.0，相邻0.6，其他0.2
        trophic_coef = np.where(
            trophic_diff < 0.5, 1.0,
            np.where(trophic_diff < 1.0, 0.6, 0.2)
        )
        
        # ======== 3. 综合竞争系数矩阵 ========
        # 竞争系数 = 相似度 × 营养级系数
        # 【强化】提高基础竞争强度（符合达尔文式淘汰）
        comp_coef_matrix = (similarity_matrix * trophic_coef * 0.45).astype(np.float64)
        np.fill_diagonal(comp_coef_matrix, 0.0)
        
        # ======== 4. 向量化计算所有地块的竞争压力 ========
        competition = np.zeros((n_tiles, n_species), dtype=np.float64)
        
        # 对每个地块批量计算
        for tile_idx in range(n_tiles):
            tile_pop = batch_population_matrix[tile_idx, :]
            
            # 获取有种群的物种掩码
            present_mask = tile_pop > 0
            n_present = present_mask.sum()
            
            if n_present <= 1:
                continue
            
            # 种群压力比矩阵
            safe_pop = np.maximum(tile_pop, 1)
            pop_ratio = tile_pop[np.newaxis, :] / safe_pop[:, np.newaxis]
            pop_ratio = np.minimum(pop_ratio, 3.0)  # 限制最大压力比
            
            # 竞争强度 = 竞争系数 × 种群压力比
            comp_strength = comp_coef_matrix * pop_ratio
            
            # 限制单个竞争者的贡献
            comp_strength = np.minimum(comp_strength, 0.25)
            
            # 只考虑在场物种之间的竞争
            present_matrix = present_mask[:, np.newaxis] & present_mask[np.newaxis, :]
            comp_strength = np.where(present_matrix, comp_strength, 0.0)
            
            # 对每个物种汇总竞争压力
            total_competition = comp_strength.sum(axis=1)
            
            # 【强化v3】提高竞争上限，促进达尔文式淘汰
            competition[tile_idx, :] = np.minimum(total_competition, 0.70)
        
        return competition
    
    def _compute_tile_trophic_pressure(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        trophic_interactions: dict[str, float],
        batch_population_matrix: np.ndarray,
    ) -> np.ndarray:
        """计算每个地块内的营养级互动压力（矩阵优化版）
        
        【核心改进】每个地块独立计算营养级生物量比例
        【性能优化】使用矩阵运算预计算生物量
        
        Args:
            species_list: 当前批次的物种列表
            species_arrays: 物种属性数组
            trophic_interactions: 营养级互动
            batch_population_matrix: 【关键】当前批次对应的population子矩阵
        """
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        if batch_population_matrix is None:
            return np.zeros((n_tiles, n_species))
        
        trophic_pressure = np.zeros((n_tiles, n_species), dtype=np.float64)
        trophic_levels = species_arrays['trophic_level']
        int_trophic = trophic_levels.astype(int)  # 取整的营养级
        
        # 【关键修复】使用当前批次的species_list来获取体重
        weights = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0) 
            for sp in species_list  # 使用species_list而不是self._species_list
        ])
        
        # 【关键修复】使用batch_population_matrix计算生物量
        biomass_matrix = batch_population_matrix * weights[np.newaxis, :]
        
        # 为每个营养级创建掩码
        level_masks = {}
        for level in range(1, 6):
            level_masks[level] = (int_trophic == level)
        
        # 计算每个地块各营养级的总生物量 (n_tiles × 5)
        # biomass_by_level[tile_idx, level-1] = 该地块该营养级的总生物量
        biomass_by_level = np.zeros((n_tiles, 5), dtype=np.float64)
        for level in range(1, 6):
            mask = level_masks[level]
            biomass_by_level[:, level - 1] = biomass_matrix[:, mask].sum(axis=1)
        
        EFFICIENCY = 0.12
        MIN_BIOMASS = 1e-6
        
        # 批量计算各种压力
        t1, t2, t3, t4, t5 = [biomass_by_level[:, i] for i in range(5)]
        
        # 【修复】使用np.divide的where参数避免除零警告
        # 先保护分母，确保不会除以0
        safe_t1 = np.maximum(t1, MIN_BIOMASS)
        safe_t2 = np.maximum(t2, MIN_BIOMASS)
        safe_t3 = np.maximum(t3, MIN_BIOMASS)
        safe_t4 = np.maximum(t4, MIN_BIOMASS)
        
        # === T1 受 T2 采食 ===
        req_t1 = np.where(t2 > 0, t2 / EFFICIENCY, 0)
        grazing_ratio = np.divide(req_t1, safe_t1, out=np.zeros_like(req_t1), where=t1 > MIN_BIOMASS)
        grazing = np.minimum(grazing_ratio * 0.5, 0.8)
        scarcity_t2 = np.where(t1 > MIN_BIOMASS, 
                               np.clip(grazing_ratio - 1.0, 0, 2.0),
                               np.where(t2 > 0, 2.0, 0.0))
        
        # === T2 受 T3 捕食 ===
        req_t2 = np.where(t3 > 0, t3 / EFFICIENCY, 0)
        ratio_t2 = np.divide(req_t2, safe_t2, out=np.zeros_like(req_t2), where=t2 > MIN_BIOMASS)
        pred_t3 = np.minimum(ratio_t2 * 0.5, 0.8)
        scarcity_t3 = np.where(t2 > MIN_BIOMASS,
                               np.clip(ratio_t2 - 1.0, 0, 2.0),
                               np.where(t3 > 0, 2.0, 0.0))
        
        # === T3 受 T4 捕食 ===
        req_t3 = np.where(t4 > 0, t4 / EFFICIENCY, 0)
        ratio_t3 = np.divide(req_t3, safe_t3, out=np.zeros_like(req_t3), where=t3 > MIN_BIOMASS)
        pred_t4 = np.minimum(ratio_t3 * 0.5, 0.8)
        scarcity_t4 = np.where(t3 > MIN_BIOMASS,
                               np.clip(ratio_t3 - 1.0, 0, 2.0),
                               np.where(t4 > 0, 2.0, 0.0))
        
        # === T4 受 T5 捕食 ===
        req_t4 = np.where(t5 > 0, t5 / EFFICIENCY, 0)
        ratio_t4 = np.divide(req_t4, safe_t4, out=np.zeros_like(req_t4), where=t4 > MIN_BIOMASS)
        pred_t5 = np.minimum(ratio_t4 * 0.5, 0.8)
        scarcity_t5 = np.where(t4 > MIN_BIOMASS,
                               np.clip(ratio_t4 - 1.0, 0, 2.0),
                               np.where(t5 > 0, 2.0, 0.0))
        
        # 将压力分配到各物种
        for sp_idx in range(n_species):
            t_level = int_trophic[sp_idx]
            
            if t_level == 1:
                trophic_pressure[:, sp_idx] = grazing
            elif t_level == 2:
                trophic_pressure[:, sp_idx] = np.maximum(pred_t3, scarcity_t2 * 0.3)
            elif t_level == 3:
                trophic_pressure[:, sp_idx] = np.maximum(pred_t4, scarcity_t3 * 0.3)
            elif t_level == 4:
                trophic_pressure[:, sp_idx] = np.maximum(pred_t5, scarcity_t4 * 0.3)
            elif t_level >= 5:
                trophic_pressure[:, sp_idx] = scarcity_t5 * 0.3
        
        # 【关键修复】使用batch_population_matrix而不是self._population_matrix
        trophic_pressure = np.where(batch_population_matrix > 0, trophic_pressure, 0)
        
        return trophic_pressure
    
    def _compute_trophic_pressures_for_tile(
        self, 
        biomass_by_level: dict[int, float]
    ) -> dict[str, float]:
        """计算单个地块的营养级压力"""
        EFFICIENCY = 0.12
        MIN_BIOMASS = 1e-6
        
        t1 = biomass_by_level.get(1, 0.0)
        t2 = biomass_by_level.get(2, 0.0)
        t3 = biomass_by_level.get(3, 0.0)
        t4 = biomass_by_level.get(4, 0.0)
        t5 = biomass_by_level.get(5, 0.0)
        
        result = {}
        
        # T1 受 T2 采食
        if t1 > MIN_BIOMASS:
            req_t1 = t2 / EFFICIENCY if t2 > 0 else 0
            grazing_ratio = req_t1 / t1
            result["grazing"] = min(grazing_ratio * 0.5, 0.8)
            result["scarcity_t2"] = max(0.0, min(2.0, grazing_ratio - 1.0))
        elif t2 > 0:
            result["scarcity_t2"] = 2.0
        
        # T2 受 T3 捕食
        if t2 > MIN_BIOMASS:
            req_t2 = t3 / EFFICIENCY if t3 > 0 else 0
            ratio = req_t2 / t2
            result["pred_t3"] = min(ratio * 0.5, 0.8)
            result["scarcity_t3"] = max(0.0, min(2.0, ratio - 1.0))
        elif t3 > 0:
            result["scarcity_t3"] = 2.0
        
        # T3 受 T4 捕食
        if t3 > MIN_BIOMASS:
            req_t3 = t4 / EFFICIENCY if t4 > 0 else 0
            ratio = req_t3 / t3
            result["pred_t4"] = min(ratio * 0.5, 0.8)
            result["scarcity_t4"] = max(0.0, min(2.0, ratio - 1.0))
        elif t4 > 0:
            result["scarcity_t4"] = 2.0
        
        # T4 受 T5 捕食
        if t4 > MIN_BIOMASS:
            req_t4 = t5 / EFFICIENCY if t5 > 0 else 0
            ratio = req_t4 / t4
            result["pred_t5"] = min(ratio * 0.5, 0.8)
            result["scarcity_t5"] = max(0.0, min(2.0, ratio - 1.0))
        elif t5 > 0:
            result["scarcity_t5"] = 2.0
        
        return result
    
    def _compute_tile_resource_pressure(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        batch_population_matrix: np.ndarray,
    ) -> np.ndarray:
        """计算每个地块的资源压力（矩阵优化版）
        
        考虑地块资源量 vs 该地块物种总需求
        
        Args:
            species_list: 当前批次的物种列表
            species_arrays: 物种属性数组
            batch_population_matrix: 【关键】当前批次对应的population子矩阵
        """
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        if batch_population_matrix is None or self._tile_env_matrix is None:
            return np.zeros((n_tiles, n_species))
        
        # 预计算物种属性向量
        weights = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0) 
            for sp in species_list
        ])
        metabolics = np.array([
            sp.morphology_stats.get("metabolic_rate", 3.0) 
            for sp in species_list
        ])
        
        # 需求系数 = 体重 × (代谢率 / 10)
        demand_coef = weights * (metabolics / 10.0)  # (n_species,)
        
        # 【关键修复】使用batch_population_matrix计算需求
        demand_matrix = batch_population_matrix * demand_coef[np.newaxis, :]
        
        # 每个地块的总需求 (n_tiles,)
        total_demand_per_tile = demand_matrix.sum(axis=1)
        
        # 地块资源 (n_tiles,)
        tile_resources = self._tile_env_matrix[:, 2]
        
        # 供给能力 (n_tiles,)
        supply_capacity = tile_resources * 1000
        
        # 短缺比例 (n_tiles,)
        # shortage = max(0, (demand - supply) / demand)
        with np.errstate(divide='ignore', invalid='ignore'):
            shortage_ratio = np.maximum(0.0, (total_demand_per_tile - supply_capacity) / total_demand_per_tile)
            shortage_ratio = np.nan_to_num(shortage_ratio, 0.0)
        
        # 每个物种的需求占比 (n_tiles × n_species)
        with np.errstate(divide='ignore', invalid='ignore'):
            demand_ratio = demand_matrix / total_demand_per_tile[:, np.newaxis]
            demand_ratio = np.nan_to_num(demand_ratio, 0.0)
        
        # 资源压力 = 短缺比例 × min(需求占比 × 2, 1.0)
        resource_pressure = shortage_ratio[:, np.newaxis] * np.minimum(demand_ratio * 2.0, 1.0)
        
        # 【关键修复】使用batch_population_matrix
        resource_pressure = np.where(batch_population_matrix > 0, resource_pressure, 0.0)
        
        return np.clip(resource_pressure, 0.0, 0.65)
    
    def _compute_predation_network_pressure(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        batch_population_matrix: np.ndarray,
    ) -> np.ndarray:
        """计算基于真实捕食关系的压力（矩阵优化版）
        
        【核心改进】
        使用矩阵运算批量计算，而非逐个物种循环：
        
        1. 构建捕食关系稀疏矩阵
        2. 批量计算饥饿压力（捕食者角度）
        3. 批量计算被捕食压力（猎物角度）
        
        Args:
            species_list: 当前批次的物种列表
            species_arrays: 物种属性数组
            batch_population_matrix: 当前批次对应的population子矩阵
            
        Returns:
            (num_tiles × num_species) 的捕食网压力矩阵
        """
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        if batch_population_matrix is None or n_species == 0:
            return np.zeros((n_tiles, n_species))
        
        # ========== 1. 构建捕食关系矩阵 (n_species × n_species) ==========
        # matrix[i,j] > 0 表示物种i捕食物种j
        code_to_idx = {sp.lineage_code: idx for idx, sp in enumerate(species_list)}
        predation_matrix = np.zeros((n_species, n_species), dtype=np.float32)
        
        for sp_idx, species in enumerate(species_list):
            for prey_code in (species.prey_species or []):
                prey_idx = code_to_idx.get(prey_code)
                if prey_idx is not None:
                    preference = (species.prey_preferences or {}).get(prey_code, 0.5)
                    predation_matrix[sp_idx, prey_idx] = preference
        
        # ========== 2. 获取物种属性向量 ==========
        trophic_levels = species_arrays['trophic_level']
        weights = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0) 
            for sp in species_list
        ], dtype=np.float64)
        
        # ========== 3. 按地块批量计算 ==========
        predation_pressure = np.zeros((n_tiles, n_species), dtype=np.float64)
        
        for tile_idx in range(n_tiles):
            tile_pop = batch_population_matrix[tile_idx, :]  # (n_species,)
            
            # 跳过空地块
            if tile_pop.sum() == 0:
                continue
            
            # 生物量向量
            tile_biomass = tile_pop * weights  # (n_species,)
            
            # === 饥饿压力（捕食者角度）===
            # available_prey[i] = 捕食者i在该地块可获得的猎物生物量
            # = sum(predation_matrix[i, j] * prey_biomass[j])
            available_prey = predation_matrix @ tile_biomass
            
            # 捕食者需求 = 自身生物量 × 0.1（每天需要体重10%的食物）
            predator_demand = tile_biomass * 0.1
            
            # 饥饿压力 = max(0, (需求 - 供给) / 需求)
            with np.errstate(divide='ignore', invalid='ignore'):
                starvation_ratio = np.where(
                    predator_demand > 0,
                    np.maximum(0, (predator_demand - available_prey) / predator_demand),
                    0.0
                )
            starvation_ratio = np.nan_to_num(starvation_ratio, 0.0)
            
            # 生产者（营养级<2）不受饥饿压力
            starvation_ratio = np.where(trophic_levels < 2.0, 0.0, starvation_ratio)
            
            # 饥饿压力 = ratio^1.5 * 0.5
            starvation_pressure = (starvation_ratio ** 1.5) * 0.5
            
            # === 被捕食压力（猎物角度）===
            # predation_demand[j] = 所有捕食者对猎物j的需求
            # = sum(predation_matrix[:, j] * predator_biomass * 0.1)
            predation_demand_vec = (predation_matrix.T @ (tile_biomass * 0.1))
            
            # 被捕食压力 = 需求 / 生物量 的sigmoid
            with np.errstate(divide='ignore', invalid='ignore'):
                pressure_ratio = np.where(
                    tile_biomass > 0,
                    predation_demand_vec / tile_biomass,
                    0.0
                )
            pressure_ratio = np.nan_to_num(pressure_ratio, 0.0)
            
            # Sigmoid转换: ratio=1 → 0.27, ratio=2 → 0.46, ratio=5 → 0.73
            predation_from_hunters = (2.0 / (1.0 + np.exp(-pressure_ratio)) - 1.0) * 0.3
            
            # 综合压力
            tile_pressure = starvation_pressure + predation_from_hunters
            
            # 只对有种群的物种应用
            has_pop = tile_pop > 0
            predation_pressure[tile_idx, has_pop] = tile_pressure[has_pop]
        
        return np.clip(predation_pressure, 0.0, 0.7)
    
    def _compute_plant_competition_pressure(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        batch_population_matrix: np.ndarray,
    ) -> np.ndarray:
        """【优化版】矩阵化计算植物竞争压力（光照+养分）
        
        只对植物（营养级<2.0）有效：
        1. 光照竞争：高大植物遮蔽矮小植物
        2. 养分竞争：根系发达的植物抢夺更多养分
        3. Embedding相似度加成：相似物种竞争更激烈
        
        Args:
            species_list: 物种列表
            species_arrays: 物种属性数组
            batch_population_matrix: 种群分布矩阵
            
        Returns:
            (n_tiles, n_species) 植物竞争压力矩阵
        """
        from ..services.species.plant_competition import plant_competition_calculator
        
        n_tiles = len(self._tiles)
        n_species = len(species_list)
        
        # 过滤出植物物种
        trophic_levels = species_arrays['trophic_level']
        plant_mask = trophic_levels < 2.0
        
        if not np.any(plant_mask):
            return np.zeros((n_tiles, n_species), dtype=np.float64)
        
        # 地块资源向量
        tile_resources = self._tile_env_matrix[:, 2] if self._tile_env_matrix is not None else np.full(n_tiles, 50.0)
        
        # 【优化】直接使用矩阵化计算
        try:
            plant_pressure = plant_competition_calculator.compute_competition_matrix(
                species_list,
                batch_population_matrix,
                tile_resources,
            )
            
            # 统计日志
            if np.any(plant_mask):
                avg_pressure = plant_pressure[:, plant_mask].mean()
                max_pressure = plant_pressure[:, plant_mask].max()
                logger.debug(
                    f"[植物竞争] 矩阵计算完成，"
                    f"平均压力={avg_pressure:.3f}, 最大压力={max_pressure:.3f}"
                )
        except Exception as e:
            logger.warning(f"[植物竞争] 矩阵计算失败: {e}")
            plant_pressure = np.zeros((n_tiles, n_species), dtype=np.float64)
        
        return np.clip(plant_pressure, 0.0, 0.5)
    
    def _compute_and_cache_herbivory_pressure(
        self,
        species_list: list[Species],
    ) -> None:
        """【新增】计算并缓存食草压力
        
        为每个植物物种计算食草动物的捕食压力，
        并缓存到 _last_herbivory_pressure 供结果汇总使用
        """
        from ..services.species.plant_competition import plant_competition_calculator
        from ..services.species.trait_config import PlantTraitConfig
        
        self._last_herbivory_pressure.clear()
        
        for species in species_list:
            if not PlantTraitConfig.is_plant(species):
                continue
            
            try:
                herbivory_info = plant_competition_calculator.get_herbivory_pressure(
                    species, species_list
                )
                self._last_herbivory_pressure[species.lineage_code] = herbivory_info.get("pressure", 0.0)
            except Exception as e:
                logger.debug(f"[食草压力] 计算失败 {species.common_name}: {e}")
                self._last_herbivory_pressure[species.lineage_code] = 0.0
    
    def _apply_generational_mortality(
        self,
        species_arrays: dict[str, np.ndarray],
        mortality: np.ndarray,
    ) -> np.ndarray:
        """【平衡修复v2】应用世代适应性加成 - 大幅降低减免
        
        50万年时间尺度说明：
        - 微生物（1天1代）：约1.8亿代，有充足时间演化适应
        - 昆虫（1月1代）：约600万代
        - 哺乳动物（1年1代）：约50万代
        
        【平衡修复】原方案减免太多（最高50%），导致高压力下死亡率仍然很低
        调整后最高减免从50%降到25%
        """
        n_tiles, n_species = mortality.shape
        
        generation_time = species_arrays['generation_time']
        body_size = species_arrays['body_size']
        population = species_arrays['population']
        
        # 计算50万年内的世代数 (n_species,)
        num_generations = (_settings.turn_years * 365) / np.maximum(1.0, generation_time)
        
        # 基于世代数的适应性加成（大幅降低）
        # 使用对数缩放
        log_generations = np.log10(np.maximum(1.0, num_generations))
        
        # 【修复】演化适应加成大幅降低：
        # 1亿代(log=8) -> 0.15加成（原0.35）
        # 100万代(log=6) -> 0.10加成（原0.25）
        # 50万代(log=5.7) -> 0.09加成（原0.22）
        # 1万代(log=4) -> 0.04加成（原0.12）
        evolution_bonus = np.clip((log_generations - 3.0) / 5.0 * 0.15, 0.0, 0.18)
        
        # 【修复】体型抗性降低
        size_bonus = np.where(
            body_size < 0.01, 0.06,  # 微生物（原0.15）
            np.where(body_size < 0.1, 0.04,  # 小型（原0.10）
                np.where(body_size < 1.0, 0.02, 0.0))  # 中型（原0.05）
        )
        
        # 【修复】种群规模抗性降低
        pop_bonus = np.where(
            population > 1_000_000, 0.04,  # 原0.10
            np.where(population > 100_000, 0.02, 0.0)  # 原0.05
        )
        
        # 【修复】综合抗性上限从50%降到25%
        total_resistance = np.minimum(0.25, evolution_bonus + size_bonus + pop_bonus)
        
        # 广播到矩阵形状 (n_tiles, n_species)
        resistance_matrix = total_resistance[np.newaxis, :]
        
        # 应用抗性：降低死亡率
        adjusted_mortality = mortality * (1.0 - resistance_matrix)
        
        return np.clip(adjusted_mortality, 0.0, 0.98)
    
    def _aggregate_tile_results(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        mortality_matrix: np.ndarray,
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        extinct_codes: set[str],
    ) -> list[AggregatedMortalityResult]:
        """汇总各地块结果，计算物种总体死亡率
        
        【v2更新】按地块独立存活制计算：
        - 每个地块独立计算存活数
        - 避难所地块（死亡率<20%）可保证物种存续
        - 汇总各地块存活数得到总存活数
        
        汇总方式：按地块独立计算后求和
        total_survivors = Σ(tile_pop × (1 - tile_death_rate))
        """
        n_species = len(species_list)
        results: list[AggregatedMortalityResult] = []
        
        for sp_idx, species in enumerate(species_list):
            total_pop = int(species_arrays['population'][sp_idx])
            
            if total_pop <= 0:
                # 种群为0，死亡率100%
                results.append(AggregatedMortalityResult(
                    species=species,
                    initial_population=0,
                    deaths=0,
                    survivors=0,
                    death_rate=1.0,
                    notes=["种群已归零"],
                    niche_overlap=species_arrays['overlap'][sp_idx],
                    resource_pressure=species_arrays['saturation'][sp_idx],
                    is_background=species.is_background,
                    tier=tier,
                    total_tiles=0,
                ))
                continue
            
            # 获取该物种在各地块的种群分布
            if self._population_matrix is not None:
                tile_pops = self._population_matrix[:, sp_idx]
            else:
                tile_pops = np.array([total_pop])
            
            # 获取各地块死亡率
            tile_rates = mortality_matrix[:, sp_idx]
            
            # 【v2核心】计算地块健康统计
            # 只统计有种群的地块
            occupied_mask = tile_pops > 0
            occupied_rates = tile_rates[occupied_mask]
            occupied_pops = tile_pops[occupied_mask]
            
            total_tiles = int(occupied_mask.sum())
            
            if total_tiles > 0:
                healthy_tiles = int((occupied_rates < 0.25).sum())
                warning_tiles = int(((occupied_rates >= 0.25) & (occupied_rates < 0.50)).sum())
                critical_tiles = int((occupied_rates >= 0.50).sum())
                best_tile_rate = float(occupied_rates.min())
                worst_tile_rate = float(occupied_rates.max())
                has_refuge = bool((occupied_rates < 0.20).any())
            else:
                healthy_tiles = warning_tiles = critical_tiles = 0
                best_tile_rate = 0.0
                worst_tile_rate = 1.0
                has_refuge = False
            
            # 【v2核心】按地块独立计算存活数
            # 每个地块独立应用死亡率，然后汇总
            tile_survivors = tile_pops * (1.0 - tile_rates)
            tile_deaths_count = tile_pops * tile_rates
            
            total_survivors = int(tile_survivors.sum())
            total_deaths = int(tile_deaths_count.sum())
            
            # 应用干预修正（按比例调整）
            if species_arrays['is_protected'][sp_idx] and species_arrays['protection_turns'][sp_idx] > 0:
                # 保护效果：减少一半死亡
                protection_saved = total_deaths // 2
                total_survivors += protection_saved
                total_deaths -= protection_saved
            
            if species_arrays['is_suppressed'][sp_idx] and species_arrays['suppression_turns'][sp_idx] > 0:
                # 压制效果：额外30%死亡
                suppress_deaths = int(total_survivors * 0.30)
                total_survivors -= suppress_deaths
                total_deaths += suppress_deaths
            
            # 边界约束
            total_survivors = max(0, min(total_pop, total_survivors))
            total_deaths = max(0, total_pop - total_survivors)
            
            # 计算总体死亡率（用于报告和记录）
            if total_pop > 0:
                overall_death_rate = total_deaths / total_pop
            else:
                overall_death_rate = 1.0
            
            overall_death_rate = min(0.98, max(0.03, overall_death_rate))
            
            # 生成分析文本（包含地块信息）
            notes = [self._generate_tile_mortality_notes(
                species, overall_death_rate, total_tiles, healthy_tiles, 
                critical_tiles, has_refuge, best_tile_rate, worst_tile_rate
            )]
            
            # 【Embedding兼容】生成死因描述
            death_causes = self._generate_death_causes(
                species, overall_death_rate, species_arrays, sp_idx
            )
            
            if overall_death_rate > 0.5:
                logger.info(f"[高死亡率警告] {species.common_name}: {overall_death_rate:.1%} (分布{total_tiles}块，危机{critical_tiles}块)")
            
            # 【新增】计算植物专用压力字段
            plant_comp_pressure = 0.0
            light_comp = 0.0
            nutrient_comp = 0.0
            herb_pressure = 0.0
            
            if species_arrays['trophic_level'][sp_idx] < 2.0:  # 是植物
                # 从缓存的植物竞争矩阵中计算加权平均
                if self._last_plant_competition_matrix is not None:
                    if self._population_matrix is not None:
                        sp_pops = self._population_matrix[:, sp_idx]
                        total_sp_pop = sp_pops.sum()
                        if total_sp_pop > 0:
                            plant_comp_pressure = float(
                                (self._last_plant_competition_matrix[:, sp_idx] * sp_pops).sum() 
                                / total_sp_pop
                            )
                    else:
                        plant_comp_pressure = float(self._last_plant_competition_matrix[:, sp_idx].mean())
                
                # 获取食草压力
                herb_pressure = self._last_herbivory_pressure.get(species.lineage_code, 0.0)
            
            results.append(AggregatedMortalityResult(
                species=species,
                initial_population=total_pop,
                deaths=total_deaths,
                survivors=total_survivors,
                death_rate=overall_death_rate,
                notes=notes,
                niche_overlap=species_arrays['overlap'][sp_idx],
                resource_pressure=species_arrays['saturation'][sp_idx],
                is_background=species.is_background,
                tier=tier,
                death_causes=death_causes,
                plant_competition_pressure=plant_comp_pressure,
                light_competition=light_comp,
                nutrient_competition=nutrient_comp,
                herbivory_pressure=herb_pressure,
                # 【v2新增】地块分布统计
                total_tiles=total_tiles,
                healthy_tiles=healthy_tiles,
                warning_tiles=warning_tiles,
                critical_tiles=critical_tiles,
                best_tile_rate=best_tile_rate,
                worst_tile_rate=worst_tile_rate,
                has_refuge=has_refuge,
            ))
        
        return results
    
    def _generate_tile_mortality_notes(
        self,
        species: Species,
        death_rate: float,
        total_tiles: int,
        healthy_tiles: int,
        critical_tiles: int,
        has_refuge: bool,
        best_rate: float,
        worst_rate: float,
    ) -> str:
        """生成包含地块信息的死亡率分析文本"""
        if total_tiles == 0:
            return f"{species.common_name}无分布数据。"
        
        # 状态描述
        if critical_tiles == total_tiles:
            status = "⚠️全域危机"
        elif critical_tiles > total_tiles * 0.5:
            status = "🔴部分危机"
        elif healthy_tiles >= total_tiles * 0.5:
            status = "🟢稳定"
        else:
            status = "🟡警告"
        
        # 避难所信息
        refuge_info = "有避难所" if has_refuge else "无避难所！"
        
        # 地块分布
        dist_info = f"分布{total_tiles}块(健康{healthy_tiles}/危机{critical_tiles})"
        
        # 死亡率范围
        rate_range = f"最低{best_rate:.0%}~最高{worst_rate:.0%}"
        
        return f"{species.common_name}【{status}】{dist_info}，{refuge_info}，死亡率{rate_range}，总体{death_rate:.1%}"
    
    def _generate_mortality_notes(
        self,
        species: Species,
        death_rate: float,
        species_arrays: dict[str, np.ndarray],
        sp_idx: int,
    ) -> str:
        """生成死亡率分析文本"""
        analysis_parts = []
        
        if species_arrays['overlap'][sp_idx] > 0.3:
            analysis_parts.append(f"生态位竞争明显(重叠度{species_arrays['overlap'][sp_idx]:.2f})")
        if species_arrays['saturation'][sp_idx] > 1.0:
            analysis_parts.append(f"种群饱和(S={species_arrays['saturation'][sp_idx]:.2f})")
        
        body_size = species_arrays['body_size'][sp_idx]
        if body_size < 0.01:
            analysis_parts.append("体型极小，对环境变化敏感")
        elif body_size > 100:
            analysis_parts.append("体型巨大，具有一定抗压能力")
        
        if analysis_parts:
            return f"{species.common_name}本回合死亡率{death_rate:.1%}（按地块加权）：" + "；".join(analysis_parts) + "。"
        else:
            return f"{species.common_name}死亡率{death_rate:.1%}（按地块加权），种群状况稳定。"
    
    def _generate_death_causes(
        self,
        species: Species,
        death_rate: float,
        species_arrays: dict[str, np.ndarray],
        sp_idx: int,
    ) -> str:
        """【Embedding兼容】生成死因描述
        
        用于Embedding模块记录灭绝事件的原因
        """
        if death_rate < 0.1:
            return "环境稳定，种群健康"
        
        causes = []
        
        # 生态位竞争
        overlap = species_arrays['overlap'][sp_idx]
        if overlap > 0.5:
            causes.append(f"激烈的生态位竞争（重叠度{overlap:.0%}）")
        elif overlap > 0.3:
            causes.append("生态位竞争")
        
        # 资源压力
        saturation = species_arrays['saturation'][sp_idx]
        if saturation > 1.5:
            causes.append("严重的资源匮乏")
        elif saturation > 1.0:
            causes.append("资源压力")
        
        # 营养级（从营养级推断）
        trophic = species_arrays['trophic_level'][sp_idx]
        if trophic >= 4.0 and death_rate > 0.4:
            causes.append("食物链顶端的猎物稀缺")
        elif trophic >= 2.0 and trophic < 3.0 and death_rate > 0.5:
            causes.append("被捕食压力或食物短缺")
        elif trophic < 2.0 and death_rate > 0.4:
            causes.append("被过度采食")
        
        # 体型相关
        body_size = species_arrays['body_size'][sp_idx]
        if body_size > 100 and death_rate > 0.5:
            causes.append("大型体型的高代谢负担")
        
        # 如果死亡率高但没有明确原因
        if not causes and death_rate > 0.3:
            causes.append("环境综合压力")
        
        if causes:
            return "；".join(causes[:3])  # 最多3个原因
        else:
            return f"死亡率{death_rate:.1%}"
    
    def _fallback_global_evaluate(
        self,
        species_list: list[Species],
        pressure_modifiers: dict[str, float],
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        trophic_interactions: dict[str, float],
        extinct_codes: set[str],
    ) -> list[AggregatedMortalityResult]:
        """降级处理：使用全局计算（兼容原有逻辑）"""
        logger.warning("[地块死亡率] 降级为全局计算模式")
        
        # 使用简化的全局计算
        results: list[AggregatedMortalityResult] = []
        
        pressure_score = sum(pressure_modifiers.values()) / max(len(pressure_modifiers), 1)
        
        for species in species_list:
            population = int(species.morphology_stats.get("population", 0) or 0)
            env_sensitivity = species.hidden_traits.get("environment_sensitivity", 0.5)
            
            metrics = niche_metrics.get(species.lineage_code, NicheMetrics(overlap=0.0, saturation=0.0))
            
            # 简化的死亡率计算
            base_mortality = (pressure_score / 25.0) * env_sensitivity
            overlap_penalty = metrics.overlap * 0.3
            saturation_penalty = min(0.3, metrics.saturation * 0.1)
            
            death_rate = min(0.98, max(0.03, base_mortality + overlap_penalty + saturation_penalty))
            
            deaths = int(population * death_rate)
            survivors = max(0, population - deaths)
            
            results.append(AggregatedMortalityResult(
                species=species,
                initial_population=population,
                deaths=deaths,
                survivors=survivors,
                death_rate=death_rate,
                notes=[f"{species.common_name}死亡率{death_rate:.1%}（全局模式）"],
                niche_overlap=metrics.overlap,
                resource_pressure=metrics.saturation,
                is_background=species.is_background,
                tier=tier,
            ))
        
        return results

