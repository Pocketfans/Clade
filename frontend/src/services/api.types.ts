export interface ActionQueueStatus {
  queued_rounds: number;
  running: boolean;
  queue_preview?: string[];
}

export interface SaveMetadata {
  name: string;
  turn: number;
  species_count: number;
  timestamp: number;
}

export interface SpeciesSnapshot {
  lineage_code: string;
  latin_name: string;
  common_name: string;
  population: number;
  population_share: number;
  deaths: number;
  death_rate: number;
  ecological_role: string;
  status: string;
  notes: string[];
  niche_overlap?: number;
  resource_pressure?: number;
  is_background?: boolean;
  tier?: string | null;
  trophic_level?: number;
  grazing_pressure?: number;
  predation_pressure?: number;
}

export interface BackgroundSummary {
  role: string;
  species_codes: string[];
  total_population: number;
  survivor_population: number;
}

export interface ReemergenceEvent {
  lineage_code: string;
  reason: string;
}

export interface MajorPressureEvent {
  severity: string;
  description: string;
  affected_tiles: number[];
}

export interface MapChange {
  stage: string;
  description: string;
  affected_region: string;
  change_type?: string; // uplift, erosion, volcanic, subsidence等
}

export interface MigrationEvent {
  lineage_code: string;
  origin: string;
  destination: string;
  rationale: string;
}

export interface BranchingEvent {
  parent_lineage: string;
  new_lineage: string;
  description: string;  // 修复：与后端保持一致
  timestamp: string;
  reason?: string;
}

export interface MapTileInfo {
  id: number;
  x: number;
  y: number;
  q: number;
  r: number;
  biome: string;
  cover: string;
  temperature: number;  // 温度（°C）
  humidity: number;     // 湿度（0-1）
  resources: number;    // 资源丰富度（1-1000，绝对值）
  elevation: number;    // 相对海拔（elevation - sea_level）
  terrain_type: string; // 地形类型（深海/浅海/海岸/平原/丘陵/山地/高山/极高山）
  climate_zone: string; // 气候带（热带/亚热带/温带/寒带/极地）
  color: string; // 当前视图模式的颜色值（hex格式）
  // 性能优化：预计算所有视图模式的颜色
  colors?: {
    terrain: string;
    terrain_type: string;
    elevation: string;
    biodiversity: string;
    climate: string;
    suitability?: string;
  };
}

export interface HabitatEntry {
  species_id: number;
  lineage_code: string;
  common_name: string;  // 物种通用名
  latin_name: string;   // 物种学名
  tile_id: number;
  population: number;
  suitability: number;
}

export interface RiverSegment {
  source_id: number;
  target_id: number;
  flux: number;
}

export interface VegetationInfo {
  density: number;
  type: string; // "grass", "forest", "mixed"
}

export interface MapOverview {
  tiles: MapTileInfo[];
  habitats: HabitatEntry[];
  rivers?: Record<string, RiverSegment>;
  vegetation?: Record<string, VegetationInfo>;
  sea_level: number; // 当前海平面高度（米）
  global_avg_temperature: number; // 全球平均温度（°C）
  turn_index: number; // 当前回合数
}

export interface TurnReport {
  turn_index: number;
  pressures_summary: string;
  narrative: string;
  species: SpeciesSnapshot[];
  background_summary: BackgroundSummary[];
  reemergence_events: ReemergenceEvent[];
  major_events: MajorPressureEvent[];
  map_changes: MapChange[];
  migration_events: MigrationEvent[];
  branching_events: BranchingEvent[];
  sea_level: number;
  global_temperature: number;
  tectonic_stage?: string; // 新增：地质阶段
}

export interface LineageNode {
  lineage_code: string;
  parent_code?: string | null;
  latin_name: string;
  common_name: string;
  state: string;
  population_share: number;
  major_events: string[];
  birth_turn: number;
  extinction_turn?: number | null;
  ecological_role: string;
  tier?: string | null;
  speciation_type: string;
  current_population: number;
  peak_population: number;
  descendant_count: number;
  taxonomic_rank: string;
  genus_code: string;
  hybrid_parent_codes: string[];
  hybrid_fertility: number;
  genetic_distances: Record<string, number>;
}

export interface LineageTree {
  nodes: LineageNode[];
}

// --- 新增配置接口 ---
export interface ProviderConfig {
  id: string;
  name: string;
  type: string;
  base_url?: string | null;
  api_key?: string | null;
  models: string[];
}

export interface CapabilityRouteConfig {
  provider_id?: string | null;
  model?: string | null;
  timeout: number;
  enable_thinking?: boolean;
}

export interface UIConfig {
  // 1. 服务商库
  providers: Record<string, ProviderConfig>;
  
  // 2. 全局默认设置
  default_provider_id?: string | null;
  default_model?: string | null;
  
  // 3. 功能路由表
  capability_routes: Record<string, CapabilityRouteConfig>;
  
  // 4. Embedding 配置
  embedding_provider_id?: string | null;
  embedding_model?: string | null;

  // --- Legacy Fields (For backward compatibility types) ---
  ai_provider?: string | null;
  ai_model?: string | null;
  ai_base_url?: string | null;
  ai_api_key?: string | null;
  ai_timeout?: number;
  capability_configs?: Record<string, any> | null;
  embedding_provider?: string | null;
  embedding_base_url?: string | null;
  embedding_api_key?: string | null;
}

export interface PressureDraft {
  kind: string;
  intensity: number;
  target_region?: [number, number] | null;
  label?: string; // For preset display
  narrative_note?: string; // For LLM context
}
export interface PressureTemplate {
  kind: string;
  label: string;
  description: string;
  narrative_template?: string; // Optional template for the description
  default_intensity?: number; // Optional default intensity
}
export interface SpeciesDetail {
  lineage_code: string;
  latin_name: string;
  common_name: string;
  description: string;
  morphology_stats: Record<string, number>;
  abstract_traits: Record<string, number>;
  hidden_traits: Record<string, number>;
  status: string;
  // 新增字段：与后端保持一致
  organs?: Record<string, Record<string, any>>;
  capabilities?: string[];
  genus_code?: string;
  taxonomic_rank?: string;
  trophic_level?: number;
  hybrid_parent_codes?: string[];
  hybrid_fertility?: number;
  parent_code?: string | null;
  created_turn?: number;
}

export interface SpeciesListItem {
  lineage_code: string;
  latin_name: string;
  common_name: string;
  population: number;
  status: string;
  ecological_role: string;
}

export interface NicheCompareResult {
  species_a: SpeciesDetail;
  species_b: SpeciesDetail;
  similarity: number;
  overlap: number;
  competition_intensity: number;
  niche_dimensions: Record<string, Record<string, number>>;
}
