"""栖息地管理服务：处理物种迁徙和栖息地变化

核心改进：消费者追踪猎物机制
- T2+的消费者迁徙时优先选择有猎物的地块
- 高营养级物种不会迁徙到没有食物来源的地方
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
    """栖息地管理器：处理物种在地块间的迁徙和分布变化
    
    核心改进：
    1. 消费者追踪猎物 - T2+消费者迁徙时优先选择有猎物的地块
    2. 距离约束 - 优先选择邻近地块，根据物种能力限制迁徙范围
    3. 迁徙冷却 - 防止频繁迁徙导致分布不稳定
    4. 种内竞争 - 考虑目标地块的同物种密度
    5. 共生追随 - 有依赖关系的物种会追随迁徙
    """
    
    def __init__(self):
        self.repo = environment_repository
        # 缓存：猎物分布信息 {trophic_range: {tile_id: biomass}}
        self._prey_distribution_cache: dict[float, dict[int, float]] = {}
        # 缓存：所有物种列表（用于计算猎物分布）
        self._species_cache: list[Species] = []
        # 缓存：地块坐标映射 {tile_id: (x, y)}
        self._tile_coords_cache: dict[int, tuple[int, int]] = {}
        # 缓存：物种迁徙冷却 {lineage_code: last_migration_turn}
        self._migration_cooldown: dict[str, int] = {}
        # 缓存：物种在各地块的分布 {species_id: {tile_id: suitability}}
        self._species_distribution_cache: dict[int, dict[int, float]] = {}
    
    def _update_tile_coords_cache(self, all_tiles: list[MapTile]) -> None:
        """更新地块坐标缓存"""
        self._tile_coords_cache = {t.id: (t.x, t.y) for t in all_tiles if t.id}
    
    def _calculate_tile_distance(self, tile1_id: int, tile2_id: int) -> float:
        """计算两个地块之间的距离（曼哈顿距离）"""
        if tile1_id not in self._tile_coords_cache or tile2_id not in self._tile_coords_cache:
            return float('inf')
        
        x1, y1 = self._tile_coords_cache[tile1_id]
        x2, y2 = self._tile_coords_cache[tile2_id]
        return abs(x1 - x2) + abs(y1 - y2)
    
    def _get_species_migration_range(self, species: Species) -> int:
        """根据物种能力获取迁徙范围
        
        【大浪淘沙v3】整体提高迁徙范围，尤其是水域物种
        
        迁徙范围基于：
        1. 移动能力（器官系统）
        2. 体型大小
        3. 栖息地类型
        
        Returns:
            最大迁徙距离（地块单位）
        """
        base_range = 4  # 【大浪淘沙v3】基础范围从3提高到4格
        
        # 1. 检查器官系统获取移动能力
        organs = getattr(species, 'organs', {})
        locomotion = organs.get('locomotion', {})
        locomotion_type = locomotion.get('type', '')
        
        if locomotion_type in ('wings', 'flight'):
            # 飞行物种：大范围迁徙
            base_range = 12  # 原10 -> 12
        elif locomotion_type in ('fins', 'swimming'):
            # 游泳物种：【大浪淘沙v3】大幅增加
            base_range = 10  # 原6 -> 10
        elif locomotion_type in ('legs', 'running'):
            # 陆地奔跑：中等范围
            base_range = 6   # 原5 -> 6
        elif locomotion_type in ('crawling', 'slithering'):
            # 爬行物种：小幅增加
            base_range = 3   # 原2 -> 3
        elif locomotion_type in ('sessile', 'rooted'):
            # 固着/植物：小幅增加被动传播
            base_range = 2   # 原1 -> 2
        
        # 2. 体型调整（小型动物迁徙相对更容易）
        body_size = species.morphology_stats.get("body_length_cm", 10.0)
        if body_size < 1:  # 微型生物
            # 【大浪淘沙v3】微生物被动传播范围增加
            base_range = max(2, base_range - 1)  # 原max(1, -2) -> max(2, -1)
        elif body_size > 100:  # 大型动物
            base_range += 3  # 原+2 -> +3
        
        # 3. 栖息地类型调整
        # 【大浪淘沙v3】大幅增加水域物种的迁徙范围
        habitat_type = getattr(species, 'habitat_type', 'terrestrial')
        if habitat_type == 'aerial':
            base_range += 4  # 原+3 -> +4
        elif habitat_type in ('marine', 'deep_sea'):
            base_range += 5  # 原+2 -> +5（水域物种大幅加成）
        elif habitat_type in ('coastal', 'amphibious'):
            base_range += 3  # 新增：两栖/海岸物种加成
        
        return max(2, min(18, base_range))  # 【大浪淘沙v3】范围从1-15调整到2-18
    
    def is_migration_on_cooldown(self, lineage_code: str, current_turn: int, cooldown_turns: int = 3) -> bool:
        """检查物种是否处于迁徙冷却期
        
        Args:
            lineage_code: 物种谱系编码
            current_turn: 当前回合
            cooldown_turns: 冷却回合数（默认3回合）
        """
        last_turn = self._migration_cooldown.get(lineage_code, -999)
        return (current_turn - last_turn) < cooldown_turns
    
    def set_migration_cooldown(self, lineage_code: str, turn: int) -> None:
        """设置物种的迁徙冷却"""
        self._migration_cooldown[lineage_code] = turn
    
    def clear_migration_cooldown(self) -> None:
        """清空迁徙冷却缓存（新游戏时调用）"""
        self._migration_cooldown.clear()
    
    def clear_all_caches(self) -> None:
        """清空所有缓存（存档切换时调用，确保数据隔离）"""
        self._migration_cooldown.clear()
        self._prey_distribution_cache.clear()
        self._species_cache.clear()
        self._tile_coords_cache.clear()
        self._species_distribution_cache.clear()
    
    def update_prey_distribution_cache(
        self, 
        all_species: list[Species],
        all_habitats: list[HabitatPopulation] | None = None
    ) -> None:
        """更新猎物分布缓存和物种分布缓存
        
        在每回合迁徙开始前调用，预计算：
        1. 各营养级在各地块的分布（用于消费者追踪猎物）
        2. 各物种在各地块的分布（用于计算种内竞争）
        
        Args:
            all_species: 所有存活物种列表
            all_habitats: 所有栖息地记录（可选，不提供则从数据库获取）
        """
        self._species_cache = [sp for sp in all_species if sp.status == "alive"]
        
        if all_habitats is None:
            all_habitats = self.repo.latest_habitats()
        
        # 构建 species_id -> Species 映射
        species_map = {sp.id: sp for sp in self._species_cache if sp.id}
        
        # 构建 species_id -> [habitats] 映射
        species_habitats: dict[int, list[HabitatPopulation]] = {}
        for habitat in all_habitats:
            if habitat.species_id not in species_habitats:
                species_habitats[habitat.species_id] = []
            species_habitats[habitat.species_id].append(habitat)
        
        # 清空缓存
        self._prey_distribution_cache.clear()
        self._species_distribution_cache.clear()
        
        for species_id, habitats in species_habitats.items():
            species = species_map.get(species_id)
            if not species:
                continue
            
            # 【新增】更新物种分布缓存（用于种内竞争计算）
            self._species_distribution_cache[species_id] = {}
            for habitat in habitats:
                self._species_distribution_cache[species_id][habitat.tile_id] = habitat.suitability
            
            # 获取营养级范围（向下取整到0.5）
            trophic_range = self._get_trophic_range(species.trophic_level)
            
            if trophic_range not in self._prey_distribution_cache:
                self._prey_distribution_cache[trophic_range] = {}
            
            for habitat in habitats:
                tile_id = habitat.tile_id
                # 使用适宜度作为生物量的代理（适宜度越高，生物量越大）
                biomass_proxy = habitat.suitability
                
                if tile_id not in self._prey_distribution_cache[trophic_range]:
                    self._prey_distribution_cache[trophic_range][tile_id] = 0.0
                self._prey_distribution_cache[trophic_range][tile_id] += biomass_proxy
        
        logger.debug(
            f"[迁徙缓存] 已更新: {len(self._prey_distribution_cache)} 个营养级分布, "
            f"{len(self._species_distribution_cache)} 个物种分布"
        )
    
    def _get_trophic_range(self, trophic_level: float) -> float:
        """将精确营养级映射到0.5间隔的范围"""
        import math
        return math.floor(trophic_level * 2) / 2.0
    
    def get_prey_tiles_for_consumer(
        self, 
        consumer_trophic_level: float,
        min_prey_density: float = 0.1
    ) -> dict[int, float]:
        """获取消费者的潜在猎物分布地块
        
        根据消费者的营养级，找出猎物（低一级营养级物种）密集的地块
        
        Args:
            consumer_trophic_level: 消费者的营养级
            min_prey_density: 最小猎物密度阈值
            
        Returns:
            {tile_id: prey_density} 猎物密集的地块及其密度
        """
        consumer_range = self._get_trophic_range(consumer_trophic_level)
        
        # 消费者的猎物是低一级的营养级
        # T3 捕食 T2, T4 捕食 T3, T5 捕食 T4
        # 杂食动物（如T2.5）可以吃T1和T2
        prey_tiles: dict[int, float] = {}
        
        # 确定猎物的营养级范围
        if consumer_range >= 2.0:
            # T2+ 消费者的猎物范围
            prey_ranges = []
            
            if consumer_range >= 5.0:
                # T5 顶级捕食者：主要吃 T4, 也可能吃 T3
                prey_ranges = [4.0, 4.5, 3.5, 3.0]
            elif consumer_range >= 4.0:
                # T4：主要吃 T3, 也可能吃 T2
                prey_ranges = [3.0, 3.5, 2.5, 2.0]
            elif consumer_range >= 3.0:
                # T3：主要吃 T2（草食动物）
                prey_ranges = [2.0, 2.5, 1.5]
            elif consumer_range >= 2.0:
                # T2 草食动物：吃 T1（生产者）
                prey_ranges = [1.0, 1.5]
            
            # 聚合所有猎物范围的分布
            for prey_range in prey_ranges:
                if prey_range in self._prey_distribution_cache:
                    for tile_id, density in self._prey_distribution_cache[prey_range].items():
                        if tile_id not in prey_tiles:
                            prey_tiles[tile_id] = 0.0
                        prey_tiles[tile_id] += density
        
        # 过滤掉密度过低的地块
        return {tid: d for tid, d in prey_tiles.items() if d >= min_prey_density}
    
    def execute_migration(
        self, 
        species: Species, 
        migration_event: MigrationEvent,
        all_tiles: list[MapTile],
        turn_index: int,
        check_cooldown: bool = True,
        cooldown_turns: int = 2
    ) -> bool:
        """实际执行迁徙（P1）- 部分迁徙版本
        
        关键改进：
        - 不会全部迁走，根据迁徙类型保留不同比例的种群
        - 压力驱动：60-80%迁走，20-40%留守
        - 资源饱和：20-40%迁走，60-80%留守
        - 种群溢出：30-50%迁走，50-70%留守
        - 【新增】迁徙冷却：防止频繁迁徙
        - 【新增】距离约束：根据物种能力限制迁徙范围
        
        Args:
            species: 要迁徙的物种
            migration_event: 迁徙建议
            all_tiles: 所有地块
            turn_index: 当前回合
            check_cooldown: 是否检查迁徙冷却（默认True）
            cooldown_turns: 冷却回合数（默认2回合）
            
        Returns:
            是否成功迁徙
        """
        if not species.id:
            logger.warning(f"[迁徙] {species.common_name} 没有ID，跳过")
            return False
        
        # 【新增】检查迁徙冷却
        if check_cooldown and self.is_migration_on_cooldown(species.lineage_code, turn_index, cooldown_turns):
            logger.debug(f"[迁徙] {species.common_name} 处于迁徙冷却期，跳过")
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
            
            # 【新增】设置迁徙冷却
            self.set_migration_cooldown(species.lineage_code, turn_index)
            
            # P3优化：计算迁徙成本（生物量损失）
            migration_cost = self._calculate_migration_cost(
                species, len(current_habitats), len(new_habitats), migration_ratio
            )
            
            # 获取迁徙范围信息
            migration_range = self._get_species_migration_range(species)
            
            logger.info(
                f"[迁徙] {species.common_name}: "
                f"保留{len(retained_habitats)}个旧地块({retention_ratio:.0%}), "
                f"迁往{len(new_habitats)}个新地块({migration_ratio:.0%}), "
                f"迁徙范围={migration_range}格, 迁徙成本={migration_cost:.1%}"
            )
            return True
        
        return False
    
    def get_symbiotic_followers(
        self, 
        migrating_species: Species,
        all_species: list[Species]
    ) -> list[Species]:
        """获取应该追随迁徙的共生物种
        
        当一个物种迁徙时，与之有共生关系的物种也应该考虑跟随
        
        Args:
            migrating_species: 正在迁徙的物种
            all_species: 所有物种列表
            
        Returns:
            应该追随迁徙的物种列表
        """
        followers = []
        migrating_code = migrating_species.lineage_code
        
        for sp in all_species:
            if sp.status != "alive" or sp.lineage_code == migrating_code:
                continue
            
            # 检查是否依赖于迁徙物种
            dependencies = getattr(sp, 'symbiotic_dependencies', [])
            if migrating_code in dependencies:
                dependency_strength = getattr(sp, 'dependency_strength', 0.0)
                # 依赖强度 > 0.5 时，追随迁徙
                if dependency_strength > 0.5:
                    followers.append(sp)
                    logger.debug(
                        f"[共生追随] {sp.common_name} 依赖于 {migrating_species.common_name} "
                        f"(强度={dependency_strength:.2f})，将追随迁徙"
                    )
        
        return followers
    
    def execute_symbiotic_following(
        self,
        leader_species: Species,
        follower_species: Species,
        leader_new_tiles: list[int],
        all_tiles: list[MapTile],
        turn_index: int
    ) -> bool:
        """执行共生物种的追随迁徙
        
        追随者会迁徙到领导者新栖息地的附近
        
        Args:
            leader_species: 领导物种（被追随的物种）
            follower_species: 追随者物种
            leader_new_tiles: 领导者的新栖息地地块ID列表
            all_tiles: 所有地块
            turn_index: 当前回合
            
        Returns:
            是否成功追随迁徙
        """
        if not follower_species.id or not leader_new_tiles:
            return False
        
        # 获取追随者当前栖息地
        all_habitats = self.repo.latest_habitats()
        follower_habitats = [h for h in all_habitats if h.species_id == follower_species.id]
        
        if not follower_habitats:
            return False
        
        # 创建一个虚拟的迁徙事件
        from ...schemas.responses import MigrationEvent
        follow_event = MigrationEvent(
            lineage_code=follower_species.lineage_code,
            origin="原栖息地",
            destination=f"追随{leader_species.common_name}的新栖息地",
            rationale=f"共生依赖：追随{leader_species.common_name}迁徙以维持共生关系"
        )
        
        # 更新地块坐标缓存
        self._update_tile_coords_cache(all_tiles)
        
        # 找到领导者新地块附近的合适地块
        leader_tile_coords = [
            self._tile_coords_cache[tid] 
            for tid in leader_new_tiles 
            if tid in self._tile_coords_cache
        ]
        
        if not leader_tile_coords:
            return False
        
        # 计算领导者新栖息地的中心
        center_x = sum(c[0] for c in leader_tile_coords) / len(leader_tile_coords)
        center_y = sum(c[1] for c in leader_tile_coords) / len(leader_tile_coords)
        
        # 筛选追随者可以去的地块（在领导者附近）
        follower_range = self._get_species_migration_range(follower_species)
        habitat_type = getattr(follower_species, 'habitat_type', 'terrestrial')
        candidate_tiles = self._filter_by_habitat_type(all_tiles, habitat_type)
        
        # 选择距离领导者新栖息地最近的地块
        nearby_tiles = []
        for tile in candidate_tiles:
            if not tile.id:
                continue
            distance = abs(tile.x - center_x) + abs(tile.y - center_y)
            if distance <= follower_range + 3:  # 给追随者一些额外范围
                suitability = self._calculate_suitability(follower_species, tile)
                if suitability > 0.3:
                    nearby_tiles.append((tile, suitability, distance))
        
        if not nearby_tiles:
            return False
        
        # 按距离排序，选择最近的几个
        nearby_tiles.sort(key=lambda x: x[2])
        target_tiles = [(t[0], t[1]) for t in nearby_tiles[:5]]
        
        # 执行迁徙（追随迁徙比例较低，30-40%）
        migration_ratio = random.uniform(0.3, 0.4)
        retention_ratio = 1.0 - migration_ratio
        
        # 保留旧栖息地
        retained = []
        for hab in follower_habitats:
            retained.append(
                HabitatPopulation(
                    tile_id=hab.tile_id,
                    species_id=follower_species.id,
                    population=0,
                    suitability=hab.suitability * max(0.2, retention_ratio),
                    turn_index=turn_index,
                )
            )
        
        # 创建新栖息地
        new_habs = []
        per_tile = migration_ratio / len(target_tiles)
        for tile, suit in target_tiles:
            new_habs.append(
                HabitatPopulation(
                    tile_id=tile.id,
                    species_id=follower_species.id,
                    population=0,
                    suitability=suit * per_tile,
                    turn_index=turn_index,
                )
            )
        
        all_new = retained + new_habs
        if all_new:
            self.repo.write_habitats(all_new)
            self.set_migration_cooldown(follower_species.lineage_code, turn_index)
            logger.info(
                f"[共生追随] {follower_species.common_name} 追随 {leader_species.common_name} "
                f"迁徙到 {len(new_habs)} 个新地块"
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
        
        【核心改进】多维度评估：
        1. 消费者追踪猎物 - T2+优先选择有猎物的地块
        2. 距离约束 - 优先选择邻近地块，根据物种能力限制迁徙范围
        3. 种内竞争 - 避开同物种密度高的地块
        4. 环境适宜度 - 基础环境匹配度
        
        策略：
        - prey_tracking: 追踪猎物，迁往有食物的地块
        - pressure_driven: 逃离当前区域，寻找低压力区（但仍需有猎物）
        - saturation_dispersal: 扩散到邻近区域
        - population_overflow: 溢出到周边空白区域
        """
        # 更新地块坐标缓存
        self._update_tile_coords_cache(all_tiles)
        
        # 获取当前地块ID集合和中心位置
        current_tile_ids = {h.tile_id for h in current_habitats}
        
        # 计算当前栖息地的中心位置（用于距离计算）
        center_x, center_y = 0.0, 0.0
        if current_habitats:
            for hab in current_habitats:
                if hab.tile_id in self._tile_coords_cache:
                    x, y = self._tile_coords_cache[hab.tile_id]
                    center_x += x * hab.suitability
                    center_y += y * hab.suitability
            total_suit = sum(h.suitability for h in current_habitats)
            if total_suit > 0:
                center_x /= total_suit
                center_y /= total_suit
        
        # 根据栖息地类型筛选候选地块
        habitat_type = getattr(species, 'habitat_type', 'terrestrial')
        candidate_tiles = self._filter_by_habitat_type(all_tiles, habitat_type)
        
        # 排除当前已占据的地块
        candidate_tiles = [t for t in candidate_tiles if t.id not in current_tile_ids]
        
        if not candidate_tiles:
            return []
        
        # 【新增】获取物种的迁徙范围限制
        migration_range = self._get_species_migration_range(species)
        
        # 【关键改进】获取消费者的猎物分布
        trophic_level = getattr(species, 'trophic_level', 1.0)
        is_consumer = trophic_level >= 2.0  # T2+ 是消费者
        
        prey_tiles: dict[int, float] = {}
        if is_consumer:
            prey_tiles = self.get_prey_tiles_for_consumer(trophic_level)
            if prey_tiles:
                logger.debug(
                    f"[迁徙-猎物追踪] {species.common_name} (T{trophic_level:.1f}) "
                    f"发现 {len(prey_tiles)} 个有猎物的地块，迁徙范围 {migration_range} 格"
                )
        
        # 【新增】获取同物种在各地块的分布（用于计算种内竞争）
        species_density_in_tiles: dict[int, float] = {}
        if species.id and species.id in self._species_distribution_cache:
            species_density_in_tiles = self._species_distribution_cache[species.id]
        
        # 计算综合评分（多维度评估）
        scored_tiles = []
        for tile in candidate_tiles:
            if not tile.id:
                continue
            
            # 【新增】计算与当前栖息地中心的距离
            tile_x, tile_y = tile.x, tile.y
            distance = abs(tile_x - center_x) + abs(tile_y - center_y)
            
            # 距离超出迁徙范围的地块，大幅降低优先级
            if distance > migration_range:
                distance_penalty = 0.2  # 超出范围仍可考虑，但大幅降低评分
            else:
                # 距离越近越好（0距离=1.0，最大距离=0.5）
                distance_penalty = 1.0 - (distance / migration_range) * 0.5
            
            base_suitability = self._calculate_suitability(species, tile)
            
            # 【大浪淘沙v3】放宽候选格适宜度门槛
            # 原0.15 -> 0.05，允许"稍差但未饱和"的地块进入候选
            if base_suitability <= 0.05:
                # 基础适宜度太低，跳过
                continue
            
            # 【新增】种内竞争惩罚（目标地块已有同物种时降低评分）
            intraspecific_penalty = 1.0
            if tile.id in species_density_in_tiles:
                existing_density = species_density_in_tiles[tile.id]
                # 已有同物种密度越高，惩罚越大
                intraspecific_penalty = max(0.3, 1.0 - existing_density * 0.5)
            
            # 【核心逻辑】消费者需要考虑猎物密度
            if is_consumer and prey_tiles:
                prey_density = prey_tiles.get(tile.id, 0.0)
                
                if prey_density <= 0.05:
                    # 没有猎物的地块
                    if "追踪" in migration_event.rationale:
                        continue  # 追踪迁徙完全跳过无猎物地块
                    else:
                        # 非追踪迁徙，大幅降低没有猎物地块的分数
                        prey_score = 0.1
                else:
                    # 有猎物的地块
                    prey_score = min(1.0, prey_density / 2.0)
                
                # 综合评分：适宜度(25%) + 猎物密度(40%) + 距离(25%) + 竞争(10%)
                combined_score = (
                    base_suitability * 0.25 + 
                    prey_score * 0.40 + 
                    distance_penalty * 0.25 +
                    intraspecific_penalty * 0.10
                )
            else:
                # 生产者或分解者：适宜度(50%) + 距离(35%) + 竞争(15%)
                combined_score = (
                    base_suitability * 0.50 + 
                    distance_penalty * 0.35 +
                    intraspecific_penalty * 0.15
                )
            
            # 【大浪淘沙v3】放宽综合评分阈值
            if combined_score > 0.08:  # 原0.15 -> 0.08
                scored_tiles.append((tile, combined_score, distance))
        
        if not scored_tiles:
            logger.warning(
                f"[迁徙] {species.common_name} 没有找到合适的目标地块 "
                f"(是否消费者: {is_consumer}, 猎物地块数: {len(prey_tiles)}, 迁徙范围: {migration_range})"
            )
            return []
        
        # 根据迁徙类型排序和选择
        rationale = migration_event.rationale
        
        if "追踪" in rationale or "猎物" in rationale:
            # 追踪猎物迁徙：选择猎物最密集的邻近地块
            if is_consumer and prey_tiles:
                # 按（猎物密度 * 距离惩罚）排序，兼顾猎物和距离
                scored_tiles.sort(
                    key=lambda x: prey_tiles.get(x[0].id, 0.0) * (1.0 - x[2] / (migration_range * 2)), 
                    reverse=True
                )
            else:
                scored_tiles.sort(key=lambda x: x[1], reverse=True)
            return [(t[0], t[1]) for t in scored_tiles[:5]]
        
        elif "死亡率" in rationale or "压力" in rationale:
            # 压力驱动：选择最适宜的邻近地块
            scored_tiles.sort(key=lambda x: x[1], reverse=True)
            return [(t[0], t[1]) for t in scored_tiles[:5]]
        
        elif "资源压力" in rationale or "竞争" in rationale:
            # 资源饱和：扩散到邻近的中等适宜度地块
            # 优先选择距离近的地块
            scored_tiles.sort(key=lambda x: (x[2], -x[1]))  # 先按距离，再按评分
            return [(t[0], t[1]) for t in scored_tiles[:8]]
        
        elif "溢出" in rationale or "增长" in rationale:
            # 种群溢出：扩散到邻近所有合适地块
            scored_tiles.sort(key=lambda x: x[2])  # 按距离排序，最近优先
            return [(t[0], t[1]) for t in scored_tiles[:10]]
        
        else:
            # 默认：选择评分最高的地块
            scored_tiles.sort(key=lambda x: x[1], reverse=True)
            return [(t[0], t[1]) for t in scored_tiles[:5]]
    
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
        """计算物种在地块的适宜度
        
        【修复v8】增加栖息地类型硬约束：
        - 水生物种（marine/deep_sea/freshwater）不能在陆地生存
        - 陆生物种（terrestrial/aerial）不能在深海生存
        """
        # === 【修复v8】首先检查栖息地类型硬约束 ===
        habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
        biome = (tile.biome or '').lower()
        
        # 判断地块类型
        is_water_tile = any(w in biome for w in ['海', '深海', '浅海', '中层', '湖', '河'])
        is_land_tile = not is_water_tile
        is_deep_sea = '深海' in biome or '深层' in biome
        is_coastal = '海岸' in biome or '浅海' in biome
        
        # 判断物种类型
        is_aquatic_species = habitat_type in {'marine', 'deep_sea', 'freshwater'}
        is_terrestrial_species = habitat_type in {'terrestrial', 'aerial'}
        is_coastal_species = habitat_type in {'coastal', 'amphibious'}
        
        # 硬约束检查
        if is_aquatic_species and is_land_tile and not is_coastal:
            # 水生物种不能在纯陆地生存
            return 0.0
        
        if is_terrestrial_species and is_deep_sea:
            # 陆生物种不能在深海生存
            return 0.0
        
        if habitat_type == 'marine' and is_land_tile:
            # 海洋物种不能在陆地
            return 0.0
        
        if habitat_type == 'deep_sea' and not is_deep_sea:
            # 深海物种只能在深海
            return 0.0 if is_land_tile else 0.3  # 非深海水域有一定适宜度
        
        # === 环境因素评分 ===
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
        
        # === 栖息地类型匹配加成/惩罚 ===
        habitat_bonus = 1.0
        
        if is_aquatic_species:
            if is_water_tile:
                habitat_bonus = 1.2  # 水生物种在水中有加成
            elif is_coastal:
                habitat_bonus = 0.5  # 海岸区域勉强可以
            else:
                habitat_bonus = 0.0  # 不应该到这里，但保险起见
        
        elif is_terrestrial_species:
            if is_land_tile:
                habitat_bonus = 1.0  # 正常
            elif is_coastal:
                habitat_bonus = 0.3  # 海岸区域降低
            else:
                habitat_bonus = 0.0  # 不应该到这里
        
        elif is_coastal_species:
            if is_coastal or (is_land_tile and tile.humidity > 0.5):
                habitat_bonus = 1.0
            elif is_water_tile:
                habitat_bonus = 0.6
            else:
                habitat_bonus = 0.4
        
        # 综合评分
        base_score = (temp_score * 0.35 + humidity_score * 0.25 + resource_score * 0.25 + 0.15)
        final_score = base_score * habitat_bonus
        
        return max(0.0, min(1.0, final_score))
    
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

    def handle_terrain_type_changes(
        self,
        species_list: Sequence[Species],
        tiles: list[MapTile],
        turn_index: int,
        dispersal_engine: 'DispersalEngine | None' = None,
    ) -> dict[str, int]:
        """处理海陆变化导致的物种强制迁徙
        
        当海洋变成陆地（或陆地变成海洋）时：
        - 海洋生物必须迁离变成陆地的地块
        - 陆生生物必须迁离变成海洋的地块
        
        使用矩阵计算寻找最佳迁徙目的地（如果提供了dispersal_engine）
        
        Returns:
            {"forced_relocations": int, "extinctions": int}
        """
        import numpy as np
        
        habitats = self.repo.latest_habitats()
        if not habitats:
            return {"forced_relocations": 0, "extinctions": 0}
        
        # 构建地块映射
        tile_map = {t.id: t for t in tiles}
        coord_to_tile = {(t.x, t.y): t for t in tiles}
        species_map = {sp.id: sp for sp in species_list if sp.id}
        
        # 更新扩散引擎的地块缓存（如果可用）
        if dispersal_engine:
            dispersal_engine.update_tile_cache(tiles)
        
        # 预计算地块的水/陆状态
        tile_is_water = {t.id: t.elevation < 0 for t in tiles}
        
        # 按物种分组栖息地
        species_habitats: dict[int, list[HabitatPopulation]] = {}
        for h in habitats:
            if h.species_id not in species_habitats:
                species_habitats[h.species_id] = []
            species_habitats[h.species_id].append(h)
        
        relocations = 0
        extinctions = 0
        updated_habitats: list[HabitatPopulation] = []
        removed_habitats: list[tuple[int, int]] = []
        
        for species_id, sp_habitats in species_habitats.items():
            species = species_map.get(species_id)
            if not species:
                continue
            
            habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
            is_aquatic = habitat_type in {'marine', 'deep_sea', 'coastal', 'freshwater'}
            
            valid_habitats = []
            invalid_habitats = []
            
            for hab in sp_habitats:
                is_water = tile_is_water.get(hab.tile_id, False)
                
                # 检查物种是否还能在这个地块生存
                if is_aquatic and not is_water:
                    invalid_habitats.append(hab)
                elif not is_aquatic and is_water and habitat_type != 'amphibious':
                    invalid_habitats.append(hab)
                else:
                    valid_habitats.append(hab)
            
            if not invalid_habitats:
                continue
            
            # 需要迁移
            total_displaced = sum(h.population for h in invalid_habitats)
            
            if valid_habitats:
                # === 使用矩阵计算分配种群 ===
                if dispersal_engine and dispersal_engine._tile_matrix is not None:
                    # 使用扩散引擎计算适宜度
                    suitability = dispersal_engine.compute_suitability_matrix(
                        species, 
                        exclude_tiles={h.tile_id for h in invalid_habitats}
                    )
                    
                    # 只考虑有效栖息地
                    valid_tile_ids = {h.tile_id for h in valid_habitats}
                    valid_indices = [
                        dispersal_engine._tile_map.get(tid, -1) 
                        for tid in valid_tile_ids
                    ]
                    valid_indices = [i for i in valid_indices if i >= 0]
                    
                    if valid_indices:
                        valid_scores = suitability[valid_indices]
                        total_score = valid_scores.sum() or 1.0
                        
                        for i, valid_hab in enumerate(valid_habitats):
                            idx = dispersal_engine._tile_map.get(valid_hab.tile_id, -1)
                            if idx >= 0 and idx in valid_indices:
                                portion = suitability[idx] / total_score
                            else:
                                portion = 1.0 / len(valid_habitats)
                            
                            added_pop = int(total_displaced * portion * 0.7)
                            updated_habitats.append(HabitatPopulation(
                                tile_id=valid_hab.tile_id,
                                species_id=species_id,
                                population=valid_hab.population + added_pop,
                                suitability=valid_hab.suitability,
                                turn_index=turn_index,
                            ))
                    else:
                        # fallback: 简单分配
                        for valid_hab in valid_habitats:
                            portion = 1.0 / len(valid_habitats)
                            added_pop = int(total_displaced * portion * 0.7)
                            updated_habitats.append(HabitatPopulation(
                                tile_id=valid_hab.tile_id,
                                species_id=species_id,
                                population=valid_hab.population + added_pop,
                                suitability=valid_hab.suitability,
                                turn_index=turn_index,
                            ))
                else:
                    # 无扩散引擎：按适宜度比例分配
                    total_valid_suit = sum(h.suitability for h in valid_habitats) or 1.0
                    for valid_hab in valid_habitats:
                        portion = valid_hab.suitability / total_valid_suit
                        added_pop = int(total_displaced * portion * 0.7)
                        updated_habitats.append(HabitatPopulation(
                            tile_id=valid_hab.tile_id,
                            species_id=species_id,
                            population=valid_hab.population + added_pop,
                            suitability=valid_hab.suitability,
                            turn_index=turn_index,
                        ))
                
                relocations += len(invalid_habitats)
                logger.info(f"[栖息地] {species.common_name} 从 {len(invalid_habitats)} 个不适宜地块迁出")
            else:
                # 没有有效栖息地，尝试寻找新栖息地
                if dispersal_engine and dispersal_engine._tile_matrix is not None:
                    # 使用矩阵计算找到最适宜的新地块
                    suitability = dispersal_engine.compute_suitability_matrix(
                        species,
                        exclude_tiles={h.tile_id for h in invalid_habitats}
                    )
                    
                    # 找到最适宜的地块
                    best_indices = np.argsort(suitability)[-5:][::-1]  # top 5
                    best_indices = [i for i in best_indices if suitability[i] > 0.3]
                    
                    if best_indices:
                        total_score = sum(suitability[i] for i in best_indices)
                        for idx in best_indices:
                            tile_id = dispersal_engine._tile_ids[idx]
                            portion = suitability[idx] / total_score
                            added_pop = int(total_displaced * portion * 0.5)  # 紧急迁徙损失更大
                            
                            updated_habitats.append(HabitatPopulation(
                                tile_id=tile_id,
                                species_id=species_id,
                                population=added_pop,
                                suitability=float(suitability[idx]),
                                turn_index=turn_index,
                            ))
                        
                        relocations += len(invalid_habitats)
                        logger.info(f"[栖息地] {species.common_name} 紧急迁徙到 {len(best_indices)} 个新地块")
                    else:
                        extinctions += 1
                        logger.warning(f"[栖息地] {species.common_name} 找不到适宜栖息地！")
                else:
                    extinctions += 1
                    logger.warning(f"[栖息地] {species.common_name} 所有栖息地变得不适宜！")
            
            # 标记需要移除的栖息地
            for inv_hab in invalid_habitats:
                removed_habitats.append((inv_hab.tile_id, species_id))
        
        # 保存更新
        if updated_habitats:
            self.repo.write_habitats(updated_habitats)
        
        # 移除不适宜的栖息地记录
        if removed_habitats:
            remove_records = []
            for tile_id, species_id in removed_habitats:
                remove_records.append(HabitatPopulation(
                    tile_id=tile_id,
                    species_id=species_id,
                    population=0,
                    suitability=0.0,
                    turn_index=turn_index,
                ))
            self.repo.write_habitats(remove_records)
        
        if relocations > 0 or extinctions > 0:
            logger.info(f"[栖息地] 海陆变化: {relocations} 次迁移, {extinctions} 个物种危机")
        
        # 【改进v4】地质变化后检查消费者的食物来源
        hunger_migrations = self.trigger_hunger_migration(
            species_list, tiles, turn_index, dispersal_engine
        )
        
        return {
            "forced_relocations": relocations, 
            "extinctions": extinctions,
            "hunger_migrations": hunger_migrations
        }
    
    def check_consumer_food_availability(
        self,
        species_list: Sequence[Species],
        tiles: list[MapTile],
    ) -> dict[int, dict]:
        """检查消费者是否有食物来源
        
        返回每个消费者的食物可用性状态：
        {species_id: {
            "has_food": bool,
            "prey_overlap_ratio": float,  # 与猎物重叠的地块比例
            "nearest_prey_distance": float,  # 最近猎物的距离
            "prey_tiles": set[int]  # 猎物所在地块
        }}
        """
        import math
        
        habitats = self.repo.latest_habitats()
        if not habitats:
            return {}
        
        # 更新地块坐标缓存
        self._update_tile_coords_cache(tiles)
        
        # 构建物种映射
        species_map = {sp.id: sp for sp in species_list if sp.id}
        
        # 按物种分组栖息地
        species_habitats: dict[int, set[int]] = {}
        for h in habitats:
            if h.species_id not in species_habitats:
                species_habitats[h.species_id] = set()
            species_habitats[h.species_id].add(h.tile_id)
        
        def _get_trophic_range(trophic: float) -> float:
            return math.floor(trophic * 2) / 2.0
        
        # 构建各营养级的分布
        trophic_tiles: dict[float, set[int]] = {}
        for species_id, tile_ids in species_habitats.items():
            sp = species_map.get(species_id)
            if sp:
                trophic = getattr(sp, 'trophic_level', 1.0) or 1.0
                trophic_range = _get_trophic_range(trophic)
                if trophic_range not in trophic_tiles:
                    trophic_tiles[trophic_range] = set()
                trophic_tiles[trophic_range].update(tile_ids)
        
        def _get_prey_tiles(consumer_trophic: float) -> set[int]:
            """根据消费者营养级获取猎物地块"""
            consumer_range = _get_trophic_range(consumer_trophic)
            prey_set: set[int] = set()
            
            if consumer_range >= 5.0:
                prey_ranges = [4.0, 4.5, 3.5, 3.0]
            elif consumer_range >= 4.0:
                prey_ranges = [3.0, 3.5, 2.5, 2.0]
            elif consumer_range >= 3.0:
                prey_ranges = [2.0, 2.5, 1.5]
            elif consumer_range >= 2.0:
                prey_ranges = [1.0, 1.5]
            else:
                prey_ranges = []
            
            for pr in prey_ranges:
                if pr in trophic_tiles:
                    prey_set.update(trophic_tiles[pr])
            return prey_set
        
        # 检查每个消费者
        result: dict[int, dict] = {}
        
        for species_id, my_tiles in species_habitats.items():
            sp = species_map.get(species_id)
            if not sp:
                continue
            
            trophic = getattr(sp, 'trophic_level', 1.0) or 1.0
            if trophic < 2.0:
                # 生产者不需要检查食物
                continue
            
            prey_tiles = _get_prey_tiles(trophic)
            
            # 计算重叠比例
            overlap = my_tiles & prey_tiles
            overlap_ratio = len(overlap) / len(my_tiles) if my_tiles else 0.0
            
            # 计算最近猎物距离
            if prey_tiles and my_tiles:
                min_distance = float('inf')
                for my_tile in my_tiles:
                    for prey_tile in prey_tiles:
                        dist = self._calculate_tile_distance(my_tile, prey_tile)
                        if dist < min_distance:
                            min_distance = dist
            else:
                min_distance = float('inf')
            
            has_food = overlap_ratio > 0.1 or (prey_tiles and min_distance <= 3)
            
            result[species_id] = {
                "has_food": has_food,
                "prey_overlap_ratio": overlap_ratio,
                "nearest_prey_distance": min_distance,
                "prey_tiles": prey_tiles,
                "my_tiles": my_tiles,
            }
            
            if not has_food and prey_tiles:
                logger.debug(
                    f"[栖息地] {sp.common_name} (T{trophic:.1f}) 缺少食物! "
                    f"重叠率={overlap_ratio:.1%}, 最近猎物距离={min_distance}"
                )
        
        return result
    
    def trigger_hunger_migration(
        self,
        species_list: Sequence[Species],
        tiles: list[MapTile],
        turn_index: int,
        dispersal_engine: 'DispersalEngine | None' = None,
    ) -> int:
        """触发饥饿迁徙：消费者向猎物方向迁移
        
        【改进v4.1】利用矩阵计算选择最佳迁徙目标
        
        当消费者的栖息地与猎物不重叠时，触发向猎物方向的迁徙
        
        Returns:
            迁徙的物种数量
        """
        import numpy as np
        
        food_status = self.check_consumer_food_availability(species_list, tiles)
        
        if not food_status:
            return 0
        
        species_map = {sp.id: sp for sp in species_list if sp.id}
        habitats = self.repo.latest_habitats()
        
        # 按物种分组栖息地
        species_habitats: dict[int, list[HabitatPopulation]] = {}
        for h in habitats:
            if h.species_id not in species_habitats:
                species_habitats[h.species_id] = []
            species_habitats[h.species_id].append(h)
        
        # 【优化】更新扩散引擎的地块缓存
        if dispersal_engine:
            dispersal_engine.update_tile_cache(tiles)
        
        migrations = 0
        updated_habitats: list[HabitatPopulation] = []
        
        for species_id, status in food_status.items():
            if status["has_food"]:
                continue  # 有食物，不需要迁徙
            
            prey_tiles = status["prey_tiles"]
            my_tiles = status["my_tiles"]
            
            if not prey_tiles:
                # 完全没有猎物（可能猎物灭绝了）
                continue
            
            sp = species_map.get(species_id)
            if not sp:
                continue
            
            sp_habitats = species_habitats.get(species_id, [])
            if not sp_habitats:
                continue
            
            # 计算总种群
            total_pop = sum(h.population for h in sp_habitats)
            
            # 迁徙比例：根据饥饿程度决定
            overlap_ratio = status["prey_overlap_ratio"]
            if overlap_ratio == 0:
                migrate_ratio = 0.6  # 完全没有重叠，迁徙60%
            elif overlap_ratio < 0.1:
                migrate_ratio = 0.4  # 少量重叠，迁徙40%
            else:
                migrate_ratio = 0.2  # 有一些重叠，迁徙20%
            
            migrate_pop = int(total_pop * migrate_ratio)
            if migrate_pop < 10:
                continue
            
            # === 【改进】使用矩阵计算选择最佳迁徙目标 ===
            target_tiles_with_scores: list[tuple[int, float]] = []
            
            if dispersal_engine and dispersal_engine._tile_matrix is not None:
                # 使用扩散引擎计算适宜度
                suitability = dispersal_engine.compute_suitability_matrix(
                    sp, 
                    exclude_tiles=my_tiles  # 排除当前栖息地
                )
                
                # 筛选有猎物的地块
                for prey_tile_id in prey_tiles:
                    idx = dispersal_engine._tile_map.get(prey_tile_id, -1)
                    if idx >= 0 and suitability[idx] > 0.2:
                        # 计算综合得分：适宜度 * 0.6 + 猎物加成 * 0.4
                        combined_score = suitability[idx] * 0.6 + 0.4
                        target_tiles_with_scores.append((prey_tile_id, combined_score))
                
                # 按综合得分排序
                target_tiles_with_scores.sort(key=lambda x: x[1], reverse=True)
                target_tiles_with_scores = target_tiles_with_scores[:8]  # 最多8个地块
                
                if target_tiles_with_scores:
                    logger.debug(
                        f"[饥饿迁徙] {sp.common_name} 使用矩阵计算，"
                        f"找到 {len(target_tiles_with_scores)} 个优质猎物地块"
                    )
            
            # 降级：使用距离计算
            if not target_tiles_with_scores:
                habitat_type = getattr(sp, 'habitat_type', 'terrestrial')
                tile_map = {t.id: t for t in tiles}
                
                for prey_tile_id in prey_tiles:
                    prey_tile = tile_map.get(prey_tile_id)
                    if not prey_tile:
                        continue
                    
                    # 检查地形是否适合
                    is_water = prey_tile.elevation < 0
                    
                    if habitat_type == "marine" and is_water:
                        pass
                    elif habitat_type == "terrestrial" and not is_water:
                        pass
                    elif habitat_type in ("amphibious", "coastal"):
                        pass
                    else:
                        continue
                    
                    # 计算到最近当前栖息地的距离
                    if my_tiles and self._tile_coords_cache:
                        min_dist = float('inf')
                        for my_tid in my_tiles:
                            d = self._calculate_tile_distance(my_tid, prey_tile_id)
                            if d < min_dist:
                                min_dist = d
                        # 距离转换为得分（越近越高）
                        score = max(0.1, 1.0 - min_dist / 20.0)
                    else:
                        score = 0.5
                    
                    target_tiles_with_scores.append((prey_tile_id, score))
                
                # 按得分排序
                target_tiles_with_scores.sort(key=lambda x: x[1], reverse=True)
                target_tiles_with_scores = target_tiles_with_scores[:5]
            
            if not target_tiles_with_scores:
                logger.debug(f"[栖息地] {sp.common_name} 没有可迁徙的猎物地块")
                continue
            
            # 从各地块按比例抽取迁徙种群
            remaining_pop = migrate_pop
            for habitat in sp_habitats:
                if remaining_pop <= 0:
                    break
                
                take = min(int(habitat.population * migrate_ratio), remaining_pop)
                if take > 0:
                    # 减少原地块种群
                    updated_habitats.append(HabitatPopulation(
                        tile_id=habitat.tile_id,
                        species_id=species_id,
                        population=habitat.population - take,
                        suitability=habitat.suitability,
                        turn_index=turn_index,
                    ))
                    remaining_pop -= take
            
            # 分配到猎物地块（按适宜度得分加权）
            actual_migrate = migrate_pop - remaining_pop
            if actual_migrate > 0:
                # 按得分加权分配
                total_score = sum(score for _, score in target_tiles_with_scores)
                if total_score <= 0:
                    total_score = 1.0
                
                distributed = 0
                for i, (tile_id, score) in enumerate(target_tiles_with_scores):
                    if i == len(target_tiles_with_scores) - 1:
                        # 最后一个地块获得剩余所有
                        tile_pop = actual_migrate - distributed
                    else:
                        tile_pop = int(actual_migrate * score / total_score)
                    
                    if tile_pop > 0:
                        # 获取该地块的适宜度
                        tile_suit = 0.6
                        if dispersal_engine and dispersal_engine._tile_map:
                            idx = dispersal_engine._tile_map.get(tile_id, -1)
                            if idx >= 0:
                                suit_matrix = dispersal_engine.compute_suitability_matrix(sp)
                                if len(suit_matrix) > idx:
                                    tile_suit = float(suit_matrix[idx])
                        
                        updated_habitats.append(HabitatPopulation(
                            tile_id=tile_id,
                            species_id=species_id,
                            population=tile_pop,
                            suitability=max(0.3, tile_suit),
                            turn_index=turn_index,
                        ))
                        distributed += tile_pop
                
                migrations += 1
                logger.info(
                    f"[栖息地] {sp.common_name} 饥饿迁徙: {actual_migrate} 个体迁移到 "
                    f"{len(target_tiles_with_scores)} 个有猎物的地块"
                )
        
        if updated_habitats:
            self.repo.write_habitats(updated_habitats)
        
        return migrations
    
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
