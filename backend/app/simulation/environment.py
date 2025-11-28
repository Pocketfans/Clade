from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..schemas.requests import PressureConfig


@dataclass(slots=True)
class ParsedPressure:
    kind: str
    intensity: int
    affected_tiles: list[int]
    narrative: str


# 压力类型到基础环境修改器的映射表
# 每个压力类型映射到一个或多个基础修改器及其强度系数
# 格式: { 压力类型: { 基础修改器: 系数 } }
# 正数系数表示增加该修改器，负数表示减少
#
# 【生物学依据说明】
# - 系数基于真实地质历史事件的研究数据
# - 考虑了不同压力之间的联动效应
# - 参考了古生物学五大灭绝事件的环境重建
#
PRESSURE_TO_MODIFIER_MAP = {
    # ============================================================
    # === 气候相关 ===
    # 参考：新生代气候变化、第四纪冰期-间冰期旋回
    # ============================================================
    "glacial_period": {       # 冰河时期
        "temperature": -1.0,   # 全球平均降温5-10°C
        "drought": 0.15,       # 【修正】冰期降水减少但蒸发也低，实际干旱程度较低
        "sea_level": -0.6,     # 大量水冻结，海平面下降可达120米
        "habitat_fragmentation": 0.4,  # 冰川切割栖息地
    },
    "greenhouse_earth": {     # 温室地球（如白垩纪）
        "temperature": 1.0,    # 全球升温，热带扩展
        "humidity": 0.6,       # 蒸发增强，大气水汽增加
        "sea_level": 0.4,      # 冰盖融化，海平面上升
        "productivity": 0.3,   # 温暖有利于初级生产力
    },
    "pluvial_period": {       # 洪积期（雨期）
        "flood": 1.0,          # 洪水频发
        "humidity": 0.9,       # 极高湿度
        "erosion": 0.5,        # 侵蚀加剧
        "freshwater_input": 0.7,  # 淡水输入增加（影响沿海盐度）
    },
    "drought_period": {       # 干旱期
        "drought": 1.0,        # 严重缺水
        "temperature": 0.25,   # 干旱通常伴随轻微升温
        "wildfire_risk": 0.6,  # 火灾风险增加
        "resource_decline": 0.5,  # 植被减少
    },
    "monsoon_shift": {        # 季风变动
        "humidity": 0.7,       # 湿度波动大
        "temperature": 0.15,   # 季节性温度变化
        "seasonality": 0.8,    # 季节性增强
        "flood": 0.3,          # 季节性洪水
    },
    "fog_period": {           # 浓雾时期（如寒武纪海洋）
        "humidity": 0.85,      # 高湿度
        "light_reduction": 0.7, # 光照减少（影响光合作用）
        "temperature": -0.1,   # 略微降温
    },
    "extreme_weather": {      # 极端天气（风暴/飓风）
        "storm_damage": 1.0,   # 物理破坏
        "flood": 0.5,          # 暴雨洪涝
        "habitat_fragmentation": 0.4,  # 栖息地破碎
        "mortality_spike": 0.3,  # 直接死亡
    },
    
    # ============================================================
    # === 地质相关 ===
    # 参考：大规模火成岩省(LIP)、威尔逊旋回、造山运动
    # ============================================================
    "volcanic_eruption": {    # 火山喷发期
        "volcanic": 1.0,       # 火山活动强度
        "volcano": 1.0,        # 死亡率计算用
        "temperature": -0.6,   # 【修正】大规模喷发可降温2-6°C（如坦博拉）
        "sulfur_aerosol": 0.8, # 硫酸盐气溶胶
        "acidity": 0.4,        # 酸雨
        "light_reduction": 0.5, # 火山灰遮光
    },
    "orogeny": {              # 造山期（如喜马拉雅造山）
        "tectonic": 1.0,       # 构造活动
        "altitude_change": 0.7,# 海拔剧变
        "habitat_fragmentation": 0.5,  # 地形隔离
        "rain_shadow": 0.4,    # 雨影效应（山脉背风坡干旱）
    },
    "subsidence": {           # 陆架沉降
        "flood": 0.7,          # 低地淹没
        "tectonic": 0.4,       # 构造活动
        "sea_level": 0.5,      # 相对海平面上升
        "habitat_loss": 0.6,   # 栖息地丧失
    },
    "land_degradation": {     # 土地退化
        "drought": 0.4,        # 土壤干燥
        "resource_decline": 0.9,  # 【增强】土壤贫瘠化严重影响生产力
        "erosion": 0.7,        # 水土流失
        "desertification": 0.6,  # 荒漠化
    },
    "sea_level_rise": {       # 海平面上升
        "sea_level": 1.0,      # 海平面上升
        "coastal_flooding": 0.8,  # 沿海淹没
        "salinity_intrusion": 0.5,  # 盐水入侵
        "habitat_loss": 0.6,   # 沿海栖息地丧失
    },
    "sea_level_fall": {       # 海平面下降
        "sea_level": -1.0,     # 海平面下降
        "continental_shelf_exposure": 0.8,  # 大陆架暴露
        "habitat_expansion": 0.4,  # 陆地面积增加
        "coastal_salinity": 0.3,  # 局部盐度升高
    },
    "earthquake_period": {    # 地震活跃期
        "tectonic": 0.8,       # 构造活动
        "habitat_fragmentation": 0.6,  # 地形破碎
        "landslide_risk": 0.7, # 滑坡风险
        "mortality_spike": 0.2,  # 直接死亡
    },
    
    # ============================================================
    # === 海洋相关 ===
    # 参考：PETM热事件、OAE缺氧事件、现代海洋环流
    # ============================================================
    "ocean_current_shift": {  # 洋流变迁（如AMOC减弱）
        "temperature": 0.5,    # 区域温度剧变
        "humidity": 0.35,      # 气候模式改变
        "nutrient_redistribution": 0.7,  # 营养盐重新分布
        "upwelling_change": 0.6,  # 上升流变化
    },
    "ocean_acidification": {  # 海洋酸化（PETM类似事件）
        "acidity": 1.0,        # 酸度增加（pH下降0.3-0.5）
        "carbonate_stress": 0.9,  # 碳酸钙壳体溶解压力
        "temperature": 0.2,    # 通常与升温相伴
        "coral_stress": 0.8,   # 珊瑚/钙质生物压力
    },
    
    # ============================================================
    # === 生态相关 ===
    # 参考：现代生态学、古生态重建
    # ============================================================
    "resource_abundance": {   # 资源繁盛期
        "resource_boost": 1.0, # 资源丰富
        "competition": -0.3,   # 竞争减弱
        "productivity": 0.8,   # 生产力高
    },
    "productivity_decline": { # 生产力衰退
        "resource_decline": 1.0,  # 资源匮乏
        "competition": 0.7,    # 竞争加剧
        "starvation_risk": 0.6,  # 饥饿风险
    },
    "predator_rise": {        # 捕食者兴起
        "predator": 1.0,       # 捕食压力
        "prey_mortality": 0.5, # 猎物死亡率增加
        "behavioral_stress": 0.3,  # 行为压力（警觉消耗）
    },
    "species_invasion": {     # 物种入侵
        "competitor": 1.0,     # 竞争压力
        "niche_displacement": 0.6,  # 生态位置换
        "disease_risk": 0.3,   # 新疾病风险
    },
    "disease_outbreak": {     # 疾病爆发
        "disease": 1.0,        # 疾病压力
        "mortality_spike": 0.7,  # 高死亡率
        "social_disruption": 0.4,  # 社会行为打乱
        "immune_stress": 0.5,  # 免疫系统压力
    },
    "wildfire_period": {      # 野火肆虐期
        "wildfire": 1.0,       # 火灾强度
        "mortality_spike": 0.6,  # 直接死亡
        "habitat_loss": 0.7,   # 栖息地丧失
        "resource_decline": 0.5,  # 食物减少
        "regeneration_opportunity": 0.3,  # 先锋物种机会
    },
    "algal_bloom": {          # 藻华爆发（赤潮）
        "algae_bloom": 1.0,    # 藻华强度
        "oxygen": -0.6,        # 夜间/死亡时消耗氧气
        "toxin_level": 0.5,    # 藻毒素
        "light_reduction": 0.4,  # 水下光照减少
    },
    
    # ============================================================
    # === 化学/大气相关 ===
    # 参考：大氧化事件、P-T灭绝硫化事件、现代臭氧研究
    # ============================================================
    "oxygen_increase": {      # 氧气增多（如石炭纪）
        "oxygen": 1.0,         # 氧含量增加
        "metabolic_boost": 0.5,  # 代谢能力增强
        "body_size_potential": 0.6,  # 大型化潜力
        "wildfire_risk": 0.4,  # 高氧助燃
    },
    "anoxic_event": {         # 缺氧事件（OAE）
        "oxygen": -1.0,        # 氧气骤降
        "mortality_spike": 0.8,  # 大规模窒息
        "sulfide_production": 0.4,  # 厌氧菌产硫化氢
        "deep_water_anoxia": 0.9,  # 深层缺氧
    },
    "sulfide_event": {        # 硫化事件（如P-T边界）
        "sulfide": 1.0,        # 硫化氢浓度
        "toxicity": 0.9,       # 剧毒
        "oxygen": -0.5,        # 伴随缺氧
        "mortality_spike": 0.8,  # 大规模死亡
    },
    "uv_radiation_increase": { # 紫外辐射增强（臭氧减少）
        "uv_radiation": 1.0,   # UV-B增强
        "dna_damage": 0.7,     # DNA损伤
        "surface_avoidance": 0.6,  # 迫使生物躲避表层
        "mutation_rate": 0.3,  # 突变率增加
    },
    "salinity_change": {      # 盐度变化
        "salinity_change": 1.0,  # 盐度波动
        "osmotic_stress": 0.8, # 渗透压力
        "habitat_shift": 0.5,  # 栖息地迁移
    },
    "methane_release": {      # 甲烷释放（如PETM）
        "methane": 1.0,        # 甲烷浓度
        "temperature": 0.6,    # 强温室效应
        "oxygen": -0.3,        # 氧化消耗氧气
        "ocean_acidification": 0.4,  # 碳循环扰动
    },
}


