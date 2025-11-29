from __future__ import annotations

from datetime import datetime
from typing import Sequence

from pydantic import BaseModel, Field


class SpeciesSnapshot(BaseModel):
    lineage_code: str
    latin_name: str
    common_name: str
    population: int
    population_share: float
    deaths: int
    death_rate: float
    ecological_role: str
    status: str
    notes: list[str] = []  # AI生成的分析段落列表（每个元素应为完整段落，非结构化数据）
    niche_overlap: float | None = None
    resource_pressure: float | None = None
    is_background: bool | None = None
    tier: str | None = None
    trophic_level: float | None = None
    grazing_pressure: float | None = None  # 新增：承受的啃食压力
    predation_pressure: float | None = None  # 新增：承受的捕食压力
    ai_narrative: str | None = None  # 【新增】AI生成的物种叙事（描述物种当前状态和演化故事）
    
    # 【新增v2】地块分布统计
    total_tiles: int = 0              # 分布的总地块数
    healthy_tiles: int = 0            # 健康地块数（死亡率<25%）
    warning_tiles: int = 0            # 警告地块数（死亡率25%-50%）
    critical_tiles: int = 0           # 危机地块数（死亡率>50%）
    best_tile_rate: float = 0.0       # 最低死亡率（最佳地块）
    worst_tile_rate: float = 1.0      # 最高死亡率（最差地块）
    has_refuge: bool = True           # 是否有避难所
    distribution_status: str = ""     # 分布状态：稳定/警告/部分危机/全域危机


class BranchingEvent(BaseModel):
    parent_lineage: str  # 也可作为parent_code使用
    new_lineage: str  # 也可作为child_code使用
    description: str  # 分化原因/reason
    timestamp: datetime
    reason: str | None = None  # 额外的详细原因字段（如果description不够用）


class BackgroundSummary(BaseModel):
    role: str
    species_codes: list[str]
    total_population: int
    survivor_population: int


class ReemergenceEvent(BaseModel):
    lineage_code: str
    reason: str


class MajorPressureEvent(BaseModel):
    severity: str
    description: str
    affected_tiles: list[int]


class MapChange(BaseModel):
    stage: str
    description: str
    affected_region: str
    change_type: str  # 修复：改为必需字段（uplift/erosion/volcanic/subsidence/glaciation等）


class MigrationEvent(BaseModel):
    lineage_code: str
    origin: str
    destination: str
    rationale: str


class MapTileInfo(BaseModel):
    id: int
    x: int
    y: int
    q: int
    r: int
    biome: str
    cover: str
    temperature: float  # 温度（°C）
    humidity: float  # 湿度（0-1）
    resources: float  # 资源丰富度（1-1000，绝对值）
    neighbors: list[int] = []
    elevation: float  # 相对海拔（elevation - sea_level）
    terrain_type: str  # 地形类型（海沟/深海/浅海/海岸/湖泊/平原/丘陵/山地/高山/极高山）
    climate_zone: str  # 气候带（热带/亚热带/温带/寒带/极地）
    color: str  # 当前视图模式的颜色值（hex格式）
    colors: dict[str, str] | None = None  # {"terrain": "#xxx", "elevation": "#yyy", ...}
    salinity: float = 35.0  # 盐度（‰），海水35，淡水0-0.5，湖泊varies
    is_lake: bool = False  # 是否为湖泊


class HabitatEntry(BaseModel):
    species_id: int
    lineage_code: str
    common_name: str  # 物种通用名
    latin_name: str  # 物种学名
    tile_id: int
    population: int
    suitability: float


class RiverSegment(BaseModel):
    source_id: int
    target_id: int
    flux: float


class VegetationInfo(BaseModel):
    density: float
    type: str  # "grass", "forest", "mixed"


class EcosystemMetrics(BaseModel):
    total_biomass: float = 0.0
    terrestrial_biomass: float = 0.0
    marine_biomass: float = 0.0
    average_trophic_level: float = 0.0
    average_body_length_cm: float = 0.0


class MapOverview(BaseModel):
    tiles: Sequence[MapTileInfo]
    habitats: Sequence[HabitatEntry]
    rivers: dict[int, RiverSegment] = {}
    vegetation: dict[int, VegetationInfo] = {}
    sea_level: float = 0.0  # 当前海平面高度（米）
    global_avg_temperature: float = 15.0  # 全球平均温度（°C）
    turn_index: int = 0  # 当前回合数


class TurnReport(BaseModel):
    turn_index: int
    pressures_summary: str
    narrative: str
    species: Sequence[SpeciesSnapshot]
    branching_events: Sequence[BranchingEvent]
    background_summary: Sequence[BackgroundSummary] = []
    reemergence_events: Sequence[ReemergenceEvent] = []
    major_events: Sequence[MajorPressureEvent] = []
    map_changes: Sequence[MapChange] = []
    migration_events: Sequence[MigrationEvent] = []
    sea_level: float = 0.0
    global_temperature: float = 15.0
    tectonic_stage: str = "稳定期"
    ecosystem_metrics: EcosystemMetrics | None = None


