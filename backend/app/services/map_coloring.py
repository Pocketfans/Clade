"""地图配色系统 - 支持五种视图模式的综合配色算法"""

from __future__ import annotations

from typing import Literal

from ..models.environment import MapTile

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
        
        Args:
            tile: 地块数据
            sea_level: 当前海平面高度
            view_mode: 视图模式
            biodiversity_score: 生物多样性评分（0-1，仅biodiversity模式使用）
        
        Returns:
            hex格式颜色值（如 "#7CB342"）
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
        """
        混合两种颜色
        
        Args:
            color1: 第一种颜色（hex格式）
            color2: 第二种颜色（hex格式）
            weight1: 第一种颜色的权重（0-1）
        
        Returns:
            混合后的颜色（hex格式）
        """
        weight2 = 1.0 - weight1
        
        # 解析颜色
        r1 = int(color1[1:3], 16)
        g1 = int(color1[3:5], 16)
        b1 = int(color1[5:7], 16)
        
        r2 = int(color2[1:3], 16)
        g2 = int(color2[3:5], 16)
        b2 = int(color2[5:7], 16)
        
        # 混合
        r = int(r1 * weight1 + r2 * weight2)
        g = int(g1 * weight1 + g2 * weight2)
        b = int(b1 * weight1 + b2 * weight2)
        
        # 返回hex格式
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _terrain_color(tile: MapTile, sea_level: float) -> str:
        """基本地图模式：综合地形+海拔+覆盖物+气候带"""
        relative_elev = tile.elevation - sea_level
        
        # 湖泊特殊处理
        if getattr(tile, "is_lake", False):
            # 淡水湖（盐度<5‰）
            if getattr(tile, "salinity", 35.0) < 5:
                return "#4FC3F7"  # 浅蓝色（淡水湖）
            else:
                return "#29B6F6"  # 蓝色（咸水湖）
        
        # 海洋地形 - 细化分级
        if relative_elev < 0:
            if relative_elev < -6000:  # <-6000m（极深海沟）
                return "#000511"  # 极深蓝黑
            elif relative_elev < -4000:  # -6000~-4000m（深海沟）
                return "#001122"  # 深蓝黑
            elif relative_elev < -2000:  # -4000~-2000m（深海）
                return "#001a33"  # 深蓝
            elif relative_elev < -1500:  # -2000~-1500m（中深海）
                return "#002a4d"  # 中深蓝
            elif relative_elev < -1000:  # -1500~-1000m（中层海）
                return "#003d66"  # 蓝
            elif relative_elev < -600:  # -1000~-600m
                return "#005080"  # 中蓝
            elif relative_elev < -200:  # -600~-200m（浅海）
                return "#0066aa"  # 浅蓝
            elif relative_elev < -50:  # -200~-50m（海岸浅海）
                return "#4da6d9"  # 浅天蓝
            else:  # -50~0m（超浅水区）
                return "#80c0f2"  # 淡蓝
        
        # 陆地地形 - 优先显示覆盖物
        cover = tile.cover
        climate = getattr(tile, "climate_zone", "温带")
        
        # 冰川覆盖
        if cover in ["冰川", "Glacier"]:
            return "#F0F8FF"
        
        # 森林覆盖 - 根据气候带调整色调
        if cover in ["森林", "Forest"]:
            if climate in ["热带", "Tropical"]:
                return "#2ECC40"  # 鲜艳绿（热带雨林）
            elif climate in ["亚热带", "Subtropical"]:
                return "#3D9970"  # 中绿（亚热带森林）
            elif climate in ["温带", "Temperate"]:
                return "#2C5F2D"  # 暗绿（温带森林）
            else:  # 寒带
                return "#1B4D3E"  # 深绿（针叶林）
        
        # 沙漠覆盖
        if cover in ["沙漠", "Desert"]:
            return "#D2B48C"
        
        # 草甸覆盖
        if cover in ["草甸", "Grassland"]:
            if climate in ["热带", "Tropical"]:
                return "#B8D56A"  # 浅黄绿（热带草原）
            else:
                return "#9ACD32"  # 黄绿（温带草原）
        
        # 沼泽覆盖
        if cover in ["沼泽", "Wetland"]:
            return "#556B2F"
        
        # 苔原覆盖
        if cover in ["苔原", "Tundra"]:
            return "#8FBC8F"
        
        # 裸地覆盖
        if cover in ["裸地", "Barren"]:
            return "#A9A9A9"
        
        # 无明显覆盖物 - 按海拔和气候渐变（细化分级）
        if relative_elev < 50:  # 0-50m（低地平原）
            if climate in ["热带", "Tropical"]:
                return "#7CB342"  # 绿色平原
            elif climate in ["温带", "Temperate"]:
                return "#9E9D24"  # 黄绿平原
            else:
                return "#827717"  # 褐色平原
        elif relative_elev < 200:  # 50-200m（平原）
            return "#9ACD32"  # 黄绿平原
        elif relative_elev < 400:  # 200-400m（低丘陵）
            return "#A0A520"  # 黄绿
        elif relative_elev < 600:  # 400-600m（丘陵）
            return "#B8A520"  # 土黄
        elif relative_elev < 800:  # 600-800m（高丘陵）
            return "#C0A853"  # 浅褐
        elif relative_elev < 1000:  # 800-1000m（低山）
            return "#A89060"  # 褐色
        elif relative_elev < 3000:  # 1000-3000m（山地）
            return "#8B7355"  # 深褐
        elif relative_elev < 5000:  # 3000-5000m（高山）
            return "#B0B0B0"  # 灰色
        else:  # >5000m（极高山）
            return "#F0F0F0"  # 雪白

    @staticmethod
    def _terrain_type_color(tile: MapTile, sea_level: float) -> str:
        """地形图模式：纯地形分类着色"""
        relative_elev = tile.elevation - sea_level
        
        # 湖泊特殊颜色
        if getattr(tile, "is_lake", False):
            return "#4FC3F7"  # 湖泊（浅蓝）
        
        if relative_elev < -6000:
            return "#00050f"  # 海沟（极深蓝黑）
        elif relative_elev < -3000:
            return "#001f3f"  # 深海（深蓝）
        elif relative_elev < -200:
            return "#0074D9"  # 浅海（蓝）
        elif relative_elev < 0:
            return "#7FDBFF"  # 海岸（浅蓝）
        elif relative_elev < 200:
            return "#66BB6A"  # 平原（绿）
        elif relative_elev < 1000:
            return "#FDD835"  # 丘陵（黄）
        elif relative_elev < 3000:
            return "#A1887F"  # 山地（棕）
        elif relative_elev < 5000:
            return "#BDBDBD"  # 高山（灰）
        else:
            return "#FFFFFF"  # 极高山（白）

    @staticmethod
    def _elevation_color(tile: MapTile, sea_level: float) -> str:
        """海拔图模式：海拔渐变色阶（细化分级），叠加基本地形"""
        relative_elev = tile.elevation - sea_level
        
        # 获取基本地形颜色作为底色
        base_color = MapColoringService._terrain_color(tile, sea_level)
        
        # 深海到极高山的渐变色阶（按细化分级）
        # 海洋分级
        if relative_elev < -6000:  # <-6000m
            overlay = "#1a0033"  # 深紫（极深海沟）
        elif relative_elev < -4000:  # -6000~-4000m
            overlay = "#2d004d"  # 紫
        elif relative_elev < -2000:  # -4000~-2000m
            overlay = "#000066"  # 深蓝
        elif relative_elev < -1500:  # -2000~-1500m
            overlay = "#000099"  # 蓝
        elif relative_elev < -1000:  # -1500~-1000m
            overlay = "#0000cc"  # 亮蓝
        elif relative_elev < -600:  # -1000~-600m
            overlay = "#0033ff"  # 中蓝
        elif relative_elev < -200:  # -600~-200m
            overlay = "#0066ff"  # 浅蓝
        elif relative_elev < -50:  # -200~-50m
            overlay = "#0099ff"  # 天蓝
        elif relative_elev < 0:  # -50~0m
            overlay = "#00ccff"  # 青蓝（海平面）
        # 陆地分级
        elif relative_elev < 50:  # 0-50m
            overlay = "#00ff99"  # 青绿（海平面附近）
        elif relative_elev < 200:  # 50-200m
            overlay = "#66ff66"  # 浅绿
        elif relative_elev < 400:  # 200-400m
            overlay = "#99ff33"  # 黄绿
        elif relative_elev < 600:  # 400-600m
            overlay = "#ccff00"  # 柠檬黄
        elif relative_elev < 800:  # 600-800m
            overlay = "#ffff00"  # 黄
        elif relative_elev < 1000:  # 800-1000m
            overlay = "#ffdd00"  # 金黄
        elif relative_elev < 3000:  # 1000-3000m
            overlay = "#ffaa00"  # 橙黄
        elif relative_elev < 5000:  # 3000-5000m
            overlay = "#ff6600"  # 橙红
        else:  # >5000m
            overlay = "#ffffff"  # 白（极高山）
        
        # 混合颜色：70%海拔色 + 30%地形色
        return MapColoringService._blend_colors(overlay, base_color, 0.7)

    @staticmethod
    def _biodiversity_color(tile: MapTile, sea_level: float, score: float) -> str:
        """生物多样性热力图模式：从冷色到暖色，叠加基本地形"""
        # 获取基本地形颜色作为底色
        base_color = MapColoringService._terrain_color(tile, sea_level)
        
        # score: 0-1 归一化的多样性评分
        score = max(0.0, min(1.0, score))
        
        if score < 0.1:
            overlay = "#081d58"  # 深蓝（极低多样性）
        elif score < 0.2:
            overlay = "#253494"  # 蓝
        elif score < 0.3:
            overlay = "#225ea8"  # 亮蓝
        elif score < 0.4:
            overlay = "#1d91c0"  # 青蓝
        elif score < 0.5:
            overlay = "#41b6c4"  # 青
        elif score < 0.6:
            overlay = "#7fcdbb"  # 青绿
        elif score < 0.7:
            overlay = "#c7e9b4"  # 黄绿
        elif score < 0.8:
            overlay = "#ffffcc"  # 浅黄
        elif score < 0.9:
            overlay = "#fd8d3c"  # 橙
        else:
            overlay = "#e31a1c"  # 红（高多样性）
        
        # 混合颜色：60%生物多样性色 + 40%地形色
        return MapColoringService._blend_colors(overlay, base_color, 0.6)

    @staticmethod
    def _climate_color(tile: MapTile, sea_level: float) -> str:
        """气候图模式：温度带着色，叠加基本地形"""
        # 获取基本地形颜色作为底色
        terrain_color = MapColoringService._terrain_color(tile, sea_level)
        
        climate = getattr(tile, "climate_zone", "温带")
        temperature = tile.temperature
        
        # 基于气候带的基础色
        base_colors = {
            "极地": "#e0f3ff",  # 浅蓝白
            "Polar": "#e0f3ff",
            "寒带": "#a8d8ea",  # 蓝
            "Cold": "#a8d8ea",
            "温带": "#66bb6a",  # 绿
            "Temperate": "#66bb6a",
            "亚热带": "#fdd835",  # 黄
            "Subtropical": "#fdd835",
            "热带": "#ff6f00",  # 橙红
            "Tropical": "#ff6f00",
        }
        
        # 使用气候带作为主要依据
        climate_overlay = base_colors.get(climate, "#66bb6a")
        
        # 根据温度微调（极端温度增强色调）
        if temperature < -20:
            climate_overlay = "#c5e3f6"  # 极冷
        elif temperature > 35:
            climate_overlay = "#d32f2f"  # 极热
        
        # 混合颜色：50%气候色 + 50%地形色
        return MapColoringService._blend_colors(climate_overlay, terrain_color, 0.5)

    @staticmethod
    def classify_terrain_type(relative_elevation: float, is_lake: bool = False) -> str:
        """根据相对海拔分类地形类型"""
        if is_lake:
            return "湖泊"
        
        if relative_elevation < -6000:
            return "海沟"
        elif relative_elevation < -3000:
            return "深海"
        elif relative_elevation < -200:
            return "浅海"
        elif relative_elevation < 0:
            return "海岸"
        elif relative_elevation < 200:
            return "平原"
        elif relative_elevation < 1000:
            return "丘陵"
        elif relative_elevation < 3000:
            return "山地"
        elif relative_elevation < 5000:
            return "高山"
        else:
            return "极高山"

    @staticmethod
    def infer_climate_zone(latitude_normalized: float, elevation: float) -> str:
        """
        推断气候带
        
        Args:
            latitude_normalized: 归一化纬度（0=赤道，1=极地）
            elevation: 海拔高度（米）
        
        Returns:
            气候带名称
        """
        # 海拔每升高1000m，温度下降约6°C，相当于向极地移动约10°纬度
        elevation_adjustment = elevation / 1000 * 0.1
        adjusted_lat = min(1.0, latitude_normalized + elevation_adjustment)
        
        if adjusted_lat < 0.2:
            return "热带"
        elif adjusted_lat < 0.35:
            return "亚热带"
        elif adjusted_lat < 0.6:
            return "温带"
        elif adjusted_lat < 0.8:
            return "寒带"
        else:
            return "极地"


# 单例实例
map_coloring_service = MapColoringService()

