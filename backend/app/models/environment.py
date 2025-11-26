from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Column, Field, JSON, SQLModel


class EnvironmentEvent(SQLModel, table=True):
    __tablename__ = "environment_events"

    id: int | None = Field(default=None, primary_key=True)
    turn_index: int = Field(index=True)
    scope: str = Field(default="global")
    description: str
    pressures: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Plate(SQLModel, table=True):
    """板块信息 (GPU 物理引擎的 CPU 映射)"""
    __tablename__ = "plates"
    
    id: int | None = Field(default=None, primary_key=True)
    plate_index: int = Field(unique=True, index=True)  # 板块编号 0-N
    velocity_x: float = Field(default=0.0) # 板块速度 X 分量 (km/年)
    velocity_y: float = Field(default=0.0) # 板块速度 Y 分量 (km/年)
    axis_x: float = Field(default=0.0) # 旋转轴 X (单位向量)
    axis_y: float = Field(default=0.0) # 旋转轴 Y
    axis_z: float = Field(default=1.0) # 旋转轴 Z (默认垂直)
    angular_velocity: float = Field(default=0.0) # 角速度 (rad/年)
    plate_type: str = Field(default="oceanic") # "oceanic" | "continental"
    density: float = Field(default=3.0) # 板块密度 (用于俯冲判定)


class MapTile(SQLModel, table=True):
    __tablename__ = "map_tiles"

    id: int | None = Field(default=None, primary_key=True)
    x: int = Field(index=True)
    y: int = Field(index=True)
    q: int = Field(default=0, index=True)
    r: int = Field(default=0, index=True)
    biome: str
    elevation: float  # 海拔（m）
    cover: str
    temperature: float  # 温度（°C）
    humidity: float  # 湿度（0-1）
    resources: float  # 资源丰富度（1-1000，绝对值，考虑温度、海拔、湿度）
    has_river: bool = False
    salinity: float = Field(default=35.0)  # 盐度（‰，千分比），海水平均35，淡水0-0.5，湖泊varies
    is_lake: bool = Field(default=False)  # 是否为湖泊（被陆地包围的水域）
    
    # 物理引擎扩展字段
    plate_id: int = Field(default=0, index=True)  # 新增：所属板块ID
    relative_elevation: float = Field(default=0.0)  # 新增：相对海平面高度
    crust_thickness: float = Field(default=30.0)  # 新增：地壳厚度(km)
    
    pressures: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class MapState(SQLModel, table=True):
    __tablename__ = "map_state"

    id: int | None = Field(default=None, primary_key=True)
    turn_index: int = Field(default=0)
    stage_name: str = "稳定期"
    stage_progress: int = 0
    stage_duration: int = 10  # 当前阶段的实际持续时间（回合数）
    sea_level: float = Field(default=0.0)  # 当前海平面高度（米）
    global_avg_temperature: float = Field(default=15.0)  # 全球平均温度（°C）
    extra_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class HabitatPopulation(SQLModel, table=True):
    __tablename__ = "habitat_populations"

    id: int | None = Field(default=None, primary_key=True)
    tile_id: int = Field(foreign_key="map_tiles.id", index=True)
    species_id: int = Field(foreign_key="species.id", index=True)
    population: int = Field(default=0)
    suitability: float = Field(default=0.0)
    turn_index: int = Field(default=0, index=True)


