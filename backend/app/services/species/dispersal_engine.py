"""矩阵化扩散引擎 - 高效计算物种扩散和迁徙

【核心功能】
1. 使用numpy矩阵批量计算所有地块的扩散适宜度
2. 利用embedding相似度辅助决策
3. 支持多种扩散模式：被动扩散、压力驱动、种群溢出

【扩散模式】
- 被动扩散（passive）：每回合自动向邻近地块扩散，小概率远距离跳跃
- 压力驱动（pressure_driven）：高死亡率触发大规模逃离
- 种群溢出（overflow）：种群超过承载力时溢出扩散
- 猎物追踪（prey_tracking）：消费者追随猎物分布

【平衡v2调整】
- 降低扩散阈值，让物种更容易散布
- 增加被动扩散概率
- 缩短迁徙冷却时间
"""
from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.environment import HabitatPopulation, MapTile
    from ...models.species import Species
    from ..analytics.embedding_integration import EmbeddingIntegrationService

from ...models.environment import HabitatPopulation, MapTile
from ...repositories.environment_repository import environment_repository
from ...simulation.constants import LOGIC_RES_X, LOGIC_RES_Y, get_time_config
from scipy.ndimage import label as scipy_label

logger = logging.getLogger(__name__)


class DispersalEngine:
    """矩阵化扩散引擎
    
    使用numpy进行高效的批量地块评分计算
    """
    
    # 【平衡调整】降低无序扩散与远跳
    PASSIVE_DISPERSAL_PROB = 0.22       # 被动扩散概率：回合22%
    LONG_JUMP_PROB = 0.02               # 远距离跳跃概率：2%
    OVERFLOW_THRESHOLD = 0.65           # 种群溢出阈值
    PRESSURE_DISPERSAL_THRESHOLD = 0.12 # 压力扩散阈值
    
    # 【新增】水域物种扩散优惠（保留但减弱）
    AQUATIC_DISTANCE_FACTOR = 0.75      # 水域物种距离成本系数
    AQUATIC_JUMP_BONUS = 0.04           # 水域物种远跳概率加成
    
    # 迁徙冷却（回合数）
    MIGRATION_COOLDOWN = 2              # 迁徙冷却：2 回合
    DISPERSAL_COOLDOWN = 1              # 被动扩散冷却：1 回合
    
    # 【时代缩放】当前时代的缩放因子（由 set_era_scaling 设置）
    _era_scaling: float = 1.0
    _effective_passive_prob: float = 0.40
    _effective_long_jump_prob: float = 0.10
    
    @classmethod
    def set_era_scaling(cls, turn_index: int) -> None:
        """根据当前回合设置时代缩放因子
        
        太古宙/元古宙：每回合代表几千万年，扩散应该非常快
        - 太古宙: scaling_factor = 40 → 扩散概率约 95%
        - 元古宙: scaling_factor = 100 → 扩散概率约 99%
        
        Args:
            turn_index: 当前回合数
        """
        time_config = get_time_config(turn_index)
        cls._era_scaling = time_config["scaling_factor"]
        
        # 使用平方根缓和极端值，但保持显著差异
        # 太古宙: sqrt(40) ≈ 6.3x, 元古宙: sqrt(100) = 10x
        effective_mult = max(1.0, cls._era_scaling ** 0.5)
        
        # 计算有效概率（使用1 - (1-p)^n 公式模拟多次机会）
        # 相当于在一回合内有 effective_mult 次扩散机会
        base_p = cls.PASSIVE_DISPERSAL_PROB
        base_j = cls.LONG_JUMP_PROB
        
        # 早期时代：大幅提高扩散概率
        cls._effective_passive_prob = min(0.95, 1.0 - (1.0 - base_p) ** effective_mult)
        cls._effective_long_jump_prob = min(0.50, 1.0 - (1.0 - base_j) ** effective_mult)
        
        if cls._era_scaling > 1.5:
            logger.info(f"[扩散引擎] {time_config['era_name']}，时代缩放={cls._era_scaling:.1f}x，"
                       f"有效扩散概率={cls._effective_passive_prob:.1%}，远跳概率={cls._effective_long_jump_prob:.1%}")
    
    def __init__(self, embedding_service: 'EmbeddingIntegrationService | None' = None):
        self.repo = environment_repository
        self.embeddings = embedding_service
        
        # 缓存
        self._tile_matrix: np.ndarray | None = None  # (n_tiles, features) 地块特征矩阵
        self._tile_coords: np.ndarray | None = None  # (n_tiles, 2) 坐标矩阵
        self._tile_ids: list[int] = []               # 地块ID列表
        self._tile_map: dict[int, int] = {}          # tile_id -> matrix_index
        
        # 【新增】连通性缓存
        self._tile_land_labels: np.ndarray | None = None   # (n_tiles,) 陆地连通区域ID
        self._tile_water_labels: np.ndarray | None = None  # (n_tiles,) 水域连通区域ID
        
        # 物种冷却
        self._last_dispersal: dict[str, int] = {}    # {lineage_code: last_turn}
        self._last_migration: dict[str, int] = {}    # {lineage_code: last_turn}
    
    def update_tile_cache(self, tiles: list[MapTile]) -> None:
        """更新地块矩阵缓存
        
        将地块信息转换为numpy矩阵，便于批量计算
        【改进】计算并缓存地块连通性（陆地/水域区域）
        """
        n_tiles = len(tiles)
        if n_tiles == 0:
            return
        
        # 特征矩阵: [温度, 湿度, 海拔, 资源, is_land, is_sea, is_coastal]
        features = np.zeros((n_tiles, 7), dtype=np.float32)
        coords = np.zeros((n_tiles, 2), dtype=np.float32)
        self._tile_ids = []
        self._tile_map = {}
        
        # 临时网格用于计算连通性
        grid_elev = np.zeros((LOGIC_RES_Y, LOGIC_RES_X), dtype=np.float32)
        grid_indices = np.full((LOGIC_RES_Y, LOGIC_RES_X), -1, dtype=int)
        
        for i, tile in enumerate(tiles):
            tile_id = tile.id or i
            self._tile_ids.append(tile_id)
            self._tile_map[tile_id] = i
            
            coords[i] = [tile.x, tile.y]
            
            # 填充网格（假设 x, y 是基于 0 到 LOGIC_RES 的）
            tx, ty = int(tile.x), int(tile.y)
            if 0 <= tx < LOGIC_RES_X and 0 <= ty < LOGIC_RES_Y:
                grid_elev[ty, tx] = tile.elevation
                grid_indices[ty, tx] = i
                
            biome = tile.biome.lower()
            
            features[i] = [
                tile.temperature / 50.0,  # 归一化温度 [-1, 1]
                tile.humidity,             # 湿度 [0, 1]
                tile.elevation / 5000.0,   # 归一化海拔
                min(1.0, tile.resources / 1000.0),  # 归一化资源
                1.0 if "海" not in biome else 0.0,  # 是否陆地
                1.0 if "海" in biome or "深" in biome else 0.0,  # 是否海洋
                1.0 if "海岸" in biome or "浅海" in biome else 0.0,  # 是否海岸
            ]
        
        self._tile_matrix = features
        self._tile_coords = coords
        
        # === 计算连通性 ===
        # 1. 陆地连通性 (elevation >= 0)
        land_mask = grid_elev >= 0
        land_labels, _ = scipy_label(land_mask, structure=np.ones((3,3)))
        
        # 2. 水域连通性 (elevation < 0)
        water_mask = grid_elev < 0
        water_labels, _ = scipy_label(water_mask, structure=np.ones((3,3)))
        
        # 映射回一维数组
        self._tile_land_labels = np.zeros(n_tiles, dtype=int)
        self._tile_water_labels = np.zeros(n_tiles, dtype=int)
        
        # 只需要遍历有效网格点
        valid_y, valid_x = np.where(grid_indices >= 0)
        for y, x in zip(valid_y, valid_x):
            idx = grid_indices[y, x]
            self._tile_land_labels[idx] = land_labels[y, x]
            self._tile_water_labels[idx] = water_labels[y, x]
            
        logger.debug(f"[扩散引擎] 已缓存 {n_tiles} 个地块的特征矩阵与连通性数据")
    
    def _get_species_preference_vector(self, species: 'Species') -> np.ndarray:
        """将物种偏好转换为特征向量
        
        用于与地块矩阵计算适宜度
        【修复v9】增强水生物种识别
        """
        traits = species.abstract_traits or {}
        habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
        growth_form = (getattr(species, 'growth_form', '') or '').lower()
        trophic = getattr(species, 'trophic_level', 1.0) or 1.0
        caps = getattr(species, 'capabilities', []) or []
        caps_set = set(c.lower() for c in caps) | set(caps)
        
        # 判断物种实际类型
        is_aquatic = habitat_type in ('marine', 'deep_sea', 'freshwater', 'hydrothermal')
        is_terrestrial = habitat_type in ('terrestrial', 'aerial')
        is_coastal = habitat_type in ('coastal', 'amphibious')
        
        # 从 growth_form 判断水生
        if growth_form == 'aquatic' and trophic < 2.0:
            is_aquatic = True
            is_terrestrial = False
        
        # 从能力判断
        if 'chemosynthesis' in caps_set or '化能合成' in caps_set:
            is_aquatic = True
            is_terrestrial = False
        
        # 温度偏好
        heat_pref = traits.get("耐热性", 5) / 10.0  # 0-1
        cold_pref = traits.get("耐寒性", 5) / 10.0  # 0-1
        temp_pref = heat_pref - cold_pref  # -1 到 1，正=喜热，负=喜冷
        
        # 湿度偏好
        drought_pref = traits.get("耐旱性", 5) / 10.0
        humidity_pref = 1.0 - drought_pref  # 高耐旱 = 低湿度偏好
        
        # 海拔偏好（暂时使用中性值）
        elevation_pref = 0.0
        
        # 资源需求（基于营养级）
        resource_pref = min(1.0, trophic / 3.0)
        
        # 栖息地类型偏好（使用实际判断结果）
        land_pref = 1.0 if is_terrestrial else 0.0
        sea_pref = 1.0 if is_aquatic else 0.0
        coastal_pref = 1.0 if is_coastal else 0.0
        
        return np.array([
            temp_pref, humidity_pref, elevation_pref, resource_pref,
            land_pref, sea_pref, coastal_pref
        ], dtype=np.float32)
    
    def compute_suitability_matrix(
        self,
        species: 'Species',
        exclude_tiles: set[int] | None = None
    ) -> np.ndarray:
        """批量计算物种对所有地块的适宜度
        
        修复v2：使用更宽松的匹配逻辑，避免适宜度过低
        
        Args:
            species: 目标物种
            exclude_tiles: 要排除的地块ID集合
            
        Returns:
            (n_tiles,) 适宜度向量，值域 [0.15, 1]
        """
        if self._tile_matrix is None:
            return np.array([])
        
        n_tiles = len(self._tile_ids)
        pref = self._get_species_preference_vector(species)
        
        # === 温度匹配（严格物理限制）===
        # tile_matrix[:, 0] 是归一化温度 [-1, 1]
        # pref[0] 是温度偏好 [-1, 1]
        # 修复：移除0.3保底，超出耐受范围直接降为0
        temp_diff = np.abs(self._tile_matrix[:, 0] - pref[0])
        # 差异 > 0.5 (即25度温差) 时归零
        temp_match = np.maximum(0.0, 1.0 - temp_diff * 2.0)
        
        # === 湿度匹配（严格物理限制）===
        # 修复：移除0.3保底
        humidity_diff = np.abs(self._tile_matrix[:, 1] - pref[1])
        humidity_match = np.maximum(0.0, 1.0 - humidity_diff * 2.0)
        
        # === 资源匹配 ===
        # 资源作为加分项，而非生存必需项（生存必需项由carrying capacity决定）
        resource_match = self._tile_matrix[:, 3]
        
        # === 栖息地类型匹配（硬约束）===
        # 【修复v8】水生物种不能到陆地，陆生物种不能到深海
        # pref[4]=陆地, pref[5]=海洋, pref[6]=海岸
        habitat_match = (
            self._tile_matrix[:, 4] * pref[4] +  # 陆地
            self._tile_matrix[:, 5] * pref[5] +  # 海洋
            self._tile_matrix[:, 6] * pref[6]    # 海岸
        )
        # 如果没有任何栖息地类型偏好，默认为陆地
        if pref[4] + pref[5] + pref[6] < 0.1:
            habitat_match = self._tile_matrix[:, 4]
        
        # 【重要】硬约束：物理介质不符直接为0
        is_aquatic_species = pref[5] > 0.5 or pref[6] > 0.5  # 海洋或海岸生物
        is_strict_terrestrial = pref[4] > 0.5 and not is_aquatic_species # 纯陆生
        
        is_land_tile = self._tile_matrix[:, 4] > 0.5
        is_sea_tile = self._tile_matrix[:, 5] > 0.5
        
        # 1. 纯陆生生物不能下海
        if is_strict_terrestrial:
            habitat_match = np.where(is_sea_tile, 0.0, habitat_match)
            
        # 2. 水生生物不能上岸（两栖除外）
        # 注意：海岸生物(pref[6])通常可以容忍沿海陆地，这里主要限制纯水生
        is_strict_aquatic = pref[5] > 0.5 and pref[4] < 0.1 and pref[6] < 0.5
        if is_strict_aquatic:
            habitat_match = np.where(is_land_tile, 0.0, habitat_match)

        # === 综合适宜度 ===
        # 任何一项为0则整体为0（木桶效应）
        # 使用几何平均或乘法逻辑，而不是加权求和
        # 这里先保留加权求和结构，但加入强惩罚
        
        base_score = (
            temp_match * 0.3 +
            humidity_match * 0.2 +
            resource_match * 0.2 +
            habitat_match * 0.3
        )
        
        # 硬性门槛：如果关键环境完全不匹配，适宜度归零
        suitability = np.where(
            (temp_match < 0.05) | (habitat_match < 0.01),
            0.0,
            base_score
        )
        
        # 排除指定地块
        if exclude_tiles:
            for tile_id in exclude_tiles:
                if tile_id in self._tile_map:
                    idx = self._tile_map[tile_id]
                    suitability[idx] = 0.0
        
        # 【修复v8】移除最低适宜度保证，允许为0
        # 原来：suitability = np.clip(suitability, 0.15, 1.0)
        suitability = np.clip(suitability, 0.0, 1.0)
        
        return suitability
    
    def compute_distance_matrix(
        self,
        origin_tiles: list[int],
        max_distance: int = 15,
        connectivity_mode: str = 'air'  # 'land', 'water', 'air'
    ) -> np.ndarray:
        """计算从原点地块到所有地块的距离权重
        
        【大浪淘沙v3】添加水域物种距离优惠
        【修复v11】添加连通性检查
        
        Args:
            origin_tiles: 起点地块ID列表
            max_distance: 最大考虑距离
            connectivity_mode: 连通性模式 ('land', 'water', 'air')
            
        Returns:
            (n_tiles,) 距离权重向量，近=1，远=0
        """
        if self._tile_coords is None:
            return np.array([])
        
        n_tiles = len(self._tile_ids)
        
        # 计算起点的中心
        if not origin_tiles:
            return np.ones(n_tiles)
        
        origin_indices = []
        origin_coords = []
        for tid in origin_tiles:
            if tid in self._tile_map:
                idx = self._tile_map[tid]
                origin_indices.append(idx)
                origin_coords.append(self._tile_coords[idx])
        
        if not origin_coords:
            return np.ones(n_tiles)
        
        center = np.mean(origin_coords, axis=0)
        
        # 计算曼哈顿距离
        distances = np.abs(self._tile_coords - center).sum(axis=1)
        
        # 【大浪淘沙v3】水域物种距离成本打折
        effective_max_distance = max_distance
        if connectivity_mode == 'water':
            # 水域物种可以更远距离扩散
            effective_max_distance = int(max_distance / self.AQUATIC_DISTANCE_FACTOR)
        
        # 转换为权重（近=1，远=0）
        weights = np.maximum(0.0, 1.0 - distances / effective_max_distance)
        
        # === 连通性检查 ===
        # 只有同一个连通区域的地块才可达（除非是飞行/空气传播）
        if connectivity_mode == 'land' and self._tile_land_labels is not None:
            # 获取起点的陆地连通ID集合 (忽略0，0通常是背景/无效)
            origin_labels = set()
            for idx in origin_indices:
                lbl = self._tile_land_labels[idx]
                if lbl > 0:
                    origin_labels.add(lbl)
            
            if origin_labels:
                # 目标必须在相同连通区域
                reachable_mask = np.isin(self._tile_land_labels, list(origin_labels))
                weights *= reachable_mask
            else:
                # 起点都在海里（错误情况），可能无法扩散到陆地
                pass
                
        elif connectivity_mode == 'water' and self._tile_water_labels is not None:
            origin_labels = set()
            for idx in origin_indices:
                lbl = self._tile_water_labels[idx]
                if lbl > 0:
                    origin_labels.add(lbl)
            
            if origin_labels:
                reachable_mask = np.isin(self._tile_water_labels, list(origin_labels))
                weights *= reachable_mask

        # 【大浪淘沙v3】超出范围的地块也有概率被选中（远距离跳跃/漂流）
        # 注意：跳跃仍然受限于连通性吗？
        # 解释：跳跃代表偶发事件（如漂流木），通常可以跨越障碍。
        # 因此我们将 long_jump 加在 connectivity mask 之后？
        # 不，漂流木可以跨海，所以 long_jump 应该绕过连通性检查。
        # 但为了严谨，陆生生物不能轻易跨海。
        # 让我们设定：连通性检查是硬约束，但 long_jump 是特例。
        
        # 使用时代调整后的有效远跳概率
        long_jump = self._effective_long_jump_prob
        if connectivity_mode == 'water':
            long_jump += self.AQUATIC_JUMP_BONUS
        
        # 只有当 connectivity_mode 为 air 时，或者发生了 rare event，才能跨越
        # 但在此函数中很难模拟 rare event per tile。
        # 妥协：保留 long_jump 但仅限于距离，不突破连通性？
        # 不，这会导致岛屿生物永远无法出去。
        # 方案：给 long_jump 一个极低的概率突破连通性 (0.01)
        
        # 基础权重（受连通性限制）
        base_weights = weights
        
        # 跳跃权重（不受连通性限制，但值很低）
        jump_weights = np.full(n_tiles, long_jump * 0.1) # 降低跳跃权重
        
        # 最终权重取最大值？不，这样连通性就失效了（因为 0 vs 0.01）
        # 正确做法：大部分情况下受连通性限制。
        # 只有在 compute_distance_matrix 之外的逻辑处理跳跃？
        # 让我们保持简单：连通性是绝对的，除非是飞行生物。
        # 漂流事件应该由特殊事件系统处理，而不是常规扩散。
        
        # 恢复 long_jump 逻辑，但受限于 masked weights
        # 如果被 mask 为 0，则保持为 0
        # weights = np.maximum(weights, long_jump) # 这会破坏mask
        
        # 正确逻辑：先加 long_jump，再乘 mask
        # weights = np.maximum(0.0, 1.0 - distances / effective_max_distance)
        # weights = np.maximum(weights, long_jump)
        # weights *= mask
        
        # 但这样就无法跨海了。
        # 用户抱怨的是"很容易跨越很大距离"，所以我们应该严格限制。
        # 想要跨海，必须进化出飞行或游泳。
        
        return weights
    
    def compute_prey_density_matrix(
        self,
        consumer_trophic: float,
        prey_habitats: dict[int, list[tuple[int, float]]]  # {species_id: [(tile_id, suitability)]}
    ) -> np.ndarray:
        """计算消费者的猎物密度矩阵
        
        Args:
            consumer_trophic: 消费者营养级
            prey_habitats: 潜在猎物的栖息地分布
            
        Returns:
            (n_tiles,) 猎物密度向量
        """
        if self._tile_matrix is None:
            return np.array([])
        
        n_tiles = len(self._tile_ids)
        density = np.zeros(n_tiles, dtype=np.float32)
        
        for species_id, habitats in prey_habitats.items():
            for tile_id, suitability in habitats:
                if tile_id in self._tile_map:
                    idx = self._tile_map[tile_id]
                    density[idx] += suitability
        
        # 归一化
        if density.max() > 0:
            density = density / density.max()
        
        return density
    
    def select_dispersal_targets(
        self,
        species: 'Species',
        current_tiles: list[int],
        num_targets: int = 5,
        mode: str = 'passive',
        prey_density: np.ndarray | None = None,
        migration_range: int = 5
    ) -> list[tuple[int, float]]:
        """选择扩散目标地块
        
        Args:
            species: 目标物种
            current_tiles: 当前占据的地块ID列表
            num_targets: 目标地块数量
            mode: 扩散模式 (passive/pressure_driven/overflow/prey_tracking)
            prey_density: 猎物密度矩阵（消费者用）
            migration_range: 迁徙范围限制
            
        Returns:
            [(tile_id, score)] 目标地块及其评分
        """
        if self._tile_matrix is None:
            return []
        
        # 计算基础适宜度
        suitability = self.compute_suitability_matrix(
            species,
            exclude_tiles=set(current_tiles)
        )
        
        # 确定连通性模式
        connectivity_mode = 'land'  # 默认陆地
        
        habitat_type = (getattr(species, 'habitat_type', '') or 'terrestrial').lower()
        organs = getattr(species, 'organs', {})
        locomotion = organs.get('locomotion', {})
        loc_type = locomotion.get('type', '')
        
        if loc_type in ('wings', 'flight') or habitat_type == 'aerial':
            connectivity_mode = 'air'  # 飞行生物不受地形阻隔
        elif habitat_type in ('marine', 'deep_sea', 'freshwater', 'hydrothermal'):
            connectivity_mode = 'water' # 水生生物受陆地阻隔
        elif habitat_type in ('amphibious', 'coastal'):
             # 两栖/海岸生物通常沿海岸线移动，视为陆地连通但允许一定的越水能力
             # 这里简化为 'land'，因为 compute_distance_matrix 会检查陆地连通性
             # 如果想让它们跨海，需要 loc_type='swimming'
             if loc_type in ('fins', 'swimming'):
                 connectivity_mode = 'water'
             else:
                 connectivity_mode = 'land'
        
        # 计算距离权重
        distance_weights = self.compute_distance_matrix(
            current_tiles,
            max_distance=migration_range,
            connectivity_mode=connectivity_mode
        )
        
        # 【新增】尝试使用embedding获取相似物种的分布提示
        embedding_bonus = np.zeros_like(suitability)
        if self.embeddings and mode in ('pressure_driven', 'prey_tracking'):
            try:
                # 获取演化提示，了解相似物种的成功栖息地
                hints = self.embeddings.get_evolution_hints(
                    species,
                    pressure_types=['habitat_expansion'],
                    pressure_strengths=[0.5]
                )
                if hints and 'reference_species' in hints:
                    # 相似物种的成功案例可以提供额外的地块加成
                    # 这里简化处理：如果有参考物种，给所有候选地块一个小加成
                    confidence = hints.get('confidence', 0.3)
                    embedding_bonus = np.ones_like(suitability) * confidence * 0.1
            except Exception:
                pass  # embedding服务不可用时静默失败
        
        # 根据模式调整权重
        if mode == 'passive':
            # 被动扩散：距离权重高，适宜度权重低
            scores = suitability * 0.4 + distance_weights * 0.6
            
        elif mode == 'pressure_driven':
            # 压力驱动：适宜度权重高，可以跑得更远
            distance_weights = self.compute_distance_matrix(
                current_tiles,
                max_distance=migration_range * 2  # 允许跑更远
            )
            scores = suitability * 0.6 + distance_weights * 0.3 + embedding_bonus * 0.1
            
        elif mode == 'overflow':
            # 种群溢出：优先邻近地块
            scores = suitability * 0.3 + distance_weights * 0.7
            
        elif mode == 'prey_tracking':
            # 猎物追踪：猎物密度权重最高
            if prey_density is not None:
                scores = (
                    suitability * 0.15 +
                    distance_weights * 0.25 +
                    prey_density * 0.5 +
                    embedding_bonus * 0.1
                )
            else:
                scores = suitability * 0.5 + distance_weights * 0.5
        else:
            scores = suitability * 0.5 + distance_weights * 0.5
        
        # 【平衡v2】添加随机扰动，增加多样性
        noise = np.random.uniform(0.85, 1.15, len(scores))
        scores = scores * noise
        
        # 选择得分最高的地块
        if len(scores) == 0:
            return []
        
        # 获取top-k索引
        top_k = min(num_targets * 2, len(scores))  # 取更多候选
        top_indices = np.argpartition(-scores, top_k)[:top_k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]
        
        # 返回结果
        results = []
        for idx in top_indices[:num_targets]:
            tile_id = self._tile_ids[idx]
            score = float(scores[idx])
            if score > 0.08:  # 【平衡v2】降低最低分数阈值
                results.append((tile_id, score))
        
        return results
    
    def should_passive_disperse(
        self,
        species: 'Species',
        current_turn: int
    ) -> bool:
        """判断物种是否应该进行被动扩散
        
        【平衡v2】提高扩散概率
        """
        lineage = species.lineage_code
        
        # 检查冷却
        last_turn = self._last_dispersal.get(lineage, -999)
        if current_turn - last_turn < self.DISPERSAL_COOLDOWN:
            return False
        
        # 【平衡v2】提高基础概率 + 【时代缩放】使用有效概率
        base_prob = self._effective_passive_prob
        
        # 微生物有更高的扩散概率
        body_size = species.morphology_stats.get("body_length_cm", 10.0)
        if body_size < 0.1:  # 微生物
            base_prob = min(0.98, base_prob * 1.5)  # 早期时代微生物扩散极快
        
        # 快速繁殖物种有更高扩散概率
        gen_time = species.morphology_stats.get("generation_time_days", 30)
        if gen_time < 10:  # 快速繁殖
            base_prob = min(0.98, base_prob * 1.3)
        
        return random.random() < min(0.5, base_prob)
    
    def should_pressure_disperse(
        self,
        species: 'Species',
        death_rate: float,
        current_turn: int
    ) -> bool:
        """判断物种是否应该进行压力驱动扩散"""
        lineage = species.lineage_code
        
        # 检查迁徙冷却
        last_turn = self._last_migration.get(lineage, -999)
        if current_turn - last_turn < self.MIGRATION_COOLDOWN:
            return False
        
        # 【平衡v2】降低阈值
        return death_rate >= self.PRESSURE_DISPERSAL_THRESHOLD
    
    def execute_dispersal(
        self,
        species: 'Species',
        current_habitats: list['HabitatPopulation'],
        target_tiles: list[tuple[int, float]],
        dispersal_ratio: float,
        turn_index: int,
        mode: str = 'passive'
    ) -> bool:
        """执行扩散操作
        
        Args:
            species: 目标物种
            current_habitats: 当前栖息地列表
            target_tiles: 目标地块 [(tile_id, score)]
            dispersal_ratio: 扩散比例（0-1）
            turn_index: 当前回合
            mode: 扩散模式
            
        Returns:
            是否成功扩散
        """
        if not species.id or not target_tiles:
            return False
        
        # 保留原栖息地（降低适宜度权重）
        retention_ratio = max(0.3, 1.0 - dispersal_ratio)
        retained = []
        for hab in current_habitats:
            retained.append(
                HabitatPopulation(
                    tile_id=hab.tile_id,
                    species_id=species.id,
                    population=0,
                    suitability=hab.suitability * retention_ratio,
                    turn_index=turn_index,
                )
            )
        
        # 创建新栖息地
        new_habitats = []
        per_tile_ratio = dispersal_ratio / len(target_tiles)
        
        for tile_id, score in target_tiles:
            new_habitats.append(
                HabitatPopulation(
                    tile_id=tile_id,
                    species_id=species.id,
                    population=0,
                    suitability=score * per_tile_ratio,
                    turn_index=turn_index,
                )
            )
        
        # 写入数据库
        all_habitats = retained + new_habitats
        if all_habitats:
            self.repo.write_habitats(all_habitats)
            
            # 更新冷却
            if mode in ('pressure_driven', 'prey_tracking'):
                self._last_migration[species.lineage_code] = turn_index
            else:
                self._last_dispersal[species.lineage_code] = turn_index
            
            logger.info(
                f"[扩散引擎] {species.common_name}: "
                f"模式={mode}, 保留{len(retained)}地块({retention_ratio:.0%}), "
                f"扩散到{len(new_habitats)}新地块({dispersal_ratio:.0%})"
            )
            return True
        
        return False
    
    def get_species_migration_range(self, species: 'Species') -> int:
        """根据物种能力获取迁徙范围"""
        base_range = 4  # 【平衡v2】从3提高到4
        
        # 检查器官系统
        organs = getattr(species, 'organs', {})
        locomotion = organs.get('locomotion', {})
        locomotion_type = locomotion.get('type', '')
        
        if locomotion_type in ('wings', 'flight'):
            base_range = 12  # 飞行物种
        elif locomotion_type in ('fins', 'swimming'):
            base_range = 8   # 游泳物种
        elif locomotion_type in ('legs', 'running'):
            base_range = 6   # 陆地奔跑
        elif locomotion_type in ('crawling', 'slithering'):
            base_range = 3   # 爬行
        elif locomotion_type in ('sessile', 'rooted'):
            base_range = 2   # 固着/植物（孢子/种子传播）
        
        # 体型调整
        body_size = species.morphology_stats.get("body_length_cm", 10.0)
        if body_size < 0.01:  # 微生物（被动传播）
            base_range = max(5, base_range)  # 微生物可以被动传播较远
        elif body_size > 100:  # 大型动物
            base_range += 2
        
        # 栖息地类型调整
        habitat_type = getattr(species, 'habitat_type', 'terrestrial')
        if habitat_type == 'aerial':
            base_range += 4
        elif habitat_type == 'marine':
            base_range += 2
        
        return max(2, min(20, base_range))  # 限制在2-20范围
    
    def check_isolation_status(
        self,
        species: 'Species',
        current_tiles: list[int]
    ) -> dict[str, any]:
        """检查物种的地理隔离状态
        
        返回:
            {
                "is_isolated": bool,
                "isolation_regions": int, # 占据的连通区域数量
                "isolation_score": float  # 隔离程度 0-1
            }
        """
        if not current_tiles:
            return {"is_isolated": False, "isolation_regions": 0, "isolation_score": 0.0}
            
        # 获取当前占据地块的连通性标签
        current_indices = [self._tile_map[tid] for tid in current_tiles if tid in self._tile_map]
        if not current_indices:
            return {"is_isolated": False, "isolation_regions": 0, "isolation_score": 0.0}
            
        # 根据物种类型选择连通性地图
        habitat_type = (getattr(species, 'habitat_type', '') or 'terrestrial').lower()
        labels = self._tile_land_labels if 'marine' not in habitat_type and 'sea' not in habitat_type else self._tile_water_labels
        
        if labels is None:
            return {"is_isolated": False, "isolation_regions": 1, "isolation_score": 0.0}
            
        occupied_labels = set()
        for idx in current_indices:
            lbl = labels[idx]
            if lbl > 0: # 0是背景
                occupied_labels.add(lbl)
                
        num_regions = len(occupied_labels)
        
        # 隔离判断：如果占据了超过1个不连通的区域
        is_isolated = num_regions > 1
        
        return {
            "is_isolated": is_isolated,
            "isolation_regions": num_regions,
            "isolation_score": 1.0 if num_regions > 1 else 0.0
        }

    def clear_caches(self) -> None:
        """清空所有缓存"""
        self._tile_matrix = None
        self._tile_coords = None
        self._tile_ids.clear()
        self._tile_map.clear()
        self._last_dispersal.clear()
        self._last_migration.clear()


