from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from ...models.environment import MapState
from ...schemas.responses import MajorPressureEvent, MapChange


@dataclass(slots=True)
class TectonicStage:
    name: str
    duration: int
    drift_direction: str
    description: str


# 板块阶段池（8个阶段，更细化和多样化）
STAGE_POOL = {
    "稳定期": TectonicStage(
        name="稳定期",
        duration=0,  # 将在运行时随机分配
        drift_direction="微弱运动",
        description="构造活动平静，地壳稳定，以侵蚀和沉积作用为主。",
    ),
    "裂谷初期": TectonicStage(
        name="裂谷初期",
        duration=0,
        drift_direction="初步张裂",
        description="大陆开始出现裂谷系统，局部岩浆活动，地壳轻度拉伸。",
    ),
    "裂谷活跃期": TectonicStage(
        name="裂谷活跃期",
        duration=0,
        drift_direction="强烈张裂",
        description="裂谷系统快速扩张，岩浆大量上涌，新洋壳形成。",
    ),
    "快速漂移期": TectonicStage(
        name="快速漂移期",
        duration=0,
        drift_direction="高速分离",
        description="板块快速移动，洋中脊活跃扩张，大陆持续分离。",
    ),
    "缓慢漂移期": TectonicStage(
        name="缓慢漂移期",
        duration=0,
        drift_direction="缓慢移动",
        description="板块缓速漂移，构造活动减弱，侵蚀作用占主导。",
    ),
    "俯冲带形成期": TectonicStage(
        name="俯冲带形成期",
        duration=0,
        drift_direction="边缘俯冲",
        description="海洋板块开始俯冲，海沟形成，火山弧初步显现。",
    ),
    "碰撞造山早期": TectonicStage(
        name="碰撞造山早期",
        duration=0,
        drift_direction="初步碰撞",
        description="大陆板块边缘碰撞，地壳开始增厚，山脉雏形形成。",
    ),
    "造山高峰期": TectonicStage(
        name="造山高峰期",
        duration=0,
        drift_direction="强烈碰撞",
        description="板块剧烈碰撞，造山运动达到高峰，形成高大山系。",
    ),
}

# 阶段转换概率表（每个阶段 -> [(下一阶段, 概率)]）
STAGE_TRANSITIONS = {
    "稳定期": [("裂谷初期", 0.35), ("缓慢漂移期", 0.30), ("稳定期", 0.35)],
    "裂谷初期": [("裂谷活跃期", 0.50), ("快速漂移期", 0.30), ("稳定期", 0.20)],
    "裂谷活跃期": [("快速漂移期", 0.60), ("裂谷活跃期", 0.40)],
    "快速漂移期": [("缓慢漂移期", 0.40), ("俯冲带形成期", 0.30), ("快速漂移期", 0.30)],
    "缓慢漂移期": [("稳定期", 0.30), ("俯冲带形成期", 0.30), ("裂谷初期", 0.20), ("缓慢漂移期", 0.20)],
    "俯冲带形成期": [("碰撞造山早期", 0.40), ("俯冲带形成期", 0.40), ("快速漂移期", 0.20)],
    "碰撞造山早期": [("造山高峰期", 0.50), ("碰撞造山早期", 0.30), ("稳定期", 0.20)],
    "造山高峰期": [("稳定期", 0.50), ("碰撞造山早期", 0.30), ("造山高峰期", 0.20)],
}

# 阶段持续时间范围（回合数）
STAGE_DURATION_RANGE = {
    "稳定期": (8, 15),
    "裂谷初期": (5, 10),
    "裂谷活跃期": (6, 12),
    "快速漂移期": (10, 18),
    "缓慢漂移期": (12, 20),
    "俯冲带形成期": (6, 12),
    "碰撞造山早期": (8, 15),
    "造山高峰期": (5, 10),
}

# 默认初始阶段（用于兼容性）
DEFAULT_STAGES = [STAGE_POOL["稳定期"]]


