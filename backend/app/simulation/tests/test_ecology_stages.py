"""
Ecology Stages Tests - 生态相关阶段测试

测试死亡率评估、迁徙扩散、繁殖种群更新、分化等阶段。
"""

import pytest
import random
from unittest.mock import MagicMock, AsyncMock, patch


# 标记整个模块使用 asyncio
pytestmark = pytest.mark.asyncio


class TestSimpleMortalityStage:
    """简单死亡率阶段测试"""
    
    @pytest.fixture
    def stage(self):
        from ..plugin_stages import SimpleMortalityStage
        return SimpleMortalityStage(base_rate=0.1, pressure_sensitivity=0.1)
    
    async def test_basic_mortality_calculation(self, stage, mock_context, mock_engine):
        """测试基础死亡率计算"""
        mock_context.modifiers = {"temperature": 1.0}
        mock_context.combined_results = []
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.combined_results is not None
        assert len(mock_context.combined_results) == len(mock_context.species_batch)
        
        # 检查死亡率在合理范围
        for result in mock_context.combined_results:
            assert 0.01 <= result.death_rate <= 0.9
    
    async def test_pressure_affects_mortality(self, stage, mock_context, mock_engine):
        """测试压力影响死亡率"""
        # 无压力
        mock_context.modifiers = {}
        mock_context.combined_results = []
        await stage.execute(mock_context, mock_engine)
        low_pressure_rates = [r.death_rate for r in mock_context.combined_results]
        
        # 重置
        mock_context.combined_results = []
        
        # 高压力
        mock_context.modifiers = {"temperature": 5.0, "drought": 3.0}
        await stage.execute(mock_context, mock_engine)
        high_pressure_rates = [r.death_rate for r in mock_context.combined_results]
        
        # 高压力下平均死亡率应该更高
        avg_low = sum(low_pressure_rates) / len(low_pressure_rates) if low_pressure_rates else 0
        avg_high = sum(high_pressure_rates) / len(high_pressure_rates) if high_pressure_rates else 0
        assert avg_high >= avg_low


class TestEcoMetricsStage:
    """生态健康度阶段测试"""
    
    @pytest.fixture
    def stage(self):
        from ..plugin_stages import EcoMetricsStage
        return EcoMetricsStage()
    
    async def test_metrics_calculation(self, stage, mock_context, mock_engine):
        """测试指标计算"""
        # 确保 _plugin_data 存在
        if not hasattr(mock_context, '_plugin_data'):
            mock_context._plugin_data = {}
        
        await stage.execute(mock_context, mock_engine)
        
        # 检查是否存储了指标
        assert 'eco_metrics' in mock_context._plugin_data
        
        metrics = mock_context._plugin_data['eco_metrics']
        assert 0 <= metrics.ecosystem_health <= 1
        assert metrics.shannon_diversity >= 0
        assert 0 <= metrics.evenness <= 1
    
    async def test_empty_species_list(self, stage, mock_context, mock_engine):
        """测试空物种列表"""
        mock_context.species_batch = []
        
        # 确保 _plugin_data 存在
        if not hasattr(mock_context, '_plugin_data'):
            mock_context._plugin_data = {}
        
        await stage.execute(mock_context, mock_engine)
        
        # 应该不会崩溃
        assert True


class TestStageProfilingStages:
    """阶段性能分析阶段测试"""
    
    @pytest.fixture
    def start_stage(self):
        from ..plugin_stages import StageProfilingStartStage
        return StageProfilingStartStage()
    
    @pytest.fixture
    def end_stage(self):
        from ..plugin_stages import StageProfilingEndStage
        return StageProfilingEndStage()
    
    async def test_profiling_start(self, start_stage, mock_context, mock_engine):
        """测试性能分析开始"""
        await start_stage.execute(mock_context, mock_engine)
        
        # StageProfilingStartStage 使用 _profiling_data 而不是 _plugin_data
        assert hasattr(mock_context, '_profiling_data')
        assert 'start_time' in mock_context._profiling_data
    
    async def test_profiling_end(self, start_stage, end_stage, mock_context, mock_engine):
        """测试性能分析结束"""
        # 先运行开始阶段
        await start_stage.execute(mock_context, mock_engine)
        
        # 模拟一些 pipeline_metrics
        from ..pipeline import StageMetrics
        mock_context.pipeline_metrics = {
            "TestStage1": StageMetrics(
                stage_name="TestStage1",
                duration_ms=150.0,
                success=True,
            ),
            "TestStage2": StageMetrics(
                stage_name="TestStage2",
                duration_ms=250.0,
                success=True,
            ),
        }
        
        await end_stage.execute(mock_context, mock_engine)
        
        # 应该不会崩溃
        assert True
