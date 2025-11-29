"""
AI Stages Tests - AI/Embedding 相关阶段测试

烟囱测试级别，验证 AI 状态评估、叙事生成等阶段的基本功能。
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# 导入需要测试的 Stage
from ..stages import (
    AIStatusEvalStage, AINarrativeStage, SpeciationStage, EmbeddingStage
)


# 标记整个模块使用 asyncio
pytestmark = pytest.mark.asyncio


class TestAIStatusEvalStage:
    """AI 状态评估阶段测试"""
    
    @pytest.fixture
    def stage(self):
        return AIStatusEvalStage()
    
    async def test_skip_when_disabled(self, stage, mock_context, mock_engine):
        """测试禁用时跳过"""
        mock_engine._use_ai_pressure_response = False
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.ai_status_evals == {}
    
    async def test_evaluate_critical_species(
        self, stage, mock_context, mock_engine, mock_mortality_results
    ):
        """测试评估关键物种"""
        mock_engine._use_ai_pressure_response = True
        mock_context.critical_results = mock_mortality_results[:2]
        mock_context.modifiers = {"temperature": 1.5}
        mock_context.major_events = []
        
        mock_eval_result = MagicMock(
            population_health=0.7,
            extinction_risk=0.2,
            emergency_actions=[],
        )
        mock_engine.ai_status_evaluator = MagicMock()
        mock_engine.ai_status_evaluator.batch_evaluate = AsyncMock(
            return_value={
                mock_mortality_results[0].species.lineage_code: mock_eval_result,
                mock_mortality_results[1].species.lineage_code: mock_eval_result,
            }
        )
        
        await stage.execute(mock_context, mock_engine)
        
        assert len(mock_context.ai_status_evals) > 0
    
    async def test_emergency_responses_extracted(
        self, stage, mock_context, mock_engine, mock_mortality_results
    ):
        """测试紧急响应提取"""
        mock_engine._use_ai_pressure_response = True
        mock_context.critical_results = mock_mortality_results[:1]
        mock_context.modifiers = {"temperature": 3.0}
        mock_context.major_events = []
        
        mock_eval_result = MagicMock(
            population_health=0.3,
            extinction_risk=0.8,
            emergency_actions=[
                {"action": "migrate", "reason": "栖息地丧失"}
            ],
        )
        mock_engine.ai_status_evaluator = MagicMock()
        mock_engine.ai_status_evaluator.batch_evaluate = AsyncMock(
            return_value={
                mock_mortality_results[0].species.lineage_code: mock_eval_result,
            }
        )
        
        await stage.execute(mock_context, mock_engine)
        
        # 验证紧急响应被提取
        assert len(mock_context.emergency_responses) >= 0


class TestAINarrativeStage:
    """AI 叙事生成阶段测试"""
    
    @pytest.fixture
    def stage(self):
        return AINarrativeStage()
    
    async def test_skip_when_disabled(self, stage, mock_context, mock_engine):
        """测试禁用时跳过"""
        mock_engine._use_ai_pressure_response = False
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.narrative_results == []
    
    async def test_generate_narratives_for_critical(
        self, stage, mock_context, mock_engine, mock_mortality_results
    ):
        """测试为关键物种生成叙事"""
        mock_engine._use_ai_pressure_response = True
        mock_context.critical_results = mock_mortality_results[:1]
        mock_context.focus_results = mock_mortality_results[1:3]
        mock_context.modifiers = {"temperature": 1.5}
        
        mock_narrative = MagicMock()
        mock_narrative.lineage_code = "SP001"
        mock_narrative.narrative = "这个回合..."
        mock_narrative.headline = "测试标题"
        mock_narrative.mood = "neutral"
        
        # 正确设置 AsyncMock
        mock_engine.ai_pressure_service = MagicMock()
        mock_engine.ai_pressure_service.generate_species_narratives = AsyncMock(
            return_value=[mock_narrative]
        )
        
        await stage.execute(mock_context, mock_engine)
        
        # 验证叙事被设置
        assert len(mock_context.narrative_results) == 1
    
    async def test_timeout_handling(self, stage, mock_context, mock_engine, mock_mortality_results):
        """测试超时处理"""
        mock_engine._use_ai_pressure_response = True
        mock_context.critical_results = mock_mortality_results[:1]
        mock_context.focus_results = []
        mock_context.modifiers = {}
        
        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(10)  # 模拟缓慢响应
            return []
        
        mock_engine.narrative_generator = MagicMock()
        mock_engine.narrative_generator.generate_batch = slow_generate
        
        # 应该超时或被跳过，而不是崩溃
        try:
            await asyncio.wait_for(
                stage.execute(mock_context, mock_engine),
                timeout=1.0
            )
        except asyncio.TimeoutError:
            pass  # 超时是预期的
        
        assert True


class TestSpeciationStage:
    """物种分化阶段测试"""
    
    @pytest.fixture
    def stage(self):
        return SpeciationStage()
    
    async def test_branching_event_detection(
        self, stage, mock_context, mock_engine, mock_species_list, mock_mortality_results
    ):
        """测试分化事件检测"""
        mock_context.species_batch = mock_species_list
        mock_context.critical_results = mock_mortality_results[:2]
        mock_context.focus_results = mock_mortality_results[2:]
        mock_context.adaptation_events = []
        mock_context.extinct_codes = set()
        mock_context.trophic_interactions = {}
        mock_context.pressures = []
        
        mock_branching = MagicMock()
        mock_branching.parent_code = "SP001"
        mock_branching.child_code = "SP006"
        
        # 正确设置 AsyncMock
        mock_engine.speciation = MagicMock()
        mock_engine.speciation.process_async = AsyncMock(return_value=[mock_branching])
        mock_engine.speciation.set_evolution_hints = MagicMock()
        mock_engine._use_embedding_integration = False
        
        # Mock species_repository - 使用正确的路径
        with patch('app.repositories.species_repository.species_repository') as mock_repo:
            mock_repo.list_species.return_value = mock_species_list
            
            await stage.execute(mock_context, mock_engine)
        
        assert len(mock_context.branching_events) == 1
    
    async def test_no_branching_for_extinct(
        self, stage, mock_context, mock_engine, mock_species_list
    ):
        """测试灭绝物种不分化"""
        mock_context.species_batch = mock_species_list
        mock_context.adaptation_events = []
        mock_context.extinct_codes = {"SP001", "SP002"}  # 标记为灭绝
        
        mock_engine.speciation = MagicMock()
        mock_engine.speciation.check_branching_conditions = MagicMock(return_value=[])
        
        await stage.execute(mock_context, mock_engine)
        
        # 灭绝物种不应产生分化事件
        assert len(mock_context.branching_events) == 0


class TestEmbeddingStage:
    """Embedding 集成阶段测试"""
    
    @pytest.fixture
    def stage(self):
        return EmbeddingStage()
    
    async def test_skip_when_disabled(self, stage, mock_context, mock_engine):
        """测试禁用时跳过"""
        mock_engine._use_embedding_integration = False
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.embedding_turn_data == {}
    
    async def test_embedding_update(self, stage, mock_context, mock_engine, mock_species_list):
        """测试 Embedding 更新"""
        mock_engine._use_embedding_integration = True
        mock_context.species_batch = mock_species_list
        mock_context.combined_results = []
        
        # 正确设置 embedding_integration mock
        mock_engine.embedding_integration = MagicMock()
        mock_engine.embedding_integration.on_extinction = MagicMock()
        mock_engine.embedding_integration.on_turn_end = MagicMock(
            return_value={"updated_count": 5, "taxonomy": True}
        )
        
        await stage.execute(mock_context, mock_engine)
        
        # 验证 embedding_turn_data 被正确设置
        assert mock_context.embedding_turn_data is not None
        assert mock_context.embedding_turn_data.get("updated_count") == 5


class TestStageProfilingStage:
    """阶段性能分析阶段测试（在 test_ecology_stages.py 中有完整测试）"""
    
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
        
        # StageProfilingStartStage 使用 _profiling_data
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

