"""板块生成器测试"""

import pytest
import numpy as np

from ..plate_generator import PlateGenerator
from ..models import Plate, PlateType


class TestPlateGenerator:
    """测试板块生成器"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.width = 64
        self.height = 20
        self.generator = PlateGenerator(self.width, self.height)
    
    def test_generate_creates_plates(self):
        """测试生成板块"""
        plates, plate_map, tiles = self.generator.generate(seed=42)
        
        # 应该生成多个板块
        assert len(plates) > 0
        assert len(plates) >= 5  # 至少5个板块
        
        # 板块地图尺寸正确
        assert plate_map.shape == (self.height, self.width)
        
        # 地块数量正确
        assert len(tiles) == self.width * self.height
    
    def test_all_tiles_assigned_to_plates(self):
        """测试所有地块都分配到板块"""
        plates, plate_map, tiles = self.generator.generate(seed=42)
        
        # 没有未分配的地块（值为-1）
        assert np.all(plate_map >= 0)
        
        # 所有板块ID都有效
        assert np.all(plate_map < len(plates))
    
    def test_plate_sizes_vary(self):
        """测试板块大小有差异（幂律分布）"""
        plates, _, _ = self.generator.generate(seed=42)
        
        sizes = [p.tile_count for p in plates]
        
        # 大小应该有差异
        assert max(sizes) > min(sizes) * 2
    
    def test_deterministic_generation(self):
        """测试相同种子生成相同结果"""
        plates1, map1, _ = self.generator.generate(seed=123)
        plates2, map2, _ = self.generator.generate(seed=123)
        
        # 板块数量相同
        assert len(plates1) == len(plates2)
        
        # 板块地图相同
        assert np.array_equal(map1, map2)
    
    def test_different_seeds_different_results(self):
        """测试不同种子生成不同结果"""
        _, map1, _ = self.generator.generate(seed=111)
        _, map2, _ = self.generator.generate(seed=222)
        
        # 板块地图不同
        assert not np.array_equal(map1, map2)
    
    def test_plates_have_valid_properties(self):
        """测试板块属性有效"""
        plates, _, _ = self.generator.generate(seed=42)
        
        for plate in plates:
            # ID有效
            assert plate.id >= 0
            
            # 板块类型有效
            assert plate.plate_type in PlateType
            
            # 密度在合理范围
            assert 2.5 <= plate.density <= 3.5
            
            # 旋转中心在地图内
            assert 0 <= plate.rotation_center_x < self.width
            assert 0 <= plate.rotation_center_y < self.height
    
    def test_tiles_have_valid_properties(self):
        """测试地块属性有效"""
        _, _, tiles = self.generator.generate(seed=42)
        
        for tile in tiles:
            # 坐标有效
            assert 0 <= tile.x < self.width
            assert 0 <= tile.y < self.height
            
            # ID正确
            assert tile.id == tile.y * self.width + tile.x
            
            # 温度在合理范围
            assert -50 <= tile.temperature <= 50
            
            # 湿度在0-1
            assert 0 <= tile.humidity <= 1
    
    def test_boundary_noise_affects_shape(self):
        """测试边界噪声影响板块形状"""
        # 不规则边界意味着边界地块数量应该较多
        plates, _, tiles = self.generator.generate(seed=42)
        
        total_boundary_tiles = sum(p.boundary_tile_count for p in plates)
        total_tiles = self.width * self.height
        
        # 边界地块应该占一定比例（不太少）
        boundary_ratio = total_boundary_tiles / total_tiles
        assert boundary_ratio > 0.05  # 至少5%是边界


class TestPlateGeneratorLargeScale:
    """大规模测试"""
    
    def test_large_map_generation(self):
        """测试大地图生成"""
        generator = PlateGenerator(128, 40)
        plates, plate_map, tiles = generator.generate(seed=42)
        
        # 应该正确生成
        assert len(plates) > 0
        assert plate_map.shape == (40, 128)
        assert len(tiles) == 128 * 40
    
    def test_small_map_generation(self):
        """测试小地图生成"""
        generator = PlateGenerator(16, 8)
        plates, plate_map, tiles = generator.generate(seed=42)
        
        # 应该正确生成（即使是小地图）
        assert len(plates) > 0
        assert plate_map.shape == (8, 16)
        assert len(tiles) == 16 * 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])












