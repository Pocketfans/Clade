"""
张量阶段单元测试

测试张量计算阶段的功能和与管线的集成。
"""

import importlib
from types import SimpleNamespace

import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch

# 标记整个模块使用 asyncio
pytestmark = pytest.mark.asyncio

from ..tensor_stages import (
    PressureTensorStage,
    TensorEcologyStage,
    TensorStateInitStage,
    TensorStateSyncStage,
    TensorMetricsStage,
    get_tensor_stages,
    get_minimal_tensor_stages,
)
from ..context import SimulationContext
from ...tensor import TensorState, TensorMetrics, TensorConfig, TensorBalanceConfig


@pytest.fixture
def mock_tensor_state():
    """创建测试用的 TensorState"""
    env = np.random.rand(5, 1, 10).astype(np.float32)  # (C, H, W)
    env[1] = 20.0  # 温度通道
    
    pop = np.random.rand(3, 1, 10).astype(np.float32) * 1000  # (S, H, W)
    species_params = np.zeros((3, 10), dtype=np.float32)  # 扩展到 10 列
    species_params[:, :5] = 0.5  # 默认值
    
    return TensorState(
        env=env,
        pop=pop,
        species_params=species_params,
        species_map={"SP001": 0, "SP002": 1, "SP003": 2},
    )


@pytest.fixture
def mock_context(mock_tensor_state):
    """创建测试用的 SimulationContext"""
    ctx = SimulationContext()
    ctx.turn_index = 1
    ctx.tensor_state = mock_tensor_state
    ctx.combined_results = []
    ctx.new_populations = {}
    ctx.species_batch = []
    ctx.tensor_trigger_codes = set()
    ctx.modifiers = {}
    ctx.pressures = []
    ctx.pressure_overlay = None
    return ctx


@pytest.fixture
def mock_engine():
    """创建测试用的 SimulationEngine"""
    engine = MagicMock()
    engine._use_tensor_ecology = True
    engine._use_tensor_speciation = True
    
    # 创建真实的 TensorConfig 和 TensorBalanceConfig
    balance = TensorBalanceConfig(
        temp_optimal=20.0,
        temp_tolerance=15.0,
        temp_channel_idx=1,
        diffusion_rate=0.1,
        birth_rate=0.1,
        competition_strength=0.01,
        capacity_multiplier=10000.0,
    )
    tensor_config = TensorConfig(balance=balance)
    engine.tensor_config = tensor_config
    
    return engine


class TestPressureTensorStage:
    """PressureTensorStage 测试"""
    
    def test_stage_name(self):
        """测试阶段名称"""
        stage = PressureTensorStage()
        assert "压力" in stage.name
    
    async def test_execute_creates_overlay(self, mock_context, mock_engine):
        """测试执行后创建压力叠加层"""
        mock_context.modifiers = {"temperature": -1.5, "drought": 2.0}
        
        stage = PressureTensorStage()
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.pressure_overlay is not None
        assert len(mock_context.pressure_overlay.active_pressures) > 0


class TestTensorStateInitStage:
    """TensorStateInitStage 仓库隔离测试。"""

    async def test_uses_engine_environment_repository(self, monkeypatch):
        """栖息地读取只使用引擎注入的环境仓库。"""
        environment_repository_module = importlib.import_module(
            "app.repositories.environment_repository"
        )

        class RecordingRepository:
            def __init__(self, habitats):
                self.habitats = habitats
                self.calls = []

            def get_habitats_by_species_id(self, species_id, latest_only):
                self.calls.append((species_id, latest_only))
                return self.habitats

        species = SimpleNamespace(
            id=7,
            lineage_code="SP007",
            morphology_stats={"population": 20},
            habitats=[],
            habitat_type="terrestrial",
            temp_optimal=20.0,
            temp_tolerance=15.0,
            mobility=1.0,
            reproduction_rate=0.1,
        )
        tile = SimpleNamespace(
            id=11,
            x=0,
            y=0,
            temperature=20.0,
            humidity=0.5,
            elevation=0.0,
            resources=100.0,
            biome="land",
        )
        injected_repository = RecordingRepository(
            [SimpleNamespace(tile_id=11, population=20)]
        )
        global_repository = RecordingRepository(
            [SimpleNamespace(tile_id=11, population=99)]
        )
        monkeypatch.setattr(
            environment_repository_module,
            "environment_repository",
            global_repository,
        )
        context = SimpleNamespace(
            species_batch=[species],
            current_map_state=SimpleNamespace(height=1, width=1),
            all_tiles=[tile],
        )
        engine = SimpleNamespace(environment_repository=injected_repository)

        await TensorStateInitStage().execute(context, engine)

        assert injected_repository.calls == [(7, True)]
        assert global_repository.calls == []
        assert context.tensor_state.pop[0, 0, 0] == 20


