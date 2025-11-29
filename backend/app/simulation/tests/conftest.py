"""
Test Fixtures - 测试夹具

提供用于 Stage 测试的共享夹具和模拟对象。
"""

import pytest
import pytest_asyncio
import random
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, AsyncMock

# 配置 pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


# ============================================================================
# Mock Species
# ============================================================================

@dataclass
class MockSpecies:
    """模拟物种对象"""
    id: int = 1
    lineage_code: str = "SP001"
    common_name: str = "测试物种"
    latin_name: str = "Testus specius"
    status: str = "alive"
    trophic_level: float = 2.0
    habitat_type: str = "terrestrial"
    genus_code: str = "GEN001"
    parent_code: str = ""
    taxonomic_rank: str = "species"
    created_turn: int = 0
    is_background: bool = False
    morphology_stats: dict = field(default_factory=lambda: {
        "population": 10000,
        "body_weight_g": 100.0,
        "body_length_cm": 10.0,
    })
    hidden_traits: dict = field(default_factory=lambda: {
        "gene_diversity": 0.7,
        "environment_sensitivity": 0.5,
        "evolution_potential": 0.6,
    })
    abstract_traits: dict = field(default_factory=dict)
    organs: dict = field(default_factory=dict)
    capabilities: list = field(default_factory=list)
    description: str = "测试物种描述"


@dataclass
class MockTile:
    """模拟地块对象"""
    id: int = 1
    x: int = 0
    y: int = 0
    biome: str = "grassland"
    cover: str = "grass"
    temperature: float = 20.0
    humidity: float = 0.5
    resources: float = 100.0
    elevation: float = 100.0
    terrain_type: str = "平原"
    climate_zone: str = "温带"


@dataclass
class MockHabitat:
    """模拟栖息地对象"""
    id: int = 1
    species_id: int = 1
    tile_id: int = 1
    population: int = 1000
    suitability: float = 0.8


@dataclass
class MockMapState:
    """模拟地图状态"""
    id: int = 1
    turn_index: int = 0
    sea_level: float = 0.0
    global_avg_temperature: float = 15.0
    stage_name: str = "稳定期"
    stage_progress: float = 0.0
    stage_duration: int = 0


# ============================================================================
# Context Fixtures
# ============================================================================

@pytest.fixture
def seed():
    """固定随机种子"""
    random.seed(42)
    return 42


@pytest.fixture
def mock_species_list():
    """生成模拟物种列表"""
    species = []
    for i in range(5):
        sp = MockSpecies(
            id=i + 1,
            lineage_code=f"SP{i+1:03d}",
            common_name=f"测试物种{i+1}",
            trophic_level=1.0 + i * 0.5,
            morphology_stats={
                "population": 10000 * (5 - i),
                "body_weight_g": 100.0 * (i + 1),
                "body_length_cm": 10.0 * (i + 1),
            }
        )
        species.append(sp)
    return species


@pytest.fixture
def mock_tiles():
    """生成模拟地块列表"""
    tiles = []
    for i in range(10):
        tile = MockTile(
            id=i + 1,
            x=i % 5,
            y=i // 5,
            temperature=15.0 + random.uniform(-5, 5),
            humidity=0.5 + random.uniform(-0.2, 0.2),
        )
        tiles.append(tile)
    return tiles


@pytest.fixture
def mock_habitats(mock_species_list, mock_tiles):
    """生成模拟栖息地列表"""
    habitats = []
    hab_id = 1
    for sp in mock_species_list:
        # 每个物种分布在2-3个地块
        num_tiles = random.randint(2, 3)
        selected_tiles = random.sample(mock_tiles, num_tiles)
        for tile in selected_tiles:
            hab = MockHabitat(
                id=hab_id,
                species_id=sp.id,
                tile_id=tile.id,
                population=sp.morphology_stats["population"] // num_tiles,
                suitability=random.uniform(0.6, 1.0),
            )
            habitats.append(hab)
            hab_id += 1
    return habitats


