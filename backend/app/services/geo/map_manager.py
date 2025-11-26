from __future__ import annotations

import math
import random
from typing import Sequence

import numpy as np
from ...models.environment import HabitatPopulation, MapState, MapTile
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

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.repo = environment_repository

    def ensure_initialized(self, map_seed: int | None = None) -> None:
        print(f"[地图管理器] 确保地图列已存在...")
        self.repo.ensure_tile_columns()
        
        print(f"[地图管理器] 检查现有地图数据...")
        tiles = self.repo.list_tiles()
        print(f"[地图管理器] 发现 {len(tiles)} 个地块")
        
        if not tiles:
            print(f"[地图管理器] 生成新地图 ({self.width}×{self.height})...")
            generated = self._generate_grid(map_seed)
            print(f"[地图管理器] 生成了 {len(generated)} 个地块，正在保存...")
            self.repo.upsert_tiles(generated)
            print(f"[地图管理器] 地块保存完成")
            
        print(f"[地图管理器] 检查地图状态...")
        if not self.repo.get_state():
            print(f"[地图管理器] 创建初始地图状态...")
            self.repo.save_state(MapState(stage_name="稳定期", stage_progress=0, stage_duration=0))
            print(f"[地图管理器] 地图状态创建完成")
        else:
            print(f"[地图管理器] 地图状态已存在")

    def reclassify_terrain_by_sea_level(self, sea_level: float) -> None:
        """
        根据当前海平面重新分类所有地块的地形类型
        
        Args:
            sea_level: 当前海平面高度（米）
        """
        print(f"[地图管理器] 根据海平面 {sea_level:.1f}m 重新分类地形...")
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
                tile.cover = self._infer_cover(new_biome, pseudo_rand)
                updated_tiles.append(tile)
        
        if updated_tiles:
            print(f"[地图管理器] 更新了 {len(updated_tiles)} 个地块: "
                  f"淹没{terrain_changes['淹没']}个, 露出{terrain_changes['露出']}个")
            self.repo.upsert_tiles(updated_tiles)
        else:
            print(f"[地图管理器] 地形无变化")
        
        # 重新分类水体（海岸判定、湖泊识别、盐度更新）
        print(f"[地图管理器] 重新分类水体...")
        all_tiles = self.repo.list_tiles()
        self._classify_water_bodies(all_tiles)
        self.repo.upsert_tiles(all_tiles)
        print(f"[地图管理器] 水体分类完成")
    
    def snapshot_habitats(self, species_list: Sequence[Species], turn_index: int, force_recalculate: bool = False) -> None:
        """记录或更新物种栖息地分布
        
        Args:
            species_list: 所有物种列表
            turn_index: 当前回合数
            force_recalculate: 是否强制重新计算分布（默认False）
                - True: 完全重新计算所有物种的栖息地分布（用于初始化）
                - False: 更新现有栖息地的种群数量，为没有栖息地的物种初始化分布
        """
        print(f"[地图管理器] 栖息地快照，回合={turn_index}, 物种数={len(species_list)}, 强制重算={force_recalculate}")
        
        tiles = self.repo.list_tiles()
        if not tiles:
            print(f"[地图管理器警告] 没有地块数据，无法记录栖息地")
            return
        
        # 非强制模式：更新现有栖息地的种群数量
        if not force_recalculate:
            self._update_habitat_populations(species_list, turn_index)
            return
        
        # 强制重算模式：用于初始化
        print(f"[地图管理器] 强制重算模式，为 {len(species_list)} 个物种初始化栖息地分布")
        habitats: list[HabitatPopulation] = []
        
        
        for species in species_list:
            # 只处理存活的物种，跳过灭绝物种
            if getattr(species, 'status', 'alive') != 'alive':
                continue
                
            total = int(species.morphology_stats.get("population", 0) or 0)
            if total <= 0:
                continue
            
            # 强制重算模式：为所有物种计算栖息地分布
            print(f"[地图管理器] 初始化 {species.common_name} 的栖息地分布")
            
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
            
            print(f"[地图管理器] {species.common_name} ({habitat_type}) 分布到 {len(top_tiles)} 个地块")
            
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
            print(f"[地图管理器] 保存 {len(habitats)} 条栖息地记录")
            self.repo.write_habitats(habitats)
        else:
            print(f"[地图管理器] 没有栖息地记录需要保存")
    
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
            print(f"[地图管理器] 更新 {len(updated_habitats)} 条栖息地种群数量")
            self.repo.write_habitats(updated_habitats)
        
        # 为没有栖息地的物种初始化分布
        if species_needing_init:
            print(f"[地图管理器] 为 {len(species_needing_init)} 个物种初始化栖息地")
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
            print(f"[地图管理器] 初始化 {len(habitats)} 条新栖息地记录")
            self.repo.write_habitats(habitats)
    
    def _filter_tiles_by_habitat_type(self, tiles: list[MapTile], habitat_type: str) -> list[MapTile]:
        """根据栖息地类型筛选合适的地块"""
        filtered = []
        
        for tile in tiles:
            biome = tile.biome.lower()
            
            if habitat_type == "marine":
                # 海洋生物：浅海和中层海域
                if "浅海" in biome or "中层" in biome:
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
        print(f"[地图管理器] 获取概览，地块限制={tile_limit}, 栖息地限制={habitat_limit}, 视图模式={view_mode}, 物种ID={species_id}")
        
        tiles = self.repo.list_tiles(limit=tile_limit)
        print(f"[地图管理器] 查询到 {len(tiles)} 个地块")
        
        if not tiles:
            print(f"[地图管理器警告] 没有地块数据，尝试初始化...")
            self.ensure_initialized()
            tiles = self.repo.list_tiles(limit=tile_limit)
            print(f"[地图管理器] 初始化后查询到 {len(tiles)} 个地块")
        
        # 如果指定了物种，优先查询该物种的栖息地
        species_ids = [species_id] if species_id else None
        habitats = self.repo.latest_habitats(limit=habitat_limit, species_ids=species_ids)
        print(f"[地图管理器] 查询到 {len(habitats)} 个栖息地记录")
        
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

        print(f"[地图管理器] 返回概览: {len(tile_infos)} 地块, {len(habitat_entries)} 栖息地, "
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
        print(f"[地图管理器] 使用随机种子: {map_seed}")
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
                
                # 5. 基于新海拔计算环境参数
                temperature = self._temperature(latitude, elevation)
                humidity = self._humidity(latitude, longitude)
                # 资源计算需要考虑温度、海拔和湿度
                resources = self._resources(temperature, elevation, humidity, latitude)
                biome = self._infer_biome(temperature, humidity, elevation)
                cover = self._infer_cover(biome, v_noise)
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
        
        # 生成随机岛屿
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
            print(f"[地图管理器] 地图种子已保存: {map_seed}")
        
        return tiles

    def _smooth_noise(self, noise_grid: np.ndarray) -> np.ndarray:
        """简单的3x3均值滤波，使噪声稍微连续一些，形成自然的斑块。处理X轴循环。"""
        h, w = noise_grid.shape
        new_grid = np.zeros_like(noise_grid)
        
        # 1. X轴使用 wrap 模式填充 (处理左右循环)
        x_padded = np.pad(noise_grid, ((0, 0), (1, 1)), mode='wrap')
        
        # 2. Y轴使用 edge 模式填充 (处理上下边界)
        padded = np.pad(x_padded, ((1, 1), (0, 0)), mode='edge')
        
        for y in range(h):
            for x in range(w):
                # 取周围 3x3 区域
                # padded 的 (1,1) 对应原图 (0,0)
                # 所以原图 (y, x) 对应 padded (y+1, x+1)
                # 3x3 区域是 padded[y:y+3, x:x+3]
                new_grid[y, x] = np.mean(padded[y:y+3, x:x+3])
                
        # 归一化回 0-1，因为均值会趋向于0.5
        min_val, max_val = new_grid.min(), new_grid.max()
        if max_val > min_val:
            new_grid = (new_grid - min_val) / (max_val - min_val)
            
        return new_grid

    def _generate_earth_like_height_map(self) -> np.ndarray:
        """
        使用高斯核模拟大陆板块，叠加噪声，并转化为全局百分位排名。
        改进版：
        1. 使用坐标扭曲 (Domain Warping) 让大陆形状更不规则
        2. 增加脊线噪声 (Ridge Noise) 制造分散的山脉
        3. 增加高频噪声让海岸线更破碎
        """
        width, height = self.width, self.height
        # 初始化网格
        grid = np.zeros((height, width), dtype=float)
        
        # 0. 坐标扭曲 (Domain Warping)
        # 让规则的坐标网格产生流动感，打破圆形的高斯分布
        y_grid, x_grid = np.ogrid[:height, :width]
        
        # 扭曲参数
        # 修正：warp_freq 必须是偶数，以保证 X 轴 wrap 时 cos 值的连续性
        # cos(0) = 1, cos(2*pi) = 1. 如果 freq=2.5, cos(2.5*pi)=0 -> 断裂
        warp_freq = 4.0 
        warp_amp_x = width * 0.12
        warp_amp_y = height * 0.12
        
        # X轴偏移受Y影响，Y轴偏移受X影响（旋涡状）
        warp_offset_x = np.sin(y_grid / height * warp_freq * math.pi) * warp_amp_x
        warp_offset_y = np.cos(x_grid / width * warp_freq * math.pi) * warp_amp_y
        
        # A. 随机放置 5-8 个“大陆核心”
        num_continents = random.randint(5, 8)
        for _ in range(num_continents):
            cx = random.uniform(0, width)
            cy = random.uniform(height * 0.15, height * 0.85)
            
            # 半径随机性增大，长宽比更夸张
            radius_x = random.uniform(width * 0.08, width * 0.25)
            radius_y = random.uniform(height * 0.08, height * 0.25)
            strength = random.uniform(1.2, 2.5)
            
            # 计算扭曲后的距离
            # 注意：这里实际上是把高斯分布的输入坐标扭曲了
            # 处理 x 轴的循环边界
            
            # 1. 计算原始距离差
            raw_dx_diff = (x_grid + warp_offset_x) - cx
            # 2. 取模，映射到 [0, width)
            dx_mod = np.abs(raw_dx_diff) % width
            # 3. 取最短路径 (环形距离)
            dx = np.minimum(dx_mod, width - dx_mod)
            
            dy = np.abs((y_grid + warp_offset_y) - cy)
            
            # 高斯叠加
            blob = strength * np.exp(-((dx**2)/(2*radius_x**2) + (dy**2)/(2*radius_y**2)))
            grid += blob

        # B. 叠加多层噪声 (Fractal Noise)
        # 使用更复杂的噪声组合来模拟侵蚀和细节
        
        noise_strength = 0.7  # 提高噪声权重
        
        # (频率, 振幅, 类型)
        layers = [
            (3, 1.0, "base"),       # 基础起伏
            (7, 0.6, "base"),       # 中等细节
            (15, 0.3, "detail"),    # 海岸线破碎细节
            (30, 0.15, "detail"),   # 微观噪点
            (5, 0.5, "ridge"),      # 大山脉 (脊线)
            (12, 0.3, "ridge"),     # 小山脉
        ]
        
        for freq, amp_weight, kind in layers:
            phase_x = random.uniform(0, 2*math.pi)
            phase_y = random.uniform(0, 2*math.pi)
            
            # 添加频率微扰，防止完美的谐波叠加
            # 修正：X轴频率必须是整数，以保证左右连续性
            fx = max(1, round(freq * random.uniform(0.9, 1.1)))
            fy = freq * random.uniform(0.9, 1.1)
            
            if kind == "base":
                # 正弦波叠加: sin(x) + cos(y)
                noise = np.sin(x_grid / width * fx * 2 * math.pi + phase_x) + \
                        np.cos(y_grid / height * fy * 2 * math.pi + phase_y)
                # 归一化到 -1~1
                noise *= 0.5
                
            elif kind == "detail":
                # 细节层使用更高频的乘法，制造断裂感
                noise = np.sin(x_grid / width * fx * 2 * math.pi + phase_x) * \
                        np.cos(y_grid / height * fy * 2 * math.pi + phase_y)
                        
            elif kind == "ridge":
                # 脊线噪声: 1 - abs(sin)
                # 这种噪声会产生尖锐的山脊线
                raw = np.sin(x_grid / width * fx * 2 * math.pi + phase_x) + \
                      np.cos(y_grid / height * fy * 2 * math.pi + phase_y)
                # 变换为脊线
                noise = 1.0 - np.abs(raw * 0.5)
                # 锐化，只保留尖端
                noise = np.power(noise, 2)
                
            grid += noise * (noise_strength * amp_weight)

        # C. 转化为百分位排名 (0.0 - 1.0)
        flat = grid.flatten()
        ranks = np.argsort(np.argsort(flat))
        rank_grid = (ranks / len(flat)).reshape(height, width)
        
        return rank_grid

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
        在海洋中生成5-10个随机岛屿，增加地形随机性
        每个岛屿包含3-15个地块
        """
        # 注意：不要在这里重新设置seed，使用主种子的随机序列
        
        # 构建坐标到地块的映射
        tile_map = {(tile.x, tile.y): tile for tile in tiles}
        
        # 找出所有深海区域（作为岛屿候选位置）
        ocean_tiles = [tile for tile in tiles if tile.elevation < -1000]
        
        if len(ocean_tiles) < 10:
            print("[地图管理器] 海洋地块不足，跳过岛屿生成")
            return
        
        # 随机选择5-10个岛屿中心
        num_islands = random.randint(5, 10)
        island_centers = random.sample(ocean_tiles, min(num_islands, len(ocean_tiles)))
        
        print(f"[地图管理器] 生成 {len(island_centers)} 个随机岛屿")
        
        for center in island_centers:
            # 每个岛屿3-15个地块
            island_size = random.randint(3, 15)
            
            # 岛屿海拔：100-800m（小岛到大岛）
            island_base_elevation = random.uniform(100, 800)
            
            # BFS扩展岛屿
            island_tiles = [(center.x, center.y)]
            visited = {(center.x, center.y)}
            queue = [(center.x, center.y, 0)]  # (x, y, distance_from_center)
            
            while queue and len(island_tiles) < island_size:
                x, y, dist = queue.pop(0)
                
                # 设置当前地块为岛屿（海拔随距离递减）
                tile = tile_map.get((x, y))
                if tile:
                    elevation_decay = 1.0 - (dist / island_size) * 0.7  # 中心高，边缘低
                    tile.elevation = island_base_elevation * elevation_decay
                    # 重新计算温度（海拔变化会影响温度）
                    latitude = 1 - (tile.y / (self.height - 1)) if self.height > 1 else 0.5
                    tile.temperature = self._temperature(latitude, tile.elevation)
                    # 重新计算资源（海拔和温度变化会影响资源）
                    tile.resources = self._resources(tile.temperature, tile.elevation, tile.humidity, latitude)
                    # 重新推断生物群系
                    tile.biome = self._infer_biome(tile.temperature, tile.humidity, tile.elevation)
                    # 岛屿上植被稍显茂盛，noise 给稍高一点的均值随机
                    tile_noise = random.uniform(0.3, 0.8)
                    tile.cover = self._infer_cover(tile.biome, tile_noise)
                
                # 随机扩展到相邻地块
                if len(island_tiles) < island_size:
                    neighbors = self._get_neighbor_offsets(x, y)
                    random.shuffle(neighbors)
                    for nx, ny in neighbors:
                        if (nx, ny) not in visited:
                            neighbor_tile = tile_map.get((nx, ny))
                            # 只扩展到海洋地块
                            if neighbor_tile and neighbor_tile.elevation < 0:
                                visited.add((nx, ny))
                                island_tiles.append((nx, ny))
                                queue.append((nx, ny, dist + 1))
                                if len(island_tiles) >= island_size:
                                    break
    
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

    def _temperature(self, lat: float, elevation: float) -> float:
        """
        计算温度（°C），基于纬度和海拔
        - 赤道（lat=0.5）约30°C，极地（lat=0或1）约-30°C
        - 海拔每升高100m，温度降低0.65°C (标准气温垂直递减率)
        
        参考值：
        4000m ≈ -11°C (假设基准15°C)
        8000m ≈ -37°C
        """
        # 基础温度（海平面）：赤道30°C，极地-30°C
        base = 30 - abs(lat - 0.5) * 120
        
        # 海拔修正：仅对陆地（elevation>=0）应用
        # 海洋温度不受"海拔"影响，只受纬度影响
        if elevation >= 0:
            # 每100m降低0.65°C
            altitude_adjustment = elevation * 0.0065
            return base - altitude_adjustment
        else:
            # 海洋温度略低于同纬度陆地
            return base - 2

    def _humidity(self, lat: float, lon: float) -> float:
        return max(0.0, min(1.0, 0.5 + 0.3 * math.sin(2 * math.pi * lon) - 0.2 * abs(lat - 0.5)))

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

    def _infer_cover(self, biome: str, noise: float = 0.5) -> str:
        """
        根据生物群系和局部噪声推断覆盖物类型
        使植被分布更加破碎和交织
        
        Args:
            biome: 生物群系名称
            noise: 局部随机噪声值 (0.0 - 1.0)，默认0.5
        """
        # 水域始终是水域
        if biome in ["深海", "浅海", "海岸", "湖泊"]:
            return "水域"

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
