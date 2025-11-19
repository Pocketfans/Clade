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
    grazing_pressure: float | None = None  # 新增：承受的啃食压力
    predation_pressure: float | None = None  # 新增：承受的捕食压力


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
    tile_id: int
    population: int
    suitability: float


class MapOverview(BaseModel):
    tiles: Sequence[MapTileInfo]
    habitats: Sequence[HabitatEntry]
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
