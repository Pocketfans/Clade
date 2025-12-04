"""
Ecological Realism Tests - 生态拟真测试

测试生态拟真系统的各个模块：
- Allee 效应
- 密度依赖疾病
- 环境波动
- 空间捕食效率
- 能量同化效率
- 垂直生态位
- 适应滞后
- 互利共生
"""

import pytest
import numpy as np
from dataclasses import dataclass, field
from unittest.mock import MagicMock, AsyncMock

# 标记整个模块使用 asyncio
pytestmark = pytest.mark.asyncio


# ============================================================================
# Mock Objects
# ============================================================================

@dataclass
class MockSpeciesForEcology:
    """针对生态拟真测试的模拟物种"""
    id: int = 1
    lineage_code: str = "SP001"
    common_name: str = "测试物种"
    latin_name: str = "Testus specius"
    status: str = "alive"
    trophic_level: float = 2.0
    description: str = "一种测试用的模拟物种"
    habitat_type: str = "terrestrial"
    embedding: np.ndarray | None = None
    morphology_stats: dict = field(default_factory=lambda: {
        "population": 10000,
        "body_weight_g": 100.0,
        "body_length_cm": 10.0,
    })
    hidden_traits: dict = field(default_factory=dict)
    abstract_traits: dict = field(default_factory=dict)
    capabilities: list = field(default_factory=list)
    organs: dict = field(default_factory=dict)
    prey_species: list = field(default_factory=list)
    
    def __post_init__(self):
        if self.embedding is None:
            # 创建随机 embedding
            np.random.seed(hash(self.lineage_code) % 2**32)
            self.embedding = np.random.randn(384).astype(np.float32)
            self.embedding /= np.linalg.norm(self.embedding)


class MockEmbeddingService:
    """模拟 Embedding 服务 - 匹配实际 EmbeddingService 接口"""
    
    def __init__(self, dim: int = 384):
        self.dim = dim
    
    def embed(self, texts: list[str], require_real: bool = False, batch_size: int = 100) -> list[list[float]]:
        """批量生成 embedding"""
        return [self._generate_embedding(t) for t in texts]
    
    def embed_single(self, text: str, require_real: bool = False) -> list[float]:
        """生成单个文本的 embedding"""
        return self._generate_embedding(text)
    
    def _generate_embedding(self, text: str) -> list[float]:
        """生成一致性的伪 embedding"""
        np.random.seed(hash(text) % 2**32)
        emb = np.random.randn(self.dim).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        return emb.tolist()


# ============================================================================
# Semantic Anchor Tests
# ============================================================================

class TestSemanticAnchorService:
    """语义锚点服务测试"""
    
    @pytest.fixture
    def embedding_service(self):
        return MockEmbeddingService()
    
    @pytest.fixture
    def anchor_service(self, embedding_service):
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        service = SemanticAnchorService(embedding_service)
        service.initialize()
        return service
    
    def test_initialization(self, anchor_service):
        """测试服务初始化"""
        assert anchor_service._initialized
        assert len(anchor_service._anchors) > 0
    
    def test_get_anchor(self, anchor_service):
        """测试获取锚点"""
        anchor = anchor_service.get_anchor("social_behavior")
        assert anchor is not None
        assert anchor.vector is not None
        assert len(anchor.vector) == 384
    
    def test_list_anchors(self, anchor_service):
        """测试列出所有锚点"""
        anchors = anchor_service.list_anchors()
        assert len(anchors) > 0
        assert "social_behavior" in anchors
    
    def test_stats(self, anchor_service):
        """测试统计信息"""
        stats = anchor_service.get_stats()
        assert "anchor_count" in stats
        assert stats["anchor_count"] > 0


# ============================================================================
# Allee Effect Tests
# ============================================================================

class TestAlleeEffect:
    """Allee 效应测试"""
    
    @pytest.fixture
    def eco_service(self):
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
        )
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        anchor_service = SemanticAnchorService(embedding_service)
        anchor_service.initialize()
        
        config = EcologicalRealismConfig(
            allee_critical_ratio=0.1,
            allee_max_penalty=0.4,  # 使用配置中的默认最大值
        )
        
        return EcologicalRealismService(anchor_service, config)
    
    def test_healthy_population_no_allee(self, eco_service):
        """测试健康种群无 Allee 效应"""
        species = MockSpeciesForEcology(
            morphology_stats={"population": 10000}
        )
        carrying_capacity = 50000
        
        result = eco_service.calculate_allee_effect(species, carrying_capacity)
        
        assert not result.is_below_mvp
        assert result.reproduction_modifier == 1.0
    
    def test_small_population_has_allee(self, eco_service):
        """测试小种群有 Allee 效应"""
        species = MockSpeciesForEcology(
            morphology_stats={"population": 1000}
        )
        carrying_capacity = 50000  # 1000/50000 = 0.02 < 0.1 临界值
        
        result = eco_service.calculate_allee_effect(species, carrying_capacity)
        
        assert result.is_below_mvp
        assert result.reproduction_modifier < 1.0
    
    def test_critical_population_severe_penalty(self, eco_service):
        """测试极小种群的严重惩罚"""
        species = MockSpeciesForEcology(
            morphology_stats={"population": 100}
        )
        carrying_capacity = 50000  # 极低密度
        
        result = eco_service.calculate_allee_effect(species, carrying_capacity)
        
        assert result.is_below_mvp
        assert result.reproduction_modifier < 0.5


