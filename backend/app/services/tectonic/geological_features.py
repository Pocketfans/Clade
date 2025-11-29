"""地质特征分布器

管理火山、热点、海沟等地质特征的生成和分布。
"""

from __future__ import annotations

import math
import random
from typing import Sequence

import numpy as np

from .config import TECTONIC_CONFIG
from .models import (
    Plate, PlateType, BoundaryType, FeatureType,
    GeologicalFeature, SimpleTile, TectonicEvent
)


# 火山名称生成器
VOLCANO_NAME_PREFIXES = [
    "火", "炎", "赤", "烈", "熔", "灼", "焰", "烧",
    "黑", "暗", "影", "幽", "玄", "冥", "深", "渊",
    "白", "冰", "霜", "雪", "寒", "冻", "凛", "冽",
    "青", "碧", "翠", "苍", "绿", "黛", "墨", "幻",
]

VOLCANO_NAME_SUFFIXES = [
    "山", "峰", "岭", "嶂", "岳", "崖", "丘", "陵",
    "口", "火山", "巨口", "烟山", "灰山", "熔岩山",
]


class GeologicalFeatureDistributor:
    """地质特征分布器
    
    基于板块边界类型和地质规则分布火山、海沟等特征。
    """
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.config = TECTONIC_CONFIG["features"]
        
        # 特征存储
        self.volcanoes: list[GeologicalFeature] = []
        self.hotspots: list[tuple[int, int]] = []  # (x, y)
        self.trenches: list[GeologicalFeature] = []
        self.ridges: list[GeologicalFeature] = []
        
        # 名称生成器状态
        self._used_names: set[str] = set()
    
    def initialize(
        self,
        plates: list[Plate],
        plate_map: np.ndarray,
        tiles: list[SimpleTile],
        seed: int,
    ) -> dict[str, list]:
        """
        初始化所有地质特征
        
        Args:
            plates: 板块列表
            plate_map: 板块ID矩阵
            tiles: 地块列表
            seed: 随机种子
            
        Returns:
            {
                "volcanoes": list[GeologicalFeature],
                "hotspots": list[(x, y)],
                "trenches": list[GeologicalFeature],
            }
        """
        random.seed(seed)
        np.random.seed(seed)
        
        self.volcanoes.clear()
        self.hotspots.clear()
        self.trenches.clear()
        self.ridges.clear()
        self._used_names.clear()
        
        # 按边界类型分组地块
        boundary_groups = self._group_tiles_by_boundary(tiles)
        
        # === 1. 生成热点（地幔柱）===
        self._generate_hotspots(tiles, seed)
        
        # === 2. 在俯冲带生成火山弧 ===
        subduction_tiles = boundary_groups.get(BoundaryType.SUBDUCTION, [])
        self._generate_subduction_volcanoes(subduction_tiles, tiles, plates)
        
        # === 3. 在热点生成火山 ===
        self._generate_hotspot_volcanoes(tiles, plates)
        
        # === 4. 在裂谷/洋中脊生成火山 ===
        divergent_tiles = boundary_groups.get(BoundaryType.DIVERGENT, [])
        self._generate_rift_volcanoes(divergent_tiles, tiles, plates)
        
        # === 5. 生成海沟 ===
        self._generate_trenches(subduction_tiles, tiles, plates)
        
        # === 6. 更新地块属性 ===
        self._update_tile_properties(tiles)
        
        return {
            "volcanoes": self.volcanoes.copy(),
            "hotspots": self.hotspots.copy(),
            "trenches": self.trenches.copy(),
        }
    
    def _group_tiles_by_boundary(
        self, 
        tiles: list[SimpleTile]
    ) -> dict[BoundaryType, list[SimpleTile]]:
        """按边界类型分组地块"""
        groups: dict[BoundaryType, list[SimpleTile]] = {}
        for tile in tiles:
            bt = tile.boundary_type
            if bt != BoundaryType.INTERNAL:
                if bt not in groups:
                    groups[bt] = []
                groups[bt].append(tile)
        return groups
    
    def _generate_hotspots(self, tiles: list[SimpleTile], seed: int) -> None:
        """生成热点（地幔柱）"""
        num_hotspots = random.randint(*self.config["num_hotspots"])
        min_distance = self.config["hotspot_min_distance"]
        
        for _ in range(num_hotspots):
            for _ in range(100):  # 尝试100次
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                
                # 检查距离
                valid = all(
                    self._distance(x, y, hx, hy) > min_distance
                    for hx, hy in self.hotspots
                )
                
                if valid:
                    self.hotspots.append((x, y))
                    
                    # 标记地块
                    tile_id = y * self.width + x
                    for tile in tiles:
                        if tile.id == tile_id:
                            tile.volcanic_potential = 0.9
                            break
                    break
    
    def _generate_subduction_volcanoes(
        self,
        subduction_tiles: list[SimpleTile],
        all_tiles: list[SimpleTile],
        plates: list[Plate],
    ) -> None:
        """在俯冲带生成火山弧"""
        if not subduction_tiles:
            return
        
        cfg = self.config
        min_dist = cfg["volcano_min_distance"]
        prob = cfg["volcano_subduction_probability"]
        
        # 火山弧位于俯冲带后方（陆地侧）
        # 采样一部分边界地块
        sample_rate = 0.3  # 每3个取1个
        sampled = subduction_tiles[::int(1/sample_rate)] if len(subduction_tiles) > 5 else subduction_tiles
        
        for tile in sampled:
            if random.random() > prob:
                continue
            
            # 找到火山弧位置（俯冲带后方2-4格）
            arc_offset = random.randint(2, 4)
            arc_tile = self._find_arc_position(tile, all_tiles, plates, arc_offset)
            
            if arc_tile and arc_tile.elevation >= 0:  # 只在陆地上生成
                # 检查距离
                if not self._check_volcano_distance(arc_tile.x, arc_tile.y, min_dist):
                    continue
                
                volcano = GeologicalFeature(
                    id=len(self.volcanoes),
                    feature_type=FeatureType.VOLCANO,
                    x=arc_tile.x,
                    y=arc_tile.y,
                    tile_id=arc_tile.id,
                    intensity=random.uniform(0.6, 1.0),
                    plate_id=arc_tile.plate_id,
                    boundary_type=BoundaryType.SUBDUCTION,
                    name=self._generate_volcano_name(),
                )
                self.volcanoes.append(volcano)
    
    def _find_arc_position(
        self,
        boundary_tile: SimpleTile,
        all_tiles: list[SimpleTile],
        plates: list[Plate],
        offset: int,
    ) -> SimpleTile | None:
        """找到火山弧位置"""
        tile_map = {t.id: t for t in all_tiles}
        plate = plates[boundary_tile.plate_id]
        
        # 简化：向板块内部方向偏移
        # 使用板块中心方向
        dx = plate.rotation_center_x - boundary_tile.x
        dy = plate.rotation_center_y - boundary_tile.y
        
        # 处理X循环
        if abs(dx) > self.width / 2:
            dx = dx - self.width if dx > 0 else dx + self.width
        
        # 归一化
        length = math.sqrt(dx*dx + dy*dy)
        if length < 0.1:
            return None
        
        dx /= length
        dy /= length
        
        # 偏移
        new_x = int(boundary_tile.x + dx * offset) % self.width
        new_y = int(boundary_tile.y + dy * offset)
        
        if 0 <= new_y < self.height:
            tile_id = new_y * self.width + new_x
            return tile_map.get(tile_id)
        
        return None
    
    def _generate_hotspot_volcanoes(
        self,
        all_tiles: list[SimpleTile],
        plates: list[Plate],
    ) -> None:
        """在热点生成火山"""
        tile_map = {(t.x, t.y): t for t in all_tiles}
        
        for hx, hy in self.hotspots:
            tile = tile_map.get((hx, hy))
            if not tile:
                continue
            
            # 热点火山强度高
            volcano = GeologicalFeature(
                id=len(self.volcanoes),
                feature_type=FeatureType.VOLCANO,
                x=hx,
                y=hy,
                tile_id=tile.id,
                intensity=random.uniform(0.8, 1.0),
                plate_id=tile.plate_id,
                boundary_type=None,  # 热点不在边界上
                name=self._generate_volcano_name(),
            )
            self.volcanoes.append(volcano)
    
    def _generate_rift_volcanoes(
        self,
        divergent_tiles: list[SimpleTile],
        all_tiles: list[SimpleTile],
        plates: list[Plate],
    ) -> None:
        """在裂谷/洋中脊生成火山"""
        if not divergent_tiles:
            return
        
        cfg = self.config
        min_dist = cfg["volcano_min_distance"]
        prob = cfg["volcano_rift_probability"]
        
        # 采样
        sample_rate = 0.2
        sampled = divergent_tiles[::int(1/sample_rate)] if len(divergent_tiles) > 5 else divergent_tiles
        
        for tile in sampled:
            if random.random() > prob:
                continue
            
            if not self._check_volcano_distance(tile.x, tile.y, min_dist):
                continue
            
            volcano = GeologicalFeature(
                id=len(self.volcanoes),
                feature_type=FeatureType.VOLCANO,
                x=tile.x,
                y=tile.y,
                tile_id=tile.id,
                intensity=random.uniform(0.4, 0.8),
                plate_id=tile.plate_id,
                boundary_type=BoundaryType.DIVERGENT,
                name=self._generate_volcano_name(),
            )
            self.volcanoes.append(volcano)
    
    def _generate_trenches(
        self,
        subduction_tiles: list[SimpleTile],
        all_tiles: list[SimpleTile],
        plates: list[Plate],
    ) -> None:
        """生成海沟标记（不直接修改海拔，海拔变化由运动引擎渐进处理）"""
        if not subduction_tiles:
            return
        
        # 获取配置
        min_ocean_depth = self.config.get("trench_min_ocean_depth", -500)
        
        for tile in subduction_tiles:
            # 只在足够深的海洋中标记海沟
            # 不直接修改海拔！海拔变化由 motion_engine 渐进处理
            if tile.elevation < min_ocean_depth:
                trench = GeologicalFeature(
                    id=len(self.trenches),
                    feature_type=FeatureType.TRENCH,
                    x=tile.x,
                    y=tile.y,
                    tile_id=tile.id,
                    intensity=abs(tile.elevation) / 8000,  # 基于当前深度计算强度
                    plate_id=tile.plate_id,
                    boundary_type=BoundaryType.SUBDUCTION,
                )
                self.trenches.append(trench)
    
    def _check_volcano_distance(self, x: int, y: int, min_dist: int) -> bool:
        """检查新火山与现有火山的距离"""
        for v in self.volcanoes:
            if self._distance(x, y, v.x, v.y) < min_dist:
                return False
        return True
    
    def _distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        """计算两点距离（考虑X轴循环）"""
        dx = min(abs(x1 - x2), self.width - abs(x1 - x2))
        dy = abs(y1 - y2)
        return math.sqrt(dx*dx + dy*dy)
    
    def _generate_volcano_name(self) -> str:
        """生成火山名称"""
        for _ in range(50):
            prefix = random.choice(VOLCANO_NAME_PREFIXES)
            suffix = random.choice(VOLCANO_NAME_SUFFIXES)
            name = prefix + suffix
            if name not in self._used_names:
                self._used_names.add(name)
                return name
        
        # 兜底
        return f"火山{len(self.volcanoes) + 1}"
    
    def _update_tile_properties(self, tiles: list[SimpleTile]) -> None:
        """更新地块的地质属性"""
        volcano_tiles = {v.tile_id: v for v in self.volcanoes}
        trench_tiles = {t.tile_id for t in self.trenches}
        
        for tile in tiles:
            if tile.id in volcano_tiles:
                v = volcano_tiles[tile.id]
                tile.volcanic_potential = v.intensity
                tile.tectonic_activity = 0.8
            
            if tile.id in trench_tiles:
                tile.earthquake_risk = 0.9
                tile.tectonic_activity = 0.9
    
    def get_eruption_candidates(
        self,
        pressure_type: str,
        intensity: int,
        target_region: tuple[int, int] | None = None,
        radius: int = 5,
    ) -> list[GeologicalFeature]:
        """
        获取可能喷发的火山列表
        
        Args:
            pressure_type: 压力类型
            intensity: 压力强度 1-10
            target_region: 目标区域 (x, y)
            radius: 搜索半径
            
        Returns:
            按喷发概率排序的火山列表
        """
        candidates = []
        
        for volcano in self.volcanoes:
            if volcano.dormant:
                continue
            
            # 基础概率
            prob = volcano.intensity * 0.3
            
            # 压力类型加成
            if pressure_type == "supervolcano":
                prob += volcano.intensity * 0.5
                # 超级火山优先热点
                if volcano.boundary_type is None:  # 热点
                    prob += 0.3
            elif pressure_type == "volcanic_eruption":
                prob += 0.2
            
            # 边界类型加成
            if volcano.boundary_type == BoundaryType.SUBDUCTION:
                prob += 0.15
            
            # 强度加成
            prob *= (1 + intensity * 0.1)
            
            # 区域限制
            if target_region:
                tx, ty = target_region
                dist = self._distance(volcano.x, volcano.y, tx, ty)
                if dist > radius:
                    prob *= 0.1  # 区域外概率大幅降低
                else:
                    prob *= (1 - dist / radius * 0.5)  # 越近概率越高
            
            candidates.append((volcano, min(1.0, prob)))
        
        # 按概率排序
        candidates.sort(key=lambda x: -x[1])
        
        return [v for v, _ in candidates]
    
    def trigger_eruption(
        self,
        volcano: GeologicalFeature,
        turn_index: int,
        intensity: float = 1.0,
    ) -> TectonicEvent:
        """
        触发火山喷发
        
        Args:
            volcano: 要喷发的火山
            turn_index: 当前回合
            intensity: 喷发强度
            
        Returns:
            地质事件
        """
        volcano.last_eruption_turn = turn_index
        
        affected_radius = 2 + int(intensity * 4)
        magnitude = intensity * 10
        
        event_type = "supervolcano_eruption" if intensity > 0.8 else "volcanic_eruption"
        
        description = f"{volcano.name or '火山'}喷发"
        if intensity > 0.8:
            description = f"超级{description}，火山灰覆盖方圆{affected_radius * 50}公里"
        
        return TectonicEvent(
            event_type=event_type,
            x=volcano.x,
            y=volcano.y,
            tile_id=volcano.tile_id,
            magnitude=magnitude,
            affected_radius=affected_radius,
            description=description,
            plate_id=volcano.plate_id,
            related_feature_id=volcano.id,
        )

