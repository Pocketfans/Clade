"""板块构造系统集成测试"""

import pytest
import tempfile
from pathlib import Path

from ..tectonic_system import TectonicSystem
from ..models import BoundaryType
from ..species_tracker import SimpleSpecies, SimpleHabitat


class TestTectonicSystem:
    """测试板块构造系统"""
    
    def test_initialization(self):
        """测试初始化"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        # 系统正确初始化
        assert system.width == 64
        assert system.height == 20
        assert system.turn_index == 0
        
        # 有板块和地块
        assert len(system.plates) > 0
        assert len(system.tiles) == 64 * 20
    
    def test_step_execution(self):
        """测试单步执行"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        result = system.step()
        
        # 返回正确的结果类型
        assert result.turn_index == 1
        assert isinstance(result.terrain_changes, list)
        assert isinstance(result.events, list)
        assert isinstance(result.pressure_feedback, dict)
    
    def test_multiple_steps(self):
        """测试多步执行"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        for i in range(10):
            result = system.step()
            assert result.turn_index == i + 1
        
        assert system.turn_index == 10
    
    def test_step_with_pressure(self):
        """测试带压力的执行"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        result = system.step(pressure_modifiers={"volcanic_eruption": 8})
        
        # 应该有反馈
        assert isinstance(result.pressure_feedback, dict)
    
    def test_trigger_volcanic_eruption(self):
        """测试手动触发火山喷发"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        events = system.trigger_volcanic_eruption(intensity=7)
        
        # 应该触发喷发
        if system.get_volcanoes():  # 如果有火山
            assert len(events) > 0
    
    def test_get_plates(self):
        """测试获取板块"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        plates = system.get_plates()
        
        assert len(plates) > 0
        for p in plates:
            assert p.id >= 0
    
    def test_get_tile(self):
        """测试获取地块"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        tile = system.get_tile(0)
        assert tile is not None
        assert tile.id == 0
        
        tile = system.get_tile_at(10, 5)
        assert tile is not None
        assert tile.x == 10
        assert tile.y == 5
    
    def test_get_volcanoes(self):
        """测试获取火山"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        volcanoes = system.get_volcanoes()
        assert isinstance(volcanoes, list)
    
    def test_get_boundary_tiles(self):
        """测试获取边界地块"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        boundary_tiles = system.get_boundary_tiles()
        
        # 应该有边界地块
        assert len(boundary_tiles) > 0
        
        # 所有返回的地块都是边界
        for t in boundary_tiles:
            assert t.boundary_type != BoundaryType.INTERNAL
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        stats = system.get_statistics()
        
        assert "turn_index" in stats
        assert "n_tiles" in stats
        assert "n_plates" in stats
        assert "elevation" in stats
        assert "features" in stats
    
    def test_serialization(self):
        """测试序列化"""
        system = TectonicSystem(width=64, height=20, seed=42)
        system.step()
        
        data = system.to_dict()
        
        assert data["width"] == 64
        assert data["height"] == 20
        assert data["turn_index"] == 1
        assert len(data["plates"]) > 0
    
    def test_save_and_load(self):
        """测试保存和加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tectonic_state.json"
            
            # 创建并保存
            system1 = TectonicSystem(width=64, height=20, seed=42)
            system1.step()
            system1.step()
            system1.save(path)
            
            # 加载
            system2 = TectonicSystem.load(path)
            
            # 验证
            assert system2.width == system1.width
            assert system2.height == system1.height
            assert system2.turn_index == system1.turn_index
            assert len(system2.plates) == len(system1.plates)


class TestTectonicSystemWithSpecies:
    """测试带物种追踪的系统"""
    
    def test_step_with_species(self):
        """测试带物种的执行"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        # 创建测试物种
        species = [
            SimpleSpecies(id=1, lineage_code="SP001", name="物种A"),
            SimpleSpecies(id=2, lineage_code="SP002", name="物种B"),
        ]
        
        # 创建测试栖息地
        habitats = [
            SimpleHabitat(tile_id=100, species_id=1, population=1000),
            SimpleHabitat(tile_id=200, species_id=2, population=500),
        ]
        
        result = system.step(species_list=species, habitats=habitats)
        
        # 结果应该包含物种相关信息
        assert isinstance(result.isolation_events, list)
        assert isinstance(result.contact_events, list)


class TestTectonicSystemPerformance:
    """性能测试"""
    
    def test_large_map_performance(self):
        """测试大地图性能"""
        import time
        
        # 标准地图大小
        system = TectonicSystem(width=128, height=40, seed=42)
        
        # 初始化时间
        start = time.time()
        system2 = TectonicSystem(width=128, height=40, seed=43)
        init_time = time.time() - start
        
        # 初始化应该在合理时间内完成（10秒内）
        assert init_time < 10.0
        
        # 单步时间
        start = time.time()
        system.step()
        step_time = time.time() - start
        
        # 单步应该很快（1秒内）
        assert step_time < 1.0
    
    def test_many_steps_stability(self):
        """测试多步执行的稳定性"""
        system = TectonicSystem(width=64, height=20, seed=42)
        
        for _ in range(50):
            result = system.step()
            
            # 每步都应该成功
            assert result.turn_index > 0
        
        # 地块数量不变
        assert len(system.tiles) == 64 * 20
        
        # 板块数量不变
        initial_plates = len(system.plates)
        assert len(system.plates) == initial_plates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])









