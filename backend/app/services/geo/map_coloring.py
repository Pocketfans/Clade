"""地图配色系统 - 支持五种视图模式的综合配色算法

配色方案设计原则：
1. 海洋：深蓝黑 → 浅蓝绿，10级精细渐变，深度感强
2. 陆地低海拔：沿海绿 → 草地黄绿，8级自然过渡
3. 陆地中海拔：台地棕 → 山麓褐，8级渐变
4. 高海拔雪山：岩石灰 → 纯净雪白，9级冷色调
5. 共35级，每级颜色区分度高，视觉丰富精细
"""

from __future__ import annotations

from typing import Literal

from ...models.environment import MapTile

ViewMode = Literal["terrain", "terrain_type", "elevation", "biodiversity", "climate"]


class MapColoringService:
    """地图配色服务，根据视图模式和地块属性计算显示颜色"""
    
    # ============== 35级地形颜色表 ==============
    LEVEL_COLORS = {
        # ========== 海洋层级 (01-10) ==========
        # 从深海沟到近岸浅水的10级精细渐变
        1:  ("#050a12", "01 超深海沟"),          # 深渊黑蓝 < -8000m
        2:  ("#081425", "02 深海沟"),            # 深邃藏蓝 -8000 ~ -6000m
        3:  ("#0c1e38", "03 深海平原"),          # 深海蓝 -6000 ~ -4000m
        4:  ("#12294a", "04 深海盆地"),          # 海底蓝 -4000 ~ -2500m
        5:  ("#1a3d66", "05 海洋丘陵"),          # 中深蓝 -2500 ~ -1500m
        6:  ("#235080", "06 大陆坡深部"),        # 海蓝 -1500 ~ -800m
        7:  ("#2d6699", "07 大陆坡"),            # 中蓝 -800 ~ -400m
        8:  ("#3a7db3", "08 大陆架深部"),        # 明亮蓝 -400 ~ -150m
        9:  ("#4a94cc", "09 大陆架"),            # 浅海蓝 -150 ~ -50m
        10: ("#5dade2", "10 近岸浅水"),          # 浅蓝绿 -50 ~ 0m
        
        # ========== 陆地低海拔 (11-18) ==========
        # 从海岸到丘陵的8级绿色系渐变
        11: ("#3d6b4a", "11 潮间带"),            # 深湿地绿 0 ~ 10m
        12: ("#457852", "12 沿海低地"),          # 湿地绿 10 ~ 30m
        13: ("#4e855b", "13 冲积平原"),          # 肥沃绿 30 ~ 80m
        14: ("#589264", "14 低海拔平原"),        # 草地绿 80 ~ 150m
        15: ("#649f6d", "15 平原"),              # 明亮绿 150 ~ 300m
        16: ("#72ab76", "16 缓坡丘陵"),          # 黄绿 300 ~ 500m
        17: ("#82b67f", "17 丘陵"),              # 浅黄绿 500 ~ 750m
        18: ("#94c088", "18 高丘陵"),            # 橄榄黄绿 750 ~ 1000m
        
        # ========== 陆地中海拔 (19-26) ==========
        # 从台地到山麓的8级棕色系渐变
        19: ("#a6c48e", "19 台地"),              # 黄橄榄 1000 ~ 1300m
        20: ("#b5c58e", "20 低高原"),            # 金绿 1300 ~ 1600m
        21: ("#c4c38d", "21 高原"),              # 土黄绿 1600 ~ 1900m
        22: ("#ccbb86", "22 亚山麓"),            # 浅褐黄 1900 ~ 2200m
        23: ("#c9ab78", "23 山麓带"),            # 浅褐 2200 ~ 2600m
        24: ("#bf9a6a", "24 低山"),              # 中褐 2600 ~ 3000m
        25: ("#b08a5c", "25 中低山"),            # 褐色 3000 ~ 3500m
        26: ("#9f7a50", "26 中山"),              # 深褐 3500 ~ 4000m
        
        # ========== 高海拔雪山 (27-35) ==========
        # 从高山到极地之巅的9级灰白色系渐变
        27: ("#8d6c47", "27 中高山"),            # 岩石褐 4000 ~ 4500m
        28: ("#7a6350", "28 高山"),              # 深岩石 4500 ~ 5000m
        29: ("#6e6a5e", "29 雪线区"),            # 岩石灰褐 5000 ~ 5500m
        30: ("#78787a", "30 高寒荒漠"),          # 冷岩灰 5500 ~ 6000m
        31: ("#8a8e94", "31 永久冰雪"),          # 冷灰 6000 ~ 6500m
        32: ("#9ea4ac", "32 冰川区"),            # 冰灰 6500 ~ 7000m
        33: ("#b5bcc6", "33 极高山"),            # 浅冰灰 7000 ~ 7500m
        34: ("#d0d8e2", "34 山峰"),              # 雪白灰 7500 ~ 8000m
        35: ("#f0f4f8", "35 极地之巅"),          # 纯净雪白 > 8000m
    }

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
        35级精细分类，颜色丰富，区分度高
        """
        C = MapColoringService.LEVEL_COLORS
        
        # ========== 海洋层级 (01-10) ==========
        if relative_elev < 0:
            if relative_elev < -8000: return C[1]   # 超深海沟
            if relative_elev < -6000: return C[2]   # 深海沟
            if relative_elev < -4000: return C[3]   # 深海平原
            if relative_elev < -2500: return C[4]   # 深海盆地
            if relative_elev < -1500: return C[5]   # 海洋丘陵
            if relative_elev < -800:  return C[6]   # 大陆坡深部
            if relative_elev < -400:  return C[7]   # 大陆坡
            if relative_elev < -150:  return C[8]   # 大陆架深部
            if relative_elev < -50:   return C[9]   # 大陆架
            return C[10]                             # 近岸浅水

        # ========== 陆地低海拔 (11-18) ==========
        if relative_elev < 10:   return C[11]       # 潮间带
        if relative_elev < 30:   return C[12]       # 沿海低地
        if relative_elev < 80:   return C[13]       # 冲积平原
        if relative_elev < 150:  return C[14]       # 低海拔平原
        if relative_elev < 300:  return C[15]       # 平原
        if relative_elev < 500:  return C[16]       # 缓坡丘陵
        if relative_elev < 750:  return C[17]       # 丘陵
        if relative_elev < 1000: return C[18]       # 高丘陵
        
        # ========== 陆地中海拔 (19-26) ==========
        if relative_elev < 1300: return C[19]       # 台地
        if relative_elev < 1600: return C[20]       # 低高原
        if relative_elev < 1900: return C[21]       # 高原
        if relative_elev < 2200: return C[22]       # 亚山麓
        if relative_elev < 2600: return C[23]       # 山麓带
        if relative_elev < 3000: return C[24]       # 低山
        if relative_elev < 3500: return C[25]       # 中低山
        if relative_elev < 4000: return C[26]       # 中山

        # ========== 高海拔雪山 (27-35) ==========
        if relative_elev < 4500: return C[27]       # 中高山
        if relative_elev < 5000: return C[28]       # 高山
        if relative_elev < 5500: return C[29]       # 雪线区
        if relative_elev < 6000: return C[30]       # 高寒荒漠
        if relative_elev < 6500: return C[31]       # 永久冰雪
        if relative_elev < 7000: return C[32]       # 冰川区
        if relative_elev < 7500: return C[33]       # 极高山
        if relative_elev < 8000: return C[34]       # 山峰
        return C[35]                                 # 极地之巅

    # ============== 覆盖物颜色表 ==============
    # 按类别细分，与35级地形系统匹配
    COVER_COLORS = {
        # ===== 冰雪类 (6种) =====
        "冰川": "#F5FAFF",          # 纯白冰川 - 高山永久冰川
        "Glacier": "#F5FAFF",
        "冰原": "#E6F2FF",          # 冷白冰盖 - 极地大冰原
        "Ice Sheet": "#E6F2FF",
        "冰帽": "#EDF6FF",          # 淡蓝白 - 山顶小冰帽
        "Ice Cap": "#EDF6FF",
        "海冰": "#C5E0F5",          # 海冰蓝白 - 极地海洋浮冰
        "Sea Ice": "#C5E0F5",
        "冰湖": "#A8D4F0",          # 冰冻湖蓝 - 结冰的湖泊
        "Frozen Lake": "#A8D4F0",
        "冻土": "#8A9BAA",          # 冷灰蓝 - 永久冻土层
        "Permafrost": "#8A9BAA",
        "季节冻土": "#9AABB8",      # 浅灰蓝 - 季节性冻土
        "Seasonal Frost": "#9AABB8",
        
        # ===== 荒漠类 (6种) =====
        "沙漠": "#E8C872",          # 明亮沙黄 - 沙质荒漠
        "Desert": "#E8C872",
        "沙丘": "#F0D080",          # 浅沙黄 - 流动沙丘
        "Dune": "#F0D080",
        "戈壁": "#C4A87A",          # 灰褐 - 石质荒漠
        "Gobi": "#C4A87A",
        "盐碱地": "#D8D0C0",        # 灰白 - 盐碱荒漠
        "Salt Flat": "#D8D0C0",
        "裸岩": "#7A7A7A",          # 岩石灰 - 裸露岩石
        "Bare Rock": "#7A7A7A",
        "裸地": "#A09080",          # 土褐色 - 一般裸地
        "Barren": "#A09080",
        
        # ===== 苔原/草地类 (6种) =====
        "苔原": "#7A9E8A",          # 灰绿 - 极地苔藓/地衣
        "Tundra": "#7A9E8A",
        "高山草甸": "#8CB878",      # 冷草绿 - 高山草甸
        "Alpine Meadow": "#8CB878",
        "草甸": "#90C878",          # 草甸绿 - 湿润草甸
        "Meadow": "#90C878",
        "草原": "#A8D068",          # 明亮草绿 - 温带草原
        "Grassland": "#A8D068",
        "稀树草原": "#C8D060",      # 黄绿 - 热带稀树草原
        "Savanna": "#C8D060",
        "灌木丛": "#6A9A58",        # 灌木绿 - 灌木地带
        "Scrub": "#6A9A58",
        
        # ===== 森林类 (7种) =====
        "苔藓林": "#4A7858",        # 深苔绿 - 苔藓覆盖的原始林
        "Moss Forest": "#4A7858",
        "针叶林": "#3E6850",        # 冷杉绿 - 寒带针叶林
        "Taiga": "#3E6850",
        "混合林": "#4A8058",        # 混交林绿 - 针阔混交林
        "Mixed": "#4A8058",
        "阔叶林": "#3A7048",        # 落叶林绿 - 温带落叶林
        "Forest": "#3A7048",
        "森林": "#3A7048",
        "常绿林": "#2A6040",        # 常绿深绿 - 亚热带常绿林
        "Evergreen": "#2A6040",
        "雨林": "#1A5030",          # 雨林墨绿 - 热带雨林
        "Rainforest": "#1A5030",
        "云雾林": "#3A6858",        # 雾林蓝绿 - 高山云雾林
        "Cloud Forest": "#3A6858",
        
        # ===== 湿地类 (5种) =====
        "沼泽": "#3D5A45",          # 沼泽深绿 - 树木沼泽
        "Swamp": "#3D5A45",
        "湿地": "#4A6A50",          # 湿地绿 - 草本湿地
        "Wetland": "#4A6A50",
        "泥炭地": "#5A5A48",        # 泥炭褐绿 - 泥炭沼泽
        "Peatland": "#5A5A48",
        "红树林": "#3A5840",        # 红树林绿 - 沿海红树林
        "Mangrove": "#3A5840",
        "水域": "#5DADE2",          # 水面蓝 - 开放水面
        "Water": "#5DADE2",
    }

    @staticmethod
    def _terrain_color(tile: MapTile, sea_level: float) -> str:
        """
        实景地图模式：
        底色：35级精细地质/海拔颜色
        覆盖物：细分的特殊地貌着色，植物层由前端独立渲染
        """
        relative_elev = tile.elevation - sea_level
        
        # 1. 湖泊特殊处理 - 根据深度和盐度细分
        if getattr(tile, "is_lake", False):
            salinity = getattr(tile, "salinity", 35.0)
            if salinity < 5:
                # 淡水湖 - 根据深度
                if relative_elev < -100:
                    return "#2196F3"  # 深湖蓝
                elif relative_elev < -30:
                    return "#42A5F5"  # 中湖蓝
                else:
                    return "#64B5F6"  # 浅湖蓝
            else:
                # 咸水湖
                if relative_elev < -50:
                    return "#1E88E5"  # 深咸水蓝
                else:
                    return "#29B6F6"  # 浅咸水蓝
        
        # 2. 获取基础地质/海拔颜色
        base_color, _ = MapColoringService._get_level_info(relative_elev)
        
        # 3. 覆盖物着色 - 查表获取颜色
        cover = tile.cover
        cover_color = MapColoringService.COVER_COLORS.get(cover)
        
        if cover_color:
            # 冰雪类 - 直接使用覆盖物颜色（覆盖地形）
            if cover in ["冰川", "Glacier", "冰原", "Ice Sheet", "冰帽", "Ice Cap",
                        "海冰", "Sea Ice", "冰湖", "Frozen Lake"]:
                return cover_color
            
            # 冻土类 - 与地形混合
            if cover in ["冻土", "Permafrost", "季节冻土", "Seasonal Frost"]:
                return MapColoringService._blend_colors(cover_color, base_color, 0.6)
            
            # 荒漠类 - 与地形混合（根据海拔调整）
            if cover in ["沙漠", "Desert", "沙丘", "Dune", "戈壁", "Gobi",
                        "盐碱地", "Salt Flat", "裸岩", "Bare Rock"]:
                if relative_elev > 0:
                    blend = 0.7 if cover in ["沙漠", "Desert", "沙丘", "Dune"] else 0.6
                    return MapColoringService._blend_colors(cover_color, base_color, blend)
            
            # 裸地 - 保持基础颜色或轻微混合
            if cover in ["裸地", "Barren"]:
                return MapColoringService._blend_colors(cover_color, base_color, 0.3)
            
            # 湿地类 - 与地形混合
            if cover in ["沼泽", "Swamp", "湿地", "Wetland", "泥炭地", "Peatland",
                        "红树林", "Mangrove"]:
                if relative_elev > 0:
                    return MapColoringService._blend_colors(cover_color, base_color, 0.5)

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
        """生物多样性热力图模式 - 更鲜明的色阶"""
        base_color = MapColoringService._terrain_color(tile, sea_level)
        score = max(0.0, min(1.0, score))
        
        # 冷色(低) -> 暖色(高) 的鲜明渐变
        if score < 0.1:   overlay = "#1a237e"   # 深靛蓝 - 几乎无生命
        elif score < 0.2: overlay = "#283593"   # 靛蓝
        elif score < 0.3: overlay = "#1565c0"   # 蓝色
        elif score < 0.4: overlay = "#0288d1"   # 浅蓝
        elif score < 0.5: overlay = "#00acc1"   # 青色
        elif score < 0.6: overlay = "#26a69a"   # 青绿
        elif score < 0.7: overlay = "#66bb6a"   # 绿色
        elif score < 0.8: overlay = "#9ccc65"   # 黄绿
        elif score < 0.9: overlay = "#ffb300"   # 橙黄 - 高生物多样性
        else: overlay = "#e53935"               # 红色 - 极高生物多样性
        
        return MapColoringService._blend_colors(overlay, base_color, 0.65)

    @staticmethod
    def _climate_color(tile: MapTile, sea_level: float) -> str:
        """气候图模式 - 更鲜明的气候带颜色"""
        terrain_color = MapColoringService._terrain_color(tile, sea_level)
        climate = getattr(tile, "climate_zone", "温带")
        temperature = tile.temperature
        
        # 更鲜明的气候带颜色
        base_colors = {
            "极地": "#b3e5fc", "Polar": "#b3e5fc",       # 冰蓝
            "寒带": "#81d4fa", "Cold": "#81d4fa",        # 冷蓝
            "温带": "#4caf50", "Temperate": "#4caf50",   # 翠绿
            "亚热带": "#ffc107", "Subtropical": "#ffc107", # 金黄
            "热带": "#ff5722", "Tropical": "#ff5722",    # 热橙
        }
        
        climate_overlay = base_colors.get(climate, "#4caf50")
        
        # 极端温度修正
        if temperature < -20: climate_overlay = "#e1f5fe"     # 极寒白蓝
        elif temperature > 35: climate_overlay = "#d84315"    # 酷热深橙
        
        return MapColoringService._blend_colors(climate_overlay, terrain_color, 0.55)

    @staticmethod
    def classify_terrain_type(relative_elevation: float, is_lake: bool = False) -> str:
        """根据相对海拔分类地形类型 (返回35级名称)"""
        if is_lake:
            # 湖泊根据深度分类
            if relative_elevation < -400: return "07 大陆坡(深湖)"
            if relative_elevation < -150: return "08 大陆架深部(湖)"
            if relative_elevation < -50:  return "09 大陆架(浅湖)" 
            return "10 近岸浅水(湖)"

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