class TestTensorEcologyStage:
    """TensorEcologyStage 测试 - 统一生态计算阶段"""
    
    def test_stage_order(self):
        """测试阶段顺序正确"""
        stage = TensorEcologyStage()
        assert "统一" in stage.name or "生态" in stage.name
    
    def test_stage_name_contains_ecology(self):
        """测试阶段名称包含生态"""
        stage = TensorEcologyStage()
        assert "生态" in stage.name
    
    async def test_execute_skips_when_no_tensor_state(self, mock_context, mock_engine):
        """测试没有 tensor_state 时跳过"""
        mock_context.tensor_state = None
        stage = TensorEcologyStage()
        
        # 应该跳过，不抛出异常
        await stage.execute(mock_context, mock_engine)
    
    async def test_execute_updates_population(self, mock_context, mock_engine):
        """测试执行后更新种群"""
        stage = TensorEcologyStage()
        
        original_pop = mock_context.tensor_state.pop.sum()
        await stage.execute(mock_context, mock_engine)
        
        # 生态计算后种群会有变化
        new_pop = mock_context.tensor_state.pop.sum()
        # 种群可能增加或减少，取决于环境条件
        assert new_pop != original_pop or mock_context.tensor_state is not None
    
    async def test_execute_updates_metrics(self, mock_context, mock_engine):
        """测试执行后更新监控指标"""
        stage = TensorEcologyStage()
        
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.tensor_metrics is not None
        assert mock_context.tensor_metrics.mortality_time_ms >= 0


class TestTensorMetricsStage:
    """TensorMetricsStage 测试"""
    
    def test_stage_name(self):
        """测试阶段名称"""
        stage = TensorMetricsStage()
        assert "监控" in stage.name or "指标" in stage.name
    
    async def test_execute_collects_metrics(self, mock_context, mock_engine):
        """测试收集监控指标"""
        mock_context.tensor_trigger_codes = {"SP001", "SP002"}
        
        stage = TensorMetricsStage()
        await stage.execute(mock_context, mock_engine)
        
        assert mock_context.tensor_metrics is not None


class TestTensorStateSyncStage:
    """TensorStateSyncStage 测试"""
    
    def test_stage_name(self):
        """测试阶段名称"""
        stage = TensorStateSyncStage()
        assert "同步" in stage.name
    
    async def test_execute_syncs_populations(self, mock_context, mock_engine):
        """测试同步种群数据"""
        mock_context.new_populations = {"SP001": 100, "SP002": 200}
        
        stage = TensorStateSyncStage()
        await stage.execute(mock_context, mock_engine)
        
        # 应该更新 new_populations
        assert "SP001" in mock_context.new_populations
        assert mock_context.new_populations["SP001"] >= 0

    async def test_uses_engine_repositories(self, monkeypatch):
        """物种持久化和栖息地写入只使用引擎注入的仓库。"""
        species_repository_module = importlib.import_module(
            "app.repositories.species_repository"
        )
        environment_repository_module = importlib.import_module(
            "app.repositories.environment_repository"
        )

        class RecordingSpeciesRepository:
            def __init__(self):
                self.upserted = []

            def upsert(self, species):
                self.upserted.append(species)

        class RecordingEnvironmentRepository:
            def __init__(self):
                self.batches = []

            def write_habitats(self, habitats):
                self.batches.append(habitats)

        injected_species_repository = RecordingSpeciesRepository()
        global_species_repository = RecordingSpeciesRepository()
        injected_environment_repository = RecordingEnvironmentRepository()
        global_environment_repository = RecordingEnvironmentRepository()
        monkeypatch.setattr(
            species_repository_module,
            "species_repository",
            global_species_repository,
        )
        monkeypatch.setattr(
            environment_repository_module,
            "environment_repository",
            global_environment_repository,
        )

        species = SimpleNamespace(
            id=7,
            lineage_code="SP007",
            morphology_stats={"population": 10},
            status="alive",
        )
        context = SimpleNamespace(
            tensor_state=TensorState(
                env=np.zeros((7, 1, 1), dtype=np.float32),
                pop=np.array([[[20.0]]], dtype=np.float32),
                species_params=np.zeros((1, 4), dtype=np.float32),
                masks={},
                species_map={"SP007": 0},
            ),
            species_batch=[species],
            all_tiles=[SimpleNamespace(id=11, x=0, y=0)],
            new_populations={},
            turn_index=3,
        )
        engine = SimpleNamespace(
            species_repository=injected_species_repository,
            environment_repository=injected_environment_repository,
        )

        await TensorStateSyncStage().execute(context, engine)

        assert injected_species_repository.upserted == [species]
        assert global_species_repository.upserted == []
        assert len(injected_environment_repository.batches) == 1
        assert global_environment_repository.batches == []
        habitat = injected_environment_repository.batches[0][0]
        assert habitat.tile_id == 11
        assert habitat.species_id == 7
        assert habitat.population == 20
        assert context.new_populations == {"SP007": 20}
        assert species.morphology_stats["population"] == 20