class EnvironmentSystem:
    """Transforms player pressures into actionable map modifiers."""

    def __init__(self, map_width: int, map_height: int) -> None:
        self.map_width = map_width
        self.map_height = map_height

    def parse_pressures(self, pressures: Sequence[PressureConfig]) -> list[ParsedPressure]:
        parsed: list[ParsedPressure] = []
        for pressure in pressures:
            affected = self._resolve_tiles(pressure)
            narrative = self._describe_pressure(pressure)
            parsed.append(
                ParsedPressure(
                    kind=pressure.kind,
                    intensity=pressure.intensity,
                    affected_tiles=affected,
                    narrative=narrative,
                )
            )
        return parsed

    def _resolve_tiles(self, pressure: PressureConfig) -> list[int]:
        if pressure.target_region is None:
            return list(range(self.map_width * self.map_height))
        x, y = pressure.target_region
        radius = pressure.radius or 1
        affected: list[int] = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx, ty = x + dx, y + dy
                if not (0 <= tx < self.map_width and 0 <= ty < self.map_height):
                    continue
                affected.append(ty * self.map_width + tx)
        return affected

    def _describe_pressure(self, pressure: PressureConfig) -> str:
        target = (
            f"局部({pressure.target_region[0]}, {pressure.target_region[1]})"
            if pressure.target_region
            else "全球"
        )
        
        # 优先使用 label 和 narrative_note 构建更丰富的描述
        event_name = pressure.label or f"{pressure.kind}事件"
        description = pressure.narrative_note or "系统解析待补充"
        
        return (
            f"{target}发生【{event_name}】，强度{pressure.intensity}/10。"
            f"附注: {description}"
        )

    def apply_pressures(self, parsed: Iterable[ParsedPressure]) -> dict[str, float]:
        """Aggregate modifiers for downstream mortality rules.
        
        将高级压力类型（如 glacial_period）映射到基础环境修改器（如 temperature）。
        这确保死亡率计算和气候变化计算能正确响应各种压力事件。
        """
        summary: dict[str, float] = {}
        
        for item in parsed:
            # 检查是否有映射关系
            if item.kind in PRESSURE_TO_MODIFIER_MAP:
                # 将高级压力映射到多个基础修改器
                modifier_map = PRESSURE_TO_MODIFIER_MAP[item.kind]
                for base_modifier, coefficient in modifier_map.items():
                    # 计算该基础修改器的值 = 压力强度 × 系数
                    modifier_value = item.intensity * coefficient
                    summary[base_modifier] = summary.get(base_modifier, 0.0) + modifier_value
            else:
                # 未知压力类型，直接使用原始kind作为修改器
                summary[item.kind] = summary.get(item.kind, 0.0) + item.intensity
        
        return summary
