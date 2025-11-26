"""地图配色系统 - 支持五种视图模式的综合配色算法"""

from __future__ import annotations

from typing import Literal

from ...models.environment import MapTile

ViewMode = Literal["terrain", "terrain_type", "elevation", "biodiversity", "climate"]


class MapColoringService:
    """地图配色服务，根据视图模式和地块属性计算显示颜色"""

    @staticmethod
    def get_color(
        tile: MapTile,
        sea_level: float,
        view_mode: ViewMode,
        biodiversity_score: float = 0.0,
    ) -> str:
        """
        根据视图模式计算地块颜色
        """
        if view_mode == "terrain":
            return MapColoringService._terrain_color(tile, sea_level)
        elif view_mode == "terrain_type":
            return MapColoringService._terrain_type_color(tile, sea_level)
        elif view_mode == "elevation":
            return MapColoringService._elevation_color(tile, sea_level)
        elif view_mode == "biodiversity":
            return MapColoringService._biodiversity_color(tile, sea_level, biodiversity_score)
        elif view_mode == "climate":
            return MapColoringService._climate_color(tile, sea_level)
        else:
            return "#5C82FF"  # 默认蓝色
    
    @staticmethod
    def _blend_colors(color1: str, color2: str, weight1: float) -> str:
        """混合两种颜色"""
        weight2 = 1.0 - weight1
        
        r1 = int(color1[1:3], 16)
        g1 = int(color1[3:5], 16)
        b1 = int(color1[5:7], 16)
        
        r2 = int(color2[1:3], 16)
        g2 = int(color2[3:5], 16)
        b2 = int(color2[5:7], 16)
        
        r = int(r1 * weight1 + r2 * weight2)
        g = int(g1 * weight1 + g2 * weight2)
        b = int(b1 * weight1 + b2 * weight2)
        
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _get_level_info(relative_elev: float) -> tuple[str, str]:
        """
        获取海拔分级信息 (颜色, 名称)
        符合用户定义的 20 级标准
        """
        # 海洋 (01-06)
        if relative_elev < 0:
            if relative_elev < -5000: return ("#000510", "01 深海平原/海沟")
            if relative_elev < -2000: return ("#001030", "02 深海盆地")
            if relative_elev < -800:  return ("#002555", "03 海洋丘陵")
            if relative_elev < -400:  return ("#004080", "04 大陆坡/深湖区")
            if relative_elev < -100:  return ("#0066aa", "05 浅水区")
            return ("#0088cc", "06 近岸水域")

        # 核心宜居带 (07-14)
        if relative_elev < 20:   return ("#5d5243", "07 水岸低地") # 滩涂/沼泽
        if relative_elev < 100:  return ("#7a6b53", "08 冲积平原") # 肥沃土地
        if relative_elev < 300:  return ("#968566", "09 低海拔平原") # 广阔低地
        if relative_elev < 600:  return ("#b09f7a", "10 起伏丘陵") # 适度起伏
        if relative_elev < 900:  return ("#c4b48e", "11 低高原/台地") # 
        if relative_elev < 1200: return ("#d6c7a1", "12 内陆高地") # 
        if relative_elev < 1600: return ("#b3a385", "13 亚山麓带") # 接近山脉
        if relative_elev < 2000: return ("#91846e", "14 高地林线") # 树木上限

        # 高海拔与极地 (15-20)
        if relative_elev < 3000: return ("#736858", "15 低山脉")
        if relative_elev < 4000: return ("#595046", "16 中山脉")
        if relative_elev < 5000: return ("#423b35", "17 高山荒漠")
        if relative_elev < 6000: return ("#8d8d8d", "18 雪线区")
        if relative_elev < 7500: return ("#cfcfcf", "19 冰川/山峰")
        return ("#ffffff", "20 极地之巅")

    @staticmethod
    def _terrain_color(tile: MapTile, sea_level: float) -> str:
        """
        基本地图模式：
        底色：严格的地质/海拔颜色（Barren Earth style）
        覆盖物：仅显示非植物覆盖物（如冰川、湖泊），植物层由前端独立渲染
        """
        relative_elev = tile.elevation - sea_level
        
        # 1. 湖泊特殊处理
        if getattr(tile, "is_lake", False):
            # 淡水湖（盐度<5‰）
            if getattr(tile, "salinity", 35.0) < 5:
                return "#4FC3F7"  # 浅蓝色（淡水湖）
            else:
                return "#29B6F6"  # 蓝色（咸水湖）
        
        # 2. 获取基础地质/海拔颜色 (Base Geology)
        base_color, _ = MapColoringService._get_level_info(relative_elev)
        
        # 3. 覆盖物微调 (Overlay)
        # 注意：不再渲染森林/草原，因为现在有独立的 Vegetation Layer
        cover = tile.cover
        
        # 冰川/雪原 (Ice/Snow) - 无论海拔如何，如果有冰川覆盖，强制白色
        # (虽然高海拔通常就是冰川色，但防止低海拔冰期)
        if cover in ["冰川", "Glacier"]:
            return "#F0F8FF"
            
        # 沙漠 (Desert) - 如果是沙漠地貌，稍微染黄一点，但保持基础地形感
        # 实际上，基础色 17 高山荒漠 已经是石头色。
        # 低海拔沙漠 (e.g. 09 平原但干旱)
        if cover in ["沙漠", "Desert"] and relative_elev > 0:
             return MapColoringService._blend_colors("#D2B48C", base_color, 0.6)
        
        # 裸地 (Barren) - 保持原色，或者稍微灰一点
        if cover in ["裸地", "Barren"] and relative_elev > 0:
            return base_color # Use the geology color directly

        # 沼泽 (Wetland) - 稍微加深
        if cover in ["沼泽", "Wetland"] and relative_elev > 0:
             return MapColoringService._blend_colors("#2f3a2f", base_color, 0.4)

        return base_color

    @staticmethod
    def _terrain_type_color(tile: MapTile, sea_level: float) -> str:
        """地形图模式：纯地形分类着色"""
        # 复用标准分级颜色
        relative_elev = tile.elevation - sea_level
        if getattr(tile, "is_lake", False):
            return "#4FC3F7"
        color, _ = MapColoringService._get_level_info(relative_elev)
        return color

    @staticmethod
    def _elevation_color(tile: MapTile, sea_level: float) -> str:
        """海拔图模式：与 Terrain 类似，但不受覆盖物影响"""
        relative_elev = tile.elevation - sea_level
        if getattr(tile, "is_lake", False):
            return "#4FC3F7"
        color, _ = MapColoringService._get_level_info(relative_elev)
        return color

    @staticmethod
    def _biodiversity_color(tile: MapTile, sea_level: float, score: float) -> str:
        """生物多样性热力图模式"""
        base_color = MapColoringService._terrain_color(tile, sea_level)
        score = max(0.0, min(1.0, score))
        
        if score < 0.1: overlay = "#081d58"
        elif score < 0.2: overlay = "#253494"
        elif score < 0.3: overlay = "#225ea8"
        elif score < 0.4: overlay = "#1d91c0"
        elif score < 0.5: overlay = "#41b6c4"
        elif score < 0.6: overlay = "#7fcdbb"
        elif score < 0.7: overlay = "#c7e9b4"
        elif score < 0.8: overlay = "#ffffcc"
        elif score < 0.9: overlay = "#fd8d3c"
        else: overlay = "#e31a1c"
        
        return MapColoringService._blend_colors(overlay, base_color, 0.6)

    @staticmethod
    def _climate_color(tile: MapTile, sea_level: float) -> str:
        """气候图模式"""
        terrain_color = MapColoringService._terrain_color(tile, sea_level)
        climate = getattr(tile, "climate_zone", "温带")
        temperature = tile.temperature
        
        base_colors = {
            "极地": "#e0f3ff", "Polar": "#e0f3ff",
            "寒带": "#a8d8ea", "Cold": "#a8d8ea",
            "温带": "#66bb6a", "Temperate": "#66bb6a",
            "亚热带": "#fdd835", "Subtropical": "#fdd835",
            "热带": "#ff6f00", "Tropical": "#ff6f00",
        }
        
        climate_overlay = base_colors.get(climate, "#66bb6a")
        if temperature < -20: climate_overlay = "#c5e3f6"
        elif temperature > 35: climate_overlay = "#d32f2f"
        
        return MapColoringService._blend_colors(climate_overlay, terrain_color, 0.5)

    @staticmethod
    def classify_terrain_type(relative_elevation: float, is_lake: bool = False) -> str:
        """根据相对海拔分类地形类型 (返回用户定义的 20 级名称)"""
        if is_lake:
            # 湖泊根据深度判断，或直接返回湖泊
            # 这里为了匹配Table，如果是浅水区(05)但is_lake=True，可能叫"深湖区"(04)或"浅水区"(05)
            # 简单起见，返回通用的湖泊，或者根据深度
            if relative_elevation < -400: return "04 大陆坡/深湖区"
            if relative_elevation < -100: return "05 浅水区" 
            return "05 浅水区(湖)"

        _, name = MapColoringService._get_level_info(relative_elevation)
        return name

    @staticmethod
    def infer_climate_zone(latitude_normalized: float, elevation: float) -> str:
        """推断气候带"""
        elevation_adjustment = elevation / 1000 * 0.1
        adjusted_lat = min(1.0, latitude_normalized + elevation_adjustment)
        
        if adjusted_lat < 0.2: return "热带"
        elif adjusted_lat < 0.35: return "亚热带"
        elif adjusted_lat < 0.6: return "温带"
        elif adjusted_lat < 0.8: return "寒带"
        else: return "极地"


# 单例实例
map_coloring_service = MapColoringService()
