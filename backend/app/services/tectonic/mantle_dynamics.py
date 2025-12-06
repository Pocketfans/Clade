"""地幔动力学模块

模拟地幔对流，为板块运动提供物理驱动力。
实现威尔逊周期（超大陆聚合-分裂循环）。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from .config import TECTONIC_CONFIG
from .models import Plate, PlateType, MotionPhase

if TYPE_CHECKING:
    pass


class WilsonPhase(Enum):
    """威尔逊周期阶段
    
    真实地球上一个完整周期约3-5亿年。
    游戏中可以压缩到30-50回合。
    """
    SUPERCONTINENT = "supercontinent"   # 超大陆稳定期
    RIFTING = "rifting"                  # 裂谷期（开始分裂）
    DRIFTING = "drifting"                # 漂移期（大陆分散）
    SUBDUCTION = "subduction"            # 俯冲期（开始汇聚）
    COLLISION = "collision"              # 碰撞期（大陆碰撞）
    OROGENY = "orogeny"                  # 造山期（形成超大陆）


@dataclass
class ConvectionCell:
    """对流单元
    
    地幔对流的基本单位，驱动板块运动。
    """
    id: int
    center_x: float
    center_y: float
    radius: float
    strength: float  # 对流强度 0-1
    direction: str   # "ascending" (上升流) 或 "descending" (下降流)
    
    # 流动速度场（简化为径向）
    # 上升流：向外推动板块（张裂）
    # 下降流：向内拉动板块（俯冲）
    
    def get_velocity_at(self, x: float, y: float, width: int) -> tuple[float, float]:
        """计算某点的流速"""
        # 计算相对位置（考虑X轴循环）
        dx = x - self.center_x
        if abs(dx) > width / 2:
            dx = dx - width if dx > 0 else dx + width
        dy = y - self.center_y
        
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 0.1:
            return 0.0, 0.0
        
        # 归一化方向
        dx /= dist
        dy /= dist
        
        # 强度随距离衰减
        if dist > self.radius:
            effect = 0.0
        else:
            # 钟形曲线：中心弱，中间强，边缘弱
            normalized_dist = dist / self.radius
            effect = math.sin(normalized_dist * math.pi) * self.strength
        
        # 方向：上升流向外推，下降流向内拉
        if self.direction == "ascending":
            return dx * effect, dy * effect
        else:
            return -dx * effect, -dy * effect


@dataclass
class MantleDynamicsState:
    """地幔动力学状态"""
    wilson_phase: WilsonPhase = WilsonPhase.DRIFTING
    phase_progress: float = 0.0  # 当前阶段进度 0-1
    phase_duration: int = 30      # 当前阶段持续回合
    total_cycles: int = 0         # 完成的威尔逊周期数
    
    convection_cells: list[ConvectionCell] = field(default_factory=list)
    
    # 全局地幔活动指数
    mantle_activity: float = 0.5
    
    # 超大陆聚合度（0=完全分散, 1=完全聚合）
    continental_aggregation: float = 0.3
    
    def to_dict(self) -> dict:
        return {
            "wilson_phase": self.wilson_phase.value,
            "phase_progress": self.phase_progress,
            "phase_duration": self.phase_duration,
            "total_cycles": self.total_cycles,
            "mantle_activity": self.mantle_activity,
            "continental_aggregation": self.continental_aggregation,
            "convection_cells": [
                {
                    "id": c.id,
                    "center_x": c.center_x,
                    "center_y": c.center_y,
                    "radius": c.radius,
                    "strength": c.strength,
                    "direction": c.direction,
                }
                for c in self.convection_cells
            ],
        }


class MantleDynamicsEngine:
    """地幔动力学引擎
    
    核心功能：
    1. 维护对流单元（提供板块运动驱动力）
    2. 管理威尔逊周期（超大陆聚合-分裂循环）
    3. 计算板块驱动力
    """
    
    # 威尔逊周期各阶段的默认持续时间（回合）
    PHASE_DURATIONS = {
        WilsonPhase.SUPERCONTINENT: (10, 20),
        WilsonPhase.RIFTING: (5, 10),
        WilsonPhase.DRIFTING: (15, 30),
        WilsonPhase.SUBDUCTION: (10, 20),
        WilsonPhase.COLLISION: (8, 15),
        WilsonPhase.OROGENY: (5, 10),
    }
    
    # 阶段转换顺序
    PHASE_SEQUENCE = [
        WilsonPhase.SUPERCONTINENT,
        WilsonPhase.RIFTING,
        WilsonPhase.DRIFTING,
        WilsonPhase.SUBDUCTION,
        WilsonPhase.COLLISION,
        WilsonPhase.OROGENY,
        # 然后循环回 SUPERCONTINENT
    ]
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.state = MantleDynamicsState()
        
        # 配置
        self.config = {
            "num_convection_cells": (3, 6),
            "cell_radius_range": (0.15, 0.35),  # 占地图宽度的比例
            "base_cell_strength": 0.1,
            
            # 驱动力系数
            "ridge_push_factor": 0.3,     # 脊推力
            "slab_pull_factor": 0.5,      # 板片拉力（俯冲板块）
            "convection_drag_factor": 0.4, # 对流拖曳
            
            # 威尔逊周期影响
            "phase_velocity_modifiers": {
                WilsonPhase.SUPERCONTINENT: 0.3,  # 超大陆期运动慢
                WilsonPhase.RIFTING: 0.8,          # 裂谷期运动加快
                WilsonPhase.DRIFTING: 1.0,         # 漂移期正常
                WilsonPhase.SUBDUCTION: 1.2,       # 俯冲期运动快
                WilsonPhase.COLLISION: 0.9,        # 碰撞期略慢
                WilsonPhase.OROGENY: 0.5,          # 造山期运动慢
            },
        }
    
    def initialize(self, seed: int, initial_phase: WilsonPhase | None = None) -> None:
        """初始化地幔动力学系统"""
        random.seed(seed)
        np.random.seed(seed)
        
        # 设置初始阶段
        if initial_phase:
            self.state.wilson_phase = initial_phase
        else:
            # 随机选择一个阶段开始
            self.state.wilson_phase = random.choice(self.PHASE_SEQUENCE)
        
        # 设置阶段持续时间
        duration_range = self.PHASE_DURATIONS[self.state.wilson_phase]
        self.state.phase_duration = random.randint(*duration_range)
        self.state.phase_progress = random.uniform(0.0, 0.3)  # 随机进度
        
        # 生成对流单元
        self._generate_convection_cells(seed)
        
        # 初始化聚合度
        self._update_aggregation_from_phase()
    
    def _generate_convection_cells(self, seed: int) -> None:
        """生成对流单元"""
        random.seed(seed + 5000)
        
        num_cells = random.randint(*self.config["num_convection_cells"])
        self.state.convection_cells.clear()
        
        for i in range(num_cells):
            # 随机位置
            cx = random.uniform(0, self.width)
            cy = random.uniform(self.height * 0.2, self.height * 0.8)  # 避开极地
            
            # 随机半径
            radius_ratio = random.uniform(*self.config["cell_radius_range"])
            radius = self.width * radius_ratio
            
            # 随机强度
            strength = self.config["base_cell_strength"] * random.uniform(0.7, 1.3)
            
            # 交替上升和下降
            direction = "ascending" if i % 2 == 0 else "descending"
            
            cell = ConvectionCell(
                id=i,
                center_x=cx,
                center_y=cy,
                radius=radius,
                strength=strength,
                direction=direction,
            )
            self.state.convection_cells.append(cell)
    
    def _update_aggregation_from_phase(self) -> None:
        """根据威尔逊阶段更新聚合度目标"""
        phase = self.state.wilson_phase
        
        if phase == WilsonPhase.SUPERCONTINENT:
            self.state.continental_aggregation = 0.9
        elif phase == WilsonPhase.RIFTING:
            self.state.continental_aggregation = 0.7
        elif phase == WilsonPhase.DRIFTING:
            self.state.continental_aggregation = 0.3
        elif phase == WilsonPhase.SUBDUCTION:
            self.state.continental_aggregation = 0.4
        elif phase == WilsonPhase.COLLISION:
            self.state.continental_aggregation = 0.6
        elif phase == WilsonPhase.OROGENY:
            self.state.continental_aggregation = 0.85
    
    def step(
        self, 
        plates: list[Plate], 
        pressure_modifiers: dict[str, float] | None = None
    ) -> dict:
        """
        执行一步地幔动力学更新
        
        Args:
            plates: 板块列表
            pressure_modifiers: 环境压力
            
        Returns:
            {
                "phase_changed": bool,
                "new_phase": str | None,
                "velocity_updates": list[(plate_id, vx, vy)],
                "mantle_activity": float,
            }
        """
        pressure_modifiers = pressure_modifiers or {}
        
        # 1. 更新威尔逊周期
        phase_changed, new_phase = self._advance_wilson_cycle()
        
        # 2. 计算板块驱动力
        velocity_updates = self._compute_plate_forces(plates)
        
        # 3. 更新对流单元（缓慢演化）
        self._evolve_convection_cells()
        
        # 4. 应用压力影响
        if "mantle_plume" in pressure_modifiers:
            self.state.mantle_activity += pressure_modifiers["mantle_plume"] * 0.05
        
        self.state.mantle_activity = max(0.2, min(1.0, self.state.mantle_activity))
        
        return {
            "phase_changed": phase_changed,
            "new_phase": new_phase.value if new_phase else None,
            "velocity_updates": velocity_updates,
            "mantle_activity": self.state.mantle_activity,
        }
    
    def _advance_wilson_cycle(self) -> tuple[bool, WilsonPhase | None]:
        """推进威尔逊周期"""
        # 增加进度
        progress_step = 1.0 / self.state.phase_duration
        self.state.phase_progress += progress_step
        
        if self.state.phase_progress >= 1.0:
            # 进入下一阶段
            current_idx = self.PHASE_SEQUENCE.index(self.state.wilson_phase)
            next_idx = (current_idx + 1) % len(self.PHASE_SEQUENCE)
            new_phase = self.PHASE_SEQUENCE[next_idx]
            
            # 如果完成一个完整周期
            if next_idx == 0:
                self.state.total_cycles += 1
            
            self.state.wilson_phase = new_phase
            self.state.phase_progress = 0.0
            
            # 设置新阶段持续时间
            duration_range = self.PHASE_DURATIONS[new_phase]
            self.state.phase_duration = random.randint(*duration_range)
            
            # 更新聚合度
            self._update_aggregation_from_phase()
            
            return True, new_phase
        
        return False, None
    
    def _compute_plate_forces(
        self, 
        plates: list[Plate]
    ) -> list[tuple[int, float, float]]:
        """计算所有板块的驱动力"""
        updates = []
        
        phase_modifier = self.config["phase_velocity_modifiers"].get(
            self.state.wilson_phase, 1.0
        )
        
        for plate in plates:
            fx, fy = 0.0, 0.0
            
            # 1. 对流拖曳力
            conv_fx, conv_fy = self._compute_convection_drag(plate)
            fx += conv_fx * self.config["convection_drag_factor"]
            fy += conv_fy * self.config["convection_drag_factor"]
            
            # 2. 脊推力（如果处于裂谷状态）
            if plate.motion_phase == MotionPhase.RIFTING:
                ridge_fx, ridge_fy = self._compute_ridge_push(plate)
                fx += ridge_fx * self.config["ridge_push_factor"]
                fy += ridge_fy * self.config["ridge_push_factor"]
            
            # 3. 板片拉力（如果是俯冲板块）
            if plate.motion_phase == MotionPhase.SUBDUCTING:
                slab_fx, slab_fy = self._compute_slab_pull(plate)
                fx += slab_fx * self.config["slab_pull_factor"]
                fy += slab_fy * self.config["slab_pull_factor"]
            
            # 4. 威尔逊周期阶段修正
            fx *= phase_modifier
            fy *= phase_modifier
            
            # 5. 地幔活动强度
            fx *= self.state.mantle_activity
            fy *= self.state.mantle_activity
            
            # 6. 更新速度（叠加到现有速度）
            new_vx = plate.velocity_x + fx * 0.1
            new_vy = plate.velocity_y + fy * 0.1
            
            updates.append((plate.id, new_vx, new_vy))
        
        return updates
    
    def _compute_convection_drag(self, plate: Plate) -> tuple[float, float]:
        """计算对流拖曳力"""
        total_fx, total_fy = 0.0, 0.0
        
        for cell in self.state.convection_cells:
            vx, vy = cell.get_velocity_at(
                plate.rotation_center_x, 
                plate.rotation_center_y,
                self.width
            )
            total_fx += vx
            total_fy += vy
        
        return total_fx, total_fy
    
    def _compute_ridge_push(self, plate: Plate) -> tuple[float, float]:
        """计算脊推力（从洋中脊向外推）"""
        # 简化模型：向远离地图中心的方向推
        dx = plate.rotation_center_x - self.width / 2
        if abs(dx) > self.width / 2:
            dx = dx - self.width if dx > 0 else dx + self.width
        dy = plate.rotation_center_y - self.height / 2
        
        length = math.sqrt(dx*dx + dy*dy)
        if length < 0.1:
            return 0.0, 0.0
        
        return dx / length * 0.1, dy / length * 0.05
    
    def _compute_slab_pull(self, plate: Plate) -> tuple[float, float]:
        """计算板片拉力（俯冲板块被拉向俯冲带）"""
        if plate.motion_target_plate is None:
            return 0.0, 0.0
        
        # 向目标方向移动
        return plate.velocity_x * 0.2, plate.velocity_y * 0.2
    
    def _evolve_convection_cells(self) -> None:
        """对流单元缓慢演化"""
        for cell in self.state.convection_cells:
            # 缓慢漂移
            cell.center_x = (cell.center_x + random.uniform(-0.1, 0.1)) % self.width
            cell.center_y = max(
                self.height * 0.15,
                min(self.height * 0.85, 
                    cell.center_y + random.uniform(-0.05, 0.05))
            )
            
            # 强度微变
            cell.strength += random.uniform(-0.01, 0.01)
            cell.strength = max(0.05, min(0.2, cell.strength))
    
    def get_wilson_phase_info(self) -> dict:
        """获取威尔逊周期信息"""
        phase = self.state.wilson_phase
        
        descriptions = {
            WilsonPhase.SUPERCONTINENT: "超大陆稳定期：大陆聚合完成，地质活动减少",
            WilsonPhase.RIFTING: "裂谷期：超大陆开始分裂，新的洋盆形成",
            WilsonPhase.DRIFTING: "漂移期：大陆分散漂移，海洋扩张",
            WilsonPhase.SUBDUCTION: "俯冲期：海洋开始消亡，板块俯冲加剧",
            WilsonPhase.COLLISION: "碰撞期：大陆开始碰撞，造山运动活跃",
            WilsonPhase.OROGENY: "造山期：山脉形成，超大陆逐渐成形",
        }
        
        effects = {
            WilsonPhase.SUPERCONTINENT: {"volcanism": -0.3, "earthquake": -0.2, "speciation": -0.2},
            WilsonPhase.RIFTING: {"volcanism": 0.4, "earthquake": 0.2, "speciation": 0.3},
            WilsonPhase.DRIFTING: {"volcanism": 0.1, "earthquake": 0.0, "speciation": 0.5},
            WilsonPhase.SUBDUCTION: {"volcanism": 0.3, "earthquake": 0.4, "speciation": 0.2},
            WilsonPhase.COLLISION: {"volcanism": 0.1, "earthquake": 0.5, "speciation": 0.1},
            WilsonPhase.OROGENY: {"volcanism": 0.2, "earthquake": 0.3, "speciation": -0.1},
        }
        
        return {
            "phase": phase.value,
            "progress": self.state.phase_progress,
            "turns_remaining": int((1 - self.state.phase_progress) * self.state.phase_duration),
            "description": descriptions[phase],
            "effects": effects[phase],
            "total_cycles": self.state.total_cycles,
            "aggregation": self.state.continental_aggregation,
        }
    
    def apply_velocity_updates(
        self, 
        plates: list[Plate], 
        updates: list[tuple[int, float, float]]
    ) -> None:
        """将速度更新应用到板块"""
        plate_map = {p.id: p for p in plates}
        
        for plate_id, vx, vy in updates:
            if plate_id in plate_map:
                plate = plate_map[plate_id]
                plate.velocity_x = vx
                plate.velocity_y = vy









