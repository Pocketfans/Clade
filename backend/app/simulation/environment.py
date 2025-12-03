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
    # 【平衡调整v2】所有系数大幅降低，确保生态系统可持续
    # ============================================================
    "glacial_period": {       # 冰河时期
        "temperature": -0.4,   # 【v2】从-1.0降到-0.4，温和降温
        "drought": 0.05,       # 【v2】从0.15降到0.05
        "sea_level": -0.2,     # 【v2】从-0.6降到-0.2
        "habitat_fragmentation": 0.15,  # 【v2】从0.4降到0.15
    },
    "greenhouse_earth": {     # 温室地球（如白垩纪）
        "temperature": 0.4,    # 【v2】从1.0降到0.4
        "humidity": 0.25,      # 【v2】从0.6降到0.25
        "sea_level": 0.15,     # 【v2】从0.4降到0.15
        "productivity": 0.2,   # 【v2】从0.3降到0.2（正面效果）
    },
    "pluvial_period": {       # 洪积期（雨期）
        "flood": 0.4,          # 【v2】从1.0降到0.4
        "humidity": 0.35,      # 【v2】从0.9降到0.35
        "erosion": 0.2,        # 【v2】从0.5降到0.2
        "freshwater_input": 0.3,  # 【v2】从0.7降到0.3
    },
    "drought_period": {       # 干旱期
        "drought": 0.4,        # 【v2】从1.0降到0.4
        "temperature": 0.1,    # 【v2】从0.25降到0.1
        "wildfire_risk": 0.25, # 【v2】从0.6降到0.25
        "resource_decline": 0.2,  # 【v2】从0.5降到0.2
    },
    "monsoon_shift": {        # 季风变动
        "humidity": 0.3,       # 【v2】从0.7降到0.3
        "temperature": 0.05,   # 【v2】从0.15降到0.05
        "seasonality": 0.35,   # 【v2】从0.8降到0.35
        "flood": 0.1,          # 【v2】从0.3降到0.1
    },
    "fog_period": {           # 浓雾时期（如寒武纪海洋）
        "humidity": 0.35,      # 【v2】从0.85降到0.35
        "light_reduction": 0.3, # 【v2】从0.7降到0.3
        "temperature": -0.03,  # 【v2】从-0.1降到-0.03
    },
    "extreme_weather": {      # 极端天气（风暴/飓风）
        "storm_damage": 0.4,   # 【v2】从1.0降到0.4
        "flood": 0.2,          # 【v2】从0.5降到0.2
        "habitat_fragmentation": 0.15, # 【v2】从0.4降到0.15
        "mortality_spike": 0.1,  # 【v2】从0.3降到0.1
    },
    
    # ============================================================
    # === 地质相关（三阶天灾）===
    # 【平衡调整v3】三阶天灾恢复大灭绝效果！
    # ============================================================
    "volcanic_eruption": {    # 火山喷发期 (Tier 3)
        "volcanic": 1.0,       # 【v3】恢复！
        "volcano": 1.0,        # 【v3】恢复！
        "temperature": -0.8,   # 【v3】恢复！大规模喷发降温
        "sulfur_aerosol": 1.0, # 【v3】恢复！硫酸盐气溶胶
        "acidity": 0.5,        # 【v3】恢复！酸雨
        "light_reduction": 0.6, # 【v3】恢复！火山灰遮光
        "mortality_spike": 0.5, # 【v3】恢复！直接死亡
        "toxin_level": 0.4,    # 【v3】恢复！
    },
    "orogeny": {              # 造山期 (Tier 3)
        "tectonic": 1.0,       # 【v3】恢复！
        "altitude_change": 0.8,# 【v3】恢复！
        "habitat_fragmentation": 0.6,  # 【v3】恢复！
        "rain_shadow": 0.5,    # 【v3】恢复！
    },
    "subsidence": {           # 陆架沉降 (Tier 3)
        "flood": 0.8,          # 【v3】恢复！
        "tectonic": 0.5,       # 【v3】恢复！
        "sea_level": 0.6,      # 【v3】恢复！
        "habitat_loss": 0.7,   # 【v3】恢复！
    },
    "land_degradation": {     # 土地退化 (Tier 2，保持较低)
        "drought": 0.2,        # 保持较低
        "resource_decline": 0.4,
        "erosion": 0.35,
        "desertification": 0.3,
    },
    "sea_level_rise": {       # 海平面上升 (Tier 3)
        "sea_level": 1.0,      # 【v3】恢复！
        "coastal_flooding": 0.9,  # 【v3】恢复！
        "salinity_intrusion": 0.6,  # 【v3】恢复！
        "habitat_loss": 0.7,   # 【v3】恢复！
    },
    "sea_level_fall": {       # 海平面下降 (Tier 3)
        "sea_level": -1.0,     # 【v3】恢复！
        "continental_shelf_exposure": 0.9,  # 【v3】恢复！
        "habitat_expansion": 0.3,  # 正面效果
        "coastal_salinity": 0.4,
    },
    "earthquake_period": {    # 地震活跃期 (Tier 3)
        "tectonic": 0.9,       # 【v3】恢复！
        "habitat_fragmentation": 0.7, # 【v3】恢复！
        "landslide_risk": 0.8, # 【v3】恢复！
        "mortality_spike": 0.3, # 【v3】恢复！
    },
    
    # ============================================================
    # === 海洋相关 ===
    # 【平衡调整v2】所有系数大幅降低
    # ============================================================
    "ocean_current_shift": {  # 洋流变迁（如AMOC减弱）
        "temperature": 0.2,    # 【v2】从0.5降到0.2
        "humidity": 0.15,      # 【v2】从0.35降到0.15
        "nutrient_redistribution": 0.3, # 【v2】从0.7降到0.3
        "upwelling_change": 0.25, # 【v2】从0.6降到0.25
    },
    "ocean_acidification": {  # 海洋酸化（PETM类似事件）
        "acidity": 0.4,        # 【v2】从1.0降到0.4
        "carbonate_stress": 0.35, # 【v2】从0.9降到0.35
        "temperature": 0.08,   # 【v2】从0.2降到0.08
        "coral_stress": 0.3,   # 【v2】从0.8降到0.3
    },
    
    # ============================================================
    # === 生态相关 ===
    # 【平衡调整v2】所有系数大幅降低
    # ============================================================
    "resource_abundance": {   # 资源繁盛期（正面效果保留较高）
        "resource_boost": 0.5, # 【v2】从1.0降到0.5
        "competition": -0.15,  # 【v2】从-0.3降到-0.15
        "productivity": 0.4,   # 【v2】从0.8降到0.4
    },
    "productivity_decline": { # 生产力衰退
        "resource_decline": 0.4,  # 【v2】从1.0降到0.4
        "competition": 0.3,    # 【v2】从0.7降到0.3
        "starvation_risk": 0.25, # 【v2】从0.6降到0.25
    },
    "predator_rise": {        # 捕食者兴起
        "predator": 0.4,       # 【v2】从1.0降到0.4
        "prey_mortality": 0.2, # 【v2】从0.5降到0.2
        "behavioral_stress": 0.12, # 【v2】从0.3降到0.12
    },
    "species_invasion": {     # 物种入侵
        "competitor": 0.4,     # 【v2】从1.0降到0.4
        "niche_displacement": 0.25, # 【v2】从0.6降到0.25
        "disease_risk": 0.12,  # 【v2】从0.3降到0.12
    },
    "disease_outbreak": {     # 疾病爆发
        "disease": 0.4,        # 【v2】从1.0降到0.4
        "mortality_spike": 0.15, # 【v2】从0.4降到0.15
        "social_disruption": 0.15, # 【v2】从0.4降到0.15
        "immune_stress": 0.2,  # 【v2】从0.5降到0.2
    },
    "wildfire_period": {      # 野火肆虐期
        "wildfire": 0.4,       # 【v2】从1.0降到0.4
        "mortality_spike": 0.15, # 【v2】从0.4降到0.15
        "habitat_loss": 0.3,   # 【v2】从0.7降到0.3
        "resource_decline": 0.2, # 【v2】从0.5降到0.2
        "regeneration_opportunity": 0.15, # 【v2】从0.3降到0.15
    },
    "algal_bloom": {          # 藻华爆发（赤潮）
        "algae_bloom": 0.4,    # 【v2】从1.0降到0.4
        "oxygen": -0.25,       # 【v2】从-0.6降到-0.25
        "toxin_level": 0.2,    # 【v2】从0.5降到0.2
        "light_reduction": 0.15, # 【v2】从0.4降到0.15
    },
    
    # ============================================================
    # === 化学/大气相关（大部分是三阶天灾）===
    # 【平衡调整v3】三阶恢复大灭绝效果！
    # ============================================================
    "oxygen_increase": {      # 氧气增多（Tier 2，正面效果）
        "oxygen": 0.5,
        "metabolic_boost": 0.3,
        "body_size_potential": 0.35,
        "wildfire_risk": 0.2,
    },
    "anoxic_event": {         # 缺氧事件 (Tier 3) 大灭绝！
        "oxygen": -1.2,        # 【v3】恢复！氧气骤降
        "mortality_spike": 0.8, # 【v3】恢复！大规模死亡
        "sulfide_production": 0.5, # 【v3】恢复！
        "deep_water_anoxia": 1.0, # 【v3】恢复！
    },
    "sulfide_event": {        # 硫化事件 (Tier 3) 大灭绝！
        "sulfide": 1.2,        # 【v3】恢复！硫化氢浓度
        "toxicity": 1.0,       # 【v3】恢复！剧毒
        "oxygen": -0.6,        # 【v3】恢复！伴随缺氧
        "mortality_spike": 0.8, # 【v3】恢复！大规模死亡
    },
    "uv_radiation_increase": { # 紫外辐射增强 (Tier 2)
        "uv_radiation": 0.5,
        "dna_damage": 0.4,
        "surface_avoidance": 0.35,
        "mutation_rate": 0.2,
    },
    "salinity_change": {      # 盐度变化 (Tier 2)
        "salinity_change": 0.5,
        "osmotic_stress": 0.4,
        "habitat_shift": 0.3,
    },
    "methane_release": {      # 甲烷释放 (Tier 3) 大灭绝！
        "methane": 1.0,        # 【v3】恢复！
        "temperature": 0.8,    # 【v3】恢复！强温室效应
        "oxygen": -0.4,        # 【v3】恢复！
        "ocean_acidification": 0.5, # 【v3】恢复！
    },
    
    # ============================================================
    # === 末日级天灾 ===
    # 【平衡调整v3】恢复大灭绝效果！天灾就应该大浪淘沙
    # ============================================================
    "meteor_impact": {        # 陨石撞击（如K-Pg灭绝事件）
        "mortality_spike": 1.0,     # 【v3】恢复！满强度直接灭绝
        "temperature": -1.0,        # 【v3】恢复！撞击冬天
        "light_reduction": 1.2,     # 【v3】恢复！尘埃遮天蔽日
        "wildfire": 0.8,            # 【v3】恢复！撞击引发大火
        "acidity": 0.6,             # 【v3】恢复！酸雨
        "habitat_fragmentation": 1.0, # 【v3】恢复！栖息地毁坏
        "resource_decline": 1.2,    # 【v3】恢复！食物链崩溃
    },
    "gamma_ray_burst": {      # 伽马射线暴（奥陶纪灭绝假说之一）
        "mortality_spike": 1.0,     # 【v3】恢复！
        "uv_radiation": 1.2,        # 【v3】恢复！臭氧层被破坏
        "dna_damage": 1.2,          # 【v3】恢复！严重基因损伤
        "mutation_rate": 1.0,       # 【v3】恢复！突变率暴增
        "light_reduction": 0.4,     # 【v3】恢复！
        "surface_avoidance": 1.0,   # 【v3】恢复！表层生物受创最重
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
        from .constants import INTENSITY_TIER_1_LIMIT, INTENSITY_TIER_2_LIMIT
        
        target = (
            f"局部({pressure.target_region[0]}, {pressure.target_region[1]})"
            if pressure.target_region
            else "全球"
        )
        
        # 优先使用 label 和 narrative_note 构建更丰富的描述
        event_name = pressure.label or f"{pressure.kind}事件"
        description = pressure.narrative_note or "系统解析待补充"
        
        intensity = pressure.intensity
        if intensity <= INTENSITY_TIER_1_LIMIT:
            tier_name = "轻微"
        elif intensity <= INTENSITY_TIER_2_LIMIT:
            tier_name = "中等"
        else:
            tier_name = "毁灭性"
        
        return (
            f"{target}发生【{event_name}】，强度{pressure.intensity}/10 ({tier_name})。"
            f"附注: {description}"
        )

    def apply_pressures(self, parsed: Iterable[ParsedPressure]) -> dict[str, float]:
        """Aggregate modifiers for downstream mortality rules.
        
        将高级压力类型（如 glacial_period）映射到基础环境修改器（如 temperature）。
        这确保死亡率计算和气候变化计算能正确响应各种压力事件。
        
        【修改】引入非线性强度倍率：
        - 1-3级: x1.0 (轻微)
        - 4-7级: x2.0 (中等)
        - 8-10级: x5.0 (毁灭性)

        【修改】引入压力类型等级倍率：
        - Tier 1: x1.0 (标准)
        - Tier 2: x1.5 (增强)
        - Tier 3: x3.0 (毁灭性加成)
        """
        from .constants import (
            get_intensity_multiplier,
            PRESSURE_TYPE_TIERS,
            PRESSURE_TYPE_TIER_MODIFIERS
        )
        
        summary: dict[str, float] = {}
        
        for item in parsed:
            # 1. 获取强度滑块带来的倍率 (Intensity Multiplier)
            intensity_mult = get_intensity_multiplier(item.intensity)
            
            # 2. 获取压力类型本身的等级带来的效果倍率 (Type Tier Modifier)
            # 默认为 Tier 2 (中等)
            type_tier = PRESSURE_TYPE_TIERS.get(item.kind, 2)
            type_tier_mult = PRESSURE_TYPE_TIER_MODIFIERS.get(type_tier, 1.5)
            
            # 3. 计算有效强度
            effective_intensity = item.intensity * intensity_mult * type_tier_mult
            
            # 检查是否有映射关系
            if item.kind in PRESSURE_TO_MODIFIER_MAP:
                # 将高级压力映射到多个基础修改器
                modifier_map = PRESSURE_TO_MODIFIER_MAP[item.kind]
                for base_modifier, coefficient in modifier_map.items():
                    # 计算该基础修改器的值 = 有效强度 × 系数
                    modifier_value = effective_intensity * coefficient
                    summary[base_modifier] = summary.get(base_modifier, 0.0) + modifier_value
            else:
                # 未知压力类型，直接使用有效强度作为修改器
                summary[item.kind] = summary.get(item.kind, 0.0) + effective_intensity
        
        return summary
