"""
Pipeline Tests - 流水线测试

测试 Pipeline 执行器、StageLoader 和模式切换功能。
"""

import asyncio
import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

import pytest

from .. import stages as stages_module
from ..pipeline import Pipeline, PipelineConfig, PipelineBuilder, PipelineResult
from ..stage_config import StageLoader, stage_registry, AVAILABLE_MODES
from ..ecological_realism_stage import EcologicalRealismStage
from ..stages import (
    AutoHybridizationStage,
    BaseStage,
    BuildReportStage,
    EmbeddingPluginsStage,
    EmbeddingStage,
    ExportDataStage,
    FetchSpeciesStage,
    FinalMortalityStage,
    GeneActivationStage,
    InitStage,
    PostMigrationNicheStage,
    SaveHistoryStage,
    SpeciationStage,
    StageDependency,
    TieringAndNicheStage,
    get_default_stages,
)
from ..context import SimulationContext
from ...services.species.description_enhancer import DescriptionEnhancerService
from ...services.species.genetic_distance import GeneticDistanceCalculator
from ...services.species.niche import NicheAnalyzer

# 标记整个模块使用 asyncio
pytestmark = pytest.mark.asyncio


# ============================================================================
# Test Stages
# ============================================================================

class SimpleTestStage(BaseStage):
    """简单测试阶段"""
    
    def __init__(self, order: int = 10, name: str = "测试阶段"):
        super().__init__(order=order, name=name)
        self.executed = False
        self.execution_count = 0
    
    async def execute(self, ctx, engine):
        self.executed = True
        self.execution_count += 1
        ctx._test_stage_executed = True


class FailingTestStage(BaseStage):
    """失败的测试阶段"""
    
    def __init__(self, order: int = 20, name: str = "失败阶段"):
        super().__init__(order=order, name=name)
    
    async def execute(self, ctx, engine):
        raise RuntimeError("故意失败")


class DependentTestStage(BaseStage):
    """有依赖的测试阶段"""
    
    def __init__(self, order: int = 30, name: str = "依赖阶段"):
        super().__init__(order=order, name=name)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"测试阶段"},
            requires_fields={"_test_stage_executed"},
            writes_fields={"_dependent_result"},
        )
    
    async def execute(self, ctx, engine):
        if not getattr(ctx, "_test_stage_executed", False):
            raise RuntimeError("依赖未满足")
        ctx._dependent_result = True


class SlowBusinessTestStage(BaseStage):
    def __init__(self, delay: float = 0.02):
        super().__init__(order=50, name="slow-business")
        self.delay = delay
        self.cancelled = False

    async def execute(self, ctx, engine):
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


# ============================================================================
# Pipeline Tests
# ============================================================================

