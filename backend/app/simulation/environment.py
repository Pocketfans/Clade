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
PRESSURE_TO_MODIFIER_MAP = {
    # === 气候相关 ===
    "glacial_period": {       # 冰河时期
        "temperature": -1.0,   # 强烈降温
        "drought": 0.3,        # 水分被冻结，干旱
    },
    "greenhouse_earth": {     # 温室地球
        "temperature": 1.0,    # 强烈升温
        "humidity": 0.5,       # 湿度增加
    },
    "pluvial_period": {       # 洪积期
        "flood": 1.0,          # 洪水
        "humidity": 0.8,       # 高湿度
    },
    "drought_period": {       # 干旱期
        "drought": 1.0,        # 干旱
        "temperature": 0.3,    # 轻微升温
    },
    "monsoon_shift": {        # 季风变动
        "humidity": 0.7,       # 湿度变化
        "temperature": 0.2,    # 轻微温度波动
    },
    "fog_period": {           # 浓雾时期
        "humidity": 0.8,       # 高湿度
        "light_reduction": 0.6, # 光照减少
    },
    
    # === 地质相关 ===
    "volcanic_eruption": {    # 火山喷发期
        "volcanic": 1.0,       # 火山活动（用于气候计算）
        "volcano": 1.0,        # 火山活动（用于死亡率计算）
        "temperature": -0.4,   # 火山冬天效应
    },
    "orogeny": {              # 造山期
        "tectonic": 1.0,       # 构造活动
        "altitude_change": 0.5,# 海拔变化
    },
    "subsidence": {           # 陆架沉降
        "flood": 0.6,          # 部分淹没
        "tectonic": 0.5,       # 轻微构造活动
    },
    "land_degradation": {     # 土地退化
        "drought": 0.5,        # 土壤退化伴随干旱
        "resource_decline": 0.8,# 资源减少
    },
    
    # === 海洋相关 ===
    "ocean_current_shift": {  # 洋流变迁
        "temperature": 0.5,    # 温度波动
        "humidity": 0.3,       # 湿度变化
    },
    "ocean_acidification": {  # 海洋酸化
        "acidity": 1.0,        # 酸度增加
        "temperature": 0.2,    # 轻微升温
    },
    
    # === 生态相关 ===
    "resource_abundance": {   # 资源繁盛期
        "resource_boost": 1.0, # 资源增加
    },
    "productivity_decline": { # 生产力衰退
        "resource_decline": 1.0,# 资源减少
        "competition": 0.5,    # 竞争加剧
    },
    "predator_rise": {        # 捕食者兴起
        "predator": 1.0,       # 捕食压力
    },
    "species_invasion": {     # 物种入侵
        "competitor": 1.0,     # 竞争压力
    },
    
    # === 大气相关 ===
    "oxygen_increase": {      # 氧气增多
        "oxygen": 1.0,         # 氧气增加
    },
    "anoxic_event": {         # 缺氧事件
        "oxygen": -1.0,        # 氧气减少
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