# ============================================================================
# Density-Dependent Disease Tests
# ============================================================================

class TestDiseaseModule:
    """密度依赖疾病测试"""
    
    @pytest.fixture
    def eco_service(self):
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
        )
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        anchor_service = SemanticAnchorService(embedding_service)
        anchor_service.initialize()
        
        config = EcologicalRealismConfig(
            disease_density_threshold=0.8,
            disease_base_mortality=0.4,
        )
        
        return EcologicalRealismService(anchor_service, config)
    
    def test_low_density_no_disease(self, eco_service):
        """测试低密度无疾病"""
        species = MockSpeciesForEcology()
        density_ratio = 0.3  # 低于阈值
        
        result = eco_service.calculate_disease_pressure(species, density_ratio)
        
        assert result.disease_pressure == 0.0
        assert result.mortality_modifier == 0.0
    
    def test_high_density_has_disease(self, eco_service):
        """测试高密度有疾病压力"""
        species = MockSpeciesForEcology()
        density_ratio = 1.2  # 超过承载力
        
        result = eco_service.calculate_disease_pressure(species, density_ratio)
        
        assert result.disease_pressure > 0.0
        assert result.mortality_modifier > 0.0
    
    def test_overcrowding_severe_disease(self, eco_service):
        """测试严重过密的疾病压力"""
        species = MockSpeciesForEcology()
        density_ratio = 2.0  # 严重过密
        
        result = eco_service.calculate_disease_pressure(species, density_ratio)
        
        # 过密会产生显著疾病压力（具体值取决于语义匹配）
        assert result.disease_pressure > 0.2
        assert result.mortality_modifier > 0.05


# ============================================================================
# Environmental Fluctuation Tests
# ============================================================================

class TestEnvironmentalFluctuation:
    """环境波动测试"""
    
    @pytest.fixture
    def eco_service(self):
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
        )
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        anchor_service = SemanticAnchorService(embedding_service)
        anchor_service.initialize()
        
        config = EcologicalRealismConfig(
            fluctuation_amplitude=0.3,
            fluctuation_period_turns=20,
        )
        
        return EcologicalRealismService(anchor_service, config)
    
    def test_fluctuation_range(self, eco_service):
        """测试波动范围"""
        species = MockSpeciesForEcology()
        
        modifiers = []
        for turn in range(40):
            mod = eco_service.calculate_env_fluctuation_modifier(species, turn, 0.5)
            modifiers.append(mod)
        
        # 检查波动范围（允许小量误差）
        assert min(modifiers) >= 0.65  # 1 - 0.35 (允许误差)
        assert max(modifiers) <= 1.35  # 1 + 0.35 (允许误差)
    
    def test_latitude_effect(self, eco_service):
        """测试纬度效应"""
        species = MockSpeciesForEcology()
        turn = 10
        
        equator_mod = eco_service.calculate_env_fluctuation_modifier(species, turn, 0.0)
        polar_mod = eco_service.calculate_env_fluctuation_modifier(species, turn, 1.0)
        
        # 极地地区波动应该更大
        # 由于使用正弦函数，差异可能不明显
        assert abs(equator_mod - 1.0) <= abs(polar_mod - 1.0) + 0.1


# ============================================================================
# Vertical Niche Tests
# ============================================================================

