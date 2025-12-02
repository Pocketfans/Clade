"""板块系统集成测试"""

import pytest

from ..integration import (
    TectonicIntegration, 
    TectonicIntegrationResult, 
    create_tectonic_integration
)
from ..species_tracker import SimpleSpecies, SimpleHabitat


class TestTectonicIntegration:
    """测试板块集成器"""
    
    def test_create_integration(self):
        """测试创建集成器"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        assert integration.width == 64
        assert integration.height == 20
        assert integration.tectonic is not None
    
    def test_step_without_species(self):
        """测试无物种时的步进"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        result = integration.step(
            species_list=[],
            habitat_data=[],
            map_tiles=[],
            pressure_modifiers={},
        )
        
        assert result.turn_index == 1
        assert isinstance(result.terrain_changes, list)
        assert isinstance(result.wilson_phase, dict)
    
    def test_step_with_mock_species(self):
        """测试带模拟物种的步进"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        # 创建模拟物种对象
        class MockSpecies:
            def __init__(self, id, habitat_type):
                self.id = id
                self.lineage_code = f"SP{id:04d}"
                self.name = f"物种{id}"
                self.trophic_level = 2.0
                self.habitat_type = habitat_type
                self.mobility = 0.5
                self.can_fly = False
                self.habitats = []
        
        species = [
            MockSpecies(1, "terrestrial"),
            MockSpecies(2, "marine"),
            MockSpecies(3, "amphibious"),
        ]
        
        habitat_data = [
            {"tile_id": 100, "species_id": 1, "population": 1000},
            {"tile_id": 200, "species_id": 2, "population": 500},
            {"tile_id": 150, "species_id": 3, "population": 300},
        ]
        
        result = integration.step(
            species_list=species,
            habitat_data=habitat_data,
            map_tiles=[],
            pressure_modifiers={"volcanic_eruption": 5},
        )
        
        assert result.turn_index == 1
        assert "phase" in result.wilson_phase
    
    def test_wilson_phase_info(self):
        """测试威尔逊周期信息"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        wilson = integration.get_wilson_phase()
        
        assert "phase" in wilson
        assert "progress" in wilson
        assert "description" in wilson
    
    def test_get_volcanoes(self):
        """测试获取火山"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        volcanoes = integration.get_volcanoes()
        
        assert isinstance(volcanoes, list)
        # 应该有一些火山
        assert len(volcanoes) > 0
    
    def test_get_plates(self):
        """测试获取板块"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        plates = integration.get_plates()
        
        assert isinstance(plates, list)
        assert len(plates) > 0
    
    def test_multiple_steps(self):
        """测试多步执行"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        for i in range(10):
            result = integration.step(
                species_list=[],
                habitat_data=[],
                map_tiles=[],
                pressure_modifiers={},
            )
            assert result.turn_index == i + 1
    
    def test_pressure_feedback(self):
        """测试压力反馈"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        result = integration.step(
            species_list=[],
            habitat_data=[],
            map_tiles=[],
            pressure_modifiers={"volcanic_eruption": 8},
        )
        
        # 压力反馈应该是字典
        assert isinstance(result.pressure_feedback, dict)


class TestTectonicIntegrationResult:
    """测试集成结果"""
    
    def test_result_properties(self):
        """测试结果属性"""
        result = TectonicIntegrationResult(
            turn_index=1,
            terrain_changes=[{"tile_id": 1}],
            tectonic_events=[
                {"type": "earthquake", "magnitude": 5.0},
                {"type": "volcanic_eruption", "magnitude": 7.0},
                {"type": "wilson_phase_change"},
            ],
            isolation_events=[],
            contact_events=[],
            wilson_phase={"phase": "drifting", "progress": 0.5},
            pressure_feedback={"volcanic": 0.3},
        )
        
        assert result.earthquake_count == 1
        assert result.volcano_eruption_count == 1
        assert result.has_phase_change == True
    
    def test_major_events_summary(self):
        """测试主要事件摘要"""
        result = TectonicIntegrationResult(
            turn_index=1,
            terrain_changes=[],
            tectonic_events=[
                {"type": "earthquake"},
                {"type": "earthquake"},
            ],
            isolation_events=[],
            contact_events=[],
            wilson_phase={"phase": "rifting"},
            pressure_feedback={},
        )
        
        summary = result.get_major_events_summary()
        
        assert any("地震" in s for s in summary)


class TestSpeciesHabitatTracking:
    """测试物种栖息地追踪"""
    
    def test_terrestrial_species_tracking(self):
        """测试陆地物种追踪"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        class MockTerrestrialSpecies:
            id = 1
            lineage_code = "SP0001"
            name = "陆生物种"
            trophic_level = 2.0
            habitat_type = "terrestrial"
            mobility = 0.5
            can_fly = False
            habitats = []
        
        result = integration.step(
            species_list=[MockTerrestrialSpecies()],
            habitat_data=[{"tile_id": 100, "species_id": 1, "population": 1000}],
            map_tiles=[],
        )
        
        assert result.turn_index == 1
    
    def test_marine_species_tracking(self):
        """测试海洋物种追踪"""
        integration = create_tectonic_integration(width=64, height=20, seed=42)
        
        class MockMarineSpecies:
            id = 2
            lineage_code = "SP0002"
            name = "海洋物种"
            trophic_level = 3.0
            habitat_type = "marine"
            mobility = 0.7
            can_fly = False
            habitats = []
        
        result = integration.step(
            species_list=[MockMarineSpecies()],
            habitat_data=[{"tile_id": 200, "species_id": 2, "population": 500}],
            map_tiles=[],
        )
        
        assert result.turn_index == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



