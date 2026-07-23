"""Embedding 插件单元测试

测试所有插件的核心功能：
- 初始化
- 索引构建
- 搜索
- 降级处理
"""
import pytest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock, MagicMock

# 模拟 Species 类
@dataclass
class MockSpecies:
    lineage_code: str = "A1_B2"
    common_name: str = "测试物种"
    latin_name: str = "Testus specius"
    description: str = "一种测试用的物种"
    trophic_level: float = 2.5
    reproduction_r: float = 0.2
    status: str = "alive"
    total_population: int = 1000
    abstract_traits: dict = field(default_factory=lambda: {
        "攻击性": 5,
        "防御性": 6,
        "运动能力": 7,
        "社会性": 4,
        "感知能力": 5,
        "耐热性": 5,
        "耐寒性": 5,
    })
    populations: list = field(default_factory=list)
    prey_species: list = field(default_factory=list)


# 模拟 SimulationContext
@dataclass
class MockContext:
    turn_index: int = 0
    all_species: list = field(default_factory=list)
    all_tiles: list = field(default_factory=list)
    all_habitats: dict = field(default_factory=dict)
    pressures: list = field(default_factory=list)
    major_events: list = field(default_factory=list)
    combined_results: list = field(default_factory=list)
    adaptation_events: list = field(default_factory=list)
    branching_events: list = field(default_factory=list)
    trophic_interactions: dict = field(default_factory=dict)
    food_web_analysis: Any = None


# 模拟 EmbeddingService
class MockEmbeddingService:
    def __init__(self, dimension: int = 64):
        self.dimension = dimension
        self._vector_stores = MockMultiVectorStore(dimension)
        self._call_count = 0
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        self._call_count += 1
        import hashlib
        import numpy as np
        
        vectors = []
        for text in texts:
            # 基于文本哈希生成确定性向量
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            np.random.seed(h % (2**32))
            vec = np.random.randn(self.dimension).tolist()
            vectors.append(vec)
        return vectors
    
    def embed_single(self, text: str) -> list[float]:
        return self.embed([text])[0]
    
    def build_species_text(self, species, include_traits=True, include_names=True) -> str:
        return f"{species.common_name} {species.description}"
    
    def search_species(self, query: str, top_k: int = 10, exclude_codes: set = None):
        return []
    
    def search_events(self, query: str, top_k: int = 10, threshold: float = 0.3):
        return []
    
    def index_events_batch(self, events: list[dict]) -> int:
        return len(events)


class MockVectorStore:
    def __init__(self, dimension: int = 64):
        self.dimension = dimension
        self._data: dict[str, tuple[list[float], dict]] = {}
    
    @property
    def size(self) -> int:
        return len(self._data)
    
    def add_batch(self, ids: list[str], vectors: list[list[float]], metadata_list: list[dict]) -> int:
        for id, vec, meta in zip(ids, vectors, metadata_list or [{}] * len(ids)):
            self._data[id] = (vec, meta)
        return len(ids)
    
    def search(self, query_vec: list[float], top_k: int = 10, threshold: float = 0.0, exclude_ids: set = None):
        import numpy as np
        
        results = []
        q = np.array(query_vec)
        
        for id, (vec, meta) in self._data.items():
            if exclude_ids and id in exclude_ids:
                continue
            v = np.array(vec)
            sim = float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-8))
            if sim >= threshold:
                results.append(MockSearchResult(id=id, score=sim, metadata=meta))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def get(self, id: str):
        if id in self._data:
            return self._data[id][0]
        return None


@dataclass
class MockSearchResult:
    id: str
    score: float
    metadata: dict = field(default_factory=dict)


class MockMultiVectorStore:
    def __init__(self, dimension: int = 64):
        self.dimension = dimension
        self._stores: dict[str, MockVectorStore] = {}
    
    def get_store(self, name: str, create: bool = True):
        if name not in self._stores and create:
            self._stores[name] = MockVectorStore(self.dimension)
        return self._stores.get(name)


@pytest.fixture
def registered_builtin_plugins():
    from ..ancestry_embedding import AncestryEmbeddingPlugin
    from ..behavior_strategy import BehaviorStrategyPlugin
    from ..evolution_space import EvolutionSpacePlugin
    from ..food_web_embedding import FoodWebEmbeddingPlugin
    from ..registry import PluginRegistry
    from ..tile_embedding import TileBiomePlugin

    plugin_classes = {
        "ancestry": AncestryEmbeddingPlugin,
        "behavior_strategy": BehaviorStrategyPlugin,
        "evolution_space": EvolutionSpacePlugin,
        "food_web": FoodWebEmbeddingPlugin,
        "tile_biome": TileBiomePlugin,
    }

    PluginRegistry.clear()
    for name, plugin_class in plugin_classes.items():
        PluginRegistry.register(name, plugin_class)

    yield

    PluginRegistry.clear()