class TestPipeline:
    """Pipeline 执行器测试"""
    
    @pytest.fixture
    def simple_stages(self):
        return [SimpleTestStage(10, "阶段1"), SimpleTestStage(20, "阶段2")]
    
    @pytest.fixture
    def mock_ctx(self):
        ctx = SimulationContext(turn_index=0)
        ctx.command = MagicMock(pressures=[], rounds=1)
        return ctx
    
    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        engine._use_embedding_integration = False
        return engine

    async def test_save_history_stage_uses_injected_repository(self):
        history_repository = MagicMock()
        record_data = {"turn_index": 7, "source": "injected-repository"}
        report = SimpleNamespace(
            turn_index=7,
            pressures_summary="stable",
            narrative="A stable turn",
            model_dump=MagicMock(return_value=record_data),
        )
        ctx = SimpleNamespace(
            report=report,
            embedding_turn_data=None,
            emit_event=MagicMock(),
        )

        stage = SaveHistoryStage(history_repository=history_repository)

        await stage.execute(ctx, SimpleNamespace())

        saved_turn = history_repository.log_turn.call_args.args[0]
        assert saved_turn.turn_index == 7
        assert saved_turn.pressures_summary == "stable"
        assert saved_turn.narrative == "A stable turn"
        assert saved_turn.record_data == record_data
    
    async def test_execute_all_stages(self, simple_stages, mock_ctx, mock_engine):
        """测试执行所有阶段"""
        config = PipelineConfig(validate_dependencies=False)
        pipeline = Pipeline(simple_stages, config)
        
        result = await pipeline.execute(mock_ctx, mock_engine)
        
        assert result.success
        assert len(result.stage_results) == 2
        for stage in simple_stages:
            assert stage.executed
    
    async def test_stage_order_preserved(self, mock_ctx, mock_engine):
        """测试阶段顺序保持"""
        stages = [
            SimpleTestStage(30, "阶段C"),
            SimpleTestStage(10, "阶段A"),
            SimpleTestStage(20, "阶段B"),
        ]
        config = PipelineConfig(validate_dependencies=False)
        pipeline = Pipeline(stages, config)
        
        result = await pipeline.execute(mock_ctx, mock_engine)
        
        # 验证按顺序执行
        assert result.stage_results[0].stage_name == "阶段A"
        assert result.stage_results[1].stage_name == "阶段B"
        assert result.stage_results[2].stage_name == "阶段C"
    
    async def test_continue_on_error(self, mock_ctx, mock_engine):
        """测试错误时继续"""
        stages = [
            SimpleTestStage(10, "正常阶段1"),
            FailingTestStage(20, "失败阶段"),
            SimpleTestStage(30, "正常阶段2"),
        ]
        config = PipelineConfig(
            continue_on_error=True,
            validate_dependencies=False,
        )
        pipeline = Pipeline(stages, config)
        
        result = await pipeline.execute(mock_ctx, mock_engine)
        
        assert not result.success
        assert len(result.failed_stages) == 1
        assert "失败阶段" in result.failed_stages
        # 第三个阶段仍然执行
        assert stages[2].executed

    async def test_degradable_failure_continues_and_keeps_pipeline_successful(
        self, mock_ctx, mock_engine
    ):
        """An auxiliary output failure is recorded without failing the core turn."""

        class FailingReportStage(BuildReportStage):
            async def execute(self, ctx, engine):
                raise RuntimeError("forced report failure")

        final_stage = SimpleTestStage(180, "final-stage")
        pipeline = Pipeline(
            [FailingReportStage(), final_stage],
            PipelineConfig(
                continue_on_error=False,
                validate_dependencies=False,
            ),
        )

        result = await pipeline.execute(mock_ctx, mock_engine)

        assert result.success
        assert result.failed_stages == ["构建报告"]
        assert result.degraded_stages == ["构建报告"]
        assert result.metrics is not None
        assert result.metrics.degraded_stages == ["构建报告"]
        assert final_stage.executed

    @pytest.mark.parametrize(
        "stage_type",
        [BuildReportStage, EmbeddingStage, EmbeddingPluginsStage, ExportDataStage],
    )
    async def test_auxiliary_output_stages_are_explicitly_degradable(self, stage_type):
        """Only allowlisted auxiliary output stages may degrade."""

        assert getattr(stage_type, "is_degradable", False)

    async def test_real_report_failure_is_recorded_as_degradation(
        self, monkeypatch, mock_ctx, mock_engine
    ):
        """The real report stage must surface an unhandled build failure."""

        class FailingTurnReportService:
            def __init__(self, **kwargs):
                pass

            async def build_report(self, **kwargs):
                raise RuntimeError("forced report service failure")

        monkeypatch.setattr(
            stages_module, "TurnReportService", FailingTurnReportService
        )
        mock_engine.report_builder = MagicMock()
        mock_engine.trophic_service = MagicMock()
        pipeline = Pipeline(
            [BuildReportStage()],
            PipelineConfig(
                continue_on_error=False,
                validate_dependencies=False,
            ),
        )

        result = await pipeline.execute(mock_ctx, mock_engine)

        assert result.success
        assert result.degraded_stages == ["构建报告"]

    async def test_real_embedding_failure_is_recorded_as_degradation(
        self, mock_ctx, mock_engine
    ):
        """The real Embedding stage must surface a failed turn-end hook."""

        def fail_turn_end(turn_index, species_batch):
            raise RuntimeError("forced embedding failure")

        mock_engine._use_embedding_integration = True
        mock_engine.embedding_integration = SimpleNamespace(on_turn_end=fail_turn_end)
        pipeline = Pipeline(
            [EmbeddingStage()],
            PipelineConfig(
                continue_on_error=False,
                validate_dependencies=False,
            ),
        )

        result = await pipeline.execute(mock_ctx, mock_engine)

        assert result.success
        assert result.degraded_stages == ["Embedding集成"]

    async def test_real_embedding_plugin_failure_is_recorded_as_degradation(
        self, mock_ctx, mock_engine
    ):
        """The real plugin stage must surface a failed plugin hook."""

        def fail_turn_end(ctx):
            raise RuntimeError("forced embedding plugin failure")

        stage = EmbeddingPluginsStage()
        stage._initialized = True
        stage._manager = SimpleNamespace(on_turn_end=fail_turn_end)
        stage._sync_tensor_bridge = lambda ctx: None
        pipeline = Pipeline(
            [stage],
            PipelineConfig(
                continue_on_error=False,
                validate_dependencies=False,
            ),
        )

        result = await pipeline.execute(mock_ctx, mock_engine)

        assert result.success
        assert result.degraded_stages == ["Embedding扩展插件"]
    
    async def test_stop_on_error(self, mock_ctx, mock_engine):
        """测试错误时停止"""
        stages = [
            SimpleTestStage(10, "正常阶段1"),
            FailingTestStage(20, "失败阶段"),
            SimpleTestStage(30, "正常阶段2"),
        ]
        config = PipelineConfig(
            continue_on_error=False,
            validate_dependencies=False,
        )
        pipeline = Pipeline(stages, config)
        
        result = await pipeline.execute(mock_ctx, mock_engine)
        
        assert not result.success
        # 第三个阶段不应执行
        assert not stages[2].executed
    
    async def test_timing_metrics(self, simple_stages, mock_ctx, mock_engine):
        """测试时间统计"""
        config = PipelineConfig(
            log_timing=True,
            validate_dependencies=False,
        )
        pipeline = Pipeline(simple_stages, config)
        
        result = await pipeline.execute(mock_ctx, mock_engine)
        
        assert result.metrics is not None
        assert result.metrics.total_duration_ms >= 0
        assert len(result.metrics.stage_metrics) == 2
    
    async def test_partial_execution_only_stage(self, mock_ctx, mock_engine):
        """测试只执行单个阶段"""
        stages = [
            SimpleTestStage(10, "阶段A"),
            SimpleTestStage(20, "阶段B"),
            SimpleTestStage(30, "阶段C"),
        ]
        config = PipelineConfig(
            only_stage="阶段B",
            validate_dependencies=False,
        )
        pipeline = Pipeline(stages, config)
        
        result = await pipeline.execute(mock_ctx, mock_engine)
        
        assert len(result.stage_results) == 1
        assert result.stage_results[0].stage_name == "阶段B"
        assert not stages[0].executed
        assert stages[1].executed
        assert not stages[2].executed

    async def test_business_stage_still_uses_generic_stage_timeout(
        self,
        mock_ctx,
        mock_engine,
    ):
        stage = SlowBusinessTestStage()
        pipeline = Pipeline(
            [stage],
            PipelineConfig(stage_timeout=0.001, validate_dependencies=False),
        )

        result = await pipeline.execute(mock_ctx, mock_engine)

        assert result.success is False
        assert stage.cancelled is True
        assert isinstance(result.stage_results[0].error, asyncio.TimeoutError)


