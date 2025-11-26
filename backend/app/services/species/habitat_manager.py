"""栖息地管理服务：处理物种迁徙和栖息地变化

"""
from __future__ import annotations

import logging
import random
from typing import Sequence

from ...models.environment import HabitatPopulation, MapTile
from ...models.species import Species
from ...repositories.environment_repository import environment_repository
from ...repositories.species_repository import species_repository
from ...schemas.responses import MigrationEvent
from ...simulation.constants import LOGIC_RES_X, LOGIC_RES_Y

logger = logging.getLogger(__name__)


class HabitatManager:
    """栖息地管理器：处理物种在地块间的迁徙和分布变化"""
    
    def __init__(self):
        self.repo = environment_repository
    
    def execute_migration(
        self, 
        species: Species, 
        migration_event: MigrationEvent,
        all_tiles: list[MapTile],
        turn_index: int
    ) -> bool:
        """实际执行迁徙（P1）- 部分迁徙版本
        
        关键改进：
        - 不会全部迁走，根据迁徙类型保留不同比例的种群
        - 压力驱动：60-80%迁走，20-40%留守
        - 资源饱和：20-40%迁走，60-80%留守
        - 种群溢出：30-50%迁走，50-70%留守
        
        Args:
            species: 要迁徙的物种
            migration_event: 迁徙建议
            all_tiles: 所有地块
            turn_index: 当前回合
            
        Returns:
            是否成功迁徙
        """
        if not species.id:
            logger.warning(f"[迁徙] {species.common_name} 没有ID，跳过")
            return False
        
        # 1. 获取当前栖息地
        all_habitats = self.repo.latest_habitats()
        current_habitats = [h for h in all_habitats if h.species_id == species.id]
        
        if not current_habitats:
            logger.warning(f"[迁徙] {species.common_name} 没有现有栖息地，跳过")
            return False
        
        # 2. 根据迁徙类型决定目标地块
        target_tiles = self._select_migration_targets(
            species, 
            migration_event, 
            all_tiles,
            current_habitats
        )
        
        if not target_tiles:
            logger.warning(f"[迁徙] {species.common_name} 没有找到合适的迁徙目标")
            return False
        
        # 3. 计算迁徙比例（关键改进）
        migration_ratio = self._calculate_migration_ratio(migration_event)
        retention_ratio = 1.0 - migration_ratio
        
        # 4. 保留旧栖息地（降低适宜度权重）
        retained_habitats = []
        for old_habitat in current_habitats:
            # 保留一定比例的种群在原地
            # 即使迁徙比例很高，也至少保留10%
            actual_retention = max(0.1, retention_ratio)
            retained_habitats.append(
                HabitatPopulation(
                    tile_id=old_habitat.tile_id,
                    species_id=species.id,
                    population=0,  # 种群数量存储在species表
                    suitability=old_habitat.suitability * actual_retention,
                    turn_index=turn_index,
                )
            )
        
        # 5. 创建新栖息地（分配迁徙比例的适宜度）
        new_habitats = []
        # 将迁徙比例的适宜度分配到新地块
        per_tile_ratio = migration_ratio / len(target_tiles)
        for tile, base_suitability in target_tiles:
            new_habitats.append(
                HabitatPopulation(
                    tile_id=tile.id,
                    species_id=species.id,
                    population=0,
                    suitability=base_suitability * per_tile_ratio,
                    turn_index=turn_index,
                )
            )
        
        # 6. 合并保存（旧+新）
        all_new_habitats = retained_habitats + new_habitats
        if all_new_habitats:
            self.repo.write_habitats(all_new_habitats)
            
            # P3优化：计算迁徙成本（生物量损失）
            migration_cost = self._calculate_migration_cost(
                species, len(current_habitats), len(new_habitats), migration_ratio
            )
            
            logger.info(
                f"[迁徙] {species.common_name}: "
                f"保留{len(retained_habitats)}个旧地块({retention_ratio:.0%}), "
                f"迁往{len(new_habitats)}个新地块({migration_ratio:.0%}), "
                f"迁徙成本={migration_cost:.1%}"
            )
            return True
        
        return False
    
    def _calculate_migration_cost(
        self,
        species: Species,
        num_old_tiles: int,
        num_new_tiles: int,
        migration_ratio: float
    ) -> float:
        """P3优化：计算迁徙成本（未来可用于实际扣除种群）
        
        迁徙成本考虑：
        1. 迁徙距离（地块数量作为代理）
        2. 迁徙比例（迁徙越多，成本越高）
        3. 物种体型（大型动物迁徙成本更高）
        
        Args:
            species: 迁徙的物种
            num_old_tiles: 原栖息地数量
            num_new_tiles: 新栖息地数量
            migration_ratio: 迁徙比例
            
        Returns:
            成本比例（0-0.3，即最多损失30%种群）
        """
        # 1. 基础成本（基于迁徙比例）
        base_cost = migration_ratio * 0.05  # 迁徙100%时基础成本5%
        
        # 2. 距离成本（新地块越多，视为距离越远）
        distance_factor = num_new_tiles / max(1, num_old_tiles)
        distance_cost = min(0.15, distance_factor * 0.05)  # 最多15%
        
        # 3. 体型成本（大型动物迁徙困难）
        body_size = species.morphology_stats.get("body_length_cm", 1.0)
        if body_size > 100:  # 大型动物
            size_cost = 0.1
        elif body_size > 10:  # 中型
            size_cost = 0.05
        else:  # 小型
            size_cost = 0.02
        
        total_cost = base_cost + distance_cost + size_cost
        
        # 限制在0-30%之间
        return min(0.3, max(0.0, total_cost))
    
    def _select_migration_targets(
        self,
        species: Species,
        migration_event: MigrationEvent,
        all_tiles: list[MapTile],
        current_habitats: list[HabitatPopulation]
    ) -> list[tuple[MapTile, float]]:
        """选择迁徙目标地块
        
        策略：
        - pressure_driven: 逃离当前区域，寻找低压力区
        - saturation_dispersal: 扩散到邻近区域
        - population_overflow: 溢出到周边空白区域
        """
        # 获取当前地块ID集合
        current_tile_ids = {h.tile_id for h in current_habitats}
        
        # 根据栖息地类型筛选候选地块
        habitat_type = getattr(species, 'habitat_type', 'terrestrial')
        candidate_tiles = self._filter_by_habitat_type(all_tiles, habitat_type)
        
        # 排除当前已占据的地块
        candidate_tiles = [t for t in candidate_tiles if t.id not in current_tile_ids]
        
        if not candidate_tiles:
            return []
        
        # 计算适宜度
        scored_tiles = []
        for tile in candidate_tiles:
            suitability = self._calculate_suitability(species, tile)
            if suitability > 0.3:  # 只考虑适宜度>0.3的地块
                scored_tiles.append((tile, suitability))
        
        # 根据迁徙类型排序
        rationale_lower = migration_event.rationale.lower()
        
        if "死亡率" in migration_event.rationale or "压力" in migration_event.rationale:
            # 压力驱动：选择最适宜的地块
            scored_tiles.sort(key=lambda x: x[1], reverse=True)
            return scored_tiles[:5]  # 迁往5个最佳地块
        
        elif "资源压力" in migration_event.rationale or "竞争" in migration_event.rationale:
            # 资源饱和：扩散到中等适宜度的地块（避开高竞争区）
            scored_tiles.sort(key=lambda x: abs(x[1] - 0.6))  # 选择适宜度接近0.6的
            return scored_tiles[:8]  # 扩散到8个中等地块
        
        elif "溢出" in migration_event.rationale or "增长" in migration_event.rationale:
            # 种群溢出：扩散到邻近所有合适地块
            scored_tiles.sort(key=lambda x: x[1], reverse=True)
            return scored_tiles[:10]  # 溢出到10个地块
        
        else:
            # 默认：选择top5
            scored_tiles.sort(key=lambda x: x[1], reverse=True)
            return scored_tiles[:5]
    
    def _filter_by_habitat_type(self, tiles: list[MapTile], habitat_type: str) -> list[MapTile]:
        """根据栖息地类型筛选地块"""
        filtered = []
        
        for tile in tiles:
            biome = tile.biome.lower()
            
            if habitat_type == "marine":
                if "浅海" in biome or "中层" in biome:
                    filtered.append(tile)
            elif habitat_type == "deep_sea":
                if "深海" in biome:
                    filtered.append(tile)
            elif habitat_type == "coastal":
                if "海岸" in biome or "浅海" in biome:
                    filtered.append(tile)
            elif habitat_type == "freshwater":
                if getattr(tile, 'is_lake', False):
                    filtered.append(tile)
            elif habitat_type == "amphibious":
                if "海岸" in biome or ("平原" in biome and tile.humidity > 0.4):
                    filtered.append(tile)
            elif habitat_type == "terrestrial":
                if "海" not in biome:
                    filtered.append(tile)
            elif habitat_type == "aerial":
                if "海" not in biome and "山" not in biome:
                    filtered.append(tile)
        
        return filtered if filtered else tiles[:10]  # 如果没有合适的，返回前10个作为备选
    
    def _calculate_suitability(self, species: Species, tile: MapTile) -> float:
        """计算物种在地块的适宜度（简化版）"""
        # 温度适应性
        temp_pref = species.abstract_traits.get("耐热性", 5)
        cold_pref = species.abstract_traits.get("耐寒性", 5)
        
        if tile.temperature > 20:
            temp_score = temp_pref / 10.0
        elif tile.temperature < 5:
            temp_score = cold_pref / 10.0
        else:
            temp_score = 0.8
        
        # 湿度适应性
        drought_pref = species.abstract_traits.get("耐旱性", 5)
        humidity_score = 1.0 - abs(tile.humidity - (1.0 - drought_pref / 10.0))
        
        # 资源可用性
        resource_score = min(1.0, tile.resources / 500.0)
        
        # 综合评分
        return (temp_score * 0.4 + humidity_score * 0.3 + resource_score * 0.3)
    
    def _calculate_migration_ratio(self, migration_event: MigrationEvent) -> float:
        """计算迁徙比例（0-1之间）
        
        根据迁徙原因决定有多少比例的种群会迁徙：
        - 压力驱动（逃离）：60-80% 迁走
        - 资源饱和（扩散）：20-40% 迁走
        - 种群溢出（扩张）：30-50% 迁走
        
        Args:
            migration_event: 迁徙事件
            
        Returns:
            迁徙比例（0.2-0.8）
        """
        rationale = migration_event.rationale.lower()
        
        if "死亡率" in rationale or "灭绝" in rationale or "危机" in rationale:
            # 压力驱动：大规模逃离（60-80%）
            return random.uniform(0.6, 0.8)
        
        elif "资源压力" in rationale or "竞争" in rationale or "饱和" in rationale:
            # 资源饱和：中等扩散（20-40%）
            return random.uniform(0.2, 0.4)
        
        elif "溢出" in rationale or "增长" in rationale or "扩张" in rationale:
            # 种群溢出：中等扩张（30-50%）
            return random.uniform(0.3, 0.5)
        
        else:
            # 默认：中等迁徙（40-60%）
            return random.uniform(0.4, 0.6)
    
    def calculate_tile_carrying_capacity(
        self, 
        tile: MapTile, 
        species: Species,
        global_state: dict = None
    ) -> float:
        """计算地块对特定物种的承载力（P3: 区域承载力）
        
        Args:
            tile: 目标地块
            species: 物种
            global_state: 全局状态（温度、海平面等）
            
        Returns:
            该地块对该物种的承载力（kg）
        """
        # 1. 基础承载力（基于地块资源）
        # resources: 1-1000，映射到承载力
        base_capacity = tile.resources * 100_000  # 资源1 = 10万kg
        
        # 2. 环境动态修正（P2: 动态承载力）
        if global_state:
            temp_change = global_state.get("temp_change", 0.0)
            sea_level_change = global_state.get("sea_level_change", 0.0)
            
            # 温度变化影响
            if abs(temp_change) > 2.0:
                # 剧烈温度变化降低承载力
                base_capacity *= (1.0 - min(0.3, abs(temp_change) / 10.0))
            
            # 海平面变化影响
            if abs(sea_level_change) > 10.0:
                # 海平面剧烈变化降低承载力
                base_capacity *= (1.0 - min(0.2, abs(sea_level_change) / 50.0))
        
        # 3. 物种适应性修正
        suitability = self._calculate_suitability(species, tile)
        effective_capacity = base_capacity * suitability
        
        # 4. 体型修正（大型动物需要更大空间）
        body_size = species.morphology_stats.get("body_length_cm", 1.0)
        if body_size > 100:  # 大型动物
            effective_capacity *= 0.5
        elif body_size < 1:  # 小型生物
            effective_capacity *= 2.0
        
        return max(1000, effective_capacity)  # 最低1000kg
    
    def get_regional_carrying_capacities(
        self,
        species_list: Sequence[Species],
        all_tiles: list[MapTile],
        global_state: dict = None
    ) -> dict[tuple[int, int], float]:
        """计算所有地块对所有物种的总承载力（P3）
        
        Returns:
            {(tile_id, species_id): carrying_capacity_kg}
        """
        capacities = {}
        
        for species in species_list:
            if species.status != "alive" or not species.id:
                continue
            
            for tile in all_tiles:
                if not tile.id:
                    continue
                
                capacity = self.calculate_tile_carrying_capacity(
                    tile, species, global_state
                )
                capacities[(tile.id, species.id)] = capacity
        
        return capacities

    def adjust_habitats_for_climate(
        self,
        species_list: Sequence[Species],
        temp_change: float,
        sea_level_change: float,
        turn_index: int,
    ) -> None:
        """根据气候变化衰减/加权栖息地适宜度。"""
        if abs(temp_change) < 0.1 and abs(sea_level_change) < 0.5:
            return
        
        habitats = self.repo.latest_habitats()
        if not habitats:
            return
        
        species_map = {sp.id: sp for sp in species_list if sp.id}
        updated: list[HabitatPopulation] = []
        
        for habitat in habitats:
            species = species_map.get(habitat.species_id)
            if not species:
                continue
            
            modifier = 1.0
            env_sensitivity = species.hidden_traits.get("environment_sensitivity", 0.5)
            
            if abs(temp_change) >= 0.1:
                temp_penalty = min(0.25, abs(temp_change) / 30.0)
                modifier -= temp_penalty * (0.5 + env_sensitivity)
            
            if abs(sea_level_change) >= 0.5:
                habitat_type = (species.habitat_type or "").lower()
                if habitat_type in {"marine", "coastal", "deep_sea"}:
                    modifier += min(0.1, sea_level_change / 100.0) if sea_level_change > 0 else -min(0.2, abs(sea_level_change) / 40.0)
                else:
                    modifier -= min(0.25, abs(sea_level_change) / 40.0)
            
            modifier = max(0.2, min(1.2, modifier))
            new_score = habitat.suitability * modifier
            if abs(new_score - habitat.suitability) < 0.01:
                continue
            
            updated.append(
                HabitatPopulation(
                    tile_id=habitat.tile_id,
                    species_id=habitat.species_id,
                    population=0,
                    suitability=max(0.05, min(1.0, new_score)),
                    turn_index=turn_index,
                )
            )
        
        if updated:
            self.repo.write_habitats(updated)
            logger.info(f"[栖息地] 气候变化调整 {len(updated)} 条栖息地记录")

# 单例实例
habitat_manager = HabitatManager()