# ==================== 测试 Registry ====================

class TestPluginRegistry:
    def test_register_and_get(self):
        from ..registry import PluginRegistry, register_plugin
        from ..base import EmbeddingPlugin
        
        PluginRegistry.clear()
        
        @register_plugin("test_plugin")
        class TestPlugin(EmbeddingPlugin):
            @property
            def name(self) -> str:
                return "test_plugin"
            
            def build_index(self, ctx):
                return 0
            
            def search(self, query: str, top_k: int = 10):
                return []
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("test_plugin", service)
        
        assert plugin is not None
        assert plugin.name == "test_plugin"
        
        PluginRegistry.clear()
    
    def test_list_plugins(self):
        from ..registry import PluginRegistry, register_plugin
        from ..base import EmbeddingPlugin
        
        PluginRegistry.clear()
        
        @register_plugin("plugin_a")
        class PluginA(EmbeddingPlugin):
            @property
            def name(self) -> str:
                return "plugin_a"
            def build_index(self, ctx):
                return 0
            def search(self, query: str, top_k: int = 10):
                return []
        
        @register_plugin("plugin_b")
        class PluginB(EmbeddingPlugin):
            @property
            def name(self) -> str:
                return "plugin_b"
            def build_index(self, ctx):
                return 0
            def search(self, query: str, top_k: int = 10):
                return []
        
        plugins = PluginRegistry.list_plugins()
        assert "plugin_a" in plugins
        assert "plugin_b" in plugins
        
        PluginRegistry.clear()


# ==================== 测试 Manager ====================

class TestPluginManager:
    def test_load_plugins(self):
        from ..manager import EmbeddingPluginManager
        from ..registry import PluginRegistry
        
        PluginRegistry.clear()
        service = MockEmbeddingService()
        manager = EmbeddingPluginManager(service)
        
        count = manager.load_plugins()
        assert count == 0  # 没有注册插件
        
        PluginRegistry.clear()
    
    def test_get_all_stats(self):
        from ..manager import EmbeddingPluginManager
        from ..registry import PluginRegistry
        
        PluginRegistry.clear()
        service = MockEmbeddingService()
        manager = EmbeddingPluginManager(service)
        manager.load_plugins()
        
        stats = manager.get_all_stats()
        assert "manager" in stats
        assert "plugins" in stats
        
        PluginRegistry.clear()


# ==================== 测试 BehaviorStrategy 插件 ====================

class TestBehaviorStrategyPlugin:
    @pytest.fixture(autouse=True)
    def setup_plugin(self, registered_builtin_plugins):
        from ..registry import PluginRegistry

        self.service = MockEmbeddingService()
        self.plugin = PluginRegistry.get_instance("behavior_strategy", self.service)
        self.plugin.initialize()
    
    def test_infer_behavior_profile(self):
        species = MockSpecies()
        profile = self.plugin.infer_behavior_profile(species)
        
        assert profile.lineage_code == species.lineage_code
        assert profile.predation_strategy != ""
        assert profile.defense_strategy != ""
        assert profile.reproduction_strategy != ""
    
    def test_build_index(self):
        ctx = MockContext()
        ctx.all_species = [MockSpecies(), MockSpecies(lineage_code="B1")]
        
        count = self.plugin.build_index(ctx)
        assert count == 2
    
    def test_search(self):
        ctx = MockContext()
        ctx.all_species = [MockSpecies()]
        self.plugin.build_index(ctx)
        
        results = self.plugin.search("捕食 群体", top_k=5)
        assert isinstance(results, list)
    
    def test_find_behavior_conflicts(self):
        sp_a = MockSpecies(lineage_code="A1", abstract_traits={"攻击性": 8})
        sp_b = MockSpecies(lineage_code="B1", abstract_traits={"运动能力": 8})
        
        conflicts = self.plugin.find_behavior_conflicts(sp_a, sp_b)
        assert isinstance(conflicts, list)


# ==================== 测试 FoodWeb 插件 ====================