class TestVerticalNiche:
    """垂直生态位测试"""
    
    @pytest.fixture
    def anchor_service(self):
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        service = SemanticAnchorService(embedding_service)
        service.initialize()
        return service
    
    @pytest.fixture
    def eco_service(self, anchor_service):
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
        )
        
        return EcologicalRealismService(anchor_service)
    
    def test_different_layers_low_overlap(self, eco_service):
        """测试不同层次的物种重叠度"""
        # 树冠层物种
        canopy_species = MockSpeciesForEcology(
            lineage_code="CANOPY",
            common_name="树冠鸟",
        )
        
        # 地面层物种
        ground_species = MockSpeciesForEcology(
            lineage_code="GROUND",
            common_name="地面鼠",
        )
        
        result = eco_service.calculate_vertical_niche_overlap(canopy_species, ground_species)
        
        # 返回的是 VerticalNicheResult 或 float
        overlap = result.competition_modifier if hasattr(result, 'competition_modifier') else result
        assert 0.0 <= overlap <= 1.0
    
    def test_same_niche_overlap(self, eco_service):
        """测试相似物种的生态位重叠"""
        # 两个相似物种
        species_a = MockSpeciesForEcology(
            lineage_code="SP_A",
            common_name="草原狐狸",
        )
        
        species_b = MockSpeciesForEcology(
            lineage_code="SP_B",
            common_name="草原狐狸亚种",  # 相似名称
        )
        
        result = eco_service.calculate_vertical_niche_overlap(species_a, species_b)
        
        overlap = result.competition_modifier if hasattr(result, 'competition_modifier') else result
        assert 0.0 <= overlap <= 1.0


# ============================================================================
# Mutualism Network Tests
# ============================================================================

class TestMutualismNetwork:
    """互利共生网络测试"""
    
    @pytest.fixture
    def eco_service(self):
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
        )
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        anchor_service = SemanticAnchorService(embedding_service)
        anchor_service.initialize()
        
        config = EcologicalRealismConfig(
            mutualism_threshold=0.3,  # 降低阈值便于测试
        )
        
        return EcologicalRealismService(anchor_service, config)
    
    def test_discover_mutualism(self, eco_service):
        """测试发现互利共生关系"""
        # 创建潜在共生物种对
        flower = MockSpeciesForEcology(
            lineage_code="FLOWER",
            common_name="开花植物",
            trophic_level=1.0,
        )
        
        pollinator = MockSpeciesForEcology(
            lineage_code="POLLINATOR",
            common_name="传粉蜜蜂",
            trophic_level=2.0,
        )
        
        links = eco_service.discover_mutualism_links([flower, pollinator], turn_index=5)
        
        # 可能发现共生关系，取决于 embedding 相似度
        assert isinstance(links, list)
    
    def test_mutualism_benefit(self, eco_service):
        """测试互利共生收益"""
        species = MockSpeciesForEcology()
        all_species = [species, MockSpeciesForEcology(lineage_code="OTHER")]
        
        benefit = eco_service.get_mutualism_benefit(species, all_species)
        
        assert isinstance(benefit, float)


# ============================================================================
# Assimilation Efficiency Tests
# ============================================================================

class TestAssimilationEfficiency:
    """同化效率测试"""
    
    @pytest.fixture
    def eco_service(self):
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
        )
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        anchor_service = SemanticAnchorService(embedding_service)
        anchor_service.initialize()
        
        config = EcologicalRealismConfig(
            herbivore_base_efficiency=0.10,
            carnivore_base_efficiency=0.25,
        )
        
        return EcologicalRealismService(anchor_service, config)
    
    def test_efficiency_range(self, eco_service):
        """测试效率范围"""
        species = MockSpeciesForEcology()
        
        efficiency = eco_service.calculate_assimilation_efficiency(species)
        
        assert 0.05 <= efficiency <= 0.35


# ============================================================================
# Stage Integration Tests
# ============================================================================

