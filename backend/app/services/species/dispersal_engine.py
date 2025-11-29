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
from ...simulation.constants import LOGIC_RES_X, LOGIC_RES_Y

logger = logging.getLogger(__name__)


class DispersalEngine:
    """矩阵化扩散引擎
    
    使用numpy进行高效的批量地块评分计算
    """
    
    # 【平衡v2】扩散参数
    PASSIVE_DISPERSAL_PROB = 0.25       # 被动扩散概率：每回合25%概率向周边扩散
    LONG_JUMP_PROB = 0.05               # 远距离跳跃概率：5%
    OVERFLOW_THRESHOLD = 0.7            # 种群溢出阈值：70%承载力触发
    PRESSURE_DISPERSAL_THRESHOLD = 0.15 # 压力扩散阈值：15%死亡率触发
    
    # 迁徙冷却（回合数）
    MIGRATION_COOLDOWN = 1              # 【平衡v2】从2-3回合降到1回合
    DISPERSAL_COOLDOWN = 0              # 被动扩散无冷却
    
    def __init__(self, embedding_service: 'EmbeddingIntegrationService | None' = None):
        self.repo = environment_repository
        self.embeddings = embedding_service
        
        # 缓存
        self._tile_matrix: np.ndarray | None = None  # (n_tiles, features) 地块特征矩阵
        self._tile_coords: np.ndarray | None = None  # (n_tiles, 2) 坐标矩阵
        self._tile_ids: list[int] = []               # 地块ID列表
        self._tile_map: dict[int, int] = {}          # tile_id -> matrix_index
        
        # 物种冷却
        self._last_dispersal: dict[str, int] = {}    # {lineage_code: last_turn}
        self._last_migration: dict[str, int] = {}    # {lineage_code: last_turn}
    
    def update_tile_cache(self, tiles: list[MapTile]) -> None:
        """更新地块矩阵缓存
        
        将地块信息转换为numpy矩阵，便于批量计算
        """
        n_tiles = len(tiles)
        if n_tiles == 0:
            return
        
        # 特征矩阵: [温度, 湿度, 海拔, 资源, is_land, is_sea, is_coastal]
        features = np.zeros((n_tiles, 7), dtype=np.float32)
        coords = np.zeros((n_tiles, 2), dtype=np.float32)
        self._tile_ids = []
        self._tile_map = {}
        
        for i, tile in enumerate(tiles):
            tile_id = tile.id or i
            self._tile_ids.append(tile_id)
            self._tile_map[tile_id] = i
            
            coords[i] = [tile.x, tile.y]
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
        
        logger.debug(f"[扩散引擎] 已缓存 {n_tiles} 个地块的特征矩阵")
    
    def _get_species_preference_vector(self, species: 'Species') -> np.ndarray:
        """将物种偏好转换为特征向量
        
        用于与地块矩阵计算适宜度
        """
        traits = species.abstract_traits or {}
        habitat_type = getattr(species, 'habitat_type', 'terrestrial')
        
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
        trophic = getattr(species, 'trophic_level', 1.0)
        resource_pref = min(1.0, trophic / 3.0)
        
        # 栖息地类型偏好
        land_pref = 1.0 if habitat_type in ('terrestrial', 'aerial') else 0.0
        sea_pref = 1.0 if habitat_type in ('marine', 'deep_sea') else 0.0
        coastal_pref = 1.0 if habitat_type in ('coastal', 'amphibious') else 0.0
        
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
        
        # === 温度匹配（更宽容）===
        # tile_matrix[:, 0] 是归一化温度 [-1, 1]
        # pref[0] 是温度偏好 [-1, 1]
        temp_diff = np.abs(self._tile_matrix[:, 0] - pref[0])
        temp_match = np.maximum(0.3, 1.0 - temp_diff * 0.7)  # 差距1.0 -> 0.3
        
        # === 湿度匹配（更宽容）===
        humidity_diff = np.abs(self._tile_matrix[:, 1] - pref[1])
        humidity_match = np.maximum(0.3, 1.0 - humidity_diff * 0.8)
        
        # === 资源匹配 ===
        # 资源越多越好，但保证最低值
        resource_match = np.maximum(0.3, self._tile_matrix[:, 3] * 0.7 + 0.3)
        
        # === 栖息地类型匹配（硬约束但不是0）===
        habitat_match = (
            self._tile_matrix[:, 4] * pref[4] +  # 陆地
            self._tile_matrix[:, 5] * pref[5] +  # 海洋
            self._tile_matrix[:, 6] * pref[6]    # 海岸
        )
        # 如果没有任何栖息地类型偏好，默认为陆地
        if pref[4] + pref[5] + pref[6] < 0.1:
            habitat_match = self._tile_matrix[:, 4]
        
        # 栖息地不匹配时给予惩罚但不是0
        habitat_match = np.where(habitat_match > 0.5, habitat_match, 0.1)
        
        # === 综合适宜度 ===
        suitability = (
            temp_match * 0.25 +
            humidity_match * 0.20 +
            resource_match * 0.20 +
            habitat_match * 0.35  # 栖息地类型权重提高
        )
        
        # 排除指定地块
        if exclude_tiles:
            for tile_id in exclude_tiles:
                if tile_id in self._tile_map:
                    idx = self._tile_map[tile_id]
                    suitability[idx] = 0.0
        
        # 保证最低适宜度（避免全部为0）
        suitability = np.clip(suitability, 0.15, 1.0)
        
        return suitability
    
    def compute_distance_matrix(
        self,
        origin_tiles: list[int],
        max_distance: int = 15
    ) -> np.ndarray:
        """计算从原点地块到所有地块的距离权重
        
        Args:
            origin_tiles: 起点地块ID列表
            max_distance: 最大考虑距离
            
        Returns:
            (n_tiles,) 距离权重向量，近=1，远=0
        """
        if self._tile_coords is None:
            return np.array([])
        
        n_tiles = len(self._tile_ids)
        
        # 计算起点的中心
        if not origin_tiles:
            return np.ones(n_tiles)
        
        origin_coords = []
        for tid in origin_tiles:
            if tid in self._tile_map:
                idx = self._tile_map[tid]
                origin_coords.append(self._tile_coords[idx])
        
        if not origin_coords:
            return np.ones(n_tiles)
        
        center = np.mean(origin_coords, axis=0)
        
        # 计算曼哈顿距离
        distances = np.abs(self._tile_coords - center).sum(axis=1)
        
        # 转换为权重（近=1，远=0）
        weights = np.maximum(0.0, 1.0 - distances / max_distance)
        
        # 【平衡v2】超出范围的地块也有小概率被选中（远距离扩散）
        weights = np.maximum(weights, self.LONG_JUMP_PROB)
        
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
        
        # 计算距离权重
        distance_weights = self.compute_distance_matrix(
            current_tiles,
            max_distance=migration_range
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
        
        # 【平衡v2】提高基础概率
        base_prob = self.PASSIVE_DISPERSAL_PROB
        
        # 微生物有更高的扩散概率
        body_size = species.morphology_stats.get("body_length_cm", 10.0)
        if body_size < 0.1:  # 微生物
            base_prob *= 1.5
        
        # 快速繁殖物种有更高扩散概率
        gen_time = species.morphology_stats.get("generation_time_days", 30)
        if gen_time < 10:  # 快速繁殖
            base_prob *= 1.3
        
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