class TestFoodWebPlugin:
    @pytest.fixture(autouse=True)
    def setup_plugin(self, registered_builtin_plugins):
        from ..registry import PluginRegistry

        self.service = MockEmbeddingService()
        self.plugin = PluginRegistry.get_instance("food_web", self.service)
        self.plugin.initialize()
    
    def test_build_ecological_positions(self):
        ctx = MockContext()
        ctx.all_species = [
            MockSpecies(lineage_code="A1", trophic_level=3.0),
            MockSpecies(lineage_code="A2", trophic_level=3.0),
            MockSpecies(lineage_code="B1", trophic_level=2.0),
        ]
        
        positions = self.plugin.build_ecological_positions(ctx)
        assert len(positions) == 3
        
        # 同营养级应该有竞争关系
        assert "A2" in positions["A1"].competitors
        assert "A1" in positions["A2"].competitors
    
    def test_find_keystone_species(self):
        ctx = MockContext()
        ctx.all_species = [
            MockSpecies(lineage_code="A1", trophic_level=2.5, prey_species=["B1", "B2"]),
            MockSpecies(lineage_code="B1", trophic_level=1.5),
            MockSpecies(lineage_code="B2", trophic_level=1.5),
        ]
        
        self.plugin.build_index(ctx)
        keystones = self.plugin.find_keystone_species(top_k=3)
        
        assert isinstance(keystones, list)
    
    def test_calculate_ecosystem_stability(self):
        ctx = MockContext()
        ctx.all_species = [MockSpecies()] * 5
        self.plugin.build_index(ctx)
        
        stability = self.plugin.calculate_ecosystem_stability()
        assert "connectance" in stability
        assert "average_degree" in stability


# ==================== 测试 TileBiome 插件 ====================

class TestTileBiomePlugin:
    @pytest.fixture(autouse=True)
    def setup_plugin(self, registered_builtin_plugins):
        from ..registry import PluginRegistry

        self.service = MockEmbeddingService()
        self.plugin = PluginRegistry.get_instance("tile_biome", self.service)
        self.plugin.initialize()
    
    def test_build_tile_profiles(self):
        ctx = MockContext()
        ctx.all_tiles = [
            {"id": "T1", "biome": "forest", "temperature": 20, "precipitation": 1000},
            {"id": "T2", "biome": "desert", "temperature": 35, "precipitation": 100},
        ]
        ctx.all_species = [MockSpecies()]
        
        profiles = self.plugin.build_tile_profiles(ctx)
        assert len(profiles) == 2
        assert profiles["T1"].biome == "forest"
        assert profiles["T2"].biome == "desert"
    
    def test_find_ecological_hotspots(self):
        ctx = MockContext()
        ctx.all_tiles = [
            {"id": "T1", "biome": "forest", "temperature": 20, "precipitation": 1000},
            {"id": "T2", "biome": "desert", "temperature": 40, "precipitation": 50},
        ]
        ctx.all_species = []
        
        self.plugin.build_index(ctx)
        hotspots = self.plugin.find_ecological_hotspots(top_k=5)
        
        assert isinstance(hotspots, list)
        # 温带森林应该排名更高
        if hotspots:
            assert hotspots[0]["tile_id"] == "T1"


# ==================== 测试 EvolutionSpace 插件 ====================

class TestEvolutionSpacePlugin:
    @pytest.fixture(autouse=True)
    def setup_plugin(self, registered_builtin_plugins):
        from ..registry import PluginRegistry

        self.service = MockEmbeddingService()
        self.plugin = PluginRegistry.get_instance("evolution_space", self.service)
        self.plugin.initialize()
    
    def test_collect_evolution_events(self):
        ctx = MockContext()
        ctx.turn_index = 5
        ctx.adaptation_events = [
            {"species_code": "A1", "species_name": "测试", "adaptation_type": "寒冷适应"},
        ]
        
        events = self.plugin._collect_evolution_events(ctx)
        assert len(events) == 1
        assert events[0].species_code == "A1"
    
    def test_get_current_trends(self):
        ctx = MockContext()
        ctx.all_species = [MockSpecies()]
        ctx.adaptation_events = [
            {"species_code": f"A{i}", "species_name": f"物种{i}", "adaptation_type": "寒冷适应"}
            for i in range(10)
        ]
        
        self.plugin.build_index(ctx)
        trends = self.plugin.get_current_trends(top_k=3)
        
        assert isinstance(trends, list)


# ==================== 测试 Ancestry 插件 ====================