# 创建全局实例
dispersal_engine = DispersalEngine()


def process_batch_dispersal(
    species_list: Sequence['Species'],
    all_tiles: list['MapTile'],
    all_habitats: list['HabitatPopulation'],
    mortality_data: dict[str, float],
    turn_index: int,
    embedding_service: 'EmbeddingIntegrationService | None' = None
) -> dict[str, list[tuple[int, float]]]:
    """批量处理所有物种的扩散
    
    【核心API】在每回合结束时调用，为所有物种计算扩散
    
    Args:
        species_list: 所有存活物种
        all_tiles: 所有地块
        all_habitats: 当前栖息地分布
        mortality_data: 死亡率数据 {lineage_code: death_rate}
        turn_index: 当前回合
        embedding_service: embedding服务（可选，用于智能决策）
        
    Returns:
        {lineage_code: [(new_tile_id, score)]} 扩散结果
    """
    engine = dispersal_engine
    
    # 【时代缩放】根据当前回合设置扩散参数
    # 太古宙/元古宙每回合几千万年，扩散应非常快
    DispersalEngine.set_era_scaling(turn_index)
    
    # 更新地块缓存
    engine.update_tile_cache(all_tiles)
    if embedding_service:
        engine.embeddings = embedding_service
    
    # 构建物种->栖息地映射
    species_habitats: dict[int, list[HabitatPopulation]] = {}
    for hab in all_habitats:
        if hab.species_id not in species_habitats:
            species_habitats[hab.species_id] = []
        species_habitats[hab.species_id].append(hab)
    
    # 构建物种ID->Species映射
    species_map = {sp.id: sp for sp in species_list if sp.id}
    
    # 为消费者构建猎物分布
    prey_by_trophic: dict[float, list[tuple[int, float]]] = {}
    for sp in species_list:
        if sp.status != 'alive' or not sp.id:
            continue
        trophic = getattr(sp, 'trophic_level', 1.0)
        if trophic not in prey_by_trophic:
            prey_by_trophic[trophic] = []
        if sp.id in species_habitats:
            for hab in species_habitats[sp.id]:
                prey_by_trophic[trophic].append((hab.tile_id, hab.suitability))
    
    results = {}
    
    for species in species_list:
        if species.status != 'alive' or not species.id:
            continue
        
        lineage = species.lineage_code
        death_rate = mortality_data.get(lineage, 0.0)
        current_habs = species_habitats.get(species.id, [])
        current_tiles = [h.tile_id for h in current_habs]
        
        if not current_tiles:
            continue
        
        migration_range = engine.get_species_migration_range(species)
        trophic = getattr(species, 'trophic_level', 1.0)
        is_consumer = trophic >= 2.0
        
        # 获取猎物密度（消费者用）
        prey_density = None
        if is_consumer:
            prey_trophics = []
            if trophic >= 4.0:
                prey_trophics = [3.0, 2.5, 2.0]
            elif trophic >= 3.0:
                prey_trophics = [2.0, 1.5, 1.0]
            elif trophic >= 2.0:
                prey_trophics = [1.0, 1.5]
            
            prey_habitats = {}
            for pt in prey_trophics:
                if pt in prey_by_trophic:
                    prey_habitats[pt] = prey_by_trophic[pt]
            
            if prey_habitats:
                prey_density = engine.compute_prey_density_matrix(
                    trophic,
                    {i: habs for i, habs in enumerate(prey_habitats.values())}
                )
        
        # 决定扩散模式
        mode = None
        dispersal_ratio = 0.0
        
        # 获取种群信息用于溢出判断
        population = species.morphology_stats.get("population", 0) or 0
        
        # 1. 压力驱动迁徙（最高优先级）
        if engine.should_pressure_disperse(species, death_rate, turn_index):
            mode = 'pressure_driven'
            dispersal_ratio = min(0.8, 0.3 + death_rate)
            logger.debug(f"[扩散] {species.common_name} 触发压力驱动迁徙 (死亡率={death_rate:.1%})")
        
        # 2. 猎物追踪（消费者专用）
        elif is_consumer and prey_density is not None and np.max(prey_density) > 0.3:
            # 检查当前地块猎物是否稀少
            current_prey = sum(
                prey_density[engine._tile_map[tid]]
                for tid in current_tiles
                if tid in engine._tile_map
            ) / max(1, len(current_tiles))
            
            if current_prey < 0.3:
                mode = 'prey_tracking'
                dispersal_ratio = 0.4
                logger.debug(f"[扩散] {species.common_name} 触发猎物追踪 (当前猎物密度={current_prey:.2f})")
        
        # 3. 【平衡v2新增】种群溢出扩散
        # 当种群较大且占据地块较少时，触发溢出扩散
        elif population > 10000 and len(current_tiles) < 5:
            # 种群密度过高，需要扩散
            mode = 'overflow'
            dispersal_ratio = min(0.5, 0.2 + len(current_tiles) * 0.1)
            logger.debug(f"[扩散] {species.common_name} 触发种群溢出 (种群={population:,}, 地块={len(current_tiles)})")
        
        # 4. 被动扩散（每回合随机触发）
        elif engine.should_passive_disperse(species, turn_index):
            mode = 'passive'
            dispersal_ratio = random.uniform(0.1, 0.25)
            logger.debug(f"[扩散] {species.common_name} 触发被动扩散")
        
        # 执行扩散
        if mode:
            targets = engine.select_dispersal_targets(
                species,
                current_tiles,
                num_targets=5 if mode == 'passive' else 8,
                mode=mode,
                prey_density=prey_density,
                migration_range=migration_range
            )
            
            if targets:
                engine.execute_dispersal(
                    species,
                    current_habs,
                    targets,
                    dispersal_ratio,
                    turn_index,
                    mode
                )
                results[lineage] = targets
    
    return results

