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
from ..services.geo.suitability import get_habitat_type_mask as unified_habitat_mask
from ..core.config import get_settings, PROJECT_ROOT
from ..models.config import EcologyBalanceConfig, MortalityConfig, SpeciationConfig

logger = logging.getLogger(__name__)

# 获取配置
_settings = get_settings()




def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """计算两个六边形格子之间的距离（轴坐标系）
    
    使用 cube 坐标转换计算曼哈顿距离
    """
    # 转换为 cube 坐标 (q, r, s)，其中 s = -q - r
    s1 = -q1 - r1
    s2 = -q2 - r2
    return max(abs(q1 - q2), abs(r1 - r2), abs(s1 - s2))


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
    
    # 【新增v3】繁殖数据（在engine.py计算完繁殖后填充）
    births: int = 0  # 本回合新出生的个体数量
    final_population: int = 0  # 回合结束时的最终种群
    
    # 【新增v4】AI修正后的参数（在种群更新阶段填充）
    adjusted_death_rate: float = 0.0  # AI修正后的死亡率
    adjusted_k: float = 0.0  # AI修正后的承载力
    
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
    
    【依赖注入】
    配置必须通过构造函数注入，内部方法不再调用 _load_*_config。
    如需刷新配置，使用 reload_config() 显式更新。
    """
    
    def __init__(
        self,
        batch_limit: int = 50,
        ecology_config: EcologyBalanceConfig | None = None,
        mortality_config: MortalityConfig | None = None,
        speciation_config: SpeciationConfig | None = None,
    ) -> None:
        """初始化死亡率计算引擎
        
        Args:
            batch_limit: 批处理大小
            ecology_config: 生态平衡配置（必须提供，或调用 reload_config 加载）
            mortality_config: 死亡率配置（必须提供，或调用 reload_config 加载）
            speciation_config: 分化配置（必须提供，或调用 reload_config 加载）
            
        注意: 如果配置未提供，将使用默认值并记录警告。
              生产环境应通过 SimulationEngine 传入配置。
        """
        self.batch_limit = batch_limit
        
        # 配置注入 - 如未提供则使用默认值并警告
        if ecology_config is None:
            logger.warning("[死亡率引擎] ecology_config 未注入，使用默认值")
            ecology_config = EcologyBalanceConfig()
        if mortality_config is None:
            logger.warning("[死亡率引擎] mortality_config 未注入，使用默认值")
            mortality_config = MortalityConfig()
        if speciation_config is None:
            logger.warning("[死亡率引擎] speciation_config 未注入，使用默认值")
            speciation_config = SpeciationConfig()
        
        self._ecology_config = ecology_config
        self._mortality_config = mortality_config
        self._speciation_config = speciation_config
        
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
        
        # 【修复】累积存活数据（跨多个evaluate批次）
        self._accumulated_tile_survivors: dict[str, dict[int, int]] = {}
        self._accumulated_tile_mortality: dict[str, dict[int, float]] = {}
        self._accumulated_tile_population: dict[str, dict[int, float]] = {}
        
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
    
    def reload_config(
        self,
        ecology_config: EcologyBalanceConfig | None = None,
        mortality_config: MortalityConfig | None = None,
        speciation_config: SpeciationConfig | None = None,
    ) -> None:
        """热更新配置
        
        Args:
            ecology_config: 生态平衡配置（必须由调用方提供）
            mortality_config: 死亡率配置（必须由调用方提供）
            speciation_config: 分化配置（必须由调用方提供）
            
        注意: 配置应由 SimulationEngine.reload_configs() 统一从容器获取后传入。
        """
        if ecology_config is not None:
            self._ecology_config = ecology_config
        if mortality_config is not None:
            self._mortality_config = mortality_config
        if speciation_config is not None:
            self._speciation_config = speciation_config
        logger.info("[死亡率引擎] 配置已重新加载")
    
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
        
        【修复】如果物种没有栖息地记录（sum_suit==0），按栖息地类型均匀分配到合适的地块，
        避免种群被错误地计算为0导致假灭绝。
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
            else:
                # 【修复】物种没有栖息地记录，按栖息地类型均匀分配
                # 这种情况通常发生在新创建的物种尚未初始化栖息地时
                habitat_type = getattr(species, 'habitat_type', 'terrestrial')
                type_mask = self._get_habitat_type_mask(habitat_type)
                suitable_count = type_mask.sum()
                
                if suitable_count > 0:
                    # 均匀分配到所有合适类型的地块
                    pop_per_tile = total_pop / suitable_count
                    self._population_matrix[type_mask, sp_idx] = pop_per_tile
                    # 同时设置一个基础适宜度，避免后续计算问题
                    self._suitability_matrix[type_mask, sp_idx] = 0.5
                    logger.warning(
                        f"[地块死亡率] {species.common_name} 无栖息地记录，"
                        f"均匀分配 {total_pop} 种群到 {suitable_count} 个 {habitat_type} 地块"
                    )
    
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
        """获取适合某种栖息地类型的地块掩码
        
        【优化】使用统一的栖息地类型筛选器
        """
        return unified_habitat_mask(self._tiles, habitat_type)
    
    def _build_tile_adjacency(self, tiles: list[MapTile]) -> None:
        """构建地块邻接关系
        
        【改进】使用六边形轴坐标 (q, r) 的 6 邻域，而非 8 邻域
        这样更准确地反映六边形网格的连通性，避免对角相连降低分裂概率
        """
        self._tile_adjacency = {}
        
        # 构建六边形轴坐标 (q, r) 到 tile_id 的映射
        coord_to_tile: dict[tuple[int, int], int] = {}
        for tile in tiles:
            q = getattr(tile, 'q', None)
            r = getattr(tile, 'r', None)
            if q is not None and r is not None and tile.id is not None:
                coord_to_tile[(q, r)] = tile.id
        
        # 六边形轴坐标的 6 邻域偏移 (dq, dr)
        # 在 axial 坐标系中，6 个相邻格子的偏移量是固定的
        hex_neighbors_offset = [
            (+1,  0), (+1, -1), ( 0, -1),
            (-1,  0), (-1, +1), ( 0, +1),
        ]
        
        # 为每个地块找邻居
        for tile in tiles:
            if tile.id is None:
                continue
            
            q = getattr(tile, 'q', None)
            r = getattr(tile, 'r', None)
            
            if q is None or r is None:
                # 没有六边形坐标，尝试使用 row/col 回退
                row = getattr(tile, 'row', None)
                col = getattr(tile, 'col', None)
                if row is None or col is None:
                    self._tile_adjacency[tile.id] = set()
                    continue
                # 回退到简单的 4 邻域（上下左右）
                fallback_offset = [(0, 1), (0, -1), (1, 0), (-1, 0)]
                neighbors = set()
                for dr, dc in fallback_offset:
                    neighbor_coord = (row + dr, col + dc)
                    # 这里需要 row/col 映射，但我们用 q/r 映射，所以跳过
                self._tile_adjacency[tile.id] = neighbors
                continue
            
            neighbors = set()
            for dq, dr in hex_neighbors_offset:
                neighbor_coord = (q + dq, r + dr)
                if neighbor_coord in coord_to_tile:
                    neighbors.add(coord_to_tile[neighbor_coord])
            
            self._tile_adjacency[tile.id] = neighbors
        
        logger.debug(f"[地块邻接] 构建了 {len(self._tile_adjacency)} 个地块的六边形6邻域关系")
    
    def clear_accumulated_data(self) -> None:
        """清空累积的存活数据（每回合开始时调用）"""
        self._accumulated_tile_survivors.clear()
        self._accumulated_tile_mortality.clear()
        self._accumulated_tile_population.clear()
    
    def _accumulate_batch_results(
        self, 
        species_list: list[Species],
        population_matrix: np.ndarray,
        mortality_matrix: np.ndarray
    ) -> None:
        """累积当前批次的存活数据
        
        每次调用 evaluate 后，将结果累积到全局字典中，
        而不是覆盖之前的数据。
        """
        for sp_idx, species in enumerate(species_list):
            lineage_code = species.lineage_code
            
            # 初始化该物种的字典
            if lineage_code not in self._accumulated_tile_survivors:
                self._accumulated_tile_survivors[lineage_code] = {}
            if lineage_code not in self._accumulated_tile_mortality:
                self._accumulated_tile_mortality[lineage_code] = {}
            if lineage_code not in self._accumulated_tile_population:
                self._accumulated_tile_population[lineage_code] = {}
            
            for tile_id, tile_idx in self._tile_id_to_idx.items():
                pop = population_matrix[tile_idx, sp_idx]
                if pop > 0:
                    mortality_rate = mortality_matrix[tile_idx, sp_idx]
                    survivors = int(pop * (1.0 - mortality_rate))
                    
                    self._accumulated_tile_population[lineage_code][tile_id] = float(pop)
                    self._accumulated_tile_mortality[lineage_code][tile_id] = float(mortality_rate)
                    if survivors > 0:
                        self._accumulated_tile_survivors[lineage_code][tile_id] = survivors
    
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
        
        【修复】使用累积数据，包含所有批次的物种
        
        Returns:
            {lineage_code: {tile_id: death_rate}} 嵌套字典
        """
        # 使用累积的数据
        if self._accumulated_tile_mortality:
            return self._accumulated_tile_mortality.copy()
        
        # 回退：使用旧逻辑
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
        
        【修复】使用累积数据，包含所有批次的物种
        
        Returns:
            {lineage_code: {tile_id: population}} 嵌套字典
        """
        # 使用累积的数据
        if self._accumulated_tile_population:
            return self._accumulated_tile_population.copy()
        
        # 回退：使用旧逻辑
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
        """【修复】获取所有物种在各地块的存活数（死亡率计算后）
        
        这是关键方法：返回每个地块的实际存活数量，用于更新栖息地种群。
        
        【重要修复】使用累积的数据而不是仅最后一批的数据，
        确保所有批次（critical, focus, background）的物种都被正确处理。
        
        Returns:
            {lineage_code: {tile_id: survivors}} 嵌套字典
        """
        # 使用累积的数据（包含所有批次的物种）
        if self._accumulated_tile_survivors:
            return self._accumulated_tile_survivors.copy()
        
        # 回退：如果没有累积数据，使用旧逻辑（仅最后一批）
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
        min_tile_population: int | None = None,
        mortality_threshold: tuple[float, float] | None = None,
        min_mortality_gradient: float | None = None,
    ) -> dict[str, dict]:
        """获取适合分化的物种及其候选地块
        
        【核心功能】基于地块级数据筛选分化候选：
        - 在特定地块上种群达到阈值
        - 地块死亡率在适宜范围内
        - 存在地块间死亡率梯度（地理/生态隔离）
        - 【新增】距离型隔离：候选地块跨度超过阈值
        - 【新增】簇间距离隔离：多簇且簇间有间隙
        
        Args:
            min_tile_population: 地块最小种群门槛（None则使用配置）
            mortality_threshold: 死亡率范围 (min, max)（None则使用配置）
            min_mortality_gradient: 最小死亡率梯度（None则使用配置）
            
        Returns:
            {lineage_code: {
                "candidate_tiles": set[int],  # 可分化的地块
                "tile_populations": dict[int, float],  # 各地块种群
                "tile_mortality": dict[int, float],  # 各地块死亡率
                "mortality_gradient": float,  # 死亡率梯度
                "is_isolated": bool,  # 是否存在隔离
                "clusters": list[set[int]],  # 隔离区域
                "max_hex_distance": int,  # 【新增】候选地块最大六边形距离
                "isolation_type": str,  # 【新增】隔离类型
            }}
        """
        if self._population_matrix is None or self._last_mortality_matrix is None:
            return {}
        
        # 【改进】使用注入的配置
        spec_config = self._speciation_config
        
        # 使用配置值或传入的参数
        min_tile_population = min_tile_population if min_tile_population is not None else spec_config.candidate_tile_min_pop
        if mortality_threshold is None:
            mortality_threshold = (spec_config.candidate_tile_death_rate_min, spec_config.candidate_tile_death_rate_max)
        min_mortality_gradient = min_mortality_gradient if min_mortality_gradient is not None else spec_config.mortality_gradient_threshold
        
        distance_threshold = spec_config.distance_threshold_hex
        elongation_threshold = spec_config.elongation_ratio_threshold
        enable_distance_isolation = spec_config.enable_distance_isolation
        min_cluster_gap = spec_config.min_cluster_gap
        
        # 【新增】构建 tile_id -> (q, r) 坐标映射
        tile_coords: dict[int, tuple[int, int]] = {}
        for tile in self._tiles:
            if tile.id is not None:
                tile_coords[tile.id] = (tile.q, tile.r)
        
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
            
            # 检测隔离区域（原有逻辑）
            clusters = self._find_population_clusters(set(tile_pops.keys()))
            
            # 【新增】计算候选地块的最大六边形距离和长宽比
            max_hex_dist = 0
            elongation_ratio = 1.0
            distance_isolated = False
            
            if enable_distance_isolation and len(candidate_tiles) >= 2:
                # 收集候选地块的坐标
                coords_list = []
                for tid in candidate_tiles:
                    if tid in tile_coords:
                        coords_list.append((tid, tile_coords[tid]))
                
                if len(coords_list) >= 2:
                    # 计算所有候选地块两两之间的最大距离
                    for i, (tid1, (q1, r1)) in enumerate(coords_list):
                        for tid2, (q2, r2) in coords_list[i+1:]:
                            dist = hex_distance(q1, r1, q2, r2)
                            if dist > max_hex_dist:
                                max_hex_dist = dist
                    
                    # 计算包围盒的长宽比（简化版：用 q 和 r 范围）
                    q_vals = [c[1][0] for c in coords_list]
                    r_vals = [c[1][1] for c in coords_list]
                    q_range = max(q_vals) - min(q_vals) + 1
                    r_range = max(r_vals) - min(r_vals) + 1
                    if min(q_range, r_range) > 0:
                        elongation_ratio = max(q_range, r_range) / min(q_range, r_range)
                    
                    # 判断距离型隔离
                    if max_hex_dist >= distance_threshold:
                        distance_isolated = True
                        logger.debug(
                            f"[距离隔离] {lineage_code}: max_dist={max_hex_dist} >= threshold={distance_threshold}"
                        )
                    elif elongation_ratio >= elongation_threshold:
                        distance_isolated = True
                        logger.debug(
                            f"[带状隔离] {lineage_code}: elongation={elongation_ratio:.2f} >= threshold={elongation_threshold}"
                        )
            
            # 【改进】综合判定隔离（放宽条件）
            cluster_isolated = len(clusters) >= 2
            gradient_isolated = mortality_gradient >= min_mortality_gradient
            
            # 【新增】相对梯度判定（max-min)/max >= 0.3 也算隔离
            max_rate_val = max(tile_rates.values()) if tile_rates else 0
            relative_gradient = mortality_gradient / max_rate_val if max_rate_val > 0 else 0
            relative_gradient_isolated = relative_gradient >= 0.25  # 相对梯度 25% 以上
            
            # 【新增】簇间距离隔离：多个簇且簇间有间隙（即使物理连通）
            cluster_gap_isolated = False
            if len(clusters) >= 2 and len(candidate_tiles) >= 4:
                # 计算不同簇之间的最小距离
                for i, cluster_a in enumerate(clusters):
                    for cluster_b in clusters[i+1:]:
                        # 找到两个簇中最近的两个地块
                        min_inter_dist = float('inf')
                        for tid_a in cluster_a:
                            if tid_a not in tile_coords:
                                continue
                            q_a, r_a = tile_coords[tid_a]
                            for tid_b in cluster_b:
                                if tid_b not in tile_coords:
                                    continue
                                q_b, r_b = tile_coords[tid_b]
                                dist = hex_distance(q_a, r_a, q_b, r_b)
                                if dist < min_inter_dist:
                                    min_inter_dist = dist
                        if min_inter_dist > min_cluster_gap:
                            cluster_gap_isolated = True
                            break
                    if cluster_gap_isolated:
                        break
            
            # 【放宽】任一条件满足即视为隔离
            is_isolated = (
                cluster_isolated or 
                gradient_isolated or 
                relative_gradient_isolated or
                distance_isolated or
                cluster_gap_isolated
            )
            
            # 【新增】隔离类型标记
            isolation_types = []
            if cluster_isolated:
                isolation_types.append("cluster")
            if gradient_isolated:
                isolation_types.append("gradient")
            if relative_gradient_isolated:
                isolation_types.append("rel_gradient")
            if cluster_gap_isolated:
                isolation_types.append("cluster_gap")
            if distance_isolated:
                if max_hex_dist >= distance_threshold:
                    isolation_types.append("distance")
                if elongation_ratio >= elongation_threshold:
                    isolation_types.append("elongated")
            isolation_type = "+".join(isolation_types) if isolation_types else "none"
            
            result[lineage_code] = {
                "candidate_tiles": candidate_tiles,
                "tile_populations": tile_pops,
                "tile_mortality": tile_rates,
                "mortality_gradient": mortality_gradient,
                "is_isolated": is_isolated,
                "clusters": clusters,
                "total_candidate_population": sum(tile_pops.get(t, 0) for t in candidate_tiles),
                # 【新增】距离隔离相关字段
                "max_hex_distance": max_hex_dist,
                "elongation_ratio": elongation_ratio,
                "isolation_type": isolation_type,
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
        - 0: 温度 (Temperature)
        - 1: 湿度 (Humidity)
        - 2: 资源 (Resources)
        - 3: 海拔 (Elevation)
        - 4: 盐度 (Salinity)
        - 5: 湿球温度因子 (Wet Bulb Factor) - 协同压力
        - 6: 紫外线强度 (UV Radiation) - 协同压力
        - 7: 阴冷指数 (Cold & Humid) - 协同压力
        """
        n_tiles = len(self._tiles)
        self._tile_env_matrix = np.zeros((n_tiles, 8), dtype=np.float64)
        
        for idx, tile in enumerate(self._tiles):
            temp = tile.temperature
            humid = tile.humidity
            elev = tile.elevation
            
            self._tile_env_matrix[idx, 0] = temp
            self._tile_env_matrix[idx, 1] = humid
            self._tile_env_matrix[idx, 2] = tile.resources
            self._tile_env_matrix[idx, 3] = elev
            self._tile_env_matrix[idx, 4] = getattr(tile, 'salinity', 35.0)
            
            # 【新增】协同压力计算
            # 1. 湿球温度因子 (高温高湿)
            # 简单启发式：当温度>20度时，湿度每增加，压力指数增长
            heat_stress = 0.0
            if temp > 20:
                heat_stress = (temp - 20) * (humid / 100.0) * 0.5
            self._tile_env_matrix[idx, 5] = heat_stress
            
            # 2. 紫外线强度 (高海拔)
            # 每上升1000米，UV显著增加
            uv_index = max(0.0, elev / 1000.0)
            self._tile_env_matrix[idx, 6] = uv_index
            
            # 3. 阴冷指数 (低温高湿)
            # "湿冷"效应：当温度<10度且高湿时，体感温度更低
            cold_stress = 0.0
            if temp < 10:
                cold_stress = (10 - temp) * (humid / 100.0) * 0.5
            self._tile_env_matrix[idx, 7] = cold_stress
    
    def evaluate(
        self,
        species_batch: Sequence[Species],
        pressure_modifiers: dict[str, float],
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        trophic_interactions: dict[str, float] | None = None,
        extinct_codes: set[str] | None = None,
        turn_index: int = 0,
    ) -> list[AggregatedMortalityResult]:
        """计算物种死亡率（按地块计算后汇总）
        
        Args:
            species_batch: 物种列表
            pressure_modifiers: 全局压力修饰符
            niche_metrics: 生态位指标（全局）
            tier: 物种层级
            trophic_interactions: 营养级互动（全局）
            extinct_codes: 已灭绝物种代码集合
            turn_index: 当前回合索引（用于计算新物种优势）
            
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
        
        # 【修复】累积本批次的存活数据（而不是只保留最后一批）
        self._accumulate_batch_results(species_list, batch_population_matrix, mortality_matrix)
        
        # ========== 阶段3: 汇总各地块结果 ==========
        results = self._aggregate_tile_results(
            species_list, species_arrays, mortality_matrix, 
            niche_metrics, tier, extinct_codes, batch_population_matrix,
            turn_index=turn_index,  # 【新增】传递 turn_index
            trophic_interactions=trophic_interactions,  # 【新增】传递食物网反馈信号
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
            # 【新增】演化相关字段
            'created_turn': np.zeros(n, dtype=np.int32),
        }
        
        # 【新增】收集 parent_code 供后续使用
        parent_codes = []
        
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
            
            # 【新增】演化相关
            arrays['created_turn'][i] = getattr(sp, 'created_turn', 0) or 0
            parent_codes.append(getattr(sp, 'parent_code', None))
        
        # 存储非数值数据供后续使用
        arrays['_parent_codes'] = parent_codes
        
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
        
        # ========== 【改进v6】使用注入的死亡率配置 ==========
        mort_cfg = self._mortality_config
        
        # 【修复1】压力上限（从配置读取）
        env_capped = np.minimum(mort_cfg.env_pressure_cap, env_pressure)
        competition_capped = np.minimum(mort_cfg.competition_pressure_cap, competition_pressure)
        trophic_capped = np.minimum(mort_cfg.trophic_pressure_cap, trophic_pressure)
        resource_capped = np.minimum(mort_cfg.resource_pressure_cap, resource_pressure)
        predation_capped = np.minimum(mort_cfg.predation_pressure_cap, predation_network_pressure)
        plant_competition_capped = np.minimum(mort_cfg.plant_competition_cap, plant_competition_pressure)
        
        # 【修复2】恢复部分抗性
        body_size = species_arrays['body_size']
        generation_time = species_arrays['generation_time']
        
        # 体型抗性：基于体型大小
        size_resistance = np.where(
            body_size < 0.01, 0.30,
            np.where(body_size < 0.1, 0.22,
                np.where(body_size < 1.0, 0.15, 0.08))
        )
        
        # 繁殖速度抗性：基于世代时间
        repro_resistance = np.where(
            generation_time < 7, 0.25,
            np.where(generation_time < 30, 0.18,
                np.where(generation_time < 365, 0.12, 0.05))
        )
        
        # 【修复3】综合抗性（从配置读取上限）
        total_resistance = np.minimum(
            size_resistance * 0.5 + repro_resistance * 0.5,
            mort_cfg.max_resistance
        )
        resistance_matrix = total_resistance[np.newaxis, :]
        
        # 【修复4】加权和模型（从配置读取权重）
        weighted_sum = (
            env_capped * mort_cfg.env_weight +
            competition_capped * mort_cfg.competition_weight +
            trophic_capped * mort_cfg.trophic_weight +
            resource_capped * mort_cfg.resource_weight +
            predation_capped * mort_cfg.predation_weight +
            plant_competition_capped * mort_cfg.plant_competition_weight
        )
        
        # 【修复5】乘法模型（从配置读取系数）
        survival_product = (
            (1.0 - env_capped * mort_cfg.env_mult_coef) *
            (1.0 - competition_capped * mort_cfg.competition_mult_coef) *
            (1.0 - trophic_capped * mort_cfg.trophic_mult_coef) *
            (1.0 - resource_capped * mort_cfg.resource_mult_coef) *
            (1.0 - predation_capped * mort_cfg.predation_mult_coef) *
            (1.0 - plant_competition_capped * mort_cfg.plant_mult_coef)
        )
        multiplicative_mortality = 1.0 - survival_product
        
        # 【修复6】混合模型（从配置读取比例）
        additive_weight = mort_cfg.additive_model_weight
        raw_mortality = weighted_sum * additive_weight + multiplicative_mortality * (1.0 - additive_weight)
        
        # 【修复7】抗性减免
        mortality = raw_mortality * (1.0 - resistance_matrix * 0.70)
        
        # ========== 7. 应用世代累积死亡率 ==========
        if _settings.enable_generational_mortality:
            mortality = self._apply_generational_mortality(species_arrays, mortality)
        
        # ========== 8. 边界约束（从配置读取） ==========
        mortality = np.clip(mortality, mort_cfg.min_mortality, mort_cfg.max_mortality)
        
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
        # 【优化v7】改进极端温度压力计算，使冰河期/温室效应产生显著影响
        # 全局温度修饰（来自冰河期/温室效应等）
        temp_modifier = pressure_modifiers.get('temperature', 0.0)
        # 【修改1】增强温度修饰效果：每单位 = 5°C（原3°C）
        adjusted_temps = tile_temps + temp_modifier * 5.0
        
        # 【修改2】引入极端温度阈值
        # - 适宜温度范围：5°C ~ 25°C（原10°C ~ 20°C）
        # - 极端温度：<-10°C 或 >35°C 产生额外压力
        OPTIMAL_LOW = 5.0
        OPTIMAL_HIGH = 25.0
        EXTREME_LOW = -10.0
        EXTREME_HIGH = 35.0
        
        # 计算偏离适宜范围的程度
        cold_deviation = np.maximum(0, OPTIMAL_LOW - adjusted_temps[:, np.newaxis])
        heat_deviation = np.maximum(0, adjusted_temps[:, np.newaxis] - OPTIMAL_HIGH)
        
        # 【修改3】非线性温度压力曲线（sigmoid形）
        # 轻微偏离（<10°C）产生温和压力，严重偏离（>20°C）产生急剧压力
        def sigmoid_pressure(deviation, scale=15.0):
            """S型压力曲线：deviation=10 → 0.5, deviation=20 → 0.88"""
            return 2.0 / (1.0 + np.exp(-deviation / scale)) - 1.0
        
        # 基础温度压力
        cold_base_pressure = sigmoid_pressure(cold_deviation)
        heat_base_pressure = sigmoid_pressure(heat_deviation)
        
        # 【修改4】极端温度额外惩罚
        extreme_cold_mask = adjusted_temps[:, np.newaxis] < EXTREME_LOW
        extreme_heat_mask = adjusted_temps[:, np.newaxis] > EXTREME_HIGH
        
        # 极端低温：<-10°C时，每低10°C额外增加0.3压力
        extreme_cold_deviation = np.maximum(0, EXTREME_LOW - adjusted_temps[:, np.newaxis])
        extreme_cold_penalty = np.where(extreme_cold_mask, extreme_cold_deviation / 10.0 * 0.3, 0.0)
        
        # 极端高温：>35°C时，每高10°C额外增加0.3压力
        extreme_heat_deviation = np.maximum(0, adjusted_temps[:, np.newaxis] - EXTREME_HIGH)
        extreme_heat_penalty = np.where(extreme_heat_mask, extreme_heat_deviation / 10.0 * 0.3, 0.0)
        
        # 【修改5】应用耐性减免，但保留最低30%基础压力
        # 耐寒性10/10 最多减免70%寒冷压力，仍保留30%
        MIN_PRESSURE_FACTOR = 0.30
        cold_resistance_factor = MIN_PRESSURE_FACTOR + (1.0 - MIN_PRESSURE_FACTOR) * (1.0 - cold_res[np.newaxis, :])
        heat_resistance_factor = MIN_PRESSURE_FACTOR + (1.0 - MIN_PRESSURE_FACTOR) * (1.0 - heat_res[np.newaxis, :])
        
        # 组合温度压力
        temp_pressure = np.zeros((n_tiles, n_species))
        cold_mask = cold_deviation > 0
        heat_mask = heat_deviation > 0
        
        # 【新增】协同压力叠加
        # 1. 湿热协同 (Wet Bulb Synergy): 高温高湿会显著增加散热难度，放大高温压力
        wet_bulb_factor = self._tile_env_matrix[:, 5][:, np.newaxis] # (n_tiles, 1)
        heat_synergy = np.where(heat_mask, wet_bulb_factor * 0.15, 0.0)
        
        # 2. 湿冷协同 (Cold & Humid Synergy): 湿冷会加速热量流失，放大低温压力
        cold_humid_factor = self._tile_env_matrix[:, 7][:, np.newaxis] # (n_tiles, 1)
        cold_synergy = np.where(cold_mask, cold_humid_factor * 0.15, 0.0)
        
        temp_pressure = np.where(
            cold_mask,
            (cold_base_pressure + extreme_cold_penalty + cold_synergy) * cold_resistance_factor,
            temp_pressure
        )
        temp_pressure = np.where(
            heat_mask,
            (heat_base_pressure + extreme_heat_penalty + heat_synergy) * heat_resistance_factor,
            temp_pressure
        )
        
        # 【新增】记录极端温度事件供日志使用
        if np.any(extreme_cold_mask) or np.any(extreme_heat_mask):
            avg_temp = np.mean(adjusted_temps)
            if avg_temp < EXTREME_LOW:
                logger.info(f"[极端气候] 检测到极端低温 {avg_temp:.1f}°C，触发冰河期死亡压力加成")
        
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
            
        # 【协同压力 v1.0】
        # 引入环境压力的交互作用（乘法放大效应）
        
        # 【修复v2】确保温度和湿度是真正的一维数组 (n_tiles,)
        # 避免之前的广播操作意外改变形状
        temps_1d = np.asarray(adjusted_temps).ravel()  # 强制一维 (n_tiles,)
        humidity_1d = np.asarray(tile_humidity).ravel()  # 强制一维 (n_tiles,)
        
        # 1. 热湿压力 (Heat Stress)
        # 高温 + 高湿 = 湿球温度压力 (难以散热)
        # 当温度>25且湿度>0.7时，产生协同压力
        heat_cond = (temps_1d > 25.0) & (humidity_1d > 0.7)  # (n_tiles,)
        heat_index_base = np.where(heat_cond, 0.15, 0.0)  # (n_tiles,)
        # 广播到 (n_tiles, n_species) 并应用耐热性
        heat_index_pressure = heat_index_base[:, np.newaxis] * (1.0 - heat_res[np.newaxis, :])
        
        # 2. 高原缺氧压力 (Hypoxia)
        # 高海拔(>2000m) -> 氧气稀薄 -> 大型动物代谢压力
        tile_elevation = self._tile_env_matrix[:, 2] * 5000.0 # 还原海拔
        hypoxia_cond = tile_elevation > 2000.0  # (n_tiles,)
        # 体型越大压力越大
        body_size = species_arrays['body_size']
        # 基础压力 (n_tiles,) 广播到 (n_tiles, n_species)
        hypoxia_base = np.where(hypoxia_cond, 1.0, 0.0)  # (n_tiles,)
        hypoxia_pressure = hypoxia_base[:, np.newaxis] * body_size[np.newaxis, :] * 0.2
        # 适应性：如果有"高山适应"特性(暂时用耐寒性代理或作为隐含属性)
        # 这里假设耐寒性高的一般适应高山
        hypoxia_pressure *= (1.0 - cold_res[np.newaxis, :] * 0.5)
        
        # 3. 紫外辐射协同 (UV Synergy)
        # 高海拔 + 缺乏覆盖(低湿度/荒漠) = 高UV
        uv_risk_cond = (tile_elevation > 1000.0) & (humidity_1d < 0.3)  # (n_tiles,)
        # 软体动物/两栖类受害严重 (假设耐旱性差的皮肤保护差)
        soft_skin_vulnerability = (1.0 - drought_res)  # (n_species,)
        uv_base = np.where(uv_risk_cond, 0.1, 0.0)  # (n_tiles,)
        uv_synergy_pressure = uv_base[:, np.newaxis] * soft_skin_vulnerability[np.newaxis, :]
        
        # 4. 寒冷潮湿协同 (Cold Damp)
        # 低温(<5度) + 高湿(>0.8) = 失温风险 (比干冷更致命)
        cold_damp_cond = (temps_1d < 5.0) & (humidity_1d > 0.8)  # (n_tiles,)
        cold_damp_base = np.where(cold_damp_cond, 0.1, 0.0)  # (n_tiles,)
        cold_damp_pressure = cold_damp_base[:, np.newaxis] * (1.0 - cold_res[np.newaxis, :])

        synergistic_pressure = (
            heat_index_pressure + 
            hypoxia_pressure + 
            uv_synergy_pressure +
            cold_damp_pressure
        )
        
        if np.any(synergistic_pressure > 0.05):
            logger.debug(f"[协同压力] 检测到环境交互压力，最大值={np.max(synergistic_pressure):.2f}")

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
        
        # ========== 【新增】正面压力减免 ==========
        # 资源繁盛、高生产力等正面条件会降低环境压力
        resource_boost = pressure_modifiers.get('resource_boost', 0.0)
        productivity_boost = pressure_modifiers.get('productivity', 0.0)
        oxygen_boost = max(0.0, pressure_modifiers.get('oxygen', 0.0))  # 正值才是加成
        habitat_expansion = pressure_modifiers.get('habitat_expansion', 0.0)
        
        # 综合正面效果：最大可减免 30% 压力
        positive_bonus = min(0.30, (
            resource_boost * 0.15 +      # 资源丰富最多减免15%
            productivity_boost * 0.10 +  # 高生产力最多减免10%
            oxygen_boost * 0.03 +        # 高氧环境最多减免3%
            habitat_expansion * 0.02     # 栖息地扩展最多减免2%
        ))
        
        if positive_bonus > 0.01:
            logger.debug(f"[正面压力] 环境减免={positive_bonus:.1%} (资源={resource_boost:.1f}, 生产力={productivity_boost:.1f})")
        
        # ========== 组合压力 ==========
        # 【优化v7】动态权重：极端温度时提升温度压力权重
        # 检测是否存在极端温度条件
        avg_temp_pressure = np.mean(temp_pressure)
        is_extreme_climate = avg_temp_pressure > 0.3  # 平均温度压力>30%视为极端气候
        
        if is_extreme_climate:
            # 极端气候模式：温度成为主导因素
            pressure = (
                temp_pressure * 0.50 +      # 【极端模式】温度压力权重翻倍
                drought_pressure * 0.12 +   # 水分权重降低
                flood_pressure * 0.08 +     # 洪水权重降低
                special_pressure * 0.20 +   # 特殊事件权重降低
                global_pressure * 0.10      # 其他综合影响降低
            )
            logger.debug(f"[极端气候模式] 温度压力主导，平均温度压力={avg_temp_pressure:.2%}")
        else:
            # 正常气候模式：平衡各因素
            pressure = (
                temp_pressure * 0.30 +      # 【提升】温度权重从0.25提升到0.30
                drought_pressure * 0.15 +   # 水分次之
                flood_pressure * 0.10 +     # 洪水影响较小
                special_pressure * 0.28 +   # 特殊事件影响显著
                global_pressure * 0.17 +    # 其他综合影响
                synergistic_pressure * 0.25 # 【新增】协同压力权重
            )
        
        # 【新增】应用正面压力减免
        pressure = pressure * (1.0 - positive_bonus)
        
        # 【修改】提高环境压力上限，允许极端条件下更高的压力值
        return np.clip(pressure, 0.0, 1.2)  # 从1.0提升到1.2
    
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
        # 竞争系数 = 相似度 × 营养级系数 × 配置系数
        # 【改进v5】使用注入的生态配置
        eco_cfg = self._ecology_config
        comp_coef_matrix = (similarity_matrix * trophic_coef * eco_cfg.competition_base_coefficient).astype(np.float64)
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
            
            # 【改进v5】从配置读取竞争上限
            comp_strength = np.minimum(comp_strength, eco_cfg.competition_per_species_cap)
            
            # 只考虑在场物种之间的竞争
            present_matrix = present_mask[:, np.newaxis] & present_mask[np.newaxis, :]
            comp_strength = np.where(present_matrix, comp_strength, 0.0)
            
            # 对每个物种汇总竞争压力
            total_competition = comp_strength.sum(axis=1)
            
            # 【改进v5】从配置读取总竞争压力上限
            competition[tile_idx, :] = np.minimum(total_competition, eco_cfg.competition_total_cap)
        
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
        【平衡改进v9】猎物丰富时给予死亡率减免（负压力）
        
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
        
        # 【平衡修复v3】降低无食物时的稀缺压力
        # 原来2.0太高，导致新物种在第一回合就有44%+的死亡率
        # 修改为1.0，让稀缺压力更温和
        SCARCITY_MAX = 1.0  # 从2.0降到1.0
        
        # 【严重饥饿判定】
        # 如果有种群但几乎没有猎物，强制设置为极高死亡率（0.9）
        # 这是一个硬约束，防止消费者在无食物地块苟活
        SEVERE_STARVATION_PENALTY = 0.9
        
        # 【新增v9】猎物丰富度奖励参数
        # 当猎物生物量 > 需求的 N 倍时，给予负压力（死亡率减免）
        # 【v10】大幅提高奖励：猎物越丰富，死亡率越低
        ABUNDANCE_THRESHOLD = 1.5  # 猎物生物量超过需求1.5倍时开始给予奖励
        ABUNDANCE_BONUS_MAX = 0.30  # 最大死亡率减免 30%
        
        # === T1 受 T2 采食 ===
        req_t1 = np.where(t2 > 0, t2 / EFFICIENCY, 0)
        grazing_ratio = np.divide(req_t1, safe_t1, out=np.zeros_like(req_t1), where=t1 > MIN_BIOMASS)
        grazing = np.minimum(grazing_ratio * 0.5, 0.8)
        scarcity_t2 = np.where(t1 > MIN_BIOMASS, 
                               np.clip(grazing_ratio - 1.0, 0, SCARCITY_MAX),
                               np.where(t2 > 0, SCARCITY_MAX, 0.0))
        # T2 严重饥饿检查: T2存在但T1几乎为0
        starvation_mask_t2 = (t2 > MIN_BIOMASS) & (t1 <= MIN_BIOMASS)
        
        # 【新增v9】T2 猎物丰富度奖励（负压力）
        # 当 T1 >> T2需求时，T2消费者获得生存优势
        # 【v10】提高奖励速度：每超过阈值1倍，减免5%死亡率
        abundance_ratio_t2 = np.divide(safe_t1, np.maximum(req_t1, MIN_BIOMASS), 
                                       out=np.ones_like(safe_t1), where=req_t1 > MIN_BIOMASS)
        abundance_bonus_t2 = np.where(
            (t2 > MIN_BIOMASS) & (t1 > MIN_BIOMASS) & (abundance_ratio_t2 > ABUNDANCE_THRESHOLD),
            -np.minimum((abundance_ratio_t2 - ABUNDANCE_THRESHOLD) * 0.05, ABUNDANCE_BONUS_MAX),
            0.0
        )
        
        # === T2 受 T3 捕食 ===
        req_t2 = np.where(t3 > 0, t3 / EFFICIENCY, 0)
        ratio_t2 = np.divide(req_t2, safe_t2, out=np.zeros_like(req_t2), where=t2 > MIN_BIOMASS)
        pred_t3 = np.minimum(ratio_t2 * 0.5, 0.8)
        scarcity_t3 = np.where(t2 > MIN_BIOMASS,
                               np.clip(ratio_t2 - 1.0, 0, SCARCITY_MAX),
                               np.where(t3 > 0, SCARCITY_MAX, 0.0))
        # T3 严重饥饿检查
        starvation_mask_t3 = (t3 > MIN_BIOMASS) & (t2 <= MIN_BIOMASS)
        
        # 【新增v9】T3 猎物丰富度奖励
        # 【v10】提高奖励速度
        abundance_ratio_t3 = np.divide(safe_t2, np.maximum(req_t2, MIN_BIOMASS),
                                       out=np.ones_like(safe_t2), where=req_t2 > MIN_BIOMASS)
        abundance_bonus_t3 = np.where(
            (t3 > MIN_BIOMASS) & (t2 > MIN_BIOMASS) & (abundance_ratio_t3 > ABUNDANCE_THRESHOLD),
            -np.minimum((abundance_ratio_t3 - ABUNDANCE_THRESHOLD) * 0.05, ABUNDANCE_BONUS_MAX),
            0.0
        )
        
        # === T3 受 T4 捕食 ===
        req_t3 = np.where(t4 > 0, t4 / EFFICIENCY, 0)
        ratio_t3 = np.divide(req_t3, safe_t3, out=np.zeros_like(req_t3), where=t3 > MIN_BIOMASS)
        pred_t4 = np.minimum(ratio_t3 * 0.5, 0.8)
        scarcity_t4 = np.where(t3 > MIN_BIOMASS,
                               np.clip(ratio_t3 - 1.0, 0, SCARCITY_MAX),
                               np.where(t4 > 0, SCARCITY_MAX, 0.0))
        # T4 严重饥饿检查
        starvation_mask_t4 = (t4 > MIN_BIOMASS) & (t3 <= MIN_BIOMASS)
        
        # 【新增v9】T4 猎物丰富度奖励
        # 【v10】提高奖励速度
        abundance_ratio_t4 = np.divide(safe_t3, np.maximum(req_t3, MIN_BIOMASS),
                                       out=np.ones_like(safe_t3), where=req_t3 > MIN_BIOMASS)
        abundance_bonus_t4 = np.where(
            (t4 > MIN_BIOMASS) & (t3 > MIN_BIOMASS) & (abundance_ratio_t4 > ABUNDANCE_THRESHOLD),
            -np.minimum((abundance_ratio_t4 - ABUNDANCE_THRESHOLD) * 0.05, ABUNDANCE_BONUS_MAX),
            0.0
        )
        
        # === T4 受 T5 捕食 ===
        req_t4 = np.where(t5 > 0, t5 / EFFICIENCY, 0)
        ratio_t4 = np.divide(req_t4, safe_t4, out=np.zeros_like(req_t4), where=t4 > MIN_BIOMASS)
        pred_t5 = np.minimum(ratio_t4 * 0.5, 0.8)
        scarcity_t5 = np.where(t4 > MIN_BIOMASS,
                               np.clip(ratio_t4 - 1.0, 0, SCARCITY_MAX),
                               np.where(t5 > 0, SCARCITY_MAX, 0.0))
        # T5 严重饥饿检查
        starvation_mask_t5 = (t5 > MIN_BIOMASS) & (t4 <= MIN_BIOMASS)
        
        # 【新增v9】T5 猎物丰富度奖励
        # 【v10】提高奖励速度
        abundance_ratio_t5 = np.divide(safe_t4, np.maximum(req_t4, MIN_BIOMASS),
                                       out=np.ones_like(safe_t4), where=req_t4 > MIN_BIOMASS)
        abundance_bonus_t5 = np.where(
            (t5 > MIN_BIOMASS) & (t4 > MIN_BIOMASS) & (abundance_ratio_t5 > ABUNDANCE_THRESHOLD),
            -np.minimum((abundance_ratio_t5 - ABUNDANCE_THRESHOLD) * 0.05, ABUNDANCE_BONUS_MAX),
            0.0
        )
        
        # 【改进v5】使用注入的生态配置
        # 消费者猎物稀缺时，死亡率显著上升
        eco_cfg = self._ecology_config
        SCARCITY_WEIGHT = eco_cfg.scarcity_weight
        
        # 将压力分配到各物种
        for sp_idx in range(n_species):
            t_level = int_trophic[sp_idx]
            
            if t_level == 1:
                # 生产者只受捕食压力
                trophic_pressure[:, sp_idx] = grazing
            elif t_level == 2:
                # T2消费者：受T3捕食 + 猎物(T1)稀缺惩罚 + 猎物丰富奖励
                pred_component = pred_t3
                scarcity_component = scarcity_t2 * SCARCITY_WEIGHT
                # 【新增v9】应用猎物丰富度奖励（负值会减少死亡率）
                final_pressure = pred_component + scarcity_component + abundance_bonus_t2
                # 应用严重饥饿惩罚
                final_pressure = np.where(starvation_mask_t2, SEVERE_STARVATION_PENALTY, final_pressure)
                trophic_pressure[:, sp_idx] = final_pressure
            elif t_level == 3:
                # T3消费者
                pred_component = pred_t4
                scarcity_component = scarcity_t3 * SCARCITY_WEIGHT
                final_pressure = pred_component + scarcity_component + abundance_bonus_t3
                final_pressure = np.where(starvation_mask_t3, SEVERE_STARVATION_PENALTY, final_pressure)
                trophic_pressure[:, sp_idx] = final_pressure
            elif t_level == 4:
                # T4消费者
                pred_component = pred_t5
                scarcity_component = scarcity_t4 * SCARCITY_WEIGHT
                final_pressure = pred_component + scarcity_component + abundance_bonus_t4
                final_pressure = np.where(starvation_mask_t4, SEVERE_STARVATION_PENALTY, final_pressure)
                trophic_pressure[:, sp_idx] = final_pressure
            elif t_level >= 5:
                # 顶级捕食者
                scarcity_component = scarcity_t5 * SCARCITY_WEIGHT
                final_pressure = scarcity_component + abundance_bonus_t5
                final_pressure = np.where(starvation_mask_t5, SEVERE_STARVATION_PENALTY, final_pressure)
                trophic_pressure[:, sp_idx] = final_pressure
        
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
        
        【v2改进】使用资源管理器的 NPP 模型，统一能量单位
        
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
        
        # 【改进】从资源配置加载参数
        # 使用 ResourceSystemConfig 默认值，避免全局单例依赖
        from ..models.config import ResourceSystemConfig
        res_cfg = ResourceSystemConfig()
        
        metabolic_coef = res_cfg.metabolic_rate_coefficient
        weight_exponent = res_cfg.metabolic_weight_exponent
        harvestable_fraction = res_cfg.harvestable_fraction
        pressure_cap = res_cfg.resource_pressure_cap
        
        # 预计算物种属性向量
        weights_g = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0) 
            for sp in species_list
        ])
        weights_kg = weights_g / 1000.0  # 转换为 kg
        
        # 【改进】使用异速生长代谢率：需求 ∝ 体重^0.75
        demand_coef = metabolic_coef * (weights_kg ** weight_exponent)  # (n_species,)
        
        # 【关键修复】使用batch_population_matrix计算需求
        demand_matrix = batch_population_matrix * demand_coef[np.newaxis, :]
        
        # 每个地块的总需求 (n_tiles,)
        total_demand_per_tile = demand_matrix.sum(axis=1)
        
        # 使用地块资源计算供给容量（避免依赖全局资源管理器）
        # tile.resources × 转换系数 × 可采份额
        tile_resources = self._tile_env_matrix[:, 2]
        supply_capacity = tile_resources * res_cfg.resource_to_npp_factor * harvestable_fraction
        
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
        # shortage_ratio 是 (demand - supply) / demand，范围 [0, 1]
        base_pressure = shortage_ratio[:, np.newaxis] * np.minimum(demand_ratio * 2.0, 1.0)
        
        # 【严重超载判定】
        # 如果短缺比例非常高（例如 > 0.8），说明资源严重不足，死亡率应接近1.0
        # 此时应该突破 pressure_cap
        severe_shortage_mask = shortage_ratio[:, np.newaxis] > 0.8
        
        resource_pressure = np.where(
            severe_shortage_mask, 
            base_pressure * 1.5,  # 放大压力
            base_pressure
        )
        
        # 【关键修复】使用batch_population_matrix
        resource_pressure = np.where(batch_population_matrix > 0, resource_pressure, 0.0)
        
        # 应用上限，但在严重短缺时允许更高
        final_cap = np.where(severe_shortage_mask, 1.0, pressure_cap)
        
        return np.clip(resource_pressure, 0.0, final_cap)
    
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
        """【平衡修复v7】应用世代适应性加成 - 极端环境下进一步削弱
        
        50万年时间尺度说明：
        - 微生物（1天1代）：约1.8亿代，有充足时间演化适应
        - 昆虫（1月1代）：约600万代
        - 哺乳动物（1年1代）：约50万代
        
        【v7优化】
        - 进一步降低抗性加成
        - 高死亡率环境下抗性效果递减（极端环境下适应能力受限）
        - 最高减免从25%降到15%
        """
        n_tiles, n_species = mortality.shape
        
        generation_time = species_arrays['generation_time']
        body_size = species_arrays['body_size']
        population = species_arrays['population']
        
        # 计算50万年内的世代数 (n_species,)
        num_generations = (_settings.turn_years * 365) / np.maximum(1.0, generation_time)
        
        # 基于世代数的适应性加成（v7进一步降低）
        log_generations = np.log10(np.maximum(1.0, num_generations))
        
        # 【v7修复】演化适应加成进一步降低：
        # 1亿代(log=8) -> 0.10加成（原0.15，再降33%）
        # 100万代(log=6) -> 0.06加成
        # 50万代(log=5.7) -> 0.05加成
        evolution_bonus = np.clip((log_generations - 3.0) / 5.0 * 0.10, 0.0, 0.12)
        
        # 【v7修复】体型抗性进一步降低
        size_bonus = np.where(
            body_size < 0.01, 0.03,  # 微生物（原0.06）
            np.where(body_size < 0.1, 0.02,  # 小型（原0.04）
                np.where(body_size < 1.0, 0.01, 0.0))  # 中型（原0.02）
        )
        
        # 【v7修复】种群规模抗性降低
        pop_bonus = np.where(
            population > 1_000_000, 0.02,  # 原0.04
            np.where(population > 100_000, 0.01, 0.0)  # 原0.02
        )
        
        # 基础综合抗性上限：15%（原25%）
        base_resistance = np.minimum(0.15, evolution_bonus + size_bonus + pop_bonus)
        
        # 【v7核心优化】极端环境下抗性效果递减
        # 计算每个地块的平均死亡率
        mean_mortality_per_tile = np.mean(mortality, axis=1, keepdims=True)
        
        # 高死亡率环境（>50%）下，抗性效果线性递减
        # 死亡率50% → 抗性保持100%
        # 死亡率70% → 抗性降至50%
        # 死亡率90% → 抗性降至10%
        resistance_effectiveness = np.clip(1.0 - (mean_mortality_per_tile - 0.5) * 2.5, 0.1, 1.0)
        resistance_effectiveness = np.where(mean_mortality_per_tile < 0.5, 1.0, resistance_effectiveness)
        
        # 应用抗性效果递减
        effective_resistance = base_resistance[np.newaxis, :] * resistance_effectiveness
        
        # 应用抗性：降低死亡率
        adjusted_mortality = mortality * (1.0 - effective_resistance)
        
        # 【v7】确保极端环境下仍有显著死亡率
        # 如果原始死亡率>60%，调整后死亡率至少为原来的70%
        high_mortality_mask = mortality > 0.6
        min_adjusted = mortality * 0.70
        adjusted_mortality = np.where(
            high_mortality_mask,
            np.maximum(adjusted_mortality, min_adjusted),
            adjusted_mortality
        )
        
        return np.clip(adjusted_mortality, 0.0, 1.0)
    
    def _aggregate_tile_results(
        self,
        species_list: list[Species],
        species_arrays: dict[str, np.ndarray],
        mortality_matrix: np.ndarray,
        niche_metrics: dict[str, NicheMetrics],
        tier: str,
        extinct_codes: set[str],
        batch_population_matrix: np.ndarray | None = None,
        turn_index: int = 0,
        trophic_interactions: dict[str, float] | None = None,
    ) -> list[AggregatedMortalityResult]:
        """汇总各地块结果，计算物种总体死亡率
        
        【v2更新】按地块独立存活制计算：
        - 每个地块独立计算存活数
        - 避难所地块（死亡率<20%）可保证物种存续
        - 汇总各地块存活数得到总存活数
        
        【v3更新】演化平衡调整：
        - 频率依赖选择：常见型受惩罚，稀有型获优势
        - 新物种适应性优势：新分化物种前几回合获得死亡率减免
        - 增强子代压制：子代对亲代的竞争效应增强
        - 高生态位重叠直接竞争：高重叠物种相互消耗
        
        【v4更新】食物网反馈压力：
        - 饥饿物种：额外死亡率惩罚
        - 孤立消费者：额外死亡率惩罚
        - 猎物丰富区域：死亡率减免
        
        汇总方式：按地块独立计算后求和
        total_survivors = Σ(tile_pop × (1 - tile_death_rate))
        """
        if trophic_interactions is None:
            trophic_interactions = {}
        n_species = len(species_list)
        results: list[AggregatedMortalityResult] = []
        
        # 【新增v3】使用注入的生态配置
        eco_cfg = self._ecology_config
        
        # 【新增v3】计算总种群和物种频率（用于频率依赖选择）
        total_ecosystem_pop = sum(int(species_arrays['population'][i]) for i in range(n_species))
        species_frequencies = {}
        if total_ecosystem_pop > 0:
            for i in range(n_species):
                pop = int(species_arrays['population'][i])
                species_frequencies[species_list[i].lineage_code] = pop / total_ecosystem_pop
        
        # 【新增v3】构建亲子关系映射（用于增强子代压制）
        parent_codes = species_arrays.get('_parent_codes', [None] * n_species)
        parent_to_children: dict[str, list[int]] = {}
        for i, pc in enumerate(parent_codes):
            if pc:
                if pc not in parent_to_children:
                    parent_to_children[pc] = []
                parent_to_children[pc].append(i)
        
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
            # 【修复】使用batch_population_matrix而不是self._population_matrix
            # 因为sp_idx是当前批次的索引，不是全局索引
            if batch_population_matrix is not None:
                tile_pops = batch_population_matrix[:, sp_idx]
            elif self._population_matrix is not None:
                # 回退：如果没有batch矩阵，尝试使用全局矩阵（可能索引不对）
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
                # 【修复】如果没有地块种群分布但物种总种群>0，这是数据异常
                # 给予保守估计：假设有1个健康避难所，避免错误触发灭绝
                if total_pop > 0:
                    logger.warning(
                        f"[地块死亡率异常] {species.common_name} 总种群={total_pop} 但无地块分布数据，"
                        f"假设存在避难所以避免错误灭绝"
                    )
                    healthy_tiles = 1
                    warning_tiles = critical_tiles = 0
                    best_tile_rate = 0.1  # 假设最佳地块有10%基础死亡率
                    worst_tile_rate = 0.1
                    has_refuge = True  # 关键：给予避难所保护
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
            
            # 【修复】如果地块分布数据缺失但有总种群，使用全局平均死亡率
            if total_survivors == 0 and total_deaths == 0 and total_pop > 0:
                # 计算平均死亡率（使用该物种栖息地类型的地块）
                habitat_type = getattr(species, 'habitat_type', 'terrestrial')
                type_mask = self._get_habitat_type_mask(habitat_type)
                if type_mask.any():
                    avg_rate = tile_rates[type_mask].mean()
                else:
                    avg_rate = 0.1  # 默认10%死亡率
                
                # 使用平均死亡率计算存活
                total_deaths = int(total_pop * avg_rate)
                total_survivors = total_pop - total_deaths
                logger.warning(
                    f"[地块死亡率] {species.common_name} 无地块分布，使用平均死亡率 {avg_rate:.1%} "
                    f"计算存活: {total_pop} -> {total_survivors}"
                )
            
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
            
            overall_death_rate = min(1.0, max(0.03, overall_death_rate))
            
            # ========== 【新增v3】演化平衡调整与过滤 ==========
            evolution_adjustment = 0.0
            adjustment_notes = []
            
            # 【新增 v12 改进版】物种生命周期过滤器 (Evolutionary Filtering System)
            
            # 1. 基因衰老 (Genetic Decay) - 替代原有的“演化停滞”
            # 不再依赖 last_description_update_turn，只看绝对寿命
            # 任何物种都有其寿命极限，无论怎么适应，老了就是老了
            species_age = turn_index - species_arrays['created_turn'][sp_idx]
            
            # 寿命阈值：20回合（约1000万年）
            # 超过这个时间，每回合增加 5% 死亡率，直到灭绝
            LIFESPAN_LIMIT = 20
            if species_age > LIFESPAN_LIMIT:
                excess_age = species_age - LIFESPAN_LIMIT
                decay_penalty = min(0.8, excess_age * 0.05)  # 上限80%
                evolution_adjustment += decay_penalty
                adjustment_notes.append(f"基因衰老T{species_age}+{decay_penalty:.1%}")

            # 2. 亲代让位与系统发生压力 (Parental Obsolescence)
            # 检查该物种是否有新生子代
            lineage_code = species.lineage_code
            has_children = False
            if lineage_code in parent_to_children:
                 children_indices = parent_to_children[lineage_code]
                 # 只要有存活的子代，就视为“已完成历史使命”
                 # 检查子代是否有存活个体
                 for ci in children_indices:
                     if species_arrays['population'][ci] > 0:
                         has_children = True
                         break

            if has_children:
                # 场景A：有子代 -> 亲代应加速退场，为子代腾出空间
                # 这是一个非常强的惩罚，确保老物种被新物种取代
                obsolescence_penalty = 0.25  # 固定 +25% 死亡率
                evolution_adjustment += obsolescence_penalty
                adjustment_notes.append(f"亲代让位+{obsolescence_penalty:.1%}")
            elif species_age > 10:
                # 场景B：老了但没子代 -> 进化死胡同
                # 施加轻微压力逼迫其分化或灭亡
                dead_end_penalty = 0.10
                evolution_adjustment += dead_end_penalty
                adjustment_notes.append(f"进化死胡同+{dead_end_penalty:.1%}")

            # 3. 阿利效应 (Allee Effect) / 崩溃加速
            # 种群过低时不再享受保护，反而加速灭亡
            # 阈值设为 500 (对于大多数物种来说这已经很少了)
            ALLEE_THRESHOLD = 500
            if total_pop < ALLEE_THRESHOLD and total_pop > 0:
                # 种群越少，惩罚越大
                # pop=250 -> 额外+25%死亡率
                # pop=50 -> 额外+45%死亡率
                allee_penalty = 0.5 * (1.0 - total_pop / ALLEE_THRESHOLD)
                evolution_adjustment += allee_penalty
                adjustment_notes.append(f"种群崩溃加速+{allee_penalty:.1%}")

            # 1. 频率依赖选择
            if eco_cfg.enable_frequency_dependence and total_ecosystem_pop > 0:
                freq = species_frequencies.get(species.lineage_code, 0.0)
                
                if freq > eco_cfg.common_type_threshold:
                    # 常见型惩罚：频率越高，惩罚越重
                    excess = freq - eco_cfg.common_type_threshold
                    penalty = min(eco_cfg.common_type_max_penalty, 
                                  excess * eco_cfg.frequency_dependence_strength * 2)
                    evolution_adjustment += penalty
                    adjustment_notes.append(f"常见型惩罚+{penalty:.1%}")
                    
                elif freq < eco_cfg.rare_type_threshold and freq > 0:
                    # 稀有型优势：频率越低，优势越大
                    rarity = eco_cfg.rare_type_threshold - freq
                    advantage = min(eco_cfg.rare_type_max_advantage,
                                    rarity * eco_cfg.frequency_dependence_strength * 3)
                    evolution_adjustment -= advantage
                    adjustment_notes.append(f"稀有型优势-{advantage:.1%}")
            
            # 2. 新物种适应性优势
            if eco_cfg.enable_new_species_advantage:
                species_age = turn_index - species_arrays['created_turn'][sp_idx]
                
                if species_age == 0:
                    # 新分化物种第1回合：最大优势
                    advantage = eco_cfg.new_species_advantage_turn0
                    evolution_adjustment -= advantage
                    adjustment_notes.append(f"新种优势T0-{advantage:.1%}")
                elif species_age == 1:
                    advantage = eco_cfg.new_species_advantage_turn1
                    evolution_adjustment -= advantage
                    adjustment_notes.append(f"新种优势T1-{advantage:.1%}")
                elif species_age == 2:
                    advantage = eco_cfg.new_species_advantage_turn2
                    evolution_adjustment -= advantage
                    adjustment_notes.append(f"新种优势T2-{advantage:.1%}")
            
            # 3. 增强子代压制（对亲代的额外惩罚）
            lineage_code = species.lineage_code
            if lineage_code in parent_to_children:
                # 该物种有子代，施加演化滞后惩罚
                children_indices = parent_to_children[lineage_code]
                
                # 计算最年轻子代的年龄
                min_child_age = min(
                    turn_index - species_arrays['created_turn'][ci]
                    for ci in children_indices
                )
                
                if min_child_age == 0:
                    penalty = eco_cfg.parent_lag_penalty_turn0
                    evolution_adjustment += penalty
                    adjustment_notes.append(f"亲代滞后T0+{penalty:.1%}")
                elif min_child_age == 1:
                    penalty = eco_cfg.parent_lag_penalty_turn1
                    evolution_adjustment += penalty
                    adjustment_notes.append(f"亲代滞后T1+{penalty:.1%}")
                elif min_child_age == 2:
                    penalty = eco_cfg.parent_lag_penalty_turn2
                    evolution_adjustment += penalty
                    adjustment_notes.append(f"亲代滞后T2+{penalty:.1%}")
            
            # 4. 高生态位重叠直接竞争 (增强版：竞争排斥)
            overlap = species_arrays['overlap'][sp_idx]
            # 原有逻辑保留作为基础压力
            if overlap > eco_cfg.high_overlap_threshold:
                excess_overlap = overlap - eco_cfg.high_overlap_threshold
                overlap_penalty = min(
                    eco_cfg.overlap_competition_max,
                    (excess_overlap / 0.1) * eco_cfg.overlap_competition_per_01
                )
                evolution_adjustment += overlap_penalty
                adjustment_notes.append(f"重叠竞争+{overlap_penalty:.1%}")
            
            # 【新增 v12】竞争排斥 (Competitive Exclusion)
            # 如果重叠度极高 (>60%) 且自身适应性不是最优，受到额外重罚
            if overlap > 0.6:
                # 简单判断：如果该物种的饱和度也高，说明它在竞争中处于劣势（资源不够分）
                saturation = species_arrays['saturation'][sp_idx]
                if saturation > 1.2:
                    # 竞争失败惩罚
                    exclusion_penalty = 0.20  # 额外+20%
                    evolution_adjustment += exclusion_penalty
                    adjustment_notes.append(f"竞争排斥淘汰+{exclusion_penalty:.1%}")
            
            # 【新增v4】5. 食物网反馈压力
            # 处理来自 FoodWebManager 的反馈信号
            lineage_code = species.lineage_code
            
            # 5a. 物种特定的食物网死亡率惩罚（饥饿/孤立）
            food_web_mortality_key = f"food_web_mortality_{lineage_code}"
            if food_web_mortality_key in trophic_interactions:
                food_web_penalty = trophic_interactions[food_web_mortality_key]
                evolution_adjustment += food_web_penalty
                adjustment_notes.append(f"食物网压力+{food_web_penalty:.1%}")
            
            # 5b. 全局食物网健康度惩罚
            if "food_web_global_penalty" in trophic_interactions:
                if species_arrays['trophic_level'][sp_idx] >= 2.0:  # 只影响消费者
                    global_penalty = trophic_interactions["food_web_global_penalty"]
                    evolution_adjustment += global_penalty
                    adjustment_notes.append(f"食物网健康度惩罚+{global_penalty:.1%}")
            
            # 5c. 营养级稀缺信号
            trophic_level_int = int(species_arrays['trophic_level'][sp_idx])
            scarcity_key = f"t{trophic_level_int}_scarcity"
            if scarcity_key in trophic_interactions:
                scarcity = trophic_interactions[scarcity_key]
                if scarcity > 0.5:  # 只有高稀缺时才应用
                    scarcity_penalty = min(0.1, (scarcity - 0.5) * 0.1)
                    evolution_adjustment += scarcity_penalty
                    adjustment_notes.append(f"T{trophic_level_int}稀缺+{scarcity_penalty:.1%}")
            
            # 应用调整
            if evolution_adjustment != 0:
                old_rate = overall_death_rate
                overall_death_rate = min(1.0, max(0.01, overall_death_rate + evolution_adjustment))
                
                # 【修复】同步更新地块统计数据，确保UI显示的一致性
                # 全局演化修正（如新种优势、竞争惩罚）应体现到每个地块的统计中
                if total_tiles > 0:
                    # 将修正应用到地块死亡率统计样本上
                    adjusted_rates = occupied_rates + evolution_adjustment
                    # 确保范围合理
                    adjusted_rates = np.clip(adjusted_rates, 0.01, 1.0)
                    
                    # 重新计算统计指标
                    healthy_tiles = int((adjusted_rates < 0.25).sum())
                    warning_tiles = int(((adjusted_rates >= 0.25) & (adjusted_rates < 0.50)).sum())
                    critical_tiles = int((adjusted_rates >= 0.50).sum())
                    best_tile_rate = float(adjusted_rates.min())
                    worst_tile_rate = float(adjusted_rates.max())
                    has_refuge = bool((adjusted_rates < 0.20).any())
                
                # 重新计算存活数
                if total_pop > 0:
                    new_survivors = int(total_pop * (1.0 - overall_death_rate))
                    new_deaths = total_pop - new_survivors
                    total_survivors = max(0, new_survivors)
                    total_deaths = max(0, new_deaths)
                
                if adjustment_notes:
                    logger.debug(
                        f"[演化平衡] {species.common_name}: "
                        f"死亡率 {old_rate:.1%} → {overall_death_rate:.1%} "
                        f"({', '.join(adjustment_notes)})"
                    )
            
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
            
            death_rate = min(1.0, max(0.03, base_mortality + overlap_penalty + saturation_penalty))
            
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

