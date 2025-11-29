"""板块运动引擎

处理板块的移动、碰撞检测、边界效应等。
"""

from __future__ import annotations

import math
import random
from typing import Sequence

import numpy as np

from .config import TECTONIC_CONFIG, BOUNDARY_TYPE_CODES
from .models import (
    Plate, PlateType, BoundaryType, MotionPhase,
    SimpleTile, TerrainChange, TectonicEvent
)


class PlateMotionEngine:
    """板块运动引擎
    
    核心功能：
    1. 计算板块运动（平移+旋转）
    2. 检测边界类型（张裂/碰撞/俯冲/转换）
    3. 应用地形变化
    4. 生成地质事件（地震、火山等）
    """
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.config = TECTONIC_CONFIG["motion"]
        self.terrain_config = TECTONIC_CONFIG["terrain"]
        self.event_config = TECTONIC_CONFIG["events"]
    
    def step(
        self,
        plates: list[Plate],
        plate_map: np.ndarray,
        tiles: list[SimpleTile],
        pressure_modifiers: dict[str, float] | None = None,
        turn_index: int = 0,
    ) -> tuple[list[TerrainChange], list[TectonicEvent], dict[str, float]]:
        """
        执行一步板块运动
        
        Args:
            plates: 板块列表
            plate_map: 板块ID矩阵
            tiles: 地块列表
            pressure_modifiers: 环境压力修改器
            turn_index: 当前回合
            
        Returns:
            (地形变化列表, 地质事件列表, 压力反馈)
        """
        pressure_modifiers = pressure_modifiers or {}
        
        # === 1. 应用压力到板块运动 ===
        self._apply_pressure_effects(plates, pressure_modifiers)
        
        # === 2. 更新板块速度（衰减+纬度效应）===
        self._update_velocities(plates)
        
        # === 3. 检测边界类型 ===
        boundary_info = self._detect_boundaries(plates, plate_map, tiles)
        
        # === 4. 计算应力和地形变化 ===
        terrain_changes = self._compute_terrain_changes(
            plates, plate_map, tiles, boundary_info, pressure_modifiers
        )
        
        # === 5. 生成地质事件 ===
        events = self._generate_events(
            plates, plate_map, tiles, boundary_info, pressure_modifiers, turn_index
        )
        
        # === 6. 更新板块状态 ===
        self._update_plate_states(plates, boundary_info)
        
        # === 7. 计算压力反馈 ===
        pressure_feedback = self._compute_pressure_feedback(terrain_changes, events)
        
        # === 8. 更新板块年龄 ===
        for plate in plates:
            plate.age += 1
        
        return terrain_changes, events, pressure_feedback
    
    def _apply_pressure_effects(
        self, 
        plates: list[Plate], 
        modifiers: dict[str, float]
    ) -> None:
        """应用环境压力到板块运动"""
        effects = TECTONIC_CONFIG["pressure_effects"]
        
        for pressure_type, intensity in modifiers.items():
            if pressure_type not in effects:
                continue
            
            effect = effects[pressure_type]
            factor = intensity / 10.0  # 归一化强度
            
            for plate in plates:
                # 全局速度加成
                if "all_speed_boost" in effect:
                    boost = 1 + (effect["all_speed_boost"] - 1) * factor
                    plate.velocity_x *= boost
                    plate.velocity_y *= boost
                
                # 全局速度减缓
                if "all_speed_damping" in effect:
                    damping = 1 - (1 - effect["all_speed_damping"]) * factor
                    plate.velocity_x *= damping
                    plate.velocity_y *= damping
                
                # 碰撞速度加成
                if "collision_speed_boost" in effect:
                    if plate.motion_phase == MotionPhase.COLLIDING:
                        boost = 1 + (effect["collision_speed_boost"] - 1) * factor
                        plate.velocity_x *= boost
                        plate.velocity_y *= boost
                
                # 张裂速度加成
                if "divergent_speed_boost" in effect:
                    if plate.motion_phase == MotionPhase.RIFTING:
                        boost = 1 + (effect["divergent_speed_boost"] - 1) * factor
                        plate.velocity_x *= boost
                        plate.velocity_y *= boost
    
    def _update_velocities(self, plates: list[Plate]) -> None:
        """更新板块速度（衰减+纬度效应+边界约束）"""
        cfg = self.config
        
        for plate in plates:
            # 速度衰减
            plate.velocity_x *= cfg["velocity_decay"]
            plate.velocity_y *= cfg["velocity_decay"]
            
            # 纬度效应
            lat = plate.rotation_center_y / self.height
            lat_factor = 1 - abs(lat - 0.5) * 2  # 0=极地, 1=赤道
            
            if lat_factor < 0.3:  # 极地
                damping = cfg["polar_motion_damping"]
                plate.velocity_x *= damping
                plate.velocity_y *= damping
            elif lat_factor > 0.7:  # 热带
                boost = cfg["tropical_motion_boost"]
                plate.velocity_x *= boost
                plate.velocity_y *= boost
            
            # Y轴速度限制
            max_vy = cfg["max_y_velocity"]
            plate.velocity_y = max(-max_vy, min(max_vy, plate.velocity_y))
            
            # 极地反弹
            if plate.rotation_center_y < 2 and plate.velocity_y < 0:
                plate.velocity_y = abs(plate.velocity_y) * cfg["polar_bounce_factor"]
            elif plate.rotation_center_y > self.height - 3 and plate.velocity_y > 0:
                plate.velocity_y = -abs(plate.velocity_y) * cfg["polar_bounce_factor"]
            
            # 速度限制
            speed = plate.speed()
            if speed > cfg["max_velocity"]:
                scale = cfg["max_velocity"] / speed
                plate.velocity_x *= scale
                plate.velocity_y *= scale
            elif speed < cfg["min_velocity"]:
                # 随机给予一个小的扰动
                plate.velocity_x += random.uniform(-0.02, 0.02)
                plate.velocity_y += random.uniform(-0.01, 0.01)
            
            # 更新旋转中心（模拟板块漂移）
            plate.rotation_center_x = (plate.rotation_center_x + plate.velocity_x) % self.width
            plate.rotation_center_y = max(1, min(self.height - 2, 
                                                  plate.rotation_center_y + plate.velocity_y))
    
    def _detect_boundaries(
        self,
        plates: list[Plate],
        plate_map: np.ndarray,
        tiles: list[SimpleTile],
    ) -> dict:
        """
        检测边界类型
        
        Returns:
            {
                "tile_boundaries": {tile_id: BoundaryType},
                "plate_adjacency": np.ndarray (n_plates, n_plates),
                "boundary_tiles": list[int],
            }
        """
        n_plates = len(plates)
        tile_boundaries: dict[int, BoundaryType] = {}
        plate_adjacency = np.zeros((n_plates, n_plates), dtype=np.int32)
        boundary_tiles: list[int] = []
        
        tile_map = {t.id: t for t in tiles}
        
        for tile in tiles:
            x, y = tile.x, tile.y
            my_plate_id = tile.plate_id
            
            neighbors = self._get_neighbors(x, y)
            is_boundary = False
            neighbor_plates = set()
            
            for nx, ny in neighbors:
                if 0 <= ny < self.height:
                    neighbor_tile_id = ny * self.width + nx
                    neighbor_tile = tile_map.get(neighbor_tile_id)
                    if neighbor_tile and neighbor_tile.plate_id != my_plate_id:
                        neighbor_plates.add(neighbor_tile.plate_id)
                        is_boundary = True
            
            if is_boundary:
                boundary_tiles.append(tile.id)
                
                # 确定边界类型
                my_plate = plates[my_plate_id]
                for neighbor_plate_id in neighbor_plates:
                    neighbor_plate = plates[neighbor_plate_id]
                    boundary_type = self._classify_boundary(my_plate, neighbor_plate)
                    
                    # 更新地块边界类型（取最高优先级）
                    current = tile_boundaries.get(tile.id, BoundaryType.INTERNAL)
                    if boundary_type.value > current.value:
                        tile_boundaries[tile.id] = boundary_type
                    
                    # 更新板块邻接矩阵
                    plate_adjacency[my_plate_id, neighbor_plate_id] = boundary_type.value
                    plate_adjacency[neighbor_plate_id, my_plate_id] = boundary_type.value
        
        # 更新地块对象
        for tile in tiles:
            if tile.id in tile_boundaries:
                tile.boundary_type = tile_boundaries[tile.id]
                tile.distance_to_boundary = 0
            else:
                tile.boundary_type = BoundaryType.INTERNAL
        
        # 计算到边界的距离
        self._compute_boundary_distances(tiles, boundary_tiles)
        
        return {
            "tile_boundaries": tile_boundaries,
            "plate_adjacency": plate_adjacency,
            "boundary_tiles": boundary_tiles,
        }
    
    def _classify_boundary(self, plate_a: Plate, plate_b: Plate) -> BoundaryType:
        """分类边界类型"""
        # 计算相对速度方向
        rel_vx = plate_a.velocity_x - plate_b.velocity_x
        rel_vy = plate_a.velocity_y - plate_b.velocity_y
        
        # 计算板块中心连线方向
        dx = plate_b.rotation_center_x - plate_a.rotation_center_x
        # 处理X轴循环
        if abs(dx) > self.width / 2:
            dx = dx - self.width if dx > 0 else dx + self.width
        dy = plate_b.rotation_center_y - plate_a.rotation_center_y
        
        # 点积判断是接近还是远离
        dot_product = rel_vx * dx + rel_vy * dy
        
        if dot_product > 0.01:
            # 接近：碰撞或俯冲
            if plate_a.plate_type == PlateType.OCEANIC and plate_b.plate_type == PlateType.CONTINENTAL:
                return BoundaryType.SUBDUCTION
            elif plate_a.plate_type == PlateType.CONTINENTAL and plate_b.plate_type == PlateType.OCEANIC:
                return BoundaryType.SUBDUCTION
            elif plate_a.plate_type == PlateType.OCEANIC and plate_b.plate_type == PlateType.OCEANIC:
                # 洋-洋：密度大的俯冲
                return BoundaryType.SUBDUCTION
            else:
                return BoundaryType.CONVERGENT
        elif dot_product < -0.01:
            # 远离：张裂
            return BoundaryType.DIVERGENT
        else:
            # 平行移动：转换
            return BoundaryType.TRANSFORM
    
    def _compute_boundary_distances(
        self, 
        tiles: list[SimpleTile], 
        boundary_tiles: list[int]
    ) -> None:
        """计算每个地块到最近边界的距离"""
        if not boundary_tiles:
            return
        
        tile_map = {t.id: t for t in tiles}
        boundary_set = set(boundary_tiles)
        
        # BFS 计算距离
        from collections import deque
        
        visited = set(boundary_tiles)
        queue = deque([(tid, 0) for tid in boundary_tiles])
        
        while queue:
            tile_id, dist = queue.popleft()
            tile = tile_map.get(tile_id)
            if not tile:
                continue
            
            tile.distance_to_boundary = dist
            
            neighbors = self._get_neighbors(tile.x, tile.y)
            for nx, ny in neighbors:
                if 0 <= ny < self.height:
                    neighbor_id = ny * self.width + nx
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, dist + 1))
    
    def _compute_terrain_changes(
        self,
        plates: list[Plate],
        plate_map: np.ndarray,
        tiles: list[SimpleTile],
        boundary_info: dict,
        pressure_modifiers: dict[str, float],
    ) -> list[TerrainChange]:
        """计算地形变化 - 渐进式、平滑的变化"""
        changes = []
        cfg = self.terrain_config
        
        # 压力加成
        elevation_boost = 1.0
        if "orogeny" in pressure_modifiers:
            boost = TECTONIC_CONFIG["pressure_effects"]["orogeny"].get("elevation_change_boost", 1.0)
            elevation_boost = 1 + (boost - 1) * (pressure_modifiers["orogeny"] / 10)
        
        # 第一步：计算原始变化
        deltas = {}  # tile_id -> delta
        causes = {}  # tile_id -> cause
        
        for tile in tiles:
            boundary_type = tile.boundary_type
            dist = tile.distance_to_boundary
            
            if boundary_type == BoundaryType.INTERNAL and dist > cfg["boundary_effect_radius"]:
                continue
            
            delta = 0.0
            cause = "internal"
            
            # 使用更平滑的距离衰减（高斯衰减）
            effect_radius = cfg["boundary_effect_radius"]
            if dist > 0:
                # 高斯衰减：边界效果平滑过渡
                distance_factor = math.exp(-(dist ** 2) / (2 * (effect_radius / 2) ** 2))
            else:
                distance_factor = 1.0
            
            # 根据边界类型计算变化
            if boundary_type == BoundaryType.CONVERGENT:
                # 大陆碰撞：缓慢隆起
                delta = cfg["mountain_growth_rate"] * distance_factor
                cause = "collision"
            
            elif boundary_type == BoundaryType.SUBDUCTION:
                # 俯冲边界：需要检查是否在海洋中
                features_cfg = TECTONIC_CONFIG["features"]
                min_ocean = features_cfg.get("trench_min_ocean_depth", -500)
                trench_max = features_cfg.get("trench_max_depth", -8000)
                deepen_rate = features_cfg.get("trench_deepen_rate", 50)
                
                if tile.elevation < min_ocean:
                    # 只有足够深的海洋才能形成海沟
                    # 渐进式加深，不会一下子变成-8000
                    current_depth = tile.elevation
                    target_depth = max(trench_max, current_depth - deepen_rate * distance_factor)
                    delta = (target_depth - current_depth) * 0.1  # 每回合只变化10%的差距
                    cause = "subduction"
                elif tile.elevation >= 0:
                    # 陆地侧：火山弧（轻微隆起）
                    delta = cfg["mountain_growth_rate"] * 0.2 * distance_factor
                    cause = "volcanic_arc"
                else:
                    # 浅海：轻微下沉
                    delta = -cfg["subduction_depth_rate"] * 0.3 * distance_factor
                    cause = "subduction"
            
            elif boundary_type == BoundaryType.DIVERGENT:
                # 张裂：缓慢下沉
                delta = -cfg["rift_subsidence_rate"] * distance_factor
                cause = "rifting"
            
            elif boundary_type == BoundaryType.TRANSFORM:
                # 转换边界：无明显垂直变化
                pass
            
            # 侵蚀作用（只对高山）
            if tile.elevation > 3000:
                erosion = cfg["erosion_rate"] * ((tile.elevation - 3000) / 5000)
                delta -= erosion
            
            # 应用压力加成
            delta *= elevation_boost
            
            # 限制单回合变化
            max_change = cfg["max_elevation_change"]
            delta = max(-max_change, min(max_change, delta))
            
            if abs(delta) > 0.001:
                deltas[tile.id] = delta
                causes[tile.id] = cause
        
        # 第二步：平滑处理 - 与邻居取平均
        smoothing_strength = cfg.get("smoothing_strength", 0.15)
        smoothing_iterations = cfg.get("smoothing_iterations", 2)
        
        tile_map = {t.id: t for t in tiles}
        
        for _ in range(smoothing_iterations):
            smoothed_deltas = {}
            for tile_id, delta in deltas.items():
                tile = tile_map.get(tile_id)
                if not tile:
                    smoothed_deltas[tile_id] = delta
                    continue
                
                # 获取邻居的变化
                neighbors = self._get_neighbors(tile.x, tile.y)
                neighbor_deltas = []
                for nx, ny in neighbors:
                    if 0 <= ny < self.height:
                        neighbor_id = ny * self.width + nx
                        if neighbor_id in deltas:
                            neighbor_deltas.append(deltas[neighbor_id])
                
                if neighbor_deltas:
                    # 与邻居平均
                    avg_neighbor = sum(neighbor_deltas) / len(neighbor_deltas)
                    smoothed = delta * (1 - smoothing_strength) + avg_neighbor * smoothing_strength
                    smoothed_deltas[tile_id] = smoothed
                else:
                    smoothed_deltas[tile_id] = delta
            
            deltas = smoothed_deltas
        
        # 第三步：应用变化并更新温度
        temp_per_100m = cfg.get("temp_per_100m_elevation", -0.6)
        
        for tile in tiles:
            if tile.id not in deltas:
                continue
            
            delta = deltas[tile.id]
            cause = causes.get(tile.id, "internal")
            
            old_elevation = tile.elevation
            old_temperature = tile.temperature
            
            tile.elevation += delta
            
            # 更新温度（海拔每变化100米，温度变化0.6°C）
            temp_change = (delta / 100) * temp_per_100m
            tile.temperature += temp_change
            
            changes.append(TerrainChange(
                tile_id=tile.id,
                x=tile.x,
                y=tile.y,
                old_elevation=old_elevation,
                new_elevation=tile.elevation,
                cause=cause,
                old_temperature=old_temperature,
                new_temperature=tile.temperature,
            ))
        
        return changes
    
    def _generate_events(
        self,
        plates: list[Plate],
        plate_map: np.ndarray,
        tiles: list[SimpleTile],
        boundary_info: dict,
        pressure_modifiers: dict[str, float],
        turn_index: int,
    ) -> list[TectonicEvent]:
        """生成地质事件"""
        events = []
        cfg = self.event_config
        
        # 压力加成
        earthquake_boost = 1.0
        volcano_boost = 1.0
        
        if "earthquake_period" in pressure_modifiers:
            earthquake_boost = TECTONIC_CONFIG["pressure_effects"]["earthquake_period"].get(
                "earthquake_probability_boost", 1.0
            ) * (pressure_modifiers["earthquake_period"] / 10)
        
        if "volcanic_eruption" in pressure_modifiers:
            volcano_boost = TECTONIC_CONFIG["pressure_effects"]["volcanic_eruption"].get(
                "eruption_probability_boost", 1.0
            ) * (pressure_modifiers["volcanic_eruption"] / 10)
        
        boundary_tiles = boundary_info.get("boundary_tiles", [])
        tile_map = {t.id: t for t in tiles}
        
        for tile_id in boundary_tiles:
            tile = tile_map.get(tile_id)
            if not tile:
                continue
            
            boundary_type = tile.boundary_type
            
            # 地震概率
            eq_base = cfg["earthquake_base_prob"]
            eq_boundary_boost = cfg["boundary_earthquake_boost"].get(
                boundary_type.name.lower(), 1.0
            )
            earthquake_prob = eq_base * eq_boundary_boost * earthquake_boost
            
            if random.random() < earthquake_prob:
                # 生成地震
                magnitude = 4.0 + random.uniform(0, 4)  # 4-8级
                if boundary_type == BoundaryType.SUBDUCTION:
                    magnitude += 1.0  # 俯冲带地震更强
                
                events.append(TectonicEvent(
                    event_type="earthquake",
                    x=tile.x,
                    y=tile.y,
                    tile_id=tile.id,
                    magnitude=magnitude,
                    affected_radius=int(magnitude / 2),
                    description=f"地震（{magnitude:.1f}级）发生在板块边界",
                    plate_id=tile.plate_id,
                ))
            
            # 火山喷发概率（只在特定边界类型）
            if boundary_type in [BoundaryType.SUBDUCTION, BoundaryType.DIVERGENT]:
                vol_base = cfg["volcano_eruption_base_prob"]
                vol_boundary_boost = cfg["boundary_volcano_boost"].get(
                    boundary_type.name.lower(), 1.0
                )
                volcano_prob = vol_base * vol_boundary_boost * volcano_boost
                
                # 考虑已有的火山潜力
                volcano_prob *= (1 + tile.volcanic_potential)
                
                if random.random() < volcano_prob:
                    intensity = random.uniform(0.5, 1.0)
                    events.append(TectonicEvent(
                        event_type="volcanic_eruption",
                        x=tile.x,
                        y=tile.y,
                        tile_id=tile.id,
                        magnitude=intensity * 10,
                        affected_radius=2 + int(intensity * 3),
                        description=f"火山喷发，强度{intensity:.1f}",
                        plate_id=tile.plate_id,
                    ))
                    
                    # 更新火山潜力
                    tile.volcanic_potential = min(1.0, tile.volcanic_potential + 0.2)
        
        return events
    
    def _update_plate_states(
        self, 
        plates: list[Plate], 
        boundary_info: dict
    ) -> None:
        """更新板块运动状态"""
        adjacency = boundary_info.get("plate_adjacency", np.array([]))
        
        if adjacency.size == 0:
            return
        
        for plate in plates:
            # 检查与其他板块的关系
            colliding = False
            subducting = False
            rifting = False
            
            for other_idx in range(len(plates)):
                if other_idx == plate.plate_index:
                    continue
                
                relation = adjacency[plate.plate_index, other_idx]
                if relation == BoundaryType.CONVERGENT.value:
                    colliding = True
                    plate.motion_target_plate = other_idx
                elif relation == BoundaryType.SUBDUCTION.value:
                    subducting = True
                    plate.motion_target_plate = other_idx
                elif relation == BoundaryType.DIVERGENT.value:
                    rifting = True
            
            # 确定运动阶段
            if colliding:
                plate.motion_phase = MotionPhase.COLLIDING
            elif subducting:
                plate.motion_phase = MotionPhase.SUBDUCTING
            elif rifting:
                plate.motion_phase = MotionPhase.RIFTING
            elif plate.speed() > 0.05:
                plate.motion_phase = MotionPhase.DRIFTING
            else:
                plate.motion_phase = MotionPhase.STABLE
    
    def _compute_pressure_feedback(
        self,
        terrain_changes: list[TerrainChange],
        events: list[TectonicEvent],
    ) -> dict[str, float]:
        """计算对压力系统的反馈"""
        feedback = {}
        
        # 统计地震
        earthquakes = [e for e in events if e.event_type == "earthquake"]
        if earthquakes:
            avg_magnitude = sum(e.magnitude for e in earthquakes) / len(earthquakes)
            feedback["tectonic"] = min(5.0, len(earthquakes) * 0.5 + avg_magnitude * 0.3)
        
        # 统计火山
        volcanoes = [e for e in events if e.event_type == "volcanic_eruption"]
        if volcanoes:
            total_intensity = sum(e.magnitude for e in volcanoes) / 10
            feedback["volcanic"] = min(8.0, total_intensity)
            feedback["sulfur_aerosol"] = len(volcanoes) * 0.3
        
        # 统计造山
        uplifts = [tc for tc in terrain_changes if tc.elevation_delta > 5]
        if len(uplifts) > 10:
            feedback["altitude_change"] = len(uplifts) * 0.2
        
        # 统计沉降
        subsidences = [tc for tc in terrain_changes if tc.elevation_delta < -3]
        if len(subsidences) > 10:
            feedback["sea_level"] = len(subsidences) * 0.1
        
        return feedback
    
    def _get_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        """获取六边形邻居"""
        if x & 1:
            offsets = [(0, -1), (1, -1), (-1, 0), (1, 0), (0, 1), (1, 1)]
        else:
            offsets = [(-1, -1), (0, -1), (-1, 0), (1, 0), (-1, 1), (0, 1)]
        
        neighbors = []
        for dx, dy in offsets:
            nx = (x + dx) % self.width
            ny = y + dy
            if 0 <= ny < self.height:
                neighbors.append((nx, ny))
        
        return neighbors

