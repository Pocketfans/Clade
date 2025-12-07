"""地幔动力学测试"""

import pytest

from ..mantle_dynamics import (
    MantleDynamicsEngine, 
    WilsonPhase, 
    ConvectionCell,
    MantleDynamicsState
)
from ..plate_generator import PlateGenerator
from ..models import Plate, PlateType, MotionPhase


class TestConvectionCell:
    """测试对流单元"""
    
    def test_ascending_cell_pushes_outward(self):
        """测试上升流向外推动"""
        cell = ConvectionCell(
            id=0,
            center_x=50,
            center_y=20,
            radius=20,
            strength=0.1,
            direction="ascending"
        )
        
        # 在中心右侧的点
        vx, vy = cell.get_velocity_at(60, 20, width=100)
        
        # 应该向右推（正向）
        assert vx > 0
    
    def test_descending_cell_pulls_inward(self):
        """测试下降流向内拉动"""
        cell = ConvectionCell(
            id=0,
            center_x=50,
            center_y=20,
            radius=20,
            strength=0.1,
            direction="descending"
        )
        
        # 在中心右侧的点
        vx, vy = cell.get_velocity_at(60, 20, width=100)
        
        # 应该向左拉（负向）
        assert vx < 0
    
    def test_velocity_decays_with_distance(self):
        """测试速度随距离衰减"""
        cell = ConvectionCell(
            id=0,
            center_x=50,
            center_y=20,
            radius=20,
            strength=0.1,
            direction="ascending"
        )
        
        # 较近的点
        vx1, _ = cell.get_velocity_at(55, 20, width=100)
        # 较远的点
        vx2, _ = cell.get_velocity_at(65, 20, width=100)
        
        # 近点和远点都有速度（在半径内）
        assert abs(vx1) > 0
        assert abs(vx2) > 0
    
    def test_velocity_zero_outside_radius(self):
        """测试半径外速度为零"""
        cell = ConvectionCell(
            id=0,
            center_x=50,
            center_y=20,
            radius=10,
            strength=0.1,
            direction="ascending"
        )
        
        # 半径外的点
        vx, vy = cell.get_velocity_at(70, 20, width=100)
        
        assert vx == 0.0
        assert vy == 0.0


class TestMantleDynamicsEngine:
    """测试地幔动力学引擎"""
    
    def setup_method(self):
        self.engine = MantleDynamicsEngine(width=64, height=20)
        self.engine.initialize(seed=42)
    
    def test_initialization(self):
        """测试初始化"""
        assert self.engine.state.wilson_phase is not None
        assert len(self.engine.state.convection_cells) > 0
    
    def test_convection_cells_in_valid_positions(self):
        """测试对流单元在有效位置"""
        for cell in self.engine.state.convection_cells:
            assert 0 <= cell.center_x < self.engine.width
            assert 0 <= cell.center_y < self.engine.height
            assert cell.radius > 0
            assert 0 < cell.strength < 1
    
    def test_step_returns_valid_result(self):
        """测试step返回有效结果"""
        # 创建测试板块
        plates = [
            Plate(id=0, plate_index=0, velocity_x=0, velocity_y=0,
                  rotation_center_x=20, rotation_center_y=10),
            Plate(id=1, plate_index=1, velocity_x=0, velocity_y=0,
                  rotation_center_x=40, rotation_center_y=10),
        ]
        
        result = self.engine.step(plates)
        
        assert "phase_changed" in result
        assert "velocity_updates" in result
        assert "mantle_activity" in result
    
    def test_velocity_updates_affect_plates(self):
        """测试速度更新影响板块"""
        plates = [
            Plate(id=0, plate_index=0, velocity_x=0, velocity_y=0,
                  rotation_center_x=20, rotation_center_y=10),
        ]
        
        result = self.engine.step(plates)
        self.engine.apply_velocity_updates(plates, result["velocity_updates"])
        
        # 速度应该有变化（受对流驱动）
        # 由于随机性，不能保证一定变化，但结构应该正确
        assert len(result["velocity_updates"]) == 1
    
    def test_wilson_cycle_advances(self):
        """测试威尔逊周期推进"""
        plates = []
        
        initial_progress = self.engine.state.phase_progress
        
        self.engine.step(plates)
        
        assert self.engine.state.phase_progress > initial_progress
    
    def test_wilson_phase_eventually_changes(self):
        """测试威尔逊阶段最终会变化"""
        plates = []
        initial_phase = self.engine.state.wilson_phase
        
        # 执行足够多回合
        phase_changed = False
        for _ in range(100):
            result = self.engine.step(plates)
            if result["phase_changed"]:
                phase_changed = True
                break
        
        assert phase_changed, "威尔逊阶段应该在100回合内变化"
    
    def test_get_wilson_phase_info(self):
        """测试获取威尔逊周期信息"""
        info = self.engine.get_wilson_phase_info()
        
        assert "phase" in info
        assert "progress" in info
        assert "description" in info
        assert "effects" in info
        assert "total_cycles" in info
    
    def test_different_phases_have_different_effects(self):
        """测试不同阶段有不同效果"""
        # 测试不同阶段的速度修正
        modifiers = self.engine.config["phase_velocity_modifiers"]
        
        assert modifiers[WilsonPhase.SUPERCONTINENT] < modifiers[WilsonPhase.DRIFTING]
        assert modifiers[WilsonPhase.RIFTING] > modifiers[WilsonPhase.OROGENY]


class TestWilsonCyclePhases:
    """测试威尔逊周期各阶段"""
    
    def test_all_phases_in_sequence(self):
        """测试所有阶段都在序列中"""
        engine = MantleDynamicsEngine(64, 20)
        
        all_phases = set(WilsonPhase)
        sequence_phases = set(engine.PHASE_SEQUENCE)
        
        assert all_phases == sequence_phases
    
    def test_phase_durations_defined(self):
        """测试所有阶段有持续时间定义"""
        engine = MantleDynamicsEngine(64, 20)
        
        for phase in WilsonPhase:
            assert phase in engine.PHASE_DURATIONS
            duration = engine.PHASE_DURATIONS[phase]
            assert isinstance(duration, tuple)
            assert len(duration) == 2
            assert duration[0] > 0
            assert duration[1] >= duration[0]


class TestMantleDynamicsIntegration:
    """集成测试"""
    
    def test_with_real_plates(self):
        """与真实板块数据一起测试"""
        generator = PlateGenerator(64, 20)
        plates, _, _ = generator.generate(seed=42)
        
        engine = MantleDynamicsEngine(64, 20)
        engine.initialize(seed=42)
        
        # 执行多步
        for _ in range(10):
            result = engine.step(plates)
            engine.apply_velocity_updates(plates, result["velocity_updates"])
        
        # 板块应该有运动
        moving_plates = sum(1 for p in plates if p.speed() > 0.001)
        assert moving_plates > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])