class LineageNode(BaseModel):
    lineage_code: str
    parent_code: str | None
    latin_name: str
    common_name: str
    state: str
    population_share: float
    major_events: list[str]
    birth_turn: int = 0
    extinction_turn: int | None = None
    ecological_role: str = "unknown"
    tier: str | None = None
    trophic_level: float = 1.0  # 营养级，用于确定族谱颜色
    speciation_type: str = "normal"
    current_population: int = 0
    peak_population: int = 0
    descendant_count: int = 0
    taxonomic_rank: str = "species"
    genus_code: str = ""
    hybrid_parent_codes: list[str] = []
    hybrid_fertility: float = 1.0
    genetic_distances: dict[str, float] = {}


class LineageTree(BaseModel):
    nodes: Sequence[LineageNode]


class ActionQueueStatus(BaseModel):
    queued_rounds: int
    running: bool
    queue_preview: list[str] = []  # 队列预览（例如：["极寒", "干旱", "回合推进"]）


class ExportRecord(BaseModel):
    turn_index: int
    markdown_path: str
    json_path: str


class PressureTemplate(BaseModel):
    kind: str
    label: str
    description: str


class SpeciesDetail(BaseModel):
    lineage_code: str
    latin_name: str
    common_name: str
    description: str
    morphology_stats: dict[str, float]
    abstract_traits: dict[str, float]  # 修复：应该是float而非int，与数据库一致
    hidden_traits: dict[str, float]
    status: str
    # 新增字段：与Species模型保持一致
    organs: dict[str, dict] = {}
    capabilities: list[str] = []
    genus_code: str = ""
    taxonomic_rank: str = "species"
    trophic_level: float = 1.0
    hybrid_parent_codes: list[str] = []
    hybrid_fertility: float = 1.0
    parent_code: str | None = None
    created_turn: int = 0
    # 修复：添加缺失的字段
    dormant_genes: dict = {}
    stress_exposure: dict = {}


class NicheCompareResult(BaseModel):
    species_a: SpeciesDetail
    species_b: SpeciesDetail
    similarity: float = Field(description="生态位相似度 (0-1)")
    overlap: float = Field(description="生态位重叠度 (0-1)")
    competition_intensity: float = Field(description="竞争强度 (0-1)")
    niche_dimensions: dict[str, dict[str, float]] = Field(
        description="各维度对比，格式：{dimension: {species_a: value, species_b: value}}"
    )


class SpeciesListItem(BaseModel):
    lineage_code: str
    latin_name: str
    common_name: str
    population: int
    status: str
    ecological_role: str


class SpeciesList(BaseModel):
    species: Sequence[SpeciesListItem]


# ========== 生态系统健康指标响应 ==========

class TrophicDistributionItem(BaseModel):
    """营养级分布项"""
    level: float
    species_count: int
    total_population: int
    total_biomass: float
    percentage: float


class ExtinctionRiskItem(BaseModel):
    """灭绝风险项"""
    lineage_code: str
    common_name: str
    risk_level: str  # "critical", "endangered", "vulnerable", "safe"
    risk_score: float
    reasons: list[str]


class EcosystemHealthResponse(BaseModel):
    """生态系统健康报告响应"""
    # 多样性指标
    shannon_index: float = Field(description="Shannon-Wiener多样性指数 (0-5+)")
    simpson_index: float = Field(description="Simpson多样性指数 (0-1)")
    species_richness: int = Field(description="物种丰富度（存活物种数）")
    evenness: float = Field(description="均匀度 (0-1)")
    
    # 营养级结构
    trophic_distribution: list[TrophicDistributionItem]
    trophic_balance_score: float = Field(description="营养级平衡分数 (0-1)")
    
    # 灭绝风险
    extinction_risks: list[ExtinctionRiskItem]
    critical_count: int = Field(description="极危物种数量")
    endangered_count: int = Field(description="濒危物种数量")
    
    # 共生网络
    symbiotic_connections: int = Field(description="共生关系数量")
    network_connectivity: float = Field(description="网络连通性 (0-1)")
    
    # 整体健康评分
    overall_health_score: float = Field(description="整体健康分数 (0-100)")
    health_grade: str = Field(description="健康等级 (A/B/C/D/F)")
    health_summary: str = Field(description="健康状况总结")


class InterventionResponse(BaseModel):
    """玩家干预操作响应"""
    success: bool
    message: str
    species_code: str | None = None
    effect_duration: int | None = None  # 效果持续回合数