@pytest.fixture
def mock_context(mock_species_list, mock_tiles, mock_habitats):
    """创建模拟 SimulationContext"""
    from ..context import SimulationContext
    
    ctx = SimulationContext(
        turn_index=0,
        command=MagicMock(pressures=[], rounds=1),
    )
    ctx.all_species = mock_species_list
    ctx.species_batch = [sp for sp in mock_species_list if sp.status == "alive"]
    ctx.extinct_codes = set()
    ctx.all_tiles = mock_tiles
    ctx.all_habitats = mock_habitats
    ctx.modifiers = {"temperature": 0.0, "drought": 0.0}
    ctx.major_events = []
    ctx.current_map_state = MockMapState()
    
    # 插件数据
    ctx._plugin_data = {}
    ctx._profiling_data = {}
    
    # 其他常用字段
    ctx.combined_results = []
    ctx.critical_results = []
    ctx.focus_results = []
    ctx.background_results = []
    ctx.pipeline_metrics = {}
    ctx.migration_count = 0
    ctx.branching_events = []
    ctx.ai_status_evals = {}
    ctx.emergency_responses = []
    ctx.narrative_results = []
    ctx.embedding_turn_data = {}
    
    return ctx


@pytest.fixture
def mock_engine():
    """创建模拟 SimulationEngine"""
    engine = MagicMock()
    
    # 模拟服务
    engine.environment = MagicMock()
    engine.environment.parse_pressures = MagicMock(return_value=[])
    engine.environment.apply_pressures = MagicMock(return_value={})
    
    engine.escalation_service = MagicMock()
    engine.escalation_service.register = MagicMock(return_value=[])
    
    engine.map_evolution = MagicMock()
    engine.map_evolution.advance = MagicMock(return_value=[])
    engine.map_evolution.calculate_climate_changes = MagicMock(return_value=(0.0, 0.0))
    
    engine.tiering = MagicMock()
    engine.niche_analyzer = MagicMock()
    engine.mortality = MagicMock()
    engine.tile_mortality = MagicMock()
    engine.migration_advisor = MagicMock()
    engine.reproduction_service = MagicMock()
    engine.speciation = MagicMock()
    engine.food_web_manager = MagicMock()
    
    # 功能开关
    engine._use_tile_based_mortality = True
    engine._use_tectonic_system = False
    engine._use_ai_pressure_response = False
    engine._use_embedding_integration = False
    
    engine.tectonic = None
    engine.watchlist = set()
    
    return engine


# ============================================================================
# Mortality Result Mock
# ============================================================================

@dataclass
class MockMortalityResult:
    """模拟死亡率结果"""
    species: MockSpecies
    initial_population: int = 10000
    death_rate: float = 0.1
    deaths: int = 1000
    survivors: int = 9000
    tier: str = "focus"
    notes: list = field(default_factory=list)
    niche_overlap: float = 0.0
    resource_pressure: float = 0.0
    grazing_pressure: float = 0.0
    predation_pressure: float = 0.0
    is_background: bool = False
    ai_narrative: str = ""
    births: int = 0
    final_population: int = 9000


@pytest.fixture
def mock_mortality_results(mock_species_list):
    """生成模拟死亡率结果"""
    results = []
    for sp in mock_species_list:
        pop = sp.morphology_stats.get("population", 10000)
        death_rate = random.uniform(0.05, 0.3)
        deaths = int(pop * death_rate)
        result = MockMortalityResult(
            species=sp,
            initial_population=pop,
            death_rate=death_rate,
            deaths=deaths,
            survivors=pop - deaths,
        )
        results.append(result)
    return results


# ============================================================================
# Tiering Result Mock
# ============================================================================

@dataclass
class MockTieringResult:
    """模拟分层结果"""
    critical: list = field(default_factory=list)
    focus: list = field(default_factory=list)
    background: list = field(default_factory=list)


@pytest.fixture
def mock_tiering_result(mock_species_list):
    """生成模拟分层结果"""
    return MockTieringResult(
        critical=mock_species_list[:1],
        focus=mock_species_list[1:3],
        background=mock_species_list[3:],
    )

