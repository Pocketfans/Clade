"""植被覆盖动态更新服务

根据地块上的植物物种分布动态更新地块覆盖物类型。

【设计理念】
1. 28亿年前（游戏初始）地表是纯地质状态，无植被覆盖
2. 随着植物物种在地块上繁衍，覆盖物逐渐从裸地变为草甸、森林等
3. 覆盖物类型由植物类型占比 + 气候条件共同决定
4. 与35级地形分类系统匹配，提供精细的生态表现

【覆盖物类型 - 30种细分】

冰雪类 (6种):
- 冰川/Glacier: 高山永久冰川
- 冰原/Ice Sheet: 极地大冰原
- 冰帽/Ice Cap: 山顶小冰帽
- 海冰/Sea Ice: 极地海洋浮冰
- 冰湖/Frozen Lake: 结冰的湖泊
- 冻土/Permafrost: 永久冻土层

荒漠类 (6种):
- 沙漠/Desert: 沙质荒漠
- 沙丘/Dune: 流动沙丘
- 戈壁/Gobi: 石质荒漠
- 盐碱地/Salt Flat: 盐碱荒漠
- 裸岩/Bare Rock: 裸露岩石
- 裸地/Barren: 一般裸地

苔原/草地类 (6种):
- 苔原/Tundra: 极地苔藓/地衣
- 高山草甸/Alpine Meadow: 高山草甸
- 草甸/Meadow: 湿润草甸
- 草原/Grassland: 温带草原
- 稀树草原/Savanna: 热带稀树草原
- 灌木丛/Scrub: 灌木地带

森林类 (7种):
- 苔藓林/Moss Forest: 苔藓覆盖的原始林
- 针叶林/Taiga: 寒带针叶林
- 混合林/Mixed: 针阔混交林
- 阔叶林/Forest: 温带落叶林
- 常绿林/Evergreen: 亚热带常绿林
- 雨林/Rainforest: 热带雨林
- 云雾林/Cloud Forest: 高山云雾林

湿地类 (5种):
- 沼泽/Swamp: 树木沼泽
- 湿地/Wetland: 草本湿地
- 泥炭地/Peatland: 泥炭沼泽
- 红树林/Mangrove: 沿海红树林
- 水域/Water: 开放水面

【使用方式】
```python
service = VegetationCoverService()
updated_tiles = service.update_vegetation_cover(tiles, habitats, species_map)
```
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.environment import MapTile, HabitatPopulation
    from ...models.species import Species

logger = logging.getLogger(__name__)


@dataclass
class PlantInfo:
    """植物物种信息摘要"""
    species_id: int
    lineage_code: str
    is_woody: bool  # 是否木本植物（树木）
    is_herbaceous: bool  # 是否草本植物
    is_moss_lichen: bool  # 是否苔藓/地衣
    population: int  # 该地块上的种群量


@dataclass
class TileVegetationStats:
    """地块植被统计"""
    tile_id: int
    total_plant_population: int
    woody_population: int  # 木本植物种群
    herbaceous_population: int  # 草本植物种群
    moss_lichen_population: int  # 苔藓/地衣种群
    plant_species_count: int  # 植物物种数
    density: float  # 植被密度 (0-1)
    dominant_type: str  # 主导植被类型: woody, herbaceous, moss, mixed, none


class VegetationCoverService:
    """植被覆盖动态更新服务"""
    
    # ================================================================
    # 【生物量密度基准计算】
    # 
    # 地球表面积：5.1亿 km² ÷ 5120 格 ≈ 100,000 km²/格
    # 
    # 真实世界生物量密度参考：
    # - 热带雨林：200-400 吨/公顷 = 20,000-40,000 吨/km²
    # - 温带森林：100-200 吨/公顷 = 10,000-20,000 吨/km²
    # - 草原：10-30 吨/公顷 = 1,000-3,000 吨/km²
    # - 苔原：1-5 吨/公顷 = 100-500 吨/km²
    #
    # 一个地块（10万 km²）的生物量：
    # - 雨林：2-4 万亿 kg (2e12 - 4e12)
    # - 森林：1-2 万亿 kg (1e12 - 2e12)
    # - 草原：1000-3000 亿 kg (1e11 - 3e11)
    # - 苔原：100-500 亿 kg (1e10 - 5e10)
    #
    # 为了游戏平衡和微生物时代的可玩性，使用对数刻度：
    # ================================================================
    
    # 完全覆盖（成熟雨林）所需的生物量基准：1万亿 kg
    DENSITY_BASELINE = 1e12  # 1,000,000,000,000 kg = 1万亿kg
    
    # 不同植被类型的相对基准（相对于 DENSITY_BASELINE）
    # 苔原/苔藓只需要很少的生物量就能形成覆盖
    VEGETATION_TYPE_FACTORS = {
        "moss": 0.001,       # 苔藓：1e9 kg (10亿kg) 即可覆盖
        "herbaceous": 0.01,  # 草本：1e10 kg (100亿kg)
        "woody": 1.0,        # 木本：1e12 kg (1万亿kg)
    }
    
    # 覆盖物更新密度阈值
    DENSITY_THRESHOLDS = {
        "none": 0.0,       # 无植被
        "sparse": 0.001,   # 极稀疏（可能开始出现苔藓）- 10亿kg
        "low": 0.01,       # 低密度（草甸开始形成）- 100亿kg
        "medium": 0.05,    # 中密度（草原/灌木丛）- 500亿kg
        "high": 0.20,      # 高密度（森林开始形成）- 2000亿kg
        "dense": 0.50,     # 密集（成熟森林/雨林）- 5000亿kg
    }
    
    # 极地温度阈值（低于此温度的地块应该是冰雪覆盖）
    POLAR_TEMPERATURE_THRESHOLD = -15.0  # °C
    
    # 用于判断植物类型的关键词
    WOODY_KEYWORDS = ["tree", "木", "森", "wood", "arbor", "shrub", "灌木", "乔木", "针叶", "阔叶", "榕", "杉", "松", "柏", "桦", "杨", "柳"]
    HERBACEOUS_KEYWORDS = ["grass", "草", "herb", "flower", "花", "禾", "蕨", "莎", "萱", "藤", "蔓", "稻"]
    MOSS_LICHEN_KEYWORDS = ["moss", "苔", "藓", "lichen", "地衣", "藻", "菌", "真菌"]
    
    def __init__(self):
        self._plant_type_cache: dict[int, PlantInfo] = {}
    
    def classify_plant_type(self, species: "Species") -> PlantInfo:
        """根据物种描述判断植物类型
        
        【更新】优先使用结构化 growth_form 字段，回退到关键词匹配
        
        Args:
            species: 物种对象
            
        Returns:
            PlantInfo: 植物类型信息
        """
        # 检查缓存
        if species.id in self._plant_type_cache:
            cached = self._plant_type_cache[species.id]
            return PlantInfo(
                species_id=species.id,
                lineage_code=species.lineage_code,
                is_woody=cached.is_woody,
                is_herbaceous=cached.is_herbaceous,
                is_moss_lichen=cached.is_moss_lichen,
                population=0
            )
        
        # 【新增】优先使用结构化字段 growth_form
        growth_form = getattr(species, 'growth_form', None)
        if growth_form:
            is_woody = growth_form in ["tree", "shrub"]
            is_herbaceous = growth_form in ["herb"]
            is_moss_lichen = growth_form in ["moss", "aquatic"]  # 水生藻类归为苔藓类
            
            # 如果结构化字段有效，直接返回
            if any([is_woody, is_herbaceous, is_moss_lichen]):
                info = PlantInfo(
                    species_id=species.id or 0,
                    lineage_code=species.lineage_code,
                    is_woody=is_woody,
                    is_herbaceous=is_herbaceous,
                    is_moss_lichen=is_moss_lichen,
                    population=0
                )
                if species.id:
                    self._plant_type_cache[species.id] = info
                return info
        
        # 回退：组合描述文本进行关键词匹配
        text = f"{species.common_name} {species.latin_name} {species.description}".lower()
        
        # 判断类型
        is_woody = any(kw in text for kw in self.WOODY_KEYWORDS)
        is_herbaceous = any(kw in text for kw in self.HERBACEOUS_KEYWORDS)
        is_moss_lichen = any(kw in text for kw in self.MOSS_LICHEN_KEYWORDS)
        
        # 如果都没匹配到，根据营养级和能力推断
        if not any([is_woody, is_herbaceous, is_moss_lichen]):
            # 光合作用能力且营养级=1通常是植物
            if species.trophic_level == 1.0:
                caps = getattr(species, 'capabilities', []) or []
                if 'photosynthesis' in caps or '光合作用' in caps:
                    # 根据生命阶段推断（如果有）
                    life_form = getattr(species, 'life_form_stage', 0)
                    if life_form <= 2:
                        is_moss_lichen = True  # 早期藻类
                    elif life_form == 3:
                        is_moss_lichen = True  # 苔藓
                    elif life_form >= 5:
                        is_woody = True  # 高级植物可能是木本
                    else:
                        is_herbaceous = True  # 蕨类默认草本
        
        info = PlantInfo(
            species_id=species.id or 0,
            lineage_code=species.lineage_code,
            is_woody=is_woody,
            is_herbaceous=is_herbaceous,
            is_moss_lichen=is_moss_lichen,
            population=0
        )
        
        # 缓存
        if species.id:
            self._plant_type_cache[species.id] = info
        
        return info
    
    def is_plant_species(self, species: "Species") -> bool:
        """判断物种是否为植物（生产者）
        
        【更新】使用 PlantTraitConfig.is_plant 保持一致性
        
        Args:
            species: 物种对象
            
        Returns:
            bool: 是否为植物
        """
        from ..species.trait_config import PlantTraitConfig
        return PlantTraitConfig.is_plant(species)
    
    def calculate_tile_vegetation_stats(
        self,
        tile_id: int,
        habitats: Sequence["HabitatPopulation"],
        species_map: dict[int, "Species"]
    ) -> TileVegetationStats:
        """计算单个地块的植被统计信息
        
        Args:
            tile_id: 地块ID
            habitats: 该地块上的栖息地记录
            species_map: 物种ID到物种对象的映射
            
        Returns:
            TileVegetationStats: 植被统计信息
        """
        woody_pop = 0
        herbaceous_pop = 0
        moss_lichen_pop = 0
        plant_species_count = 0
        total_pop = 0
        
        for habitat in habitats:
            if habitat.tile_id != tile_id:
                continue
            
            species = species_map.get(habitat.species_id)
            if not species:
                continue
            
            # 只统计植物
            if not self.is_plant_species(species):
                continue
            
            plant_info = self.classify_plant_type(species)
            pop = habitat.population
            total_pop += pop
            plant_species_count += 1
            
            if plant_info.is_woody:
                woody_pop += pop
            if plant_info.is_herbaceous:
                herbaceous_pop += pop
            if plant_info.is_moss_lichen:
                moss_lichen_pop += pop
            
            # 如果没有匹配到任何类型，归为草本（最常见的默认）
            if not (plant_info.is_woody or plant_info.is_herbaceous or plant_info.is_moss_lichen):
                herbaceous_pop += pop
        
        # 计算密度
        density = min(1.0, total_pop / self.DENSITY_BASELINE) if total_pop > 0 else 0.0
        
        # 确定主导类型
        if total_pop == 0:
            dominant_type = "none"
        else:
            type_pops = {
                "woody": woody_pop,
                "herbaceous": herbaceous_pop,
                "moss": moss_lichen_pop,
            }
            max_type = max(type_pops, key=type_pops.get)
            max_pop = type_pops[max_type]
            
            # 如果最大类型占比不足50%，则认为是混合型
            if max_pop < total_pop * 0.5:
                dominant_type = "mixed"
            else:
                dominant_type = max_type
        
        return TileVegetationStats(
            tile_id=tile_id,
            total_plant_population=total_pop,
            woody_population=woody_pop,
            herbaceous_population=herbaceous_pop,
            moss_lichen_population=moss_lichen_pop,
            plant_species_count=plant_species_count,
            density=density,
            dominant_type=dominant_type
        )
    
    def determine_cover_type(
        self,
        stats: TileVegetationStats,
        tile: "MapTile"
    ) -> str:
        """根据植被统计和气候条件确定覆盖物类型（30种细分）
        
        Args:
            stats: 植被统计信息
            tile: 地块对象（包含气候信息）
            
        Returns:
            str: 覆盖物类型（30种之一）
        """
        density = stats.density
        dominant = stats.dominant_type
        temp = tile.temperature
        humidity = tile.humidity
        elevation = tile.elevation
        
        # ============================================================
        # 【冰雪类处理】优先级最高 - 6种细分
        # ============================================================
        if temp < self.POLAR_TEMPERATURE_THRESHOLD:
            return self._get_ice_cover(temp, elevation, humidity)
        
        # ============================================================
        # 【海洋/湖泊冰盖处理】
        # ============================================================
        if tile.biome in ["深海", "浅海", "海岸"]:
            if temp < -5:
                return "海冰"
            return "水域"
        
        if tile.biome == "湖泊":
            if temp < -5:
                return "冰湖"
            return "水域"
        
        # ============================================================
        # 【无植被/极稀疏】- 荒漠类 6种
        # ============================================================
        if density < self.DENSITY_THRESHOLDS["sparse"]:
            return self._get_barren_cover(temp, humidity, elevation)
        
        # ============================================================
        # 【极稀疏植被】- 苔原或荒漠边缘
        # ============================================================
        if density < self.DENSITY_THRESHOLDS["low"]:
            if temp < 0:
                return "苔原"
            elif temp < 5 and elevation > 2000:
                return "高山草甸"
            elif humidity < 0.15:
                return "沙漠"
            elif humidity < 0.25:
                return "戈壁"
            else:
                return "裸地"
        
        # ============================================================
        # 【低密度植被】- 草甸/苔原形成
        # ============================================================
        if density < self.DENSITY_THRESHOLDS["medium"]:
            if temp < -5:
                return "苔原"
            elif temp < 5 and elevation > 1500:
                return "高山草甸"
            elif dominant == "moss":
                return "苔原" if temp < 10 else "苔藓林"
            elif dominant in ["herbaceous", "mixed", "none"]:
                if humidity > 0.75 and elevation < 100:
                    return "湿地"
                return "草甸"
            else:  # woody
                return "灌木丛"
        
        # ============================================================
        # 【中密度植被】- 草原/灌木丛
        # ============================================================
        if density < self.DENSITY_THRESHOLDS["high"]:
            if temp < -5:
                return "苔原"
            elif temp < 5 and elevation > 1500:
                return "高山草甸"
            elif dominant == "woody":
                if temp < 5:
                    return "针叶林"
                else:
                    return "灌木丛"
            elif dominant == "herbaceous":
                if humidity > 0.80 and elevation < 50:
                    return "湿地"
                elif humidity > 0.65:
                    return "草甸"
                elif temp > 20 and humidity < 0.5:
                    return "稀树草原"
                else:
                    return "草原"
            else:  # mixed or moss
                return "混合林"
        
        # ============================================================
        # 【高密度植被】- 森林开始形成
        # ============================================================
        if density < self.DENSITY_THRESHOLDS["dense"]:
            return self._get_forest_cover(temp, humidity, dominant, elevation)
        
        # ============================================================
        # 【密集植被】- 成熟森林
        # ============================================================
        return self._get_dense_forest_cover(temp, humidity, dominant, elevation)
    
    def _get_ice_cover(self, temp: float, elevation: float, humidity: float) -> str:
        """获取冰雪类覆盖物（6种细分）
        
        根据温度和海拔精细划分冰雪类型：
        - 极高山 + 极寒 -> 冰川
        - 高山 + 寒冷 -> 冰帽
        - 极地平原 -> 冰原
        - 边缘区域 -> 冻土
        """
        if temp < -30:
            # 极寒区
            if elevation > 4000:
                return "冰川"
            elif elevation > 2500:
                return "冰帽"
            else:
                return "冰原"
        elif temp < -20:
            # 严寒区
            if elevation > 3500:
                return "冰川"
            elif elevation > 2000:
                return "冰帽"
            else:
                return "冰原"
        else:  # -20 ~ -15°C
            # 寒冷边缘
            if elevation > 3000:
                return "冰帽"
            elif humidity < 0.3:
                return "冻土"
            else:
                return "冻土"
    
    def _get_barren_cover(self, temp: float, humidity: float, elevation: float) -> str:
        """获取无植被时的覆盖物类型（6种细分）
        
        根据气候条件精细划分荒漠类型：
        - 极寒 + 高海拔 -> 冰川/冰帽
        - 寒冷 -> 冻土（永久/季节性）
        - 极干旱 -> 沙漠/沙丘
        - 干旱 -> 戈壁
        - 高盐 -> 盐碱地
        - 高海拔 -> 裸岩
        - 其他 -> 裸地
        """
        # 寒冷区域边缘（-15°C 到 0°C）
        if temp < -10:
            if elevation > 3500:
                return "冰川"
            elif elevation > 2500:
                return "冰帽"
            return "冻土"
        elif temp < -5:
            if elevation > 3000:
                return "冰帽"
            return "冻土"
        elif temp < 0:
            return "季节冻土"
        
        # 干旱区域
        if humidity < 0.10:
            # 极端干旱
            if temp > 25:
                return "沙丘"  # 热沙漠的流动沙丘
            return "沙漠"
        elif humidity < 0.20:
            return "沙漠"
        elif humidity < 0.30:
            if temp > 20:
                return "戈壁"
            return "戈壁"
        elif humidity < 0.40:
            # 半干旱，可能有盐碱化
            if elevation < 200 and temp > 15:
                return "盐碱地"
            return "戈壁"
        
        # 高海拔裸露
        if elevation > 4000:
            return "裸岩"
        elif elevation > 3000 and temp < 10:
            return "裸岩"
        
        return "裸地"
    
    def _get_forest_cover(self, temp: float, humidity: float, dominant: str, elevation: float) -> str:
        """获取中高密度植被的森林类型（7种细分）"""
        # 高湿度低洼区 -> 湿地类
        if humidity > 0.85 and elevation < 50:
            if dominant == "woody":
                return "沼泽"
            else:
                return "湿地"
        
        # 沿海低海拔高湿度 -> 红树林
        if elevation < 10 and humidity > 0.70 and temp > 18:
            return "红树林"
        
        if dominant == "woody":
            if temp > 22 and humidity > 0.65:
                return "常绿林"  # 亚热带常绿林
            elif temp < 3:
                return "针叶林"
            elif temp < 10:
                return "混合林"
            else:
                return "阔叶林"
        elif dominant == "herbaceous":
            if humidity > 0.80:
                return "湿地"
            elif temp > 20 and humidity < 0.5:
                return "稀树草原"
            else:
                return "草原"
        elif dominant == "moss":
            return "苔藓林"
        else:  # mixed
            return "混合林"
    
    def _get_dense_forest_cover(self, temp: float, humidity: float, dominant: str, elevation: float) -> str:
        """获取密集植被的森林类型（7种细分）"""
        # 高湿度低洼区 -> 湿地类
        if humidity > 0.85 and elevation < 50:
            if dominant == "woody":
                return "沼泽"
            elif humidity > 0.90:
                return "泥炭地"
            else:
                return "湿地"
        
        # 沿海低海拔高湿度 -> 红树林
        if elevation < 10 and humidity > 0.70 and temp > 20:
            return "红树林"
        
        # 高山云雾带
        if elevation > 1500 and elevation < 3000 and humidity > 0.75 and temp < 15:
            return "云雾林"
        
        if dominant == "woody" or dominant == "mixed":
            # 热带高温高湿 -> 雨林
            if temp > 24 and humidity > 0.70:
                return "雨林"
            # 亚热带 -> 常绿林
            elif temp > 18 and humidity > 0.55:
                return "常绿林"
            # 寒冷地区 -> 针叶林
            elif temp < 3:
                return "针叶林"
            # 冷温带 -> 混合林
            elif temp < 10:
                return "混合林"
            # 温带 -> 阔叶林
            else:
                return "阔叶林"
        elif dominant == "herbaceous":
            if humidity > 0.80:
                return "湿地"
            return "草原"
        elif dominant == "moss":
            return "苔藓林"
        else:
            return "混合林"
    
    def update_vegetation_cover(
        self,
        tiles: Sequence["MapTile"],
        habitats: Sequence["HabitatPopulation"],
        species_map: dict[int, "Species"]
    ) -> list["MapTile"]:
        """更新所有地块的植被覆盖
        
        Args:
            tiles: 地块列表
            habitats: 栖息地记录列表
            species_map: 物种ID到物种对象的映射
            
        Returns:
            list[MapTile]: 更新后的地块列表（仅包含有变化的地块）
        """
        # 按地块ID分组栖息地
        tile_habitats: dict[int, list["HabitatPopulation"]] = {}
        for habitat in habitats:
            if habitat.tile_id not in tile_habitats:
                tile_habitats[habitat.tile_id] = []
            tile_habitats[habitat.tile_id].append(habitat)
        
        updated_tiles: list["MapTile"] = []
        stats_summary = {
            "total_tiles": len(tiles),
            "updated_tiles": 0,
            "cover_changes": {}
        }
        
        for tile in tiles:
            # 水域跳过
            if tile.biome in ["深海", "浅海", "海岸", "湖泊"]:
                continue
            
            tile_id = tile.id
            if tile_id is None:
                continue
            
            # 计算该地块的植被统计
            tile_habitat_list = tile_habitats.get(tile_id, [])
            stats = self.calculate_tile_vegetation_stats(tile_id, tile_habitat_list, species_map)
            
            # 确定新的覆盖物类型
            new_cover = self.determine_cover_type(stats, tile)
            
            # 如果覆盖物有变化，更新地块
            if new_cover != tile.cover:
                old_cover = tile.cover
                tile.cover = new_cover
                updated_tiles.append(tile)
                
                # 统计变化
                change_key = f"{old_cover}->{new_cover}"
                stats_summary["cover_changes"][change_key] = stats_summary["cover_changes"].get(change_key, 0) + 1
        
        stats_summary["updated_tiles"] = len(updated_tiles)
        
        if updated_tiles:
            logger.info(f"[植被覆盖] 更新了 {len(updated_tiles)} 个地块的覆盖物")
            for change, count in stats_summary["cover_changes"].items():
                logger.debug(f"  {change}: {count} 个")
        
        return updated_tiles
    
    def get_global_vegetation_summary(
        self,
        tiles: Sequence["MapTile"],
        habitats: Sequence["HabitatPopulation"],
        species_map: dict[int, "Species"]
    ) -> dict:
        """获取全球植被覆盖摘要
        
        Args:
            tiles: 地块列表
            habitats: 栖息地记录列表
            species_map: 物种ID到物种对象的映射
            
        Returns:
            dict: 植被覆盖统计信息
        """
        cover_counts: dict[str, int] = {}
        total_plant_population = 0
        total_plant_species = set()
        
        # 按地块ID分组栖息地
        tile_habitats: dict[int, list["HabitatPopulation"]] = {}
        for habitat in habitats:
            if habitat.tile_id not in tile_habitats:
                tile_habitats[habitat.tile_id] = []
            tile_habitats[habitat.tile_id].append(habitat)
        
        for tile in tiles:
            cover = tile.cover
            cover_counts[cover] = cover_counts.get(cover, 0) + 1
            
            if tile.id and tile.id in tile_habitats:
                for habitat in tile_habitats[tile.id]:
                    species = species_map.get(habitat.species_id)
                    if species and self.is_plant_species(species):
                        total_plant_population += habitat.population
                        total_plant_species.add(habitat.species_id)
        
        return {
            "cover_distribution": cover_counts,
            "total_plant_population": total_plant_population,
            "plant_species_count": len(total_plant_species),
            "vegetated_tile_count": sum(
                v for k, v in cover_counts.items() 
                if k not in ["裸地", "沙漠", "冰川", "水域", "Barren", "Desert", "Glacier"]
            ),
            "barren_tile_count": cover_counts.get("裸地", 0) + cover_counts.get("Barren", 0),
        }


# 全局单例
vegetation_cover_service = VegetationCoverService()