@pytest.mark.parametrize(
    "stage_type",
    [TieringAndNicheStage, FinalMortalityStage, PostMigrationNicheStage],
)
async def test_niche_stage_reaches_embedding_when_vectors_are_missing(
    stage_type: type[BaseStage],
    monkeypatch,
) -> None:
    class RecordingEmbedding:
        def __init__(self) -> None:
            self.embed_calls: list[tuple[list[str], bool]] = []

        def get_species_vectors(self, lineage_codes):
            return [], []

        def embed(self, texts, require_real=False):
            text_list = list(texts)
            self.embed_calls.append((text_list, require_real))
            return [[1.0, 0.0] for _ in text_list]

    species = SimpleNamespace(
        id=1,
        lineage_code="SP001",
        common_name="test species",
        latin_name="Species testus",
        description="terrestrial test species",
        abstract_traits={},
        morphology_stats={"population": 100},
    )
    embedding = RecordingEmbedding()
    engine = MagicMock()
    engine.watchlist = set()
    engine.tiering.classify.return_value = SimpleNamespace(
        critical=[], focus=[], background=[]
    )
    engine.niche_analyzer = NicheAnalyzer(embedding, carrying_capacity=1000)
    engine._use_tile_based_mortality = False
    engine.mortality.evaluate.return_value = []
    ctx = SimulationContext(turn_index=0, species_batch=[species])
    ctx.tiered = SimpleNamespace(critical=[], focus=[], background=[])
    ctx.migration_count = 1

    from ...repositories.environment_repository import environment_repository

    monkeypatch.setattr(environment_repository, "latest_habitats", lambda: [])
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: [])

    await stage_type().execute(ctx, engine)

    assert embedding.embed_calls == [(["test species Species testus terrestrial test species"], False)]
    assert "SP001" in ctx.niche_metrics


