"""地质特征分布器测试"""

import pytest
import numpy as np

from ..plate_generator import PlateGenerator
from ..motion_engine import PlateMotionEngine
from ..geological_features import GeologicalFeatureDistributor
from ..models import BoundaryType, FeatureType


class TestGeologicalFeatureDistributor:
    """测试地质特征分布器"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.width = 64
        self.height = 20
        
        # 生成初始板块和地块
        generator = PlateGenerator(self.width, self.height)
        self.plates, self.plate_map, self.tiles = generator.generate(seed=42)
        
        # 检测边界
        engine = PlateMotionEngine(self.width, self.height)
        engine._detect_boundaries(self.plates, self.plate_map, self.tiles)
        
        # 初始化分布器
        self.distributor = GeologicalFeatureDistributor(self.width, self.height)
    
    def test_initialize_creates_features(self):
        """测试初始化创建地质特征"""
        result = self.distributor.initialize(
            self.plates, self.plate_map, self.tiles, seed=42
        )
        
        # 应该创建火山
        assert len(result["volcanoes"]) > 0
        
        # 应该创建热点
        assert len(result["hotspots"]) > 0
    
    def test_hotspots_have_distance(self):
        """测试热点之间有距离"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        hotspots = self.distributor.hotspots
        min_dist = self.distributor.config["hotspot_min_distance"]
        
        for i, (x1, y1) in enumerate(hotspots):
            for x2, y2 in hotspots[i+1:]:
                dx = min(abs(x1 - x2), self.width - abs(x1 - x2))
                dy = abs(y1 - y2)
                dist = (dx*dx + dy*dy) ** 0.5
                assert dist >= min_dist * 0.9  # 允许10%误差
    
    def test_volcanoes_have_valid_properties(self):
        """测试火山属性有效"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        for volcano in self.distributor.volcanoes:
            # 位置有效
            assert 0 <= volcano.x < self.width
            assert 0 <= volcano.y < self.height
            
            # 强度有效
            assert 0 < volcano.intensity <= 1
            
            # 类型正确
            assert volcano.feature_type == FeatureType.VOLCANO
            
            # 有名称
            assert volcano.name is not None
    
    def test_volcano_names_unique(self):
        """测试火山名称唯一"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        names = [v.name for v in self.distributor.volcanoes]
        assert len(names) == len(set(names))
    
    def test_subduction_volcanoes_on_land(self):
        """测试俯冲带火山在陆地上"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        tile_map = {t.id: t for t in self.tiles}
        
        subduction_volcanoes = [
            v for v in self.distributor.volcanoes
            if v.boundary_type == BoundaryType.SUBDUCTION
        ]
        
        land_count = 0
        for v in subduction_volcanoes:
            tile = tile_map.get(v.tile_id)
            if tile and tile.elevation >= 0:
                land_count += 1
        
        # 大部分俯冲带火山应该在陆地上
        if subduction_volcanoes:
            assert land_count / len(subduction_volcanoes) > 0.5
    
    def test_get_eruption_candidates(self):
        """测试获取喷发候选"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        candidates = self.distributor.get_eruption_candidates(
            pressure_type="volcanic_eruption",
            intensity=5
        )
        
        # 应该返回候选列表
        assert isinstance(candidates, list)
        
        # 候选按概率排序
        if len(candidates) > 1:
            # 较强的火山应该排在前面
            assert candidates[0].intensity >= candidates[-1].intensity * 0.5
    
    def test_get_eruption_candidates_with_region(self):
        """测试区域限制的喷发候选"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        # 选择一个火山附近的区域
        if self.distributor.volcanoes:
            volcano = self.distributor.volcanoes[0]
            candidates = self.distributor.get_eruption_candidates(
                pressure_type="volcanic_eruption",
                intensity=5,
                target_region=(volcano.x, volcano.y),
                radius=10
            )
            
            # 第一个候选应该是目标火山附近
            if candidates:
                dx = min(abs(candidates[0].x - volcano.x), 
                        self.width - abs(candidates[0].x - volcano.x))
                dy = abs(candidates[0].y - volcano.y)
                assert (dx*dx + dy*dy) ** 0.5 <= 10
    
    def test_trigger_eruption(self):
        """测试触发喷发"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        if self.distributor.volcanoes:
            volcano = self.distributor.volcanoes[0]
            event = self.distributor.trigger_eruption(volcano, turn_index=5, intensity=0.8)
            
            # 事件位置正确
            assert event.x == volcano.x
            assert event.y == volcano.y
            
            # 火山记录了喷发回合
            assert volcano.last_eruption_turn == 5
            
            # 事件类型正确
            assert "volcanic" in event.event_type
    
    def test_trenches_in_ocean(self):
        """测试海沟在海洋中"""
        self.distributor.initialize(self.plates, self.plate_map, self.tiles, seed=42)
        
        tile_map = {t.id: t for t in self.tiles}
        
        for trench in self.distributor.trenches:
            tile = tile_map.get(trench.tile_id)
            if tile:
                # 海沟应该在海洋中（负海拔）
                assert tile.elevation < 0


class TestFeatureDistributorDeterminism:
    """测试确定性"""
    
    def test_same_seed_same_features(self):
        """测试相同种子产生相同特征"""
        width, height = 64, 20
        
        # 第一次
        gen1 = PlateGenerator(width, height)
        plates1, map1, tiles1 = gen1.generate(seed=42)
        engine1 = PlateMotionEngine(width, height)
        engine1._detect_boundaries(plates1, map1, tiles1)
        dist1 = GeologicalFeatureDistributor(width, height)
        result1 = dist1.initialize(plates1, map1, tiles1, seed=42)
        
        # 第二次
        gen2 = PlateGenerator(width, height)
        plates2, map2, tiles2 = gen2.generate(seed=42)
        engine2 = PlateMotionEngine(width, height)
        engine2._detect_boundaries(plates2, map2, tiles2)
        dist2 = GeologicalFeatureDistributor(width, height)
        result2 = dist2.initialize(plates2, map2, tiles2, seed=42)
        
        # 火山数量相同
        assert len(result1["volcanoes"]) == len(result2["volcanoes"])
        
        # 热点相同
        assert result1["hotspots"] == result2["hotspots"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])