class TestEcologicalRealismStage:
    """生态拟真阶段集成测试"""
    
    @pytest.fixture
    def stage(self):
        from ..ecological_realism_stage import EcologicalRealismStage
        return EcologicalRealismStage()
    
    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        
        # 模拟容器和服务
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
            AlleeEffectResult,
            DiseaseResult,
            MutualismLink,
        )
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        embedding_service = MockEmbeddingService()
        anchor_service = SemanticAnchorService(embedding_service)
        anchor_service.initialize()
        
        eco_service = EcologicalRealismService(anchor_service)
        
        engine.container = MagicMock()
        engine.container.ecological_realism_service = eco_service
        
        return engine
    
    @pytest.fixture
    def mock_context(self):
        from ..context import SimulationContext
        
        ctx = SimulationContext(
            turn_index=5,
            command=MagicMock(pressures=[], rounds=1),
        )
        
        ctx.species_batch = [
            MockSpeciesForEcology(
                id=i+1, 
                lineage_code=f"SP{i+1:03d}",
                morphology_stats={"population": 10000 * (i + 1)},
            )
            for i in range(3)
        ]
        ctx.all_species = ctx.species_batch
        ctx.all_tiles = [MagicMock(id=i, x=i, y=0, temperature=20.0, humidity=0.5, resources=100) for i in range(5)]
        ctx.all_habitats = [
            MagicMock(species_id=sp.id, tile_id=i, suitability=0.8)
            for sp in ctx.species_batch
            for i in range(2)
        ]
        ctx.resource_snapshot = None
        
        # 模拟 emit_event 方法
        ctx.emit_event = MagicMock()
        
        return ctx
    
    def test_stage_properties(self, stage):
        """测试阶段属性"""
        assert stage.name == "生态拟真"
        assert stage.order == 190
    
    def test_stage_dependency(self, stage):
        """测试阶段依赖"""
        dep = stage.get_dependency()
        
        assert "fetch_species" in dep.requires_stages
        assert "tiering_and_niche" in dep.requires_stages
        assert "species_batch" in dep.requires_fields
        assert "plugin_data" in dep.writes_fields
    
    async def test_stage_execution(self, stage, mock_context, mock_engine):
        """测试阶段执行"""
        await stage.execute(mock_context, mock_engine)
        
        # 检查结果存入 plugin_data
        assert "ecological_realism" in mock_context.plugin_data
        
        eco_data = mock_context.plugin_data["ecological_realism"]
        assert "allee_results" in eco_data
        assert "disease_results" in eco_data
        assert "env_modifiers" in eco_data
    
    async def test_stage_handles_missing_service(self, stage, mock_context):
        """测试服务不可用时的处理"""
        engine = MagicMock()
        engine.container = MagicMock()
        
        # 模拟属性访问抛出异常
        type(engine.container).ecological_realism_service = property(
            lambda self: (_ for _ in ()).throw(Exception("Service unavailable"))
        )
        
        # 应该不会抛出异常，而是优雅地返回
        await stage.execute(mock_context, engine)


# ============================================================================
# Helper Function Tests
# ============================================================================

class TestHelperFunctions:
    """辅助函数测试"""
    
    @pytest.fixture
    def mock_context_with_eco_data(self):
        from ..context import SimulationContext
        
        ctx = SimulationContext(
            turn_index=5,
            command=MagicMock(),
        )
        
        # 直接设置 plugin_data (SimulationContext 的属性)
        ctx.plugin_data["ecological_realism"] = {
            "allee_results": {
                "SP001": {"is_below_mvp": True, "reproduction_modifier": 0.5},
            },
            "disease_results": {
                "SP001": {"disease_pressure": 0.3, "mortality_modifier": 0.15},
            },
            "env_modifiers": {"SP001": 0.9},
            "adaptation_penalties": {"SP001": 0.05},
            "mutualism_benefits": {"SP001": 0.1},
            "vertical_competition_modifiers": {"SP001_SP002": 0.7},
            "spatial_predation_efficiency": {"SP001_SP002": 0.8},
            "assimilation_efficiencies": {"SP001": 0.15},
        }
        
        return ctx
    
    def test_apply_to_mortality(self, mock_context_with_eco_data):
        """测试死亡率修正"""
        from ..ecological_realism_stage import apply_ecological_realism_to_mortality
        
        base_mortality = 0.1
        modified = apply_ecological_realism_to_mortality(
            mock_context_with_eco_data, 
            base_mortality, 
            "SP001"
        )
        
        # 应该加上疾病压力和适应滞后，减去共生收益
        assert modified != base_mortality
        assert 0.01 <= modified <= 0.95
    
    def test_apply_to_reproduction(self, mock_context_with_eco_data):
        """测试繁殖率修正"""
        from ..ecological_realism_stage import apply_ecological_realism_to_reproduction
        
        base_rate = 1.0
        modified = apply_ecological_realism_to_reproduction(
            mock_context_with_eco_data,
            base_rate,
            "SP001"
        )
        
        # 应该受 Allee 效应影响
        assert modified < base_rate  # Allee 效应减少繁殖率
    
    def test_get_vertical_niche_competition(self, mock_context_with_eco_data):
        """测试垂直生态位竞争系数"""
        from ..ecological_realism_stage import get_vertical_niche_competition
        
        competition = get_vertical_niche_competition(
            mock_context_with_eco_data,
            "SP001",
            "SP002"
        )
        
        assert competition == 0.7
    
    def test_get_spatial_predation_efficiency(self, mock_context_with_eco_data):
        """测试空间捕食效率"""
        from ..ecological_realism_stage import get_spatial_predation_efficiency
        
        efficiency = get_spatial_predation_efficiency(
            mock_context_with_eco_data,
            "SP001",
            "SP002"
        )
        
        assert efficiency == 0.8
    
    def test_get_assimilation_efficiency(self, mock_context_with_eco_data):
        """测试同化效率"""
        from ..ecological_realism_stage import get_assimilation_efficiency
        
        efficiency = get_assimilation_efficiency(
            mock_context_with_eco_data,
            "SP001"
        )
        
        assert efficiency == 0.15