@pytest.mark.parametrize(
    "stage_type",
    [TieringAndNicheStage, FinalMortalityStage, PostMigrationNicheStage],
)
async def test_niche_stage_uses_its_internal_request_budget_in_pipeline(
    stage_type: type[BaseStage],
) -> None:
    stage = stage_type()
    completed = False

    async def delayed_execute(ctx, engine):
        nonlocal completed
        await asyncio.sleep(0.02)
        completed = True

    stage.execute = delayed_execute
    pipeline = Pipeline(
        [stage],
        PipelineConfig(stage_timeout=0.001, validate_dependencies=False),
    )

    result = await pipeline.execute(SimulationContext(turn_index=0), MagicMock())

    assert stage.uses_internal_request_budget is True
    assert result.success is True
    assert completed is True


@pytest.mark.parametrize("stage_type", [InitStage, AutoHybridizationStage])
async def test_local_stage_remains_protected_by_pipeline_timeout(
    stage_type: type[BaseStage],
) -> None:
    stage = stage_type()
    cancelled = False

    async def delayed_execute(ctx, engine):
        nonlocal cancelled
        try:
            await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            cancelled = True
            raise

    stage.execute = delayed_execute
    pipeline = Pipeline(
        [stage],
        PipelineConfig(stage_timeout=0.001, validate_dependencies=False),
    )

    result = await pipeline.execute(SimulationContext(turn_index=0), MagicMock())

    assert stage.uses_internal_request_budget is False
    assert result.success is False
    assert cancelled is True
    assert isinstance(result.stage_results[0].error, asyncio.TimeoutError)


async def test_init_and_auto_hybridization_current_paths_do_not_own_remote_requests() -> None:
    from ...services.embedding_plugins.ancestry_embedding import AncestryEmbeddingPlugin
    from ...services.embedding_plugins.base import EmbeddingPlugin
    from ...services.embedding_plugins.behavior_strategy import BehaviorStrategyPlugin
    from ...services.embedding_plugins.evolution_space import EvolutionSpacePlugin
    from ...services.embedding_plugins.food_web_embedding import FoodWebEmbeddingPlugin
    from ...services.embedding_plugins.prompt_optimizer import PromptOptimizerPlugin
    from ...services.embedding_plugins.tile_embedding import TileBiomePlugin

    built_in_plugin_types = [
        BehaviorStrategyPlugin,
        FoodWebEmbeddingPlugin,
        TileBiomePlugin,
        PromptOptimizerPlugin,
        EvolutionSpacePlugin,
        AncestryEmbeddingPlugin,
    ]

    assert all(
        plugin_type.on_turn_start is EmbeddingPlugin.on_turn_start
        for plugin_type in built_in_plugin_types
    )
    assert GeneticDistanceCalculator().embedding_service is None
    assert not hasattr(DescriptionEnhancerService(router=object()), "router")