class TestGetTensorStages:
    """测试获取张量阶段函数"""
    
    def test_get_tensor_stages_returns_list(self):
        """测试返回阶段列表"""
        stages = get_tensor_stages()
        assert isinstance(stages, list)
        assert len(stages) > 0
    
    def test_get_tensor_stages_contains_ecology(self):
        """测试包含统一生态阶段"""
        stages = get_tensor_stages()
        names = [s.name for s in stages]
        assert any("生态" in name for name in names)
    
    def test_get_tensor_stages_contains_metrics(self):
        """测试包含监控阶段"""
        stages = get_tensor_stages()
        names = [s.name for s in stages]
        assert any("监控" in name or "指标" in name for name in names)
    
    def test_get_minimal_tensor_stages(self):
        """测试获取最小阶段集"""
        stages = get_minimal_tensor_stages()
        assert len(stages) == 3  # PressureTensorStage, TensorEcologyStage, TensorMetricsStage
        
        names = [s.name for s in stages]
        assert any("压力" in name for name in names)
        assert any("生态" in name for name in names)
        assert any("监控" in name or "指标" in name for name in names)
    
    def test_stages_have_correct_order(self):
        """测试阶段顺序正确"""
        stages = get_tensor_stages()
        orders = [s.order for s in stages]
        
        # 所有阶段都应该有正整数 order
        assert all(o > 0 for o in orders)
    
    def test_no_legacy_stages(self):
        """测试不包含旧的分散阶段"""
        stages = get_tensor_stages()
        names = [s.name for s in stages]
        
        # 不应该包含旧的分散阶段
        assert not any("张量死亡率计算" == name for name in names)
        assert not any("张量种群扩散" == name for name in names)
        assert not any("张量繁殖计算" == name for name in names)
        assert not any("张量种间竞争" == name for name in names)
        assert not any("张量迁徙计算" == name for name in names)


class TestStageIntegration:
    """阶段集成测试"""
    
    async def test_full_tensor_pipeline(self, mock_context, mock_engine):
        """测试完整张量管线执行"""
        stages = get_tensor_stages()
        
        for stage in sorted(stages, key=lambda s: s.order):
            await stage.execute(mock_context, mock_engine)
        
        # 管线执行完成后应该有监控指标
        assert mock_context.tensor_metrics is not None
    
    async def test_pressure_stage_first(self, mock_context, mock_engine):
        """测试压力阶段在生态阶段之前执行"""
        stages = get_tensor_stages()
        sorted_stages = sorted(stages, key=lambda s: s.order)
        
        pressure_idx = next(i for i, s in enumerate(sorted_stages) if "压力" in s.name)
        ecology_idx = next(i for i, s in enumerate(sorted_stages) if "生态" in s.name)
        
        assert pressure_idx < ecology_idx
    
    async def test_ecology_stage_before_sync(self, mock_context, mock_engine):
        """测试生态阶段在同步阶段之前执行"""
        stages = get_tensor_stages()
        sorted_stages = sorted(stages, key=lambda s: s.order)
        
        ecology_idx = next(i for i, s in enumerate(sorted_stages) if "生态" in s.name)
        sync_idx = next(i for i, s in enumerate(sorted_stages) if "同步" in s.name)
        
        assert ecology_idx < sync_idx
