from __future__ import annotations

import logging
import math
import random
import time
from typing import Sequence

import numpy as np
from ...models.environment import HabitatPopulation, MapState, MapTile

logger = logging.getLogger(__name__)
from ...models.species import Species
from ...repositories.environment_repository import environment_repository
from ...repositories.species_repository import species_repository
from ...schemas.responses import (
    HabitatEntry,
    MapOverview,
    MapTileInfo,
    RiverSegment,
    VegetationInfo,
)
from .hydrology import HydrologyService
from .map_coloring import ViewMode, map_coloring_service


class MapStateManager:
    """负责初始化网格地图并记录物种在格子中的分布。"""

    def __init__(self, width: int, height: int, primordial_mode: bool = True) -> None:
        """初始化地图状态管理器
        
        Args:
            width: 地图宽度（格子数）
            height: 地图高度（格子数）
            primordial_mode: 是否使用原始地质模式（28亿年前无植物）
                - True: 陆地覆盖物为裸地/沙漠/冰川，无任何植被
                - False: 根据气候生成正常植被覆盖
        """
        self.width = width
        self.height = height
        self.repo = environment_repository
        self.primordial_mode = primordial_mode  # 原始地质模式

    def ensure_initialized(self, map_seed: int | None = None) -> None:
        logger.debug(f"[地图管理器] 确保地图列已存在...")
        self.repo.ensure_tile_columns()
        
        logger.debug(f"[地图管理器] 检查现有地图数据...")
        tiles = self.repo.list_tiles()
        logger.debug(f"[地图管理器] 发现 {len(tiles)} 个地块")
        
        if not tiles:
            logger.debug(f"[地图管理器] 生成新地图 ({self.width}×{self.height})...")
            generated = self._generate_grid(map_seed)
            logger.debug(f"[地图管理器] 生成了 {len(generated)} 个地块，正在保存...")
            self.repo.upsert_tiles(generated)
            logger.debug(f"[地图管理器] 地块保存完成")
            
        logger.debug(f"[地图管理器] 检查地图状态...")
        if not self.repo.get_state():
            logger.debug(f"[地图管理器] 创建初始地图状态...")
            self.repo.save_state(MapState(stage_name="稳定期", stage_progress=0, stage_duration=0))
            logger.debug(f"[地图管理器] 地图状态创建完成")
        else:
            logger.debug(f"[地图管理器] 地图状态已存在")

    def reclassify_terrain_by_sea_level(self, sea_level: float) -> None:
        """
        根据当前海平面重新分类所有地块的地形类型
        
        Args:
            sea_level: 当前海平面高度（米）
        """
        logger.debug(f"[地图管理器] 根据海平面 {sea_level:.1f}m 重新分类地形...")
        tiles = self.repo.list_tiles()
        
        updated_tiles = []
        terrain_changes = {"淹没": 0, "露出": 0, "保持": 0}
        
        for tile in tiles:
            relative_elevation = tile.elevation - sea_level
            old_biome = tile.biome
            
            # 根据相对海拔重新分类
            if relative_elevation < -500:
                new_biome = "深海"
            elif relative_elevation < -100:
                new_biome = "浅海"
            elif relative_elevation < 0:
                new_biome = "海岸"
            elif relative_elevation > 2500:
                new_biome = "高山"
            elif relative_elevation > 800:
                new_biome = "山地"
            elif relative_elevation > 200:
                new_biome = "丘陵"
            else:
                # 平原区域，根据气候细分
                temp = tile.temperature
                humidity = tile.humidity
                if temp > 25 and humidity > 0.6:
                    new_biome = "雨林"
                elif temp > 20 and humidity <= 0.6:
                    new_biome = "草原"
                elif temp < 0:
                    new_biome = "冻原"
                elif humidity < 0.2:
                    new_biome = "荒漠"
                else:
                    new_biome = "温带森林"
            
            # 统计变化
            was_land = old_biome not in ["深海", "浅海", "海岸", "湖泊"]
            is_land = new_biome not in ["深海", "浅海", "海岸"]
            
            if was_land and not is_land:
                terrain_changes["淹没"] += 1
            elif not was_land and is_land:
                terrain_changes["露出"] += 1
            elif old_biome != new_biome:
                terrain_changes["保持"] += 1
            
            if new_biome != old_biome:
                tile.biome = new_biome
                # 重新计算cover时使用确定性的伪随机（基于坐标）
                # 这样在相同种子下会得到相同结果
                coord_hash = (tile.x * 73856093) ^ (tile.y * 19349663)
                pseudo_rand = (coord_hash % 1000) / 1000.0
                # 传入气候参数以正确处理极地冰盖
                tile.cover = self._infer_cover(
                    new_biome, pseudo_rand,
                    temperature=tile.temperature,
                    humidity=tile.humidity,
                    elevation=tile.elevation
                )
                updated_tiles.append(tile)
        
        if updated_tiles:
            logger.debug(f"[地图管理器] 更新了 {len(updated_tiles)} 个地块: "
                  f"淹没{terrain_changes['淹没']}个, 露出{terrain_changes['露出']}个")
            self.repo.upsert_tiles(updated_tiles)
        else:
            logger.debug(f"[地图管理器] 地形无变化")
        
        # 重新分类水体（海岸判定、湖泊识别、盐度更新）
        logger.debug(f"[地图管理器] 重新分类水体...")
        all_tiles = self.repo.list_tiles()
        self._classify_water_bodies(all_tiles)
        self.repo.upsert_tiles(all_tiles)
        logger.debug(f"[地图管理器] 水体分类完成")
    
    def snapshot_habitats(self, species_list: Sequence[Species], turn_index: int, force_recalculate: bool = False) -> None:
        """记录或更新物种栖息地分布
        
        Args:
            species_list: 所有物种列表
            turn_index: 当前回合数
            force_recalculate: 是否强制重新计算分布（默认False）
                - True: 完全重新计算所有物种的栖息地分布（用于初始化）
                - False: 更新现有栖息地的种群数量，为没有栖息地的物种初始化分布
        """
        logger.debug(f"[地图管理器] 栖息地快照，回合={turn_index}, 物种数={len(species_list)}, 强制重算={force_recalculate}")
        
        tiles = self.repo.list_tiles()
        if not tiles:
            print(f"[地图管理器警告] 没有地块数据，无法记录栖息地")
            return
        
        # 非强制模式：更新现有栖息地的种群数量
        if not force_recalculate:
            self._update_habitat_populations(species_list, turn_index)
            return
        
        # 强制重算模式：用于初始化
        logger.debug(f"[地图管理器] 强制重算模式，为 {len(species_list)} 个物种初始化栖息地分布")
        habitats: list[HabitatPopulation] = []
        
        
        for species in species_list:
            # 只处理存活的物种，跳过灭绝物种
            if getattr(species, 'status', 'alive') != 'alive':
                continue
            
            # 【修复】即使 population 为 0 或未设置，也应该初始化栖息地分布
            # 这样后续回合能正确识别该物种
            total = int(species.morphology_stats.get("population", 0) or 0)
            if total <= 0:
                # 使用最小种群值以便创建栖息地记录
                total = 1000
                logger.warning(f"[地图管理器] {species.common_name} 种群为0，使用默认值1000初始化栖息地")
            
            # 强制重算模式：为所有物种计算栖息地分布
            logger.debug(f"[地图管理器] 初始化 {species.common_name} 的栖息地分布")
            
            # 根据栖息地类型筛选合适的地块
            habitat_type = getattr(species, 'habitat_type', 'terrestrial')
            suitable_tiles = self._filter_tiles_by_habitat_type(tiles, habitat_type)
            
            if not suitable_tiles:
                print(f"[地图管理器警告] {species.common_name} ({habitat_type}) 没有合适的栖息地")
                continue
            
            # 计算适宜度
            suitability = [
                (tile, self._suitability_score(species, tile)) for tile in suitable_tiles
            ]
            suitability = [item for item in suitability if item[1] > 0]
            if not suitability:
                print(f"[地图管理器警告] {species.common_name} 适宜度计算后没有合适地块")
                continue
            
            suitability.sort(key=lambda item: item[1], reverse=True)
            # 根据栖息地类型决定分布范围
            top_count = self._get_distribution_count(habitat_type)
            top_tiles = suitability[:top_count]
            score_sum = sum(score for _, score in top_tiles) or 1.0
            
            logger.debug(f"[地图管理器] {species.common_name} ({habitat_type}) 分布到 {len(top_tiles)} 个地块")
            
            # 【关键修复】按适宜度分配总生物量到多个地块
            # 而不是每个地块都分配全部生物量
            for tile, score in top_tiles:
                # ⚠️ 修复：跳过没有ID的地块或物种
                if tile.id is None or species.id is None:
                    print(f"[地图管理器警告] 地块或物种ID为None，跳过: tile.id={tile.id}, species.id={species.id}")
                    continue
                
                portion = score / score_sum  # 按适宜度比例分配
                tile_biomass = int(total * portion)  # 该地块分配的生物量
                if tile_biomass > 0:  # 只记录非零的分布
                    habitats.append(
                        HabitatPopulation(
                            tile_id=tile.id,
                            species_id=species.id,
                            population=tile_biomass,  # 这里是生物量kg，不是个体数
                            suitability=score,
                            turn_index=turn_index,
                        )
                    )
        
        if habitats:
            logger.debug(f"[地图管理器] 保存 {len(habitats)} 条栖息地记录")
            self.repo.write_habitats(habitats)
        else:
            logger.debug(f"[地图管理器] 没有栖息地记录需要保存")
    
    def _update_habitat_populations(self, species_list: Sequence[Species], turn_index: int) -> None:
        """更新现有栖息地的种群数量（非强制模式）
        
        不重新计算分布，只更新种群数量到现有栖息地。
        对于没有栖息地记录的物种，为其初始化栖息地分布。
        
        Args:
            species_list: 所有物种列表
            turn_index: 当前回合数
        """
        # 获取当前所有栖息地记录
        all_habitats = self.repo.latest_habitats()
        
        # 按物种ID分组栖息地
        species_habitats: dict[int, list[HabitatPopulation]] = {}
        for habitat in all_habitats:
            if habitat.species_id not in species_habitats:
                species_habitats[habitat.species_id] = []
            species_habitats[habitat.species_id].append(habitat)
        
        updated_habitats: list[HabitatPopulation] = []
        species_needing_init: list[Species] = []
        
        for species in species_list:
            # 跳过灭绝物种
            if getattr(species, 'status', 'alive') != 'alive':
                continue
            
            if species.id is None:
                continue
            
            total_pop = int(species.morphology_stats.get("population", 0) or 0)
            
            # 检查该物种是否有栖息地记录
            existing_habitats = species_habitats.get(species.id, [])
            
            if not existing_habitats:
                # 没有栖息地记录，需要初始化
                if total_pop > 0:
                    species_needing_init.append(species)
                continue
            
            if total_pop <= 0:
                # 种群为0，跳过更新
                continue
            
            # 计算总适宜度用于按比例分配
            total_suitability = sum(h.suitability for h in existing_habitats)
            if total_suitability <= 0:
                total_suitability = len(existing_habitats)  # 平均分配
            
            # 更新每个栖息地的种群数量
            for habitat in existing_habitats:
                if total_suitability > 0:
                    portion = habitat.suitability / total_suitability
                else:
                    portion = 1.0 / len(existing_habitats)
                
                tile_population = int(total_pop * portion)
                
                updated_habitats.append(
                    HabitatPopulation(
                        tile_id=habitat.tile_id,
                        species_id=species.id,
                        population=tile_population,
                        suitability=habitat.suitability,
                        turn_index=turn_index,
                    )
                )
        
        # 保存更新的栖息地
        if updated_habitats:
            logger.debug(f"[地图管理器] 更新 {len(updated_habitats)} 条栖息地种群数量")
            self.repo.write_habitats(updated_habitats)
        
        # 为没有栖息地的物种初始化分布
        if species_needing_init:
            logger.debug(f"[地图管理器] 为 {len(species_needing_init)} 个物种初始化栖息地")
            tiles = self.repo.list_tiles()
            self._init_habitats_for_species(species_needing_init, tiles, turn_index)
    
    def _init_habitats_for_species(self, species_list: list[Species], tiles: list[MapTile], turn_index: int) -> None:
        """为指定物种初始化栖息地分布"""
        habitats: list[HabitatPopulation] = []
        
        for species in species_list:
            if species.id is None:
                continue
            
            total = int(species.morphology_stats.get("population", 0) or 0)
            if total <= 0:
                continue
            
            habitat_type = getattr(species, 'habitat_type', 'terrestrial')
            suitable_tiles = self._filter_tiles_by_habitat_type(tiles, habitat_type)
            
            if not suitable_tiles:
                continue
            
            suitability = [
                (tile, self._suitability_score(species, tile)) for tile in suitable_tiles
            ]
            suitability = [item for item in suitability if item[1] > 0]
            if not suitability:
                continue
            
            suitability.sort(key=lambda item: item[1], reverse=True)
            top_count = self._get_distribution_count(habitat_type)
            top_tiles = suitability[:top_count]
            score_sum = sum(score for _, score in top_tiles) or 1.0
            
            for tile, score in top_tiles:
                if tile.id is None:
                    continue
                
                portion = score / score_sum
                tile_biomass = int(total * portion)
                if tile_biomass > 0:
                    habitats.append(
                        HabitatPopulation(
                            tile_id=tile.id,
                            species_id=species.id,
                            population=tile_biomass,
                            suitability=score,
                            turn_index=turn_index,
                        )
                    )
        
        if habitats:
            logger.debug(f"[地图管理器] 初始化 {len(habitats)} 条新栖息地记录")
            self.repo.write_habitats(habitats)
    
    def _filter_tiles_by_habitat_type(self, tiles: list[MapTile], habitat_type: str) -> list[MapTile]:
        """根据栖息地类型筛选合适的地块"""
        filtered = []
        
        for tile in tiles:
            biome = tile.biome.lower()
            
            if habitat_type == "marine":
                # 海洋生物：浅海、深海和海岸（不包括湖泊）
                # 【修复】添加更多海洋 biome 类型的匹配
                if any(t in biome for t in ["浅海", "深海", "海岸", "中层"]) and not getattr(tile, 'is_lake', False):
                    filtered.append(tile)
            
            elif habitat_type == "deep_sea":
                # 深海生物：深海区域
                if "深海" in biome:
                    filtered.append(tile)
            
            elif habitat_type == "coastal":
                # 海岸生物：海岸带和浅海
                if "海岸" in biome or "浅海" in biome:
                    filtered.append(tile)
            
            elif habitat_type == "freshwater":
                # 淡水生物：湖泊和河流
                if getattr(tile, 'is_lake', False):
                    filtered.append(tile)
            
            elif habitat_type == "amphibious":
                # 两栖生物：海岸、平原（靠近水体）
                if "海岸" in biome or "平原" in biome:
                    # 优先选择湿度较高的地块
                    if tile.humidity > 0.4:
                        filtered.append(tile)
            
            elif habitat_type == "terrestrial":
                # 陆生生物：陆地地块
                if "海" not in biome:
                    filtered.append(tile)
            
            elif habitat_type == "aerial":
                # 空中生物：可以在任何地块上空活动，优先开阔地带
                if "海" not in biome and "山" not in biome:
                    filtered.append(tile)
        
        return filtered if filtered else tiles  # 如果没有合适的，返回所有地块作为备选
    
    def _get_distribution_count(self, habitat_type: str) -> int:
        """根据栖息地类型决定分布地块数量"""
        # 海洋生物通常分布更广
        if habitat_type in ["marine", "deep_sea"]:
            return 10
        # 淡水生物分布较集中
        elif habitat_type == "freshwater":
            return 3
        # 陆生生物中等分布
        elif habitat_type in ["terrestrial", "amphibious"]:
            return 5
        # 海岸生物分布较集中
        elif habitat_type == "coastal":
            return 4
        # 空中生物分布广泛
        elif habitat_type == "aerial":
            return 8
        else:
            return 5

    def get_overview(
        self, 
        tile_limit: int = 3200, 
        habitat_limit: int = 3200,
        view_mode: ViewMode = "terrain",
        species_id: int | None = None,
    ) -> MapOverview:
        logger.debug(f"[地图管理器] 获取概览，地块限制={tile_limit}, 栖息地限制={habitat_limit}, 视图模式={view_mode}, 物种ID={species_id}")
        
        tiles = self.repo.list_tiles(limit=tile_limit)
        logger.debug(f"[地图管理器] 查询到 {len(tiles)} 个地块")
        
        if not tiles:
            print(f"[地图管理器警告] 没有地块数据，尝试初始化...")
            self.ensure_initialized()
            tiles = self.repo.list_tiles(limit=tile_limit)
            logger.debug(f"[地图管理器] 初始化后查询到 {len(tiles)} 个地块")
        
        # 如果指定了物种，优先查询该物种的栖息地
        species_ids = [species_id] if species_id else None
        habitats = self.repo.latest_habitats(limit=habitat_limit, species_ids=species_ids)
        logger.debug(f"[地图管理器] 查询到 {len(habitats)} 个栖息地记录")
        
        species_map = {sp.id: sp for sp in species_repository.list_species()}
        tile_by_coords = {(tile.x, tile.y): tile.id or 0 for tile in tiles}
        
        # 获取当前地图状态（海平面和温度）
        map_state = self.repo.get_state()
        sea_level = map_state.sea_level if map_state else 0.0
        global_temp = map_state.global_avg_temperature if map_state else 15.0
        turn_idx = map_state.turn_index if map_state else 0
        
        # 计算生物多样性评分（仅biodiversity模式使用）
        biodiversity_scores: dict[int, float] = {}
        if view_mode == "biodiversity":
            tile_populations: dict[int, list[int]] = {}
            for habitat in habitats:
                tile_id = habitat.tile_id
                if tile_id not in tile_populations:
                    tile_populations[tile_id] = []
                tile_populations[tile_id].append(habitat.population)
            
            # 归一化生物多样性评分
            max_diversity = 1.0
            for tile_id, populations in tile_populations.items():
                species_count = len(populations)
                total_pop = sum(populations)
                # 综合物种数量和种群规模
                diversity = (species_count * 0.7 + (total_pop / 1000000) * 0.3) if total_pop > 0 else 0
                biodiversity_scores[tile_id] = min(1.0, diversity / 10)  # 归一化到0-1
                max_diversity = max(max_diversity, biodiversity_scores[tile_id])
            
            # 二次归一化确保最高值接近1.0
            if max_diversity > 0:
                biodiversity_scores = {
                    tid: score / max_diversity 
                    for tid, score in biodiversity_scores.items()
                }
        
        # 构建地块信息（包含颜色、相对海拔、地形类型、气候带）
        tile_infos = []
        for tile in tiles:
            relative_elev = tile.elevation - sea_level
            is_lake = getattr(tile, "is_lake", False)
            terrain_type = map_coloring_service.classify_terrain_type(relative_elev, is_lake)
            
            # 推断气候带（基于纬度，0为赤道，1为极地）
            latitude = tile.y / (self.height - 1) if self.height > 1 else 0.5
            # 将 0-1 (Top-Bottom) 转换为 0-1 (Equator-Pole)
            # 假设地图 y=0 和 y=max 都是极地，中间是赤道
            # lat: 0(top/polar) -> 0.5(mid/equator) -> 1(bottom/polar)
            # distance_from_equator: abs(0 - 0.5)*2 = 1 (Polar); abs(0.5-0.5)*2 = 0 (Equator)
            dist_from_equator = abs((1 - latitude) - 0.5) * 2
            climate_zone = map_coloring_service.infer_climate_zone(dist_from_equator, max(0, relative_elev))
            
            # 预计算所有视图模式的颜色
            biodiversity_score = biodiversity_scores.get(tile.id or 0, 0.0)
            colors_dict = {
                "terrain": map_coloring_service.get_color(tile, sea_level, "terrain", biodiversity_score),
                "terrain_type": map_coloring_service.get_color(tile, sea_level, "terrain_type", biodiversity_score),
                "elevation": map_coloring_service.get_color(tile, sea_level, "elevation", biodiversity_score),
                "biodiversity": map_coloring_service.get_color(tile, sea_level, "biodiversity", biodiversity_score),
                "climate": map_coloring_service.get_color(tile, sea_level, "climate", biodiversity_score),
            }
            current_color = colors_dict.get(view_mode, colors_dict["terrain"])
            
            tile_infos.append(
                MapTileInfo(
                    id=tile.id or 0,
                    x=tile.x,
                    y=tile.y,
                    q=tile.q,
                    r=tile.r,
                    biome=tile.biome,
                    cover=tile.cover,
                    temperature=tile.temperature,
                    humidity=tile.humidity,
                    resources=tile.resources,
                    neighbors=self._neighbor_ids(tile, tile_by_coords),
                    elevation=relative_elev,
                    terrain_type=terrain_type,
                    climate_zone=climate_zone,
                    color=current_color,
                    colors=colors_dict,  # 预计算的颜色字典
                    salinity=getattr(tile, "salinity", 35.0),
                    is_lake=getattr(tile, "is_lake", False),
                )
            )
        
        habitat_entries = []
        for item in habitats:
            species = species_map.get(item.species_id)
            habitat_entries.append(
                HabitatEntry(
                    species_id=item.species_id,
                    lineage_code=species.lineage_code if species else "未知",
                    common_name=species.common_name if species else "未知物种",
                    latin_name=species.latin_name if species else "Unknown",
                    tile_id=item.tile_id,
                    population=item.population,
                    suitability=item.suitability,
                )
            )
        
        # 计算河流数据
        hydro_service = HydrologyService(self.width, self.height)
        river_network = hydro_service.calculate_flow(tiles)
        rivers_map = {}
        for tid, rdata in river_network.items():
            rivers_map[tid] = RiverSegment(
                source_id=tid,
                target_id=rdata["target_id"],
                flux=rdata["flux"]
            )

        # 计算植被数据
        vegetation_map = {}
        plant_species_ids = set()
        species_cache = {}
        
        # Pre-fetch tile objects for faster lookup inside loop
        tile_obj_map = {t.id: t for t in tiles}

        for item in habitats:
            if item.species_id not in species_cache:
                sp = species_map.get(item.species_id)
                is_plant = False
                if sp:
                    # Check if producer
                    is_plant = (sp.trophic_level == 1.0) or ("producer" in getattr(sp, 'ecological_role', ''))
                    if not is_plant and sp.capabilities and ("photosynthesis" in sp.capabilities or "光合作用" in sp.capabilities):
                        is_plant = True
                    if is_plant:
                        plant_species_ids.add(item.species_id)
                species_cache[item.species_id] = sp

            if item.species_id in plant_species_ids:
                curr = vegetation_map.get(item.tile_id, {"density": 0.0, "types": []})
                # Normalize population (heuristic: 100,000 = 1.0 density for visibility)
                # Micro-algae might have huge numbers, so we should cap or use log
                added = item.population / 500000.0
                curr["density"] += added
                
                sp = species_cache[item.species_id]
                
                # 细化植被分类逻辑
                desc = sp.description.lower() if sp else ""
                is_woody = "tree" in desc or "wood" in desc or "forest" in desc or "树" in desc
                is_herb = "grass" in desc or "herb" in desc or "草" in desc
                
                # 获取地块的环境特征
                tile = tile_obj_map.get(item.tile_id)
                
                s_type = "mixed"
                
                # Use tile info if available, otherwise fallback to simple logic
                if tile:
                    # Temperature-based classification
                    if tile.temperature > 20: # Tropical/Subtropical
                        if is_woody:
                            if tile.humidity > 0.6:
                                s_type = "rainforest" # 热带雨林
                            elif tile.humidity > 0.3:
                                s_type = "savanna" # 稀树草原 (wooded)
                            else:
                                s_type = "scrub" # 灌木丛
                        elif is_herb:
                            if tile.humidity > 0.4:
                                s_type = "savanna" # 稀树草原 (grassy)
                            else:
                                s_type = "scrub"
                        else:
                             # Default for tropical
                             s_type = "rainforest" if tile.humidity > 0.6 else "savanna"

                    elif tile.temperature > 0: # Temperate
                        if is_woody:
                            s_type = "forest" # 温带阔叶林
                        elif is_herb:
                            s_type = "grassland" # 温带草原
                        else:
                             s_type = "forest" if tile.humidity > 0.5 else "grassland"

                    else: # Cold
                        if is_woody:
                            s_type = "taiga" # 针叶林/泰加林
                        elif is_herb:
                            s_type = "tundra" # 苔原
                        else:
                            s_type = "taiga" if tile.humidity > 0.4 else "tundra"
                    
                    # Special case: Wetland
                    if tile.humidity > 0.85 and tile.elevation < 50:
                        s_type = "swamp"
                else:
                    # Fallback without tile info
                    if is_woody:
                        s_type = "forest"
                    elif is_herb:
                        s_type = "grass"

                curr["types"].append((added, s_type))
                vegetation_map[item.tile_id] = curr

        final_vegetation = {}
        for tid, data in vegetation_map.items():
            density = min(1.0, data["density"])
            if density > 0.05: # Only show if visible
                type_counts = {}
                for amt, t in data["types"]:
                    type_counts[t] = type_counts.get(t, 0.0) + amt
                v_type = max(type_counts, key=type_counts.get)
                final_vegetation[tid] = VegetationInfo(density=density, type=v_type)

        logger.debug(f"[地图管理器] 返回概览: {len(tile_infos)} 地块, {len(habitat_entries)} 栖息地, "
              f"{len(rivers_map)} 河流段, {len(final_vegetation)} 植被区, "
              f"海平面={sea_level:.1f}m, 温度={global_temp:.1f}°C, 视图={view_mode}")
        
        return MapOverview(
            tiles=tile_infos,
            habitats=habitat_entries,
            rivers=rivers_map,
            vegetation=final_vegetation,
            sea_level=sea_level,
            global_avg_temperature=global_temp,
            turn_index=turn_idx,
        )

    def _generate_grid(self, map_seed: int | None = None) -> list[MapTile]:
        tiles: list[MapTile] = []
        
        # 初始化随机种子（基于时间戳，确保每次生成不同的地图）
        import time
        if map_seed is None:
            map_seed = int(time.time() * 1000000) % 2147483647
        logger.debug(f"[地图管理器] 使用随机种子: {map_seed}")
        random.seed(map_seed)
        np.random.seed(map_seed % (2**32))  # numpy也需要设置种子
        
        # 1. 生成基于高斯大陆+噪声的全局高度图 (用于严格控制海陆比)
        # 返回的是 0-1 的 percentile 矩阵，值越高海拔越高
        height_ranks = self._generate_earth_like_height_map()
        
        # 2. 生成植被纹理噪声层 (0.0 - 1.0)，用于产生破碎的覆盖物
        # 使用随机噪声并进行轻微平滑，形成自然的斑块
        vegetation_noise = np.random.rand(self.height, self.width)
        vegetation_noise = self._smooth_noise(vegetation_noise)
        
        # 3. 定义海平面阈值 (70% 海洋, 30% 陆地)
        SEA_LEVEL_THRESHOLD = 0.7
        
        for y in range(self.height):
            latitude = 1 - (y / (self.height - 1)) if self.height > 1 else 0.5
            for x in range(self.width):
                longitude = x / (self.width - 1) if self.width > 1 else 0.5
                
                # 获取该点的相对高度排名 (0.0 - 1.0)
                rank = height_ranks[y][x]
                # 获取该点的植被噪声 (0.0 - 1.0)
                v_noise = vegetation_noise[y][x]
                
                # 4. 将排名映射为具体海拔 (米)
                elevation = self._rank_to_elevation(rank, SEA_LEVEL_THRESHOLD)
                
                # 5. 基于新海拔计算环境参数（使用改进的气候模型）
                temperature = self._temperature(latitude, elevation, longitude)
                humidity = self._humidity(latitude, longitude, elevation)
                # 资源计算需要考虑温度、海拔和湿度
                resources = self._resources(temperature, elevation, humidity, latitude)
                biome = self._infer_biome(temperature, humidity, elevation)
                # 原始地质模式下，陆地覆盖物为裸地/沙漠/冰川/冰原
                cover = self._infer_cover(
                    biome, v_noise, 
                    primordial=self.primordial_mode,
                    temperature=temperature,
                    humidity=humidity,
                    elevation=elevation
                )
                offset = x - (y - (y & 1)) // 2
                tiles.append(
                    MapTile(
                        x=x,
                        y=y,
                        q=offset,
                        r=y,
                        biome=biome,
                        elevation=elevation,
                        cover=cover,
                        temperature=temperature,
                        humidity=humidity,
                        resources=resources,
                        has_river=self._has_river(latitude, longitude),
                        pressures={},
                    )
                )
        
        # 生成内海、海湾和半岛
        self._generate_coastal_features(tiles)
        
        # 生成随机岛屿（包括岛链、群岛等）
        self._generate_random_islands(tiles)
        
        # 优化海岸附近浅海区深度
        self._adjust_coastal_depth(tiles)
        
        # 修正海岸判定和识别湖泊
        self._classify_water_bodies(tiles)
        
        # 保存地图种子到状态（用于未来重现）
        map_state = self.repo.get_state()
        if map_state:
            map_state.map_seed = map_seed
            self.repo.save_state(map_state)
            logger.debug(f"[地图管理器] 地图种子已保存: {map_seed}")
        
        return tiles

    # ========================================================================
    # 柏林噪声实现 (Perlin Noise)
    # ========================================================================
    
    def _init_perlin_gradients(self, seed: int) -> np.ndarray:
        """初始化柏林噪声的梯度向量表"""
        np.random.seed(seed)
        # 256个随机梯度向量
        angles = np.random.uniform(0, 2 * math.pi, 256)
        gradients = np.column_stack([np.cos(angles), np.sin(angles)])
        return gradients
    
    def _perlin_noise_2d(self, x: np.ndarray, y: np.ndarray, 
                         gradients: np.ndarray, wrap_x: bool = True) -> np.ndarray:
        """
        2D柏林噪声实现
        
        Args:
            x, y: 坐标网格 (已归一化到噪声空间)
            gradients: 梯度向量表
            wrap_x: X轴是否循环（地球是圆的）
        
        Returns:
            噪声值矩阵 (-1 到 1)
        """
        # 获取整数坐标
        xi = x.astype(int)
        yi = y.astype(int)
        
        # 获取小数部分
        xf = x - xi
        yf = y - yi
        
        # 平滑插值函数 (6t^5 - 15t^4 + 10t^3)
        def fade(t):
            return t * t * t * (t * (t * 6 - 15) + 10)
        
        u = fade(xf)
        v = fade(yf)
        
        # 获取四个角的梯度索引
        def get_gradient_idx(ix, iy):
            if wrap_x:
                ix = ix % 256
            else:
                ix = np.clip(ix, 0, 255)
            iy = np.clip(iy, 0, 255)
            return (ix + iy * 17) % 256
        
        # 四个角的梯度
        g00_idx = get_gradient_idx(xi, yi)
        g10_idx = get_gradient_idx(xi + 1, yi)
        g01_idx = get_gradient_idx(xi, yi + 1)
        g11_idx = get_gradient_idx(xi + 1, yi + 1)
        
        # 计算点积
        def dot_grid_gradient(grad_idx, dx, dy):
            g = gradients[grad_idx]
            return g[:, 0] * dx.flatten() + g[:, 1] * dy.flatten()
        
        n00 = dot_grid_gradient(g00_idx.flatten(), xf.flatten(), yf.flatten())
        n10 = dot_grid_gradient(g10_idx.flatten(), (xf - 1).flatten(), yf.flatten())
        n01 = dot_grid_gradient(g01_idx.flatten(), xf.flatten(), (yf - 1).flatten())
        n11 = dot_grid_gradient(g11_idx.flatten(), (xf - 1).flatten(), (yf - 1).flatten())
        
        # 双线性插值
        u_flat = u.flatten()
        v_flat = v.flatten()
        
        nx0 = n00 * (1 - u_flat) + n10 * u_flat
        nx1 = n01 * (1 - u_flat) + n11 * u_flat
        result = nx0 * (1 - v_flat) + nx1 * v_flat
        
        return result.reshape(x.shape)
    
    def _fractal_noise(self, width: int, height: int, 
                       octaves: int = 6, 
                       persistence: float = 0.5,
                       lacunarity: float = 2.0,
                       base_scale: float = 4.0,
                       seed: int = 0) -> np.ndarray:
        """
        分形噪声（多层柏林噪声叠加）
        
        Args:
            width, height: 输出尺寸
            octaves: 噪声层数（越多细节越丰富）
            persistence: 每层振幅衰减系数
            lacunarity: 每层频率放大系数
            base_scale: 基础缩放
            seed: 随机种子
        
        Returns:
            噪声矩阵 (0 到 1)
        """
        gradients = self._init_perlin_gradients(seed)
        
        # 创建坐标网格
        y_coords, x_coords = np.mgrid[0:height, 0:width].astype(float)
        
        result = np.zeros((height, width))
        amplitude = 1.0
        frequency = base_scale
        max_value = 0.0
        
        for _ in range(octaves):
            # 缩放坐标
            scaled_x = x_coords * frequency / width
            scaled_y = y_coords * frequency / height
            
            # 生成噪声层
            noise_layer = self._perlin_noise_2d(scaled_x, scaled_y, gradients, wrap_x=True)
            
            result += noise_layer * amplitude
            max_value += amplitude
            
            amplitude *= persistence
            frequency *= lacunarity
        
        # 归一化到 0-1
        result = (result / max_value + 1) / 2
        return np.clip(result, 0, 1)
    
    def _ridge_noise(self, width: int, height: int, 
                     octaves: int = 4,
                     base_scale: float = 3.0,
                     seed: int = 0) -> np.ndarray:
        """
        脊线噪声 - 用于生成山脉
        通过取柏林噪声的绝对值并反转，产生尖锐的脊线
        """
        gradients = self._init_perlin_gradients(seed)
        y_coords, x_coords = np.mgrid[0:height, 0:width].astype(float)
        
        result = np.zeros((height, width))
        amplitude = 1.0
        frequency = base_scale
        max_value = 0.0
        
        for i in range(octaves):
            scaled_x = x_coords * frequency / width
            scaled_y = y_coords * frequency / height
            
            noise_layer = self._perlin_noise_2d(scaled_x, scaled_y, gradients, wrap_x=True)
            
            # 脊线变换: 1 - |noise|
            ridge_layer = 1.0 - np.abs(noise_layer)
            # 锐化脊线
            ridge_layer = ridge_layer ** 2
            
            result += ridge_layer * amplitude
            max_value += amplitude
            
            amplitude *= 0.5
            frequency *= 2.0
        
        return result / max_value
    
    def _smooth_noise(self, noise_grid: np.ndarray, iterations: int = 1) -> np.ndarray:
        """高斯模糊平滑噪声，处理X轴循环"""
        result = noise_grid.copy()
        
        for _ in range(iterations):
            # X轴循环填充
            padded = np.pad(result, ((1, 1), (1, 1)), mode='wrap')
            padded[:, 0] = padded[:, -2]
            padded[:, -1] = padded[:, 1]
            # Y轴边缘填充
            padded[0, :] = padded[1, :]
            padded[-1, :] = padded[-2, :]
            
            # 3x3 高斯核
            kernel = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]]) / 16.0
            
            new_result = np.zeros_like(result)
            h, w = result.shape
            for y in range(h):
                for x in range(w):
                    region = padded[y:y+3, x:x+3]
                    new_result[y, x] = np.sum(region * kernel)
            
            result = new_result
        
        # 归一化
        min_val, max_val = result.min(), result.max()
        if max_val > min_val:
            result = (result - min_val) / (max_val - min_val)
        
        return result

    # ========================================================================
    # 拟真地图生成
    # ========================================================================
    
    def _generate_earth_like_height_map(self) -> np.ndarray:
        """
        生成拟真的地球高度图
        
        基于真实地球地理特征：
        1. 构造板块模拟 - 大陆不是简单的圆形，而是复杂的多边形
        2. 山脉沿板块边界分布 - 碰撞带形成山脉
        3. 大陆架和大陆坡 - 海岸线向海洋的自然过渡
        4. 岛弧和海沟 - 俯冲带特征
        5. 洋中脊 - 海底山脉
        """
        width, height = self.width, self.height
        
        # 地图尺寸比例
        # 128x40 ≈ 地球展开，每格约2.8°经度 × 4.5°纬度
        
        # ================================================================
        # 第一层：基础大陆轮廓（使用分形噪声）
        # ================================================================
        base_seed = random.randint(0, 99999)
        
        # 低频噪声决定大陆位置
        continental_noise = self._fractal_noise(
            width, height,
            octaves=4,
            persistence=0.6,
            lacunarity=2.0,
            base_scale=3.0,  # 低频 = 大结构
            seed=base_seed
        )
        
        # 中频噪声增加海岸线细节
        coastal_detail = self._fractal_noise(
            width, height,
            octaves=5,
            persistence=0.5,
            lacunarity=2.2,
            base_scale=8.0,  # 中频
            seed=base_seed + 1
        )
        
        # 高频噪声增加海岸线破碎
        fine_detail = self._fractal_noise(
            width, height,
            octaves=4,
            persistence=0.4,
            lacunarity=2.5,
            base_scale=20.0,  # 高频
            seed=base_seed + 2
        )
        
        # ================================================================
        # 第二层：纬度权重（赤道附近更多陆地，极地较少）
        # ================================================================
        y_coords = np.arange(height)
        # 纬度: 0=北极, height-1=南极, 中间=赤道
        latitude_normalized = np.abs(y_coords / (height - 1) - 0.5) * 2  # 0=赤道, 1=极地
        
        # 陆地分布权重（赤道附近陆地更多）
        # 真实地球：北半球陆地多于南半球，赤道附近有很多大陆
        land_weight = np.zeros((height, width))
        for y in range(height):
            lat = latitude_normalized[y]
            # 基础权重：赤道0.6，极地0.2
            base_weight = 0.6 - lat * 0.4
            # 北半球权重略高（模拟真实地球）
            if y < height // 2:
                base_weight += 0.1
            land_weight[y, :] = base_weight
        
        # ================================================================
        # 第三层：大陆核心（使用Voronoi思想）
        # ================================================================
        # 放置若干大陆种子点，形成大陆核心
        num_major_continents = random.randint(5, 7)  # 主要大陆
        num_minor_landmasses = random.randint(8, 12)  # 次要陆块
        
        continent_grid = np.zeros((height, width))
        
        # 主要大陆
        for i in range(num_major_continents):
            # 大陆中心位置
            cx = random.uniform(0, width)
            # 避开极地
            cy = random.uniform(height * 0.15, height * 0.85)
            
            # 大陆大小（较大）
            size_x = random.uniform(width * 0.12, width * 0.25)
            size_y = random.uniform(height * 0.15, height * 0.35)
            strength = random.uniform(1.5, 2.5)
            
            # 添加形状扭曲
            self._add_warped_continent(
                continent_grid, cx, cy, size_x, size_y, strength,
                warp_seed=base_seed + 100 + i
            )
        
        # 次要陆块（岛屿群、半岛等）
        for i in range(num_minor_landmasses):
            cx = random.uniform(0, width)
            cy = random.uniform(height * 0.1, height * 0.9)
            
            size_x = random.uniform(width * 0.04, width * 0.12)
            size_y = random.uniform(height * 0.05, height * 0.15)
            strength = random.uniform(0.8, 1.5)
            
            self._add_warped_continent(
                continent_grid, cx, cy, size_x, size_y, strength,
                warp_seed=base_seed + 200 + i
            )
        
        # ================================================================
        # 第四层：山脉系统
        # ================================================================
        mountain_noise = self._ridge_noise(
            width, height,
            octaves=4,
            base_scale=4.0,
            seed=base_seed + 300
        )
        
        # 山脉主要出现在大陆边缘和大陆内部
        # 边缘山脉（碰撞带）
        edge_mountains = self._generate_edge_mountains(continent_grid)
        
        # ================================================================
        # 第五层：海底地形（洋中脊、海沟）
        # ================================================================
        ocean_floor = self._fractal_noise(
            width, height,
            octaves=3,
            persistence=0.4,
            base_scale=5.0,
            seed=base_seed + 400
        )
        
        # 洋中脊（海底山脉）
        mid_ocean_ridge = self._generate_mid_ocean_ridges(width, height, base_seed + 500)
        
        # ================================================================
        # 组合所有层
        # ================================================================
        grid = np.zeros((height, width))
        
        # 大陆基础
        grid += continent_grid * 1.0
        
        # 纬度权重调制
        grid *= (land_weight * 0.5 + 0.5)
        
        # 叠加分形噪声
        grid += continental_noise * 0.4
        grid += coastal_detail * 0.15
        grid += fine_detail * 0.05
        
        # 添加山脉（仅在陆地区域）
        land_mask = grid > 0.5
        grid += (mountain_noise * 0.3 + edge_mountains * 0.4) * land_mask
        
        # 海底地形（仅在海洋区域）
        ocean_mask = ~land_mask
        grid += (ocean_floor * 0.15 + mid_ocean_ridge * 0.1) * ocean_mask
        
        # ================================================================
        # 转换为百分位排名（控制海陆比例）
        # ================================================================
        flat = grid.flatten()
        ranks = np.argsort(np.argsort(flat))
        rank_grid = (ranks / len(flat)).reshape(height, width)
        
        return rank_grid
    
    def _add_warped_continent(self, grid: np.ndarray, 
                              cx: float, cy: float,
                              size_x: float, size_y: float,
                              strength: float,
                              warp_seed: int) -> None:
        """
        添加一个形状扭曲的大陆块
        使用域扭曲让大陆形状不规则
        """
        height, width = grid.shape
        y_coords, x_coords = np.mgrid[0:height, 0:width].astype(float)
        
        # 域扭曲噪声
        warp_noise_x = self._fractal_noise(width, height, octaves=3, base_scale=4.0, seed=warp_seed)
        warp_noise_y = self._fractal_noise(width, height, octaves=3, base_scale=4.0, seed=warp_seed + 1)
        
        # 扭曲幅度
        warp_amp = min(size_x, size_y) * 0.5
        
        # 扭曲后的坐标
        warped_x = x_coords + (warp_noise_x - 0.5) * warp_amp
        warped_y = y_coords + (warp_noise_y - 0.5) * warp_amp
        
        # 计算到大陆中心的距离（处理X轴循环）
        dx = warped_x - cx
        # X轴环形距离
        dx = np.where(np.abs(dx) > width / 2, dx - np.sign(dx) * width, dx)
        dy = warped_y - cy
        
        # 椭圆形衰减
        dist_sq = (dx / size_x) ** 2 + (dy / size_y) ** 2
        
        # 高斯衰减
        continent_blob = strength * np.exp(-dist_sq * 2)
        
        grid += continent_blob
    
    def _generate_edge_mountains(self, continent_grid: np.ndarray) -> np.ndarray:
        """
        在大陆边缘生成山脉（模拟板块碰撞）
        """
        height, width = continent_grid.shape
        
        # 计算梯度（边缘检测）
        # X方向梯度（处理循环）
        padded = np.pad(continent_grid, ((0, 0), (1, 1)), mode='wrap')
        grad_x = padded[:, 2:] - padded[:, :-2]
        
        # Y方向梯度
        padded_y = np.pad(continent_grid, ((1, 1), (0, 0)), mode='edge')
        grad_y = padded_y[2:, :] - padded_y[:-2, :]
        
        # 梯度幅值
        edge_strength = np.sqrt(grad_x ** 2 + grad_y ** 2)
        
        # 只保留强边缘
        edge_strength = np.clip(edge_strength * 3, 0, 1)
        
        # 添加一些随机性
        noise = np.random.rand(height, width) * 0.3
        edge_strength = edge_strength * (0.7 + noise)
        
        return edge_strength
    
    def _generate_mid_ocean_ridges(self, width: int, height: int, seed: int) -> np.ndarray:
        """
        生成洋中脊（海底山脉）
        洋中脊通常呈南北走向，蜿蜒穿过大洋
        """
        np.random.seed(seed)
        ridges = np.zeros((height, width))
        
        # 生成2-3条洋中脊
        num_ridges = random.randint(2, 3)
        
        for _ in range(num_ridges):
            # 起始位置
            x = random.uniform(0, width)
            
            # 沿Y轴蜿蜒
            for y in range(height):
                # 添加水平摆动
                x += random.uniform(-1.5, 1.5)
                x = x % width  # 循环
                
                # 在脊线附近添加凸起
                for dx in range(-3, 4):
                    px = int(x + dx) % width
                    dist = abs(dx)
                    ridges[y, px] += max(0, 1 - dist * 0.3)
        
        # 平滑
        ridges = self._smooth_noise(ridges, iterations=1)
        
        return ridges

    def _rank_to_elevation(self, rank: float, sea_threshold: float) -> float:
        """
        将 0-1 的排名映射到真实海拔 (米)
        """
        if rank < sea_threshold:
            # === 海洋 (0% - 70%) ===
            # 归一化深度 (0.0 - 1.0，越接近1越浅)
            ocean_progress = rank / sea_threshold
            
            # 分布设计：
            # 0.00 - 0.10: 海沟 (-11000 ~ -6000) - 占海洋约10%
            # 0.10 - 0.80: 深海平原/盆地 (-6000 ~ -200) - 占海洋约70%
            # 0.80 - 1.00: 大陆架/浅海 (-200 ~ 0) - 占海洋约20%
            
            if ocean_progress < 0.1:
                # 海沟
                p = ocean_progress / 0.1
                return -11000 + p * 5000  # -11000 -> -6000
            elif ocean_progress < 0.8:
                # 深海
                p = (ocean_progress - 0.1) / 0.7
                return -6000 + p * 5800   # -6000 -> -200
            else:
                # 浅海
                p = (ocean_progress - 0.8) / 0.2
                return -200 + p * 200     # -200 -> 0
        else:
            # === 陆地 (70% - 100%) ===
            # 归一化高度 (0.0 - 1.0)
            land_progress = (rank - sea_threshold) / (1 - sea_threshold)
            
            # 分布设计：
            # 0.00 - 0.45: 平原 (0 - 200m) - 占陆地45%
            # 0.45 - 0.75: 丘陵 (200 - 800m) - 占陆地30%
            # 0.75 - 0.92: 山地 (800 - 2500m) - 占陆地17%
            # 0.92 - 1.00: 高山 (2500 - 6000m) - 占陆地8%
            
            if land_progress < 0.45:
                return land_progress / 0.45 * 200
            elif land_progress < 0.75:
                return 200 + (land_progress - 0.45) / 0.30 * 600
            elif land_progress < 0.92:
                return 800 + (land_progress - 0.75) / 0.17 * 1700
            else:
                return 2500 + (land_progress - 0.92) / 0.08 * 3500
    
    def _generate_random_islands(self, tiles: list[MapTile]) -> None:
        """
        在海洋中生成丰富的岛屿系统
        
        包括：
        1. 岛链/岛弧 - 火山岛弧（如日本、菲律宾）
        2. 群岛 - 分散的岛群（如印尼、加勒比）
        3. 大陆架岛屿 - 靠近大陆的岛（如英国、台湾）
        4. 海山岛屿 - 孤立的海底火山（如夏威夷）
        5. 环礁 - 低矮的珊瑚岛
        """
        tile_map = {(tile.x, tile.y): tile for tile in tiles}
        
        # 分类海洋区域
        deep_ocean = [t for t in tiles if t.elevation < -2000]  # 深海
        mid_ocean = [t for t in tiles if -2000 <= t.elevation < -500]  # 中层海
        shallow_ocean = [t for t in tiles if -500 <= t.elevation < -50]  # 浅海/大陆架
        
        if len(deep_ocean) < 10 and len(mid_ocean) < 10:
            logger.debug("[地图管理器] 海洋地块不足，跳过岛屿生成")
            return
        
        total_islands = 0
        
        # ================================================================
        # 1. 岛链/岛弧（模拟太平洋火山弧）
        # ================================================================
        num_arcs = random.randint(2, 4)
        for _ in range(num_arcs):
            if len(mid_ocean) < 20:
                continue
            
            # 选择弧的起点（中层海域）
            start_tile = random.choice(mid_ocean)
            arc_length = random.randint(6, 15)  # 弧长度
            arc_direction = random.uniform(0, 2 * math.pi)  # 弧方向
            arc_curvature = random.uniform(-0.15, 0.15)  # 弯曲度
            
            # 沿弧生成岛屿
            current_x = float(start_tile.x)
            current_y = float(start_tile.y)
            
            for i in range(arc_length):
                # 每隔1-3格放置一个岛
                step = random.uniform(1.5, 3.0)
                arc_direction += arc_curvature  # 逐渐弯曲
                
                current_x += math.cos(arc_direction) * step
                current_y += math.sin(arc_direction) * step
                
                # 处理X循环
                current_x = current_x % self.width
                
                # 检查Y边界
                if current_y < 2 or current_y >= self.height - 2:
                    break
                
                # 在该位置创建火山岛
                island_size = random.randint(1, 4)
                island_height = random.uniform(200, 1500)  # 火山岛较高
                self._create_island_at(
                    tile_map, int(current_x), int(current_y),
                    island_size, island_height, is_volcanic=True
                )
                total_islands += 1
        
        # ================================================================
        # 2. 群岛（大片散落的岛群）
        # ================================================================
        num_archipelagos = random.randint(2, 4)
        for _ in range(num_archipelagos):
            ocean_pool = mid_ocean if len(mid_ocean) > 30 else deep_ocean
            if len(ocean_pool) < 30:
                continue
            
            # 群岛中心
            center_tile = random.choice(ocean_pool)
            archipelago_radius = random.randint(8, 15)
            num_islands_in_group = random.randint(5, 12)
            
            for _ in range(num_islands_in_group):
                # 在中心周围随机位置
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(2, archipelago_radius)
                
                island_x = int(center_tile.x + math.cos(angle) * distance) % self.width
                island_y = int(center_tile.y + math.sin(angle) * distance)
                
                if 2 <= island_y < self.height - 2:
                    island_size = random.randint(1, 5)
                    island_height = random.uniform(50, 600)
                    self._create_island_at(
                        tile_map, island_x, island_y,
                        island_size, island_height
                    )
                    total_islands += 1
        
        # ================================================================
        # 3. 大陆架岛屿（靠近陆地）
        # ================================================================
        if shallow_ocean:
            num_shelf_islands = random.randint(8, 15)
            shelf_candidates = random.sample(
                shallow_ocean, 
                min(num_shelf_islands * 2, len(shallow_ocean))
            )
            
            for tile in shelf_candidates[:num_shelf_islands]:
                # 检查是否靠近陆地
                has_nearby_land = False
                for dx, dy in self._get_neighbor_offsets(tile.x, tile.y):
                    neighbor = tile_map.get((dx, dy))
                    if neighbor and neighbor.elevation >= 0:
                        has_nearby_land = True
                        break
                
                if has_nearby_land or random.random() < 0.3:
                    island_size = random.randint(2, 8)
                    island_height = random.uniform(20, 300)
                    self._create_island_at(
                        tile_map, tile.x, tile.y,
                        island_size, island_height
                    )
                    total_islands += 1
        
        # ================================================================
        # 4. 海山岛屿（孤立的深海火山，如夏威夷）
        # ================================================================
        if deep_ocean:
            num_seamounts = random.randint(3, 8)
            seamount_candidates = random.sample(
                deep_ocean,
                min(num_seamounts * 2, len(deep_ocean))
            )
            
            for tile in seamount_candidates[:num_seamounts]:
                island_size = random.randint(1, 3)
                island_height = random.uniform(500, 2000)  # 高大的火山
                self._create_island_at(
                    tile_map, tile.x, tile.y,
                    island_size, island_height, is_volcanic=True
                )
                total_islands += 1
        
        # ================================================================
        # 5. 环礁/低矮珊瑚岛（热带浅海）
        # ================================================================
        # 只在热带区域（纬度0.35-0.65）
        tropical_shallow = [
            t for t in shallow_ocean 
            if 0.35 < (1 - t.y / (self.height - 1)) < 0.65
        ]
        
        if tropical_shallow:
            num_atolls = random.randint(5, 10)
            atoll_candidates = random.sample(
                tropical_shallow,
                min(num_atolls * 2, len(tropical_shallow))
            )
            
            for tile in atoll_candidates[:num_atolls]:
                # 环礁很低（几米高）
                island_size = random.randint(1, 2)
                island_height = random.uniform(2, 10)
                self._create_island_at(
                    tile_map, tile.x, tile.y,
                    island_size, island_height, is_atoll=True
                )
                total_islands += 1
        
        logger.debug(f"[地图管理器] 生成了 {total_islands} 个岛屿")
    
    def _create_island_at(self, tile_map: dict, x: int, y: int,
                          size: int, base_elevation: float,
                          is_volcanic: bool = False,
                          is_atoll: bool = False) -> None:
        """
        在指定位置创建一个岛屿
        
        Args:
            tile_map: 坐标到地块的映射
            x, y: 岛屿中心坐标
            size: 岛屿大小（格数）
            base_elevation: 基础海拔
            is_volcanic: 是否是火山岛
            is_atoll: 是否是环礁
        """
        visited = set()
        queue = [(x, y, 0)]
        visited.add((x, y))
        
        while queue and len(visited) <= size:
            cx, cy, dist = queue.pop(0)
            
            tile = tile_map.get((cx, cy))
            if tile and tile.elevation < 0:
                # 计算海拔
                if is_atoll:
                    # 环礁：中心略低（泻湖），边缘略高
                    elev = base_elevation * (0.5 + dist * 0.2)
                elif is_volcanic:
                    # 火山岛：中心最高，陡峭下降
                    decay = 1.0 - (dist / max(1, size)) ** 0.5
                    elev = base_elevation * max(0.1, decay)
                else:
                    # 普通岛：平缓下降
                    decay = 1.0 - (dist / max(1, size)) * 0.6
                    elev = base_elevation * max(0.1, decay)
                
                tile.elevation = elev
                
                # 重新计算环境参数
                latitude = 1 - (tile.y / (self.height - 1)) if self.height > 1 else 0.5
                longitude = tile.x / (self.width - 1) if self.width > 1 else 0.5
                tile.temperature = self._temperature(latitude, tile.elevation, longitude)
                
                # 岛屿通常比较湿润
                island_humidity_bonus = 0.15 if not is_atoll else 0.05
                tile.humidity = min(0.95, tile.humidity + island_humidity_bonus)
                
                tile.resources = self._resources(
                    tile.temperature, tile.elevation, tile.humidity, latitude
                )
                tile.biome = self._infer_biome(tile.temperature, tile.humidity, tile.elevation)
                
                tile_noise = random.uniform(0.4, 0.9)
                tile.cover = self._infer_cover(
                    tile.biome, tile_noise,
                    primordial=self.primordial_mode,
                    temperature=tile.temperature,
                    humidity=tile.humidity,
                    elevation=tile.elevation
                )
                
                # 扩展到相邻
                if len(visited) < size:
                    neighbors = self._get_neighbor_offsets(cx, cy)
                    random.shuffle(neighbors)
                    for nx, ny in neighbors:
                        if (nx, ny) not in visited:
                            neighbor = tile_map.get((nx, ny))
                            if neighbor and neighbor.elevation < 0:
                                visited.add((nx, ny))
                                queue.append((nx, ny, dist + 1))
    
    def _generate_coastal_features(self, tiles: list[MapTile]) -> None:
        """
        生成海岸特征：内海、海湾和半岛
        
        使海岸线更加丰富多变，而不是简单的直线
        """
        tile_map = {(tile.x, tile.y): tile for tile in tiles}
        
        # 找出所有海岸线地块（陆地且邻近海洋）
        coastal_land = []
        coastal_ocean = []
        
        for tile in tiles:
            neighbors = self._get_neighbor_offsets(tile.x, tile.y)
            has_land_neighbor = False
            has_ocean_neighbor = False
            
            for nx, ny in neighbors:
                neighbor = tile_map.get((nx, ny))
                if neighbor:
                    if neighbor.elevation >= 0:
                        has_land_neighbor = True
                    else:
                        has_ocean_neighbor = True
            
            if tile.elevation >= 0 and has_ocean_neighbor:
                coastal_land.append(tile)
            elif tile.elevation < 0 and has_land_neighbor:
                coastal_ocean.append(tile)
        
        if not coastal_land or not coastal_ocean:
            return
        
        features_created = {"bays": 0, "peninsulas": 0, "inland_seas": 0}
        
        # ================================================================
        # 1. 生成海湾（将部分沿海陆地变成海洋）
        # ================================================================
        num_bays = random.randint(3, 8)
        bay_candidates = random.sample(coastal_land, min(num_bays * 2, len(coastal_land)))
        
        for tile in bay_candidates[:num_bays]:
            # 海湾深入陆地的深度
            bay_depth = random.randint(2, 5)
            bay_width = random.randint(1, 3)
            
            # 找一个向内陆的方向
            inland_dir = self._find_inland_direction(tile, tile_map)
            if inland_dir is None:
                continue
            
            # 沿方向创建海湾
            self._create_bay(tile_map, tile.x, tile.y, inland_dir, bay_depth, bay_width)
            features_created["bays"] += 1
        
        # ================================================================
        # 2. 生成半岛（将部分沿海海洋变成陆地）
        # ================================================================
        num_peninsulas = random.randint(2, 5)
        peninsula_candidates = random.sample(
            coastal_ocean, 
            min(num_peninsulas * 2, len(coastal_ocean))
        )
        
        for tile in peninsula_candidates[:num_peninsulas]:
            # 半岛延伸入海的长度
            peninsula_length = random.randint(3, 7)
            peninsula_width = random.randint(1, 2)
            
            # 找一个向海洋的方向
            ocean_dir = self._find_ocean_direction(tile, tile_map)
            if ocean_dir is None:
                continue
            
            # 沿方向创建半岛
            self._create_peninsula(
                tile_map, tile.x, tile.y, ocean_dir, 
                peninsula_length, peninsula_width
            )
            features_created["peninsulas"] += 1
        
        # ================================================================
        # 3. 生成内海/湖泊（在大陆内部创建水域）
        # ================================================================
        # 找出深入内陆的陆地（距海较远）
        inland_land = [
            t for t in tiles 
            if t.elevation >= 0 and t not in coastal_land
        ]
        
        if len(inland_land) > 50:
            num_inland_seas = random.randint(1, 3)
            inland_candidates = random.sample(
                inland_land,
                min(num_inland_seas * 3, len(inland_land))
            )
            
            for tile in inland_candidates[:num_inland_seas]:
                # 内海大小
                sea_size = random.randint(5, 15)
                
                # 检查周围是否有足够空间
                neighbors = self._get_neighbor_offsets(tile.x, tile.y)
                land_count = sum(
                    1 for nx, ny in neighbors 
                    if tile_map.get((nx, ny)) and tile_map[(nx, ny)].elevation >= 0
                )
                
                if land_count >= 4:  # 确保不在海岸附近
                    self._create_inland_sea(tile_map, tile.x, tile.y, sea_size)
                    features_created["inland_seas"] += 1
        
        logger.debug(
            f"[地图管理器] 生成海岸特征: "
            f"{features_created['bays']}个海湾, "
            f"{features_created['peninsulas']}个半岛, "
            f"{features_created['inland_seas']}个内海"
        )
    
    def _find_inland_direction(self, tile: MapTile, 
                               tile_map: dict) -> tuple[float, float] | None:
        """找到一个向内陆的方向"""
        neighbors = self._get_neighbor_offsets(tile.x, tile.y)
        land_neighbors = []
        
        for nx, ny in neighbors:
            neighbor = tile_map.get((nx, ny))
            if neighbor and neighbor.elevation >= 0:
                # 计算方向向量
                dx = nx - tile.x
                # 处理X循环
                if abs(dx) > self.width / 2:
                    dx = -dx
                dy = ny - tile.y
                land_neighbors.append((dx, dy))
        
        if not land_neighbors:
            return None
        
        # 返回平均方向（指向内陆）
        avg_dx = sum(d[0] for d in land_neighbors) / len(land_neighbors)
        avg_dy = sum(d[1] for d in land_neighbors) / len(land_neighbors)
        
        # 归一化
        length = math.sqrt(avg_dx ** 2 + avg_dy ** 2)
        if length < 0.1:
            return None
        
        return (avg_dx / length, avg_dy / length)
    
    def _find_ocean_direction(self, tile: MapTile,
                              tile_map: dict) -> tuple[float, float] | None:
        """找到一个向海洋的方向"""
        neighbors = self._get_neighbor_offsets(tile.x, tile.y)
        ocean_neighbors = []
        
        for nx, ny in neighbors:
            neighbor = tile_map.get((nx, ny))
            if neighbor and neighbor.elevation < 0:
                dx = nx - tile.x
                if abs(dx) > self.width / 2:
                    dx = -dx
                dy = ny - tile.y
                ocean_neighbors.append((dx, dy))
        
        if not ocean_neighbors:
            return None
        
        avg_dx = sum(d[0] for d in ocean_neighbors) / len(ocean_neighbors)
        avg_dy = sum(d[1] for d in ocean_neighbors) / len(ocean_neighbors)
        
        length = math.sqrt(avg_dx ** 2 + avg_dy ** 2)
        if length < 0.1:
            return None
        
        return (avg_dx / length, avg_dy / length)
    
    def _create_bay(self, tile_map: dict, start_x: int, start_y: int,
                    direction: tuple[float, float], depth: int, width: int) -> None:
        """创建一个海湾（将陆地变成海洋）"""
        dx, dy = direction
        
        for step in range(depth):
            # 当前中心点
            cx = int(start_x + dx * step) % self.width
            cy = int(start_y + dy * step)
            
            if cy < 0 or cy >= self.height:
                break
            
            # 创建宽度
            for w in range(-width, width + 1):
                # 垂直于方向的偏移
                perp_x = int(-dy * w)
                perp_y = int(dx * w)
                
                px = (cx + perp_x) % self.width
                py = cy + perp_y
                
                if 0 <= py < self.height:
                    tile = tile_map.get((px, py))
                    if tile and tile.elevation >= 0:
                        # 将陆地变成浅海
                        tile.elevation = random.uniform(-20, -5)
                        
                        # 重新计算属性
                        lat = 1 - (tile.y / (self.height - 1))
                        lon = tile.x / (self.width - 1)
                        tile.temperature = self._temperature(lat, tile.elevation, lon)
                        tile.biome = "浅海"
                        tile.cover = "水域"
    
    def _create_peninsula(self, tile_map: dict, start_x: int, start_y: int,
                          direction: tuple[float, float], length: int, width: int) -> None:
        """创建一个半岛（将海洋变成陆地）"""
        dx, dy = direction
        
        for step in range(length):
            cx = int(start_x + dx * step) % self.width
            cy = int(start_y + dy * step)
            
            if cy < 0 or cy >= self.height:
                break
            
            # 半岛逐渐变窄
            current_width = max(1, width - step // 3)
            
            for w in range(-current_width, current_width + 1):
                perp_x = int(-dy * w)
                perp_y = int(dx * w)
                
                px = (cx + perp_x) % self.width
                py = cy + perp_y
                
                if 0 <= py < self.height:
                    tile = tile_map.get((px, py))
                    if tile and tile.elevation < 0:
                        # 将海洋变成低地
                        tile.elevation = random.uniform(10, 100)
                        
                        lat = 1 - (tile.y / (self.height - 1))
                        lon = tile.x / (self.width - 1)
                        tile.temperature = self._temperature(lat, tile.elevation, lon)
                        tile.humidity = self._humidity(lat, lon, tile.elevation)
                        tile.resources = self._resources(
                            tile.temperature, tile.elevation, tile.humidity, lat
                        )
                        tile.biome = self._infer_biome(
                            tile.temperature, tile.humidity, tile.elevation
                        )
                        tile.cover = self._infer_cover(
                            tile.biome, random.random(),
                            primordial=self.primordial_mode,
                            temperature=tile.temperature,
                            humidity=tile.humidity,
                            elevation=tile.elevation
                        )
    
    def _create_inland_sea(self, tile_map: dict, center_x: int, center_y: int,
                           size: int) -> None:
        """创建内海/大湖"""
        visited = set()
        queue = [(center_x, center_y, 0)]
        visited.add((center_x, center_y))
        
        while queue and len(visited) < size:
            x, y, dist = queue.pop(0)
            
            tile = tile_map.get((x, y))
            if tile and tile.elevation >= 0:
                # 变成湖泊
                tile.elevation = random.uniform(-30, -5)
                tile.biome = "湖泊"
                tile.cover = "水域"
                tile.is_lake = True
                tile.salinity = 0.5  # 淡水
                
                lat = 1 - (tile.y / (self.height - 1))
                lon = tile.x / (self.width - 1)
                tile.temperature = self._temperature(lat, tile.elevation, lon)
                
                # 扩展
                if len(visited) < size:
                    neighbors = self._get_neighbor_offsets(x, y)
                    random.shuffle(neighbors)
                    for nx, ny in neighbors:
                        if (nx, ny) not in visited:
                            neighbor = tile_map.get((nx, ny))
                            # 优先扩展到低海拔陆地
                            if neighbor and neighbor.elevation >= 0:
                                if neighbor.elevation < 300 or random.random() < 0.3:
                                    visited.add((nx, ny))
                                    queue.append((nx, ny, dist + 1))
    
    def _adjust_coastal_depth(self, tiles: list[MapTile]) -> None:
        """
        调整海岸附近海域深度，使其相对较浅（-1m到-30m）
        符合真实海岸坡度
        """
        # 构建坐标到地块的映射
        tile_map = {(tile.x, tile.y): tile for tile in tiles}
        
        # 找出所有陆地地块
        land_tiles = [(tile.x, tile.y) for tile in tiles if tile.elevation >= 0]
        
        # 对每个海洋地块，计算距最近陆地的距离
        for tile in tiles:
            if tile.elevation < 0:  # 仅处理海洋
                min_distance = float('inf')
                
                # 搜索最近的陆地（简化版，只检查10格内）
                for lx, ly in land_tiles:
                    # 简化距离计算（曼哈顿距离的近似）
                    dx = min(abs(tile.x - lx), self.width - abs(tile.x - lx))  # 考虑循环
                    dy = abs(tile.y - ly)
                    distance = dx + dy
                    
                    if distance < min_distance:
                        min_distance = distance
                        if distance <= 1:  # 优化：找到1格内的就停止
                            break
                
                # 根据距离调整深度
                if min_distance <= 4:
                    # 距陆地4格内：逐渐加深
                    if min_distance == 1:
                        # 1格内：-1m到-30m（海岸浅海）
                        # 使用确定性的伪随机（基于坐标），这样相同种子会得到相同结果
                        coord_hash = (tile.x * 73856093) ^ (tile.y * 19349663)
                        pseudo_rand = (coord_hash % 1000) / 1000.0
                        tile.elevation = -1 - pseudo_rand * 29  # -1到-30m
                    elif min_distance == 2:
                        # 2格内：-30m到-100m
                        coord_hash = (tile.x * 73856093) ^ (tile.y * 19349663)
                        pseudo_rand = (coord_hash % 1000) / 1000.0
                        tile.elevation = -30 - pseudo_rand * 70  # -30到-100m
                    elif min_distance == 3:
                        # 3格内：-100m到-300m
                        tile.elevation = max(-300, min(-100, tile.elevation * 0.4))
                    elif min_distance == 4:
                        # 4格内：-300m到-600m
                        tile.elevation = max(-600, min(-300, tile.elevation * 0.5))
    
    def _classify_water_bodies(self, tiles: list[MapTile]) -> None:
        """
        分类水体：识别海岸、湖泊，并设置盐度
        - 海岸：任何海域（elevation<0）如果邻近陆地（一格之内）
        - 湖泊：被陆地完全包围的水域（相对海拔<0）
        - 盐度：海水35‰，淡水湖0-0.5‰，咸水湖5-35‰
        """
        # 构建坐标到地块的映射
        tile_map = {(tile.x, tile.y): tile for tile in tiles}
        
        # 第一遍：识别海岸
        for tile in tiles:
            # 只处理水域（初始化时相对海拔 = 固定海拔）
            if tile.elevation < 0:
                # 检查是否邻近陆地（一格之内）
                has_land_neighbor = False
                for dx, dy in self._get_neighbor_offsets(tile.x, tile.y):
                    neighbor = tile_map.get((dx, dy))
                    if neighbor and neighbor.elevation >= 0:
                        has_land_neighbor = True
                        break
                
                # 海岸判定：邻近陆地的海域
                if has_land_neighbor:
                    if tile.elevation >= -200:
                        tile.biome = "海岸"
                    else:
                        tile.biome = "浅海"  # 深度超过200m但邻近陆地
                else:
                    # 远离陆地，按深度分类
                    if tile.elevation < -500:
                        tile.biome = "深海"
                    else:
                        tile.biome = "浅海"
                
                # 初始盐度：海水默认35‰
                tile.salinity = 35.0
                tile.cover = "水域"
        
        # 第二遍：识别湖泊（被陆地完全包围的水域）
        for tile in tiles:
            if tile.elevation < 0:
                # 使用广度优先搜索检查是否能到达地图边界
                if self._is_landlocked(tile, tile_map):
                    tile.is_lake = True
                    tile.biome = "湖泊"
                    # 湖泊盐度根据位置和气候推断
                    # 干旱区域湖泊盐度高（咸水湖），湿润区域盐度低（淡水湖）
                    if tile.humidity < 0.3:
                        tile.salinity = 15.0 + (0.3 - tile.humidity) * 50  # 5-35‰咸水湖
                    else:
                        tile.salinity = 0.5  # 淡水湖
                else:
                    tile.is_lake = False
    
    def _is_landlocked(self, start_tile: MapTile, tile_map: dict[tuple[int, int], MapTile]) -> bool:
        """
        检查水域是否被陆地完全包围（使用BFS）
        返回True表示是湖泊，False表示连通到海洋
        """
        visited = set()
        queue = [(start_tile.x, start_tile.y)]
        visited.add((start_tile.x, start_tile.y))
        
        while queue:
            x, y = queue.pop(0)
            
            # 检查是否到达地图边界（说明连通到外海）
            # 注意：X轴是循环的，所以只有Y轴边界（南北极）算作"地图边界"
            # 如果到达南北极的水域，视为连通大洋
            if y == 0 or y == self.height - 1:
                tile = tile_map.get((x, y))
                if tile and tile.elevation < 0:
                    return False  # 连通到边界海洋
            
            # 扩展到相邻水域
            for dx, dy in self._get_neighbor_offsets(x, y):
                # _get_neighbor_offsets 已经处理了X循环和Y越界
                
                if (dx, dy) in visited:
                    continue
                
                neighbor = tile_map.get((dx, dy))
                if neighbor and neighbor.elevation < 0:
                    visited.add((dx, dy))
                    queue.append((dx, dy))
        
        # BFS完成，未到达边界，说明是湖泊
        return True
    
    def _get_neighbor_offsets(self, x: int, y: int) -> list[tuple[int, int]]:
        """获取六边形相邻格子的坐标 (odd-q布局)，处理东西方向循环"""
        offsets = []
        if y & 1:  # 奇数行
            candidates = [
                (x, y - 1), (x + 1, y - 1),  # 上方两个
                (x - 1, y), (x + 1, y),      # 左右
                (x, y + 1), (x + 1, y + 1),  # 下方两个
            ]
        else:  # 偶数行
            candidates = [
                (x - 1, y - 1), (x, y - 1),  # 上方两个
                (x - 1, y), (x + 1, y),      # 左右
                (x - 1, y + 1), (x, y + 1),  # 下方两个
            ]
            
        for cx, cy in candidates:
            # 处理X轴循环 (世界是圆的)
            nx = cx % self.width
            # Y轴不循环
            if 0 <= cy < self.height:
                offsets.append((nx, cy))
                
        return offsets

    def _elevation(self, lat: float, lon: float) -> float:
        """
        生成固定基岩海拔（米），采用赤道大陆模型
        返回范围：-11000m（深海沟）到 5000m（极高山）
        
        特点：
        1. 大部分陆地集中在赤道带（纬度0.4-0.6），全球陆地占比30%
        2. 多尺度噪声叠加（板块+山脉+局部+随机）
        3. 连续性与随机性平衡
        """
        # 纬度权重：五档平滑过渡，赤道带高，极地低
        if 0.45 <= lat <= 0.55:
            lat_weight = 1.2  # 核心赤道带，最高陆地概率
        elif 0.40 <= lat < 0.45 or 0.55 < lat <= 0.60:
            lat_weight = 0.9  # 赤道边缘，高陆地概率
        elif 0.25 <= lat < 0.40 or 0.60 < lat <= 0.75:
            lat_weight = 0.4  # 副热带，中等概率
        elif 0.15 <= lat < 0.25 or 0.75 < lat <= 0.85:
            lat_weight = 0.15  # 温带，较低概率
        else:
            lat_weight = 0.05  # 极地，极低概率
        
        # 多尺度噪声叠加
        # 大尺度：板块构造（超大尺度，频率1-3，权重40%）
        plate_noise = (
            math.sin(lon * math.pi * 2.3) * 0.4 +
            math.cos(lat * math.pi * 1.7) * 0.4 +
            math.sin((lon + lat) * math.pi * 1.1) * 0.2
        ) * 0.6
        
        # 中尺度：山脉系统（大尺度，频率5-10，权重27%）
        mountain_noise = (
            math.sin(lon * math.pi * 7.3 + lat * math.pi * 5.7) * 0.25 +
            math.cos(lon * math.pi * 6.1 - lat * math.pi * 8.3) * 0.25 +
            math.sin((lon * lat) * math.pi * 9.7) * 0.1
        ) * 0.4
        
        # 小尺度：局部起伏（中尺度，频率15-30，权重13%）
        local_noise = (
            math.sin(lon * math.pi * 23.7) * 0.08 +
            math.cos(lat * math.pi * 27.3) * 0.08 +
            math.sin((lon + lat) * math.pi * 19.1) * 0.04
        ) * 0.2
        
        # 随机扰动（使用确定性伪随机，基于坐标，权重10%）
        # 使用坐标哈希而非时间戳，确保相同种子下地图可重现
        coord_hash = int((lon * 1000 + lat * 10000) * 12345) % 2147483647
        pseudo_rand = (coord_hash % 10000) / 10000.0
        random_noise = (pseudo_rand - 0.5) * 0.15
        
        # 综合噪声（应用纬度权重）
        combined = (plate_noise + mountain_noise + local_noise + random_noise) * lat_weight
        
        # 归一化到0-1
        normalized = (combined + 1.2) / 2.4
        normalized = max(0, min(1, normalized))
        
        # 陆地阈值计算，确保全球总陆地占比30%
        # 核心赤道带（10%区域）：55%陆地
        # 赤道边缘（10%区域）：45%陆地
        # 副热带（50%区域）：22%陆地
        # 温带（20%区域）：10%陆地
        # 极地（10%区域）：5%陆地
        # 加权平均：0.1*55% + 0.1*45% + 0.5*22% + 0.2*10% + 0.1*5% = 28.5%（接近30%）
        if 0.45 <= lat <= 0.55:
            land_threshold = 0.45  # 55%陆地
        elif 0.40 <= lat < 0.45 or 0.55 < lat <= 0.60:
            land_threshold = 0.55  # 45%陆地
        elif 0.25 <= lat < 0.40 or 0.60 < lat <= 0.75:
            land_threshold = 0.78  # 22%陆地
        elif 0.15 <= lat < 0.25 or 0.75 < lat <= 0.85:
            land_threshold = 0.90  # 10%陆地
        else:
            land_threshold = 0.95  # 5%陆地
        
        if normalized < land_threshold:
            # 海洋：深海沟到海平面
            ocean_depth = normalized / land_threshold
            
            # 深海分布
            if ocean_depth < 0.60:
                # 60% - 浅海（0到-200m）
                return -200 * ocean_depth / 0.60
            elif ocean_depth < 0.85:
                # 25% - 中深海（-200到-2000m）
                return -200 - 1800 * (ocean_depth - 0.60) / 0.25
            elif ocean_depth < 0.98:
                # 13% - 深海（-2000到-6000m）
                return -2000 - 4000 * (ocean_depth - 0.85) / 0.13
            else:
                # 2% - 深海沟（-6000到-11000m）
                return -6000 - 5000 * (ocean_depth - 0.98) / 0.02
        else:
            # 陆地：低洼地到极高山（上限5000m）
            land_height = (normalized - land_threshold) / (1.0 - land_threshold)
            
            # 陆地海拔分布
            if land_height < 0.03:
                # 3% - 低洼地（-50到0m，可能形成内陆湖泊）
                return -50 + land_height / 0.03 * 50
            elif land_height < 0.40:
                # 37% - 平原（0-200m）
                return (land_height - 0.03) / 0.37 * 200
            elif land_height < 0.75:
                # 35% - 丘陵（200-500m）
                return 200 + (land_height - 0.40) / 0.35 * 300
            elif land_height < 0.90:
                # 15% - 山地（500-1500m）
                return 500 + (land_height - 0.75) / 0.15 * 1000
            elif land_height < 0.97:
                # 7% - 高山（1500-3000m）
                return 1500 + (land_height - 0.90) / 0.07 * 1500
            else:
                # 3% - 极高山（3000-5000m）
                return 3000 + (land_height - 0.97) / 0.03 * 2000

    def _temperature(self, lat: float, elevation: float, lon: float = 0.5) -> float:
        """
        计算温度（°C），基于纬度、海拔和洋流效应
        
        真实地球温度分布特征：
        - 赤道（lat=0.5）约27°C，极地（lat=0或1）约-40°C
        - 海拔每升高100m，温度降低0.65°C（湿绝热递减率）
        - 大陆西岸有寒流（降温），东岸有暖流（升温）
        - 海洋温差比陆地小
        
        Args:
            lat: 纬度（0=北极，0.5=赤道，1=南极）
            elevation: 海拔（米）
            lon: 经度（0-1）
        """
        # ================================================================
        # 第一层：基础纬度温度
        # ================================================================
        # 使用余弦函数模拟太阳辐射分布
        # 赤道约27°C，极地约-40°C
        lat_rad = abs(lat - 0.5) * 2  # 0=赤道，1=极地
        base_temp = 27 - 67 * (lat_rad ** 1.3)  # 非线性，极地更冷
        
        # ================================================================
        # 第二层：洋流效应（仅海洋）
        # ================================================================
        ocean_current_effect = 0.0
        if elevation < 0:  # 海洋
            # 模拟主要洋流模式：
            # 大洋西岸（经度0.0-0.3, 0.5-0.8）有暖流
            # 大洋东岸（经度0.3-0.5, 0.8-1.0）有寒流
            # 这是简化模型，真实洋流更复杂
            
            # 判断在哪个半球
            is_northern = lat < 0.5
            
            # 洋流强度随纬度变化（中纬度最强）
            current_strength = 1.0 - abs(lat_rad - 0.4) * 2
            current_strength = max(0, current_strength)
            
            # 西岸暖流/东岸寒流模式
            # 真实地球：北半球顺时针，南半球逆时针
            lon_phase = (lon * 4) % 1.0  # 分成4个大洋区
            if lon_phase < 0.4:
                # 大洋西岸偏暖
                ocean_current_effect = current_strength * 5
            elif lon_phase > 0.6:
                # 大洋东岸偏冷
                ocean_current_effect = -current_strength * 4
            
            # 热带海洋温度更稳定
            if lat_rad < 0.2:
                ocean_current_effect *= 0.3
        
        # ================================================================
        # 第三层：海拔修正
        # ================================================================
        altitude_effect = 0.0
        if elevation >= 0:
            # 陆地：每100m降低0.65°C
            altitude_effect = -elevation * 0.0065
        else:
            # 深海：温度随深度变化
            # 表层水温接近气温，深层约4°C
            depth = abs(elevation)
            if depth > 200:
                # 温跃层以下逐渐趋向4°C
                deep_factor = min(1.0, (depth - 200) / 3000)
                target_deep_temp = 4.0
                altitude_effect = (target_deep_temp - base_temp) * deep_factor * 0.3
        
        # ================================================================
        # 第四层：大陆性气候
        # ================================================================
        # 海洋温差小，极端温度被缓冲
        continental_effect = 0.0
        if elevation >= 0:
            # 陆地：极端温度更明显
            if lat_rad < 0.2:
                # 热带陆地更热
                continental_effect = 3
            elif lat_rad > 0.6:
                # 高纬度陆地更冷
                continental_effect = -5 * (lat_rad - 0.6) / 0.4
        
        # ================================================================
        # 组合所有效应
        # ================================================================
        final_temp = base_temp + ocean_current_effect + altitude_effect + continental_effect
        
        # 添加微小随机扰动（基于坐标的确定性）
        coord_hash = int((lon * 1000 + lat * 10000)) % 1000
        noise = (coord_hash / 1000 - 0.5) * 2  # -1 到 1
        final_temp += noise
        
        return final_temp

    def _humidity(self, lat: float, lon: float, elevation: float = 0, 
                  tiles: list | None = None, x: int = 0, y: int = 0) -> float:
        """
        计算湿度（0-1），考虑多种气候因素
        
        真实地球湿度分布特征：
        1. 热带辐合带（ITCZ）- 赤道附近高湿
        2. 副热带高压带 - 南北纬30°附近干燥（沙漠带）
        3. 西风带 - 中纬度较湿润
        4. 极地 - 干燥（冷空气含水量低）
        5. 大陆内部 - 干燥（距海远）
        6. 雨影效应 - 山脉背风面干燥
        
        Args:
            lat: 纬度（0-1，0.5为赤道）
            lon: 经度（0-1）
            elevation: 海拔（米）
            tiles: 地块列表（用于计算距海距离）
            x, y: 当前坐标
        """
        # ================================================================
        # 第一层：纬度带湿度（大气环流）
        # ================================================================
        lat_rad = abs(lat - 0.5) * 2  # 0=赤道，1=极地
        
        # 模拟哈德利环流、费雷尔环流、极地环流
        if lat_rad < 0.15:
            # 热带辐合带（ITCZ）- 高湿
            base_humidity = 0.8
        elif lat_rad < 0.35:
            # 副热带高压带 - 干燥（撒哈拉、阿拉伯沙漠区）
            # 平滑过渡
            progress = (lat_rad - 0.15) / 0.2
            base_humidity = 0.8 - progress * 0.5  # 0.8 -> 0.3
        elif lat_rad < 0.55:
            # 中纬度西风带 - 较湿润
            progress = (lat_rad - 0.35) / 0.2
            base_humidity = 0.3 + progress * 0.3  # 0.3 -> 0.6
        elif lat_rad < 0.75:
            # 亚极地 - 中等
            progress = (lat_rad - 0.55) / 0.2
            base_humidity = 0.6 - progress * 0.2  # 0.6 -> 0.4
        else:
            # 极地 - 干燥（极地沙漠）
            base_humidity = 0.3
        
        # ================================================================
        # 第二层：海陆分布影响
        # ================================================================
        if elevation < 0:
            # 海洋上空湿度高
            ocean_bonus = 0.2
        else:
            # 陆地基础较干
            ocean_bonus = -0.05
            
            # 高海拔更干燥（空气稀薄）
            if elevation > 2000:
                altitude_penalty = min(0.2, (elevation - 2000) / 5000 * 0.2)
                ocean_bonus -= altitude_penalty
        
        # ================================================================
        # 第三层：经度变化（模拟季风和信风）
        # ================================================================
        # 简化模型：大洋西岸偏湿，东岸偏干
        lon_effect = math.sin(lon * 4 * math.pi) * 0.1
        
        # 信风带：热带东部偏干（下沉气流）
        if lat_rad < 0.3:
            lon_phase = (lon * 2) % 1.0
            if lon_phase > 0.6:  # 大洋东部
                lon_effect -= 0.15
        
        # ================================================================
        # 第四层：季风区域（模拟亚洲季风）
        # ================================================================
        # 假设在某些经度带有强季风效应
        monsoon_effect = 0.0
        if 0.3 < lat_rad < 0.5:  # 中低纬度
            # 某些经度带（如亚洲季风区）更湿润
            monsoon_zone = math.sin(lon * 3 * math.pi)
            if monsoon_zone > 0.5:
                monsoon_effect = 0.15
        
        # ================================================================
        # 组合所有效应
        # ================================================================
        final_humidity = base_humidity + ocean_bonus + lon_effect + monsoon_effect
        
        # 添加微小随机扰动
        coord_hash = int((lon * 7777 + lat * 3333)) % 1000
        noise = (coord_hash / 1000 - 0.5) * 0.1
        final_humidity += noise
        
        # 限制在合理范围
        return max(0.05, min(0.95, final_humidity))

    def _resources(self, temperature: float, elevation: float, humidity: float, latitude: float) -> float:
        """
        计算地块的资源丰富度（绝对值：1-1000）
        
        设计原则：
        1. 温度越低资源越少（极寒地区生物量低）
        2. 浅海和陆地资源更多（光合作用带、近岸营养盐）
        3. 适当湿度提升资源
        4. 赤道地区通常更丰富（但高温也有上限）
        
        Args:
            temperature: 温度（°C）
            elevation: 海拔（m）
            humidity: 湿度（0-1）
            latitude: 纬度（0-1，0.5为赤道）
        
        Returns:
            资源值（1-1000）
        """
        base_resources = 100.0
        
        # 1. 温度因子（-30°C到35°C是最佳范围）
        if temperature < -30:
            temp_factor = 0.1  # 极寒地区资源极少
        elif temperature < -10:
            temp_factor = 0.3 + (temperature + 30) / 20 * 0.4  # -30到-10: 0.3到0.7
        elif temperature < 10:
            temp_factor = 0.7 + (temperature + 10) / 20 * 0.3  # -10到10: 0.7到1.0
        elif temperature < 30:
            temp_factor = 1.0  # 10到30°C：最佳温度
        elif temperature < 40:
            temp_factor = 1.0 - (temperature - 30) / 10 * 0.3  # 30到40: 1.0到0.7
        else:
            temp_factor = 0.5  # 极热地区资源下降
        
        # 2. 海拔/深度因子
        if elevation < -1000:
            # 深海：资源稀少（深海平原、海沟）
            depth_factor = 0.2
        elif elevation < -200:
            # 中深海：资源较少
            depth_factor = 0.4
        elif elevation < -50:
            # 浅海：资源丰富（大陆架，阳光充足，营养盐丰富）
            depth_factor = 1.5
        elif elevation < 0:
            # 超浅海岸：资源极其丰富（潮间带、河口）
            depth_factor = 2.0
        elif elevation < 200:
            # 低地平原：资源丰富
            depth_factor = 1.8
        elif elevation < 1000:
            # 丘陵：资源中等
            depth_factor = 1.2
        elif elevation < 2500:
            # 山地：资源减少
            depth_factor = 0.8
        elif elevation < 4000:
            # 高山：资源稀少
            depth_factor = 0.4
        else:
            # 极高山：资源极少
            depth_factor = 0.2
        
        # 3. 湿度因子（0.3-0.8是最佳范围）
        if humidity < 0.2:
            humidity_factor = 0.5  # 极干旱
        elif humidity < 0.3:
            humidity_factor = 0.5 + (humidity - 0.2) / 0.1 * 0.3  # 0.5到0.8
        elif humidity < 0.8:
            humidity_factor = 0.8 + (humidity - 0.3) / 0.5 * 0.4  # 0.8到1.2
        elif humidity < 0.95:
            humidity_factor = 1.2 - (humidity - 0.8) / 0.15 * 0.2  # 1.2到1.0
        else:
            humidity_factor = 0.9  # 过度潮湿（沼泽）
        
        # 4. 纬度因子（赤道附近通常更丰富，但不是绝对）
        latitude_factor = 0.8 + 0.4 * (1 - abs(latitude - 0.5) * 2)  # 赤道1.2，极地0.8
        
        # 综合计算
        total_resources = base_resources * temp_factor * depth_factor * humidity_factor * latitude_factor
        
        # 限制在1-1000范围
        return max(1.0, min(1000.0, total_resources))

    def _infer_biome(self, temp: float, humidity: float, elevation: float) -> str:
        """
        根据温度、湿度和海拔推断生物群系
        注意：这里的elevation是固定基岩海拔，初始化时sea_level=0
        """
        # 使用相对海拔分类（初始化时sea_level=0，所以等同于固定海拔）
        relative_elevation = elevation  # 初始化阶段，相对海拔 = 固定海拔
        
        # 水域地形
        if relative_elevation < 0:
            if relative_elevation < -500:
                return "深海"
            elif relative_elevation < -100:
                return "浅海"
            else:
                return "海岸"
        
        # 陆地地形
        if relative_elevation > 2500:
            return "高山"
        elif relative_elevation > 800:
            return "山地"
        elif relative_elevation > 200:
            return "丘陵"
        else:
            # 平原区域，根据气候细分
            if temp > 25 and humidity > 0.6:
                return "雨林"
            elif temp > 20 and humidity <= 0.6:
                return "草原"
            elif temp < 0:
                return "冻原"
            elif humidity < 0.2:
                return "荒漠"
            else:
                return "温带森林"

    def _infer_cover(
        self, 
        biome: str, 
        noise: float = 0.5, 
        primordial: bool = False,
        temperature: float | None = None,
        humidity: float | None = None,
        elevation: float | None = None
    ) -> str:
        """
        根据生物群系和局部噪声推断覆盖物类型
        使植被分布更加破碎和交织
        
        Args:
            biome: 生物群系名称
            noise: 局部随机噪声值 (0.0 - 1.0)，默认0.5
            primordial: 是否为原始地质模式（28亿年前无植物时代）
            temperature: 温度（°C），用于判断极地冰雪
            humidity: 湿度（0-1），用于判断沙漠/戈壁
            elevation: 海拔（m），用于判断冰川
        """
        # 【极地海洋冰盖】极寒海域应该有冰盖
        if biome in ["深海", "浅海", "海岸"]:
            if temperature is not None and temperature < -5:
                return "海冰"
            return "水域"
        
        if biome == "湖泊":
            if temperature is not None and temperature < -5:
                return "冰湖"
            return "水域"

        # 【原始地质模式】28亿年前的地表没有植物
        # 只有裸岩、沙漠（干燥区）、冰川/冰原（极寒区）
        if primordial:
            return self._infer_primordial_cover(biome, noise, temperature, humidity, elevation)

        if biome == "雨林":
            # 主要是森林，偶尔有林窗（草甸）或湿地
            if noise < 0.15: return "草甸"
            if noise > 0.90: return "水域" # 沼泽
            return "森林"
            
        elif biome == "温带森林":
            # 森林为主，大量混杂草甸和灌木
            if noise < 0.3: return "草甸" # 林间空地
            if noise > 0.8: return "混合林"
            return "森林"
            
        elif biome == "草原":
            # 草甸为主，混杂稀疏树木（森林）和裸地
            if noise < 0.15: return "裸地"
            if noise > 0.75: return "森林" # 稀树草原
            return "草甸"
            
        elif biome == "丘陵":
            # 草甸为主，混杂森林和裸地
            if noise < 0.2: return "裸地" # 石头
            if noise > 0.6: return "森林" # 山坡林
            return "草甸"
            
        elif biome == "山地":
            # 裸地为主，低处有草甸或针叶林
            if noise < 0.4: return "草甸" # 高山草甸
            if noise > 0.8: return "森林" # 针叶林
            return "裸地"
            
        elif biome == "冻原":
            # 苔原为主，偶有裸岩或冰雪
            if noise < 0.2: return "裸地"
            if noise > 0.8: return "冰川"
            return "苔原"
            
        elif biome == "荒漠":
            # 沙漠为主，偶有绿洲（草甸）或裸岩
            if noise > 0.95: return "草甸" # 绿洲
            if noise < 0.3: return "裸地" # 戈壁
            return "沙漠"

        elif biome == "高山":
            if noise > 0.7: return "冰川"
            return "裸地"

        return "混合林"
    
    def _infer_primordial_cover(
        self, 
        biome: str, 
        noise: float,
        temperature: float | None = None,
        humidity: float | None = None,
        elevation: float | None = None
    ) -> str:
        """
        原始地质模式下的覆盖物推断
        28亿年前（太古宙晚期）的地表特征：
        - 没有任何陆地植物（最早的陆地植物出现在4.7亿年前）
        - 陆地表面为裸岩、风化碎屑、原始沙漠
        - 极寒区域有冰川/冰原（南北极）
        - 湿润区域可能有原始藻类膜（但视觉上仍是裸地）
        
        Args:
            biome: 生物群系名称
            noise: 局部噪声值
            temperature: 温度（°C）
            humidity: 湿度（0-1）
            elevation: 海拔（m）
        """
        temp = temperature if temperature is not None else 15.0
        humid = humidity if humidity is not None else 0.5
        elev = elevation if elevation is not None else 0.0
        
        # ============================================================
        # 【极地冰雪覆盖】最高优先级
        # 南北极的陆地应该被冰雪覆盖
        # ============================================================
        if temp < -25:
            # 极寒区域：冰川覆盖
            return "冰川"
        elif temp < -15:
            # 冷极区域：冰原（冰盖）
            if elev > 2000 or noise > 0.5:
                return "冰川"
            return "冰原"
        elif temp < -5:
            # 寒冷区域：冻土
            return "冻土"
        
        # ============================================================
        # 【非极地区域】根据气候分类
        # ============================================================
        if biome in ["高山", "山地"]:
            # 高海拔：裸岩或冰川（如果够冷）
            if temp < 0 or elev > 4000:
                return "冰川"
            if elev > 3000:
                return "冻土"
            return "裸地"
        
        elif biome == "冻原":
            # 冻原区域（已经是寒冷地带）
            if temp < 0:
                return "冻土"
            return "裸地"
        
        elif biome == "荒漠":
            # 干旱区域：沙漠或戈壁
            if humid < 0.15:
                return "沙漠"
            elif humid < 0.3:
                if noise < 0.4:
                    return "戈壁"  # 岩石荒漠
                return "沙漠"
            return "裸地"
        
        elif biome in ["雨林", "温带森林", "草原", "丘陵"]:
            # 现代本应是植被茂盛的区域，在原始地质时代是裸地
            return "裸地"
        
        else:
            # 默认裸地
            return "裸地"

    def _has_river(self, lat: float, lon: float) -> bool:
        return abs(math.sin(6 * math.pi * lon) * (0.5 - lat)) > 0.45

    def _suitability_score(self, species: Species, tile: MapTile) -> float:
        """计算物种在某地块的适应性评分（0-1范围）"""
        temperature_pref = species.abstract_traits.get("耐寒性", 5)
        dryness_pref = species.abstract_traits.get("耐旱性", 5)
        
        # 温度适应性
        temp_norm = (tile.temperature + 30) / 70  # map to 0-1 approximate
        temp_score = max(0.0, 1 - abs(temp_norm * 10 - temperature_pref) / 10)
        
        # 湿度适应性
        humidity_norm = tile.humidity
        humidity_score = max(0.0, 1 - abs(humidity_norm * 10 - (10 - dryness_pref)) / 10)
        
        # 资源适应性（将1-1000的资源值归一化到0-1）
        # 使用对数刻度，因为资源是指数分布的
        resource_normalized = min(1.0, math.log(tile.resources + 1) / math.log(1001))
        resource_score = resource_normalized
        
        # 生物群系匹配度
        adjacency = 1.0 if species.description.find(tile.biome[:1]) >= 0 else 0.5
        
        # 综合评分（权重：温度25% + 湿度25% + 资源30% + 群系20%）
        # 资源权重提升，因为它现在更准确地反映了环境承载力
        return max(0.0, (temp_score * 0.25 + humidity_score * 0.25 + resource_score * 0.3 + adjacency * 0.2))

    def _neighbor_ids(self, tile: MapTile, coord_map: dict[tuple[int, int], int]) -> list[int]:
        """Return neighbor ids treating the east/west boundary as wrapped."""
        # Odd-q style directions so columns extend horizontally like the client-view
        even_column = [
            (-1, 0),
            (0, -1),
            (1, -1),
            (1, 0),
            (1, 1),
            (0, 1),
        ]
        odd_column = [
            (-1, 0),
            (-1, -1),
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 1),
        ]
        directions = odd_column if (tile.x & 1) else even_column
        ids: list[int] = []
        for dx, dy in directions:
            nx = (tile.x + dx) % self.width
            ny = tile.y + dy
            if ny < 0 or ny >= self.height:
                continue
            neighbor_id = coord_map.get((nx, ny))
            if neighbor_id:
                ids.append(neighbor_id)
        return ids