@pytest.mark.parametrize(
    "stage_type",
    [
        FetchSpeciesStage,
        GeneActivationStage,
        SpeciationStage,
        BuildReportStage,
        EmbeddingStage,
        EmbeddingPluginsStage,
        EcologicalRealismStage,
    ],
)
async def test_previously_verified_remote_stage_keeps_budget_ownership(
    stage_type: type[BaseStage],
) -> None:
    assert BaseStage.uses_internal_request_budget is False
    assert stage_type.uses_internal_request_budget is True


@pytest.mark.parametrize("stage_type", [SpeciationStage, BuildReportStage])
async def test_ai_stage_has_no_local_wait_for_wrapper(
    stage_type: type[BaseStage],
) -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(stage_type.execute)))
    wait_for_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
        and node.func.attr == "wait_for"
    ]

    assert wait_for_calls == []


class TestPipelineBuilder:
    """PipelineBuilder 测试"""
    
    def test_build_pipeline(self):
        """测试构建流水线"""
        stages = [SimpleTestStage(10, "测试")]
        
        pipeline = (
            PipelineBuilder()
            .add_stages(stages)
            .continue_on_error(True)
            .log_timing(True)
            .build()
        )
        
        assert pipeline is not None
        assert len(pipeline.stages) == 1


# ============================================================================
# StageLoader Tests
# ============================================================================

class TestStageLoader:
    """StageLoader 测试"""
    
    def test_list_available_stages(self):
        """测试列出可用阶段"""
        loader = StageLoader()
        stages = loader.list_available_stages()
        
        assert len(stages) > 0
        assert "init" in stages
        assert "parse_pressures" in stages
    
    def test_load_stages_for_mode(self):
        """测试按模式加载阶段"""
        loader = StageLoader()
        
        for mode in AVAILABLE_MODES:
            try:
                stages = loader.load_stages_for_mode(mode, validate=False)
                # 验证返回的是阶段列表
                assert isinstance(stages, list)
                # 验证每个阶段都有 execute 方法
                for stage in stages:
                    assert hasattr(stage, 'execute')
            except Exception as e:
                pytest.fail(f"加载模式 {mode} 失败: {e}")
    
    def test_get_dependency_graph(self):
        """测试获取依赖图"""
        loader = StageLoader()
        graph = loader.get_dependency_graph("standard")
        
        assert "Stage 依赖关系图" in graph


# ============================================================================
# Stage Registry Tests
# ============================================================================

class TestStageRegistry:
    """StageRegistry 测试"""
    
    def test_registered_stages(self):
        """测试 GPU-only 架构下的核心阶段注册"""
        expected_stages = [
            "init",
            "parse_pressures",
            "map_evolution",
            "fetch_species",
            "tensor_ecology",
            "population_update",
        ]
        legacy_stages = [
            "preliminary_mortality",
            "migration",
            "final_mortality",
        ]

        for stage_name in expected_stages:
            stage_class = stage_registry.get(stage_name)
            assert stage_class is not None, f"阶段 {stage_name} 未注册"

        for stage_name in legacy_stages:
            assert stage_registry.get(stage_name) is None, f"旧阶段 {stage_name} 不应注册"
    
    def test_create_stage_instance(self):
        """测试创建阶段实例"""
        stage = stage_registry.create_stage("init")
        
        assert stage is not None
        assert hasattr(stage, 'execute')
        assert stage.name == "回合初始化"


# ============================================================================
# Default Stages Tests
# ============================================================================

class TestDefaultStages:
    """默认阶段测试"""
    
    def test_get_default_stages(self):
        """测试获取默认阶段列表"""
        stages = get_default_stages()
        
        assert len(stages) > 0
        # 验证按顺序排列
        orders = [s.order for s in stages]
        assert orders == sorted(orders)
    
    def test_default_stages_have_execute(self):
        """测试默认阶段都有 execute 方法"""
        stages = get_default_stages()
        
        for stage in stages:
            assert callable(getattr(stage, 'execute', None)), \
                f"阶段 {stage.name} 没有 execute 方法"

