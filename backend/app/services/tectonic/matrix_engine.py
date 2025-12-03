"""板块构造矩阵引擎

使用 NumPy 矩阵进行高效的批量计算。
"""

from __future__ import annotations

import math
from typing import Sequence, TYPE_CHECKING

import numpy as np

from .config import TECTONIC_CONFIG
from .models import (
    Plate, PlateType, BoundaryType, SimpleTile,
    GeologicalFeature, FeatureType
)

if TYPE_CHECKING:
    pass


class TectonicMatrixEngine:
    """板块构造矩阵引擎
    
    核心矩阵：
    - plate_assignment: (n_tiles,) 板块归属
    - boundary_type: (n_tiles,) 边界类型编码
    - plate_adjacency: (n_plates, n_plates) 板块邻接关系
    - volcanic_potential: (n_tiles,) 火山潜力
    - earthquake_risk: (n_tiles,) 地震风险
    - tectonic_activity: (n_tiles,) 构造活动强度
    """
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.n_tiles = width * height
        
        # 核心矩阵
        self._plate_assignment: np.ndarray | None = None
        self._boundary_type: np.ndarray | None = None
        self._plate_adjacency: np.ndarray | None = None
        self._volcanic_potential: np.ndarray | None = None
        self._earthquake_risk: np.ndarray | None = None
        self._tectonic_activity: np.ndarray | None = None
        self._distance_to_boundary: np.ndarray | None = None
        
        # 地块坐标矩阵
        self._tile_coords: np.ndarray | None = None
        self._tile_elevations: np.ndarray | None = None
        
        # 邻接矩阵（稀疏表示）
        self._neighbor_indices: dict[int, list[int]] = {}
    
    def build(
        self,
        tiles: list[SimpleTile],
        plates: list[Plate],
        plate_map: np.ndarray,
    ) -> None:
        """构建所有矩阵"""
        n_tiles = len(tiles)
        n_plates = len(plates)
        
        # === 1. 板块归属矩阵 ===
        self._plate_assignment = np.array(
            [t.plate_id for t in tiles], dtype=np.int32
        )
        
        # === 2. 地块坐标和高程 ===
        self._tile_coords = np.array(
            [[t.x, t.y] for t in tiles], dtype=np.float32
        )
        self._tile_elevations = np.array(
            [t.elevation for t in tiles], dtype=np.float32
        )
        
        # === 3. 构建邻接关系 ===
        self._build_neighbor_indices(tiles)
        
        # === 4. 边界检测 ===
        self._boundary_type = np.zeros(n_tiles, dtype=np.int32)
        self._plate_adjacency = np.zeros((n_plates, n_plates), dtype=np.int32)
        
        for tile in tiles:
            neighbors = self._neighbor_indices.get(tile.id, [])
            for neighbor_id in neighbors:
                if neighbor_id < n_tiles:
                    neighbor_plate = self._plate_assignment[neighbor_id]
                    if neighbor_plate != tile.plate_id:
                        # 边界地块
                        bt = tiles[tile.id].boundary_type.value if tiles[tile.id].boundary_type else 0
                        self._boundary_type[tile.id] = max(self._boundary_type[tile.id], bt)
                        
                        self._plate_adjacency[tile.plate_id, neighbor_plate] = bt
                        self._plate_adjacency[neighbor_plate, tile.plate_id] = bt
        
        # === 5. 边界距离 ===
        self._distance_to_boundary = np.array(
            [t.distance_to_boundary for t in tiles], dtype=np.int32
        )
        
        # === 6. 地质活动矩阵 ===
        self._volcanic_potential = np.array(
            [t.volcanic_potential for t in tiles], dtype=np.float32
        )
        self._earthquake_risk = np.array(
            [t.earthquake_risk for t in tiles], dtype=np.float32
        )
        self._tectonic_activity = np.array(
            [t.tectonic_activity for t in tiles], dtype=np.float32
        )
    
    def _build_neighbor_indices(self, tiles: list[SimpleTile]) -> None:
        """构建邻接索引"""
        for tile in tiles:
            neighbors = self._get_neighbor_tile_ids(tile.x, tile.y)
            self._neighbor_indices[tile.id] = neighbors
    
    def _get_neighbor_tile_ids(self, x: int, y: int) -> list[int]:
        """获取邻居地块ID"""
        if x & 1:
            offsets = [(0, -1), (1, -1), (-1, 0), (1, 0), (0, 1), (1, 1)]
        else:
            offsets = [(-1, -1), (0, -1), (-1, 0), (1, 0), (-1, 1), (0, 1)]
        
        neighbors = []
        for dx, dy in offsets:
            nx = (x + dx) % self.width
            ny = y + dy
            if 0 <= ny < self.height:
                neighbors.append(ny * self.width + nx)
        
        return neighbors
    
    def compute_boundary_mask(self) -> np.ndarray:
        """获取边界地块掩码"""
        if self._boundary_type is None:
            return np.array([])
        return self._boundary_type > 0
    
    def compute_plate_centroids(self, n_plates: int) -> np.ndarray:
        """计算每个板块的质心"""
        if self._tile_coords is None or self._plate_assignment is None:
            return np.zeros((n_plates, 2))
        
        centroids = np.zeros((n_plates, 2), dtype=np.float32)
        counts = np.zeros(n_plates, dtype=np.int32)
        
        for i, plate_id in enumerate(self._plate_assignment):
            centroids[plate_id] += self._tile_coords[i]
            counts[plate_id] += 1
        
        # 避免除零
        counts = np.maximum(counts, 1)
        centroids /= counts[:, np.newaxis]
        
        return centroids
    
    def compute_elevation_stats_by_plate(self, n_plates: int) -> dict[int, dict[str, float]]:
        """计算每个板块的海拔统计"""
        if self._tile_elevations is None or self._plate_assignment is None:
            return {}
        
        stats = {}
        for plate_id in range(n_plates):
            mask = self._plate_assignment == plate_id
            if not np.any(mask):
                continue
            
            elevations = self._tile_elevations[mask]
            stats[plate_id] = {
                "mean": float(np.mean(elevations)),
                "min": float(np.min(elevations)),
                "max": float(np.max(elevations)),
                "std": float(np.std(elevations)),
                "land_ratio": float(np.mean(elevations >= 0)),
            }
        
        return stats
    
    def compute_boundary_stress_matrix(
        self,
        plates: list[Plate],
    ) -> np.ndarray:
        """
        计算边界应力矩阵
        
        Returns:
            (n_tiles,) 应力值
        """
        if self._boundary_type is None or self._distance_to_boundary is None:
            return np.zeros(self.n_tiles)
        
        stress = np.zeros(self.n_tiles, dtype=np.float32)
        
        # 边界地块基础应力
        boundary_stress = {
            0: 0.0,   # internal
            1: 0.3,   # divergent
            2: 0.8,   # convergent
            3: 0.9,   # subduction
            4: 0.5,   # transform
        }
        
        for i in range(self.n_tiles):
            bt = self._boundary_type[i]
            dist = self._distance_to_boundary[i]
            
            base_stress = boundary_stress.get(bt, 0.0)
            
            # 距离衰减
            if dist > 0:
                distance_factor = 1.0 / (1 + dist * 0.5)
            else:
                distance_factor = 1.0
            
            stress[i] = base_stress * distance_factor
        
        return stress
    
    def compute_volcanic_probability_matrix(
        self,
        pressure_boost: float = 1.0
    ) -> np.ndarray:
        """
        计算火山喷发概率矩阵
        
        Args:
            pressure_boost: 压力加成系数
            
        Returns:
            (n_tiles,) 喷发概率
        """
        if self._volcanic_potential is None or self._boundary_type is None:
            return np.zeros(self.n_tiles)
        
        probability = self._volcanic_potential.copy()
        
        # 边界类型加成
        boundary_boost = {
            0: 0.0,
            1: 0.2,   # divergent
            2: 0.1,   # convergent
            3: 0.5,   # subduction
            4: 0.0,   # transform
        }
        
        for i in range(self.n_tiles):
            bt = self._boundary_type[i]
            probability[i] += boundary_boost.get(bt, 0.0)
        
        # 压力加成
        probability *= pressure_boost
        
        return np.clip(probability, 0, 1)
    
    def compute_earthquake_probability_matrix(
        self,
        pressure_boost: float = 1.0
    ) -> np.ndarray:
        """
        计算地震概率矩阵
        
        Args:
            pressure_boost: 压力加成系数
            
        Returns:
            (n_tiles,) 地震概率
        """
        if self._earthquake_risk is None or self._boundary_type is None:
            return np.zeros(self.n_tiles)
        
        probability = self._earthquake_risk.copy()
        
        # 边界类型是主要因素
        boundary_boost = {
            0: 0.0,
            1: 0.15,  # divergent
            2: 0.3,   # convergent
            3: 0.4,   # subduction
            4: 0.25,  # transform
        }
        
        for i in range(self.n_tiles):
            bt = self._boundary_type[i]
            probability[i] += boundary_boost.get(bt, 0.0)
        
        # 压力加成
        probability *= pressure_boost
        
        return np.clip(probability, 0, 1)
    
    def apply_elevation_changes(
        self,
        tiles: list[SimpleTile],
        delta_matrix: np.ndarray,
    ) -> None:
        """
        批量应用海拔变化
        
        Args:
            tiles: 地块列表
            delta_matrix: (n_tiles,) 海拔变化值
        """
        if len(delta_matrix) != len(tiles):
            return
        
        for i, tile in enumerate(tiles):
            tile.elevation += delta_matrix[i]
        
        # 更新内部矩阵
        if self._tile_elevations is not None:
            self._tile_elevations += delta_matrix
    
    def get_tiles_in_radius(
        self,
        center_x: int,
        center_y: int,
        radius: int,
    ) -> list[int]:
        """
        获取半径内的所有地块ID
        
        Args:
            center_x, center_y: 中心坐标
            radius: 半径
            
        Returns:
            地块ID列表
        """
        tile_ids = []
        
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                # 计算距离
                dist = math.sqrt(dx*dx + dy*dy)
                if dist <= radius:
                    x = (center_x + dx) % self.width
                    y = center_y + dy
                    if 0 <= y < self.height:
                        tile_ids.append(y * self.width + x)
        
        return tile_ids
    
    def compute_plate_area_matrix(self, n_plates: int) -> np.ndarray:
        """计算板块面积向量"""
        if self._plate_assignment is None:
            return np.zeros(n_plates)
        
        return np.bincount(self._plate_assignment, minlength=n_plates).astype(np.float32)
    
    def compute_plate_boundary_length(self, n_plates: int) -> np.ndarray:
        """计算板块边界长度"""
        if self._plate_assignment is None or self._boundary_type is None:
            return np.zeros(n_plates)
        
        boundary_length = np.zeros(n_plates, dtype=np.int32)
        
        for i in range(self.n_tiles):
            if self._boundary_type[i] > 0:
                plate_id = self._plate_assignment[i]
                boundary_length[plate_id] += 1
        
        return boundary_length.astype(np.float32)
    
    # ==================== 辅助方法 ====================
    
    @property
    def plate_assignment(self) -> np.ndarray | None:
        return self._plate_assignment
    
    @property
    def boundary_type(self) -> np.ndarray | None:
        return self._boundary_type
    
    @property
    def plate_adjacency(self) -> np.ndarray | None:
        return self._plate_adjacency
    
    @property
    def volcanic_potential(self) -> np.ndarray | None:
        return self._volcanic_potential
    
    @property
    def earthquake_risk(self) -> np.ndarray | None:
        return self._earthquake_risk
    
    @property
    def tectonic_activity(self) -> np.ndarray | None:
        return self._tectonic_activity