class TestAncestryPlugin:
    @pytest.fixture(autouse=True)
    def setup_plugin(self, registered_builtin_plugins):
        from ..registry import PluginRegistry

        self.service = MockEmbeddingService()
        self.plugin = PluginRegistry.get_instance("ancestry", self.service)
        self.plugin.initialize()
    
    def test_get_ancestor_chain(self):
        species = MockSpecies(lineage_code="A_B_C_D")
        ancestors = self.plugin._get_ancestor_chain(species)
        
        assert ancestors == ["A", "A_B", "A_B_C"]
    
    def test_predict_genetic_inertia(self):
        species = MockSpecies()
        ctx = MockContext(all_species=[species])

        for _ in range(5):
            self.plugin.build_index(ctx)

        inertia = self.plugin.predict_genetic_inertia(species, "攻击性")
        assert inertia["inertia"] > 0.5
        assert inertia["trend_direction"] == "stable"
    
    def test_build_index(self):
        ctx = MockContext()
        ctx.all_species = [
            MockSpecies(lineage_code="A"),
            MockSpecies(lineage_code="A_B"),
            MockSpecies(lineage_code="A_B_C"),
        ]
        
        count = self.plugin.build_index(ctx)
        assert count == 3

    def test_build_index_embedding_failure_does_not_publish_empty_cache(self):
        existing_species = MockSpecies(lineage_code="A")
        assert self.plugin.build_index(MockContext(all_species=[existing_species])) == 1
        existing_ancestry = self.plugin._ancestry_cache["A"]

        self.service.embed = Mock(return_value=[])
        count = self.plugin.build_index(
            MockContext(
                all_species=[existing_species, MockSpecies(lineage_code="A_B")]
            )
        )

        assert count == 0
        assert set(self.plugin._ancestry_cache) == {"A"}
        assert self.plugin._ancestry_cache["A"] is existing_ancestry


# ==================== 降级路径测试 ====================

@pytest.mark.usefixtures("registered_builtin_plugins")
class TestDegradationPaths:
    """测试插件在缺少数据时的降级处理"""

    def test_behavior_strategy_degradation_no_traits(self):
        """行为策略：缺少 abstract_traits 时应降级"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("behavior_strategy", service)
        plugin.initialize()
        
        # 物种没有 abstract_traits
        species = MockSpecies(abstract_traits=None)
        
        # 应该不抛异常，使用 trophic_level 推断
        profile = plugin.infer_behavior_profile(species)
        assert profile.predation_strategy != ""
        assert profile.defense_strategy != ""
    
    def test_behavior_strategy_empty_species_list(self):
        """行为策略：空物种列表应返回 0"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("behavior_strategy", service)
        plugin.initialize()
        
        ctx = MockContext()
        ctx.all_species = []  # 空列表
        
        count = plugin.build_index(ctx)
        assert count == 0
    
    def test_tile_biome_degradation_no_tiles(self):
        """地块向量：缺少 all_tiles 时应走降级路径"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("tile_biome", service)
        plugin.initialize()
        
        ctx = MockContext()
        ctx.all_tiles = []  # 无地块
        ctx.all_species = [MockSpecies()]
        
        # 应该返回 0，不抛异常
        count = plugin.build_index(ctx)
        assert count == 0
    
    def test_tile_biome_with_list_habitats(self):
        """地块向量：all_habitats 为 list 时应正确处理"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("tile_biome", service)
        plugin.initialize()
        
        ctx = MockContext()
        ctx.all_tiles = [{"id": "T1", "biome": "forest"}]
        ctx.all_species = []
        # all_habitats 作为 list 而非 dict
        ctx.all_habitats = [{"id": "T1", "biome": "rainforest"}]
        
        # 应该不抛异常
        profiles = plugin.build_tile_profiles(ctx)
        assert len(profiles) == 1
    
    def test_food_web_degradation_no_food_web_analysis(self):
        """食物网：缺少 food_web_analysis 时应使用 prey_species"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("food_web", service)
        plugin.initialize()
        
        ctx = MockContext()
        ctx.all_species = [
            MockSpecies(lineage_code="A1", prey_species=["B1"]),
            MockSpecies(lineage_code="B1", trophic_level=1.5),
        ]
        ctx.food_web_analysis = None  # 无食物网分析
        ctx.trophic_interactions = {}
        
        # 应该不抛异常
        positions = plugin.build_ecological_positions(ctx)
        assert len(positions) == 2
    
    def test_ancestry_empty_trait_history(self):
        """血统：无特征历史时应返回低置信度"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("ancestry", service)
        plugin.initialize()
        
        species = MockSpecies()
        # 无特征历史
        
        inertia = plugin.predict_genetic_inertia(species, "攻击性")
        assert inertia["confidence"] < 0.5  # 低置信度
    
    def test_search_on_empty_index(self):
        """所有插件：索引为空时搜索应返回空列表"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("behavior_strategy", service)
        plugin.initialize()
        
        # 不构建索引直接搜索
        results = plugin.search("任何查询")
        assert results == []
    
    def test_stats_track_degraded_mode(self):
        """统计信息应记录降级模式"""
        from ..registry import PluginRegistry
        
        service = MockEmbeddingService()
        plugin = PluginRegistry.get_instance("behavior_strategy", service)
        plugin.initialize()
        
        # 检查初始状态
        stats = plugin.get_stats()
        assert "degraded_mode" in stats
        assert "quality_warnings" in stats


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

