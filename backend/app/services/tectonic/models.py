"""板块构造系统数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlateType(Enum):
    """板块类型"""
    CONTINENTAL = "continental"  # 大陆板块
    OCEANIC = "oceanic"         # 洋壳板块
    MIXED = "mixed"             # 混合板块


class BoundaryType(Enum):
    """边界类型"""
    INTERNAL = 0      # 板块内部
    DIVERGENT = 1     # 张裂边界（洋中脊、裂谷）
    CONVERGENT = 2    # 碰撞边界（大陆-大陆）
    SUBDUCTION = 3    # 俯冲边界（洋壳俯冲）
    TRANSFORM = 4     # 转换边界（水平错动）


class FeatureType(Enum):
    """地质特征类型"""
    VOLCANO = "volcano"           # 火山
    HOTSPOT = "hotspot"           # 热点（地幔柱）
    TRENCH = "trench"             # 海沟
    RIDGE = "ridge"               # 洋中脊
    RIFT = "rift"                 # 裂谷
    MOUNTAIN_RANGE = "mountain"   # 山脉


class MotionPhase(Enum):
    """板块运动阶段"""
    STABLE = "stable"           # 稳定期
    RIFTING = "rifting"         # 张裂期
    DRIFTING = "drifting"       # 漂移期
    COLLIDING = "colliding"     # 碰撞期
    SUBDUCTING = "subducting"   # 俯冲期


@dataclass
class Plate:
    """板块数据"""
    id: int
    plate_index: int
    
    # 运动参数
    velocity_x: float = 0.0      # X轴速度 (格/回合)
    velocity_y: float = 0.0      # Y轴速度 (格/回合)
    angular_velocity: float = 0.0  # 旋转速度 (rad/回合)
    rotation_center_x: float = 0.0  # 旋转中心X
    rotation_center_y: float = 0.0  # 旋转中心Y
    
    # 物理属性
    plate_type: PlateType = PlateType.CONTINENTAL
    density: float = 2.7         # 密度 (g/cm³)
    thickness: float = 35.0      # 地壳厚度 (km)
    age: int = 0                 # 板块年龄（回合数）
    
    # 运动状态
    motion_phase: MotionPhase = MotionPhase.STABLE
    motion_target_plate: int | None = None  # 碰撞/俯冲的目标板块
    
    # 统计信息
    tile_count: int = 0          # 包含的地块数量
    boundary_tile_count: int = 0  # 边界地块数量
    
    def speed(self) -> float:
        """计算当前速度大小"""
        return (self.velocity_x ** 2 + self.velocity_y ** 2) ** 0.5
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "plate_index": self.plate_index,
            "velocity_x": self.velocity_x,
            "velocity_y": self.velocity_y,
            "angular_velocity": self.angular_velocity,
            "rotation_center_x": self.rotation_center_x,
            "rotation_center_y": self.rotation_center_y,
            "plate_type": self.plate_type.value,
            "density": self.density,
            "thickness": self.thickness,
            "age": self.age,
            "motion_phase": self.motion_phase.value,
            "motion_target_plate": self.motion_target_plate,
            "tile_count": self.tile_count,
            "boundary_tile_count": self.boundary_tile_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plate:
        """从字典创建"""
        plate_type = PlateType(data.get("plate_type", "continental"))
        motion_phase = MotionPhase(data.get("motion_phase", "stable"))
        return cls(
            id=data["id"],
            plate_index=data["plate_index"],
            velocity_x=data.get("velocity_x", 0.0),
            velocity_y=data.get("velocity_y", 0.0),
            angular_velocity=data.get("angular_velocity", 0.0),
            rotation_center_x=data.get("rotation_center_x", 0.0),
            rotation_center_y=data.get("rotation_center_y", 0.0),
            plate_type=plate_type,
            density=data.get("density", 2.7),
            thickness=data.get("thickness", 35.0),
            age=data.get("age", 0),
            motion_phase=motion_phase,
            motion_target_plate=data.get("motion_target_plate"),
            tile_count=data.get("tile_count", 0),
            boundary_tile_count=data.get("boundary_tile_count", 0),
        )


@dataclass
class GeologicalFeature:
    """地质特征"""
    id: int
    feature_type: FeatureType
    x: int
    y: int
    tile_id: int
    
    intensity: float = 0.5       # 强度 0-1
    plate_id: int = 0            # 所属板块
    boundary_type: BoundaryType | None = None  # 所在边界类型
    
    name: str | None = None      # 名称
    last_eruption_turn: int | None = None  # 上次喷发回合（火山专用）
    dormant: bool = False        # 是否休眠
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "feature_type": self.feature_type.value,
            "x": self.x,
            "y": self.y,
            "tile_id": self.tile_id,
            "intensity": self.intensity,
            "plate_id": self.plate_id,
            "boundary_type": self.boundary_type.value if self.boundary_type else None,
            "name": self.name,
            "last_eruption_turn": self.last_eruption_turn,
            "dormant": self.dormant,
        }


@dataclass
class TectonicEvent:
    """地质事件"""
    event_type: str              # "earthquake", "volcanic_eruption", "orogeny", "rifting"
    x: int
    y: int
    tile_id: int
    
    magnitude: float = 0.0       # 强度/震级
    affected_radius: int = 1     # 影响范围
    description: str = ""
    plate_id: int = 0
    related_feature_id: int | None = None  # 关联的地质特征ID
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "x": self.x,
            "y": self.y,
            "tile_id": self.tile_id,
            "magnitude": self.magnitude,
            "affected_radius": self.affected_radius,
            "description": self.description,
            "plate_id": self.plate_id,
            "related_feature_id": self.related_feature_id,
        }


@dataclass
class IsolationEvent:
    """物种隔离事件（板块分裂导致）"""
    species_id: int
    lineage_code: str
    plate_a: int
    plate_b: int
    distance_increase: float
    may_speciate: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "species_id": self.species_id,
            "lineage_code": self.lineage_code,
            "plate_a": self.plate_a,
            "plate_b": self.plate_b,
            "distance_increase": self.distance_increase,
            "may_speciate": self.may_speciate,
        }


@dataclass
class ContactEvent:
    """物种接触事件（板块碰撞导致）"""
    species_a_id: int
    species_b_id: int
    plate_a: int
    plate_b: int
    interaction_type: str  # "competition", "predation", "neutral"
    similarity: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "species_a_id": self.species_a_id,
            "species_b_id": self.species_b_id,
            "plate_a": self.plate_a,
            "plate_b": self.plate_b,
            "interaction_type": self.interaction_type,
            "similarity": self.similarity,
        }


@dataclass
class TerrainChange:
    """地形变化记录"""
    tile_id: int
    x: int
    y: int
    old_elevation: float
    new_elevation: float
    cause: str  # "collision", "subduction", "rifting", "erosion", "volcanic"
    
    # 温度变化
    old_temperature: float = 0.0
    new_temperature: float = 0.0
    
    @property
    def elevation_delta(self) -> float:
        return self.new_elevation - self.old_elevation
    
    @property
    def temperature_delta(self) -> float:
        return self.new_temperature - self.old_temperature


@dataclass
class TectonicStepResult:
    """单步板块运动的结果"""
    turn_index: int
    
    # 地形变化
    terrain_changes: list[TerrainChange] = field(default_factory=list)
    
    # 地质事件
    events: list[TectonicEvent] = field(default_factory=list)
    
    # 物种相关事件
    isolation_events: list[IsolationEvent] = field(default_factory=list)
    contact_events: list[ContactEvent] = field(default_factory=list)
    
    # 压力反馈（叠加到环境压力）
    pressure_feedback: dict[str, float] = field(default_factory=dict)
    
    # 统计信息
    tiles_affected: int = 0
    plates_moved: int = 0
    volcanoes_erupted: int = 0
    earthquakes_occurred: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "terrain_changes": [
                {
                    "tile_id": tc.tile_id,
                    "old_elevation": tc.old_elevation,
                    "new_elevation": tc.new_elevation,
                    "cause": tc.cause,
                }
                for tc in self.terrain_changes
            ],
            "events": [e.to_dict() for e in self.events],
            "isolation_events": [e.to_dict() for e in self.isolation_events],
            "contact_events": [e.to_dict() for e in self.contact_events],
            "pressure_feedback": self.pressure_feedback,
            "tiles_affected": self.tiles_affected,
            "plates_moved": self.plates_moved,
            "volcanoes_erupted": self.volcanoes_erupted,
            "earthquakes_occurred": self.earthquakes_occurred,
        }


@dataclass
class SimpleTile:
    """简化的地块数据（用于独立测试，不依赖主系统的MapTile）"""
    id: int
    x: int
    y: int
    elevation: float = 0.0
    temperature: float = 15.0
    humidity: float = 0.5
    biome: str = "平原"
    plate_id: int = 0
    
    # 地质属性
    volcanic_potential: float = 0.0
    tectonic_activity: float = 0.0
    earthquake_risk: float = 0.0
    boundary_type: BoundaryType = BoundaryType.INTERNAL
    distance_to_boundary: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "biome": self.biome,
            "plate_id": self.plate_id,
            "volcanic_potential": self.volcanic_potential,
            "tectonic_activity": self.tectonic_activity,
            "earthquake_risk": self.earthquake_risk,
            "boundary_type": self.boundary_type.value,
            "distance_to_boundary": self.distance_to_boundary,
        }

