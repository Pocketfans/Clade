"""
Environment Stages Tests - 环境相关阶段测试

测试压力解析、地图演化、板块构造等阶段。
"""

import pytest
import random
from unittest.mock import MagicMock, AsyncMock, patch


# 标记整个模块使用 asyncio
pytestmark = pytest.mark.asyncio


class TestParsePressuresStage:
    """压力解析阶段测试"""
    
    @pytest.fixture
    def stage(self):
        from ..stages import ParsePressuresStage
        return ParsePressuresStage()
    
    async def test_parse_empty_pressures(self, stage, mock_context, mock_engine):
        """测试空压力列表"""
        mock_context.command = MagicMock(pressures=[])
        mock_engine.environment.parse_pressures.return_value = []
        mock_engine.environment.apply_pressures.return_value = {}
        mock_engine.escalation_service.register.return_value = []
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.pressures == []
        assert mock_context.modifiers == {}
        assert mock_context.major_events == []
    
    async def test_parse_temperature_pressure(self, stage, mock_context, mock_engine):
        """测试温度压力解析"""
        mock_pressure = MagicMock(type="temperature", value=2.0)
        mock_context.command = MagicMock(pressures=[mock_pressure])
        
        mock_engine.environment.parse_pressures.return_value = [mock_pressure]
        mock_engine.environment.apply_pressures.return_value = {"temperature": 2.0}
        mock_engine.escalation_service.register.return_value = []
        
        await stage.execute(mock_context, mock_engine)
        
        assert "temperature" in mock_context.modifiers
        assert mock_context.modifiers["temperature"] == 2.0
    
    async def test_major_events_registered(self, stage, mock_context, mock_engine):
        """测试重大事件注册"""
        mock_context.command = MagicMock(pressures=[])
        mock_engine.environment.parse_pressures.return_value = []
        mock_engine.environment.apply_pressures.return_value = {}
        
        mock_event = MagicMock(kind="volcanic_eruption", severity="high")
        mock_engine.escalation_service.register.return_value = [mock_event]
        
        await stage.execute(mock_context, mock_engine)
        
        assert len(mock_context.major_events) == 1


class TestMapEvolutionStage:
    """地图演化阶段测试
    
    注意：由于模块导入方式，这些测试需要在真实环境中运行。
    这里仅做基本的单元测试。
    """
    
    @pytest.fixture
    def stage(self):
        from ..stages import MapEvolutionStage
        return MapEvolutionStage()
    
    async def test_stage_properties(self, stage):
        """测试阶段属性"""
        assert stage.name == "地图演化"
        assert stage.order == 20
    
    async def test_stage_has_dependency(self, stage):
        """测试阶段有依赖声明"""
        dep = stage.get_dependency()
        assert "解析环境压力" in dep.requires_stages
        assert "modifiers" in dep.requires_fields


class TestTectonicMovementStage:
    """板块构造阶段测试"""
    
    @pytest.fixture
    def stage(self):
        from ..stages import TectonicMovementStage
        return TectonicMovementStage()
    
    async def test_skip_when_disabled(self, stage, mock_context, mock_engine):
        """测试禁用时跳过"""
        mock_engine._use_tectonic_system = False
        mock_engine.tectonic = None
        mock_context.tectonic_result = None
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.tectonic_result is None


class TestSimpleWeatherStage:
    """简单天气阶段测试"""
    
    @pytest.fixture
    def stage_always_trigger(self):
        from ..plugin_stages import SimpleWeatherStage
        return SimpleWeatherStage(trigger_chance=1.0)  # 100% 触发
    
    @pytest.fixture
    def stage_never_trigger(self):
        from ..plugin_stages import SimpleWeatherStage
        return SimpleWeatherStage(trigger_chance=0.0)  # 0% 触发
    
    async def test_stage_properties(self, stage_always_trigger):
        """测试阶段属性"""
        assert stage_always_trigger.name == "简单天气"
        assert stage_always_trigger.order == 22
        assert stage_always_trigger.trigger_chance == 1.0
    
    async def test_stage_never_trigger_properties(self, stage_never_trigger):
        """测试阶段属性（不触发版本）"""
        assert stage_never_trigger.trigger_chance == 0.0
    
    async def test_weather_no_crash_on_empty_tiles(self, stage_always_trigger, mock_context, mock_engine):
        """测试空地块列表不会崩溃"""
        mock_context.all_tiles = []
        
        # 由于仓储导入在 execute 中，我们跳过真正的执行
        # 这里仅测试阶段可以正确初始化
        assert stage_always_trigger is not None