class MapEvolutionService:
    """根据阶段和重大压力事件更新地图叙事。使用概率驱动的多阶段系统。"""

    def __init__(self, width: int, height: int, stages: Sequence[TectonicStage] | None = None) -> None:
        self.width = width
        self.height = height
        # 初始化当前阶段
        self.current_stage_name = "稳定期"
        self.stage_progress = 0
        # 为初始阶段分配随机持续时间
        self.stage_duration = random.randint(*STAGE_DURATION_RANGE[self.current_stage_name])

    def current_stage(self) -> TectonicStage:
        """获取当前阶段对象"""
        stage = STAGE_POOL[self.current_stage_name]
        # 返回带有实际持续时间的副本
        return TectonicStage(
            name=stage.name,
            duration=self.stage_duration,
            drift_direction=stage.drift_direction,
            description=stage.description,
        )

    def advance(
        self,
        major_events: Sequence[MajorPressureEvent],
        turn_index: int,
        pressure_modifiers: dict[str, float] | None = None,
        current_state: MapState | None = None,
    ) -> list[MapChange]:
        """推进地图演化，计算温度和海平面变化（使用概率转换）"""
        stage = self.current_stage()
        self.stage_progress += 1
        
        # 检查是否需要切换阶段
        if self.stage_progress >= self.stage_duration:
            self.stage_progress = 0
            # 使用概率转换选择下一阶段
            next_stage_name = self._transition_to_next_stage()
            self.current_stage_name = next_stage_name
            self.stage_duration = random.randint(*STAGE_DURATION_RANGE[next_stage_name])
            stage = self.current_stage()
        
        # 更新MapState的阶段信息
        if current_state:
            current_state.stage_name = self.current_stage_name
            current_state.stage_progress = self.stage_progress
            current_state.stage_duration = self.stage_duration
        
        changes: list[MapChange] = [
            MapChange(
                stage=stage.name,
                description=(
                    f"{stage.description}（阶段进度 {self.stage_progress + 1}/{stage.duration}）"
                ),
                affected_region=stage.drift_direction,
                change_type="tectonic_stage",  # 板块阶段变化
            )
        ]
        
        # 计算温度和海平面变化
        if current_state and pressure_modifiers:
            temp_change, sea_level_change = self.calculate_climate_changes(
                pressure_modifiers, current_state
            )
            
            if abs(temp_change) > 0.01:
                temp_desc = f"全球平均温度{'上升' if temp_change > 0 else '下降'}{abs(temp_change):.1f}°C"
                if abs(sea_level_change) > 0.5:
                    temp_desc += f"，海平面{'上升' if sea_level_change > 0 else '下降'}{abs(sea_level_change):.1f}米"
                    if sea_level_change > 10:
                        temp_desc += "，沿海低地遭到淹没"
                    elif sea_level_change < -10:
                        temp_desc += "，大陆架暴露形成陆桥"
                changes.append(
                    MapChange(
                        stage=stage.name,
                        description=temp_desc,
                        affected_region="全球",
                        change_type="climate_change",  # 气候变化
                    )
                )
        
        for event in major_events:
            region = (
                f"影响格子 {len(event.affected_tiles)} 个"
                if event.affected_tiles
                else "全球"
            )
            changes.append(
                MapChange(
                    stage=stage.name,
                    description=f"重大压力引发 {event.description}",
                    affected_region=region,
                    change_type="major_event",  # 重大事件
                )
            )
        return changes
    
    def _transition_to_next_stage(self) -> str:
        """使用概率表选择下一阶段"""
        transitions = STAGE_TRANSITIONS.get(self.current_stage_name, [("稳定期", 1.0)])
        
        # 随机选择
        rand_val = random.random()
        cumulative = 0.0
        for next_stage, probability in transitions:
            cumulative += probability
            if rand_val < cumulative:
                return next_stage
        
        # 兜底：返回最后一个选项
        return transitions[-1][0]
    
    def calculate_climate_changes(
        self, pressure_modifiers: dict[str, float], current_state: MapState
    ) -> tuple[float, float]:
        """
        根据压力计算温度和海平面变化
        
        压力修改器已经通过 EnvironmentSystem.apply_pressures() 从高级类型
        (如 glacial_period) 转换为基础类型 (如 temperature)。
        
        Returns:
            (temperature_change, sea_level_change) 温度变化（°C）和海平面变化（米）
        """
        temp_change = 0.0
        sea_level_modifier = 0.0  # 额外的海平面修改
        
        # === 温度压力直接影响全球温度 ===
        if "temperature" in pressure_modifiers:
            # 压力强度范围 -10 到 +10，每点约0.3°C变化
            # 负值表示降温（如冰河期），正值表示升温（如温室效应）
            temp_pressure = pressure_modifiers["temperature"]
            temp_change += temp_pressure * 0.3
        
        # === 火山活动影响温度（短期降温效应）===
        if "volcanic" in pressure_modifiers:
            volcanic_pressure = pressure_modifiers["volcanic"]
            # 火山冬天效应：火山灰遮蔽阳光导致降温
            temp_change -= volcanic_pressure * 0.2
        
        # === 陨石撞击造成短期剧烈降温 ===
        if "impact" in pressure_modifiers:
            impact_pressure = pressure_modifiers["impact"]
            temp_change -= impact_pressure * 0.4
        
        # === 湿度变化对温度的间接影响 ===
        if "humidity" in pressure_modifiers:
            humidity_pressure = pressure_modifiers["humidity"]
            # 高湿度略微升温（温室效应），低湿度略微降温
            temp_change += humidity_pressure * 0.05
        
        # === 干旱对温度的影响 ===
        if "drought" in pressure_modifiers:
            drought_pressure = pressure_modifiers["drought"]
            # 干旱通常伴随轻微升温（缺水→蒸发减少→热量累积）
            temp_change += drought_pressure * 0.1
        
        # === 洪水对海平面的直接影响 ===
        if "flood" in pressure_modifiers:
            flood_pressure = pressure_modifiers["flood"]
            # 洪水期海平面额外上升
            sea_level_modifier += flood_pressure * 2.0  # 每强度2米
        
        # === 构造活动对海平面的影响 ===
        if "tectonic" in pressure_modifiers:
            tectonic_pressure = pressure_modifiers["tectonic"]
            # 构造活动可能导致海平面变化（造山期降低、沉降期升高）
            # 这里取中性影响，具体由其他因子决定
            pass
        
        # === 计算基于温度的海平面变化 ===
        # 温度每升高1°C，海平面上升2-3米（取中值2.5米）
        sea_level_change = temp_change * 2.5 + sea_level_modifier
        
        # === 极端冰期效应 ===
        new_temp = current_state.global_avg_temperature + temp_change
        if new_temp < 5.0:
            # 冰期加成：温度低于5°C时，冰川扩张导致海平面额外下降
            ice_age_factor = (5.0 - new_temp) / 5.0  # 0-1之间
            sea_level_change -= ice_age_factor * 50  # 额外下降0-50米
        
        # === 极端温室效应 ===
        if new_temp > 25.0:
            # 极端高温：冰盖加速融化
            heat_factor = (new_temp - 25.0) / 10.0  # 25-35°C → 0-1
            heat_factor = min(1.0, heat_factor)
            sea_level_change += heat_factor * 30  # 额外上升0-30米
        
        return temp_change, sea_level_change
