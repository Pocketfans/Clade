export interface ActionQueueStatus {
  queued_rounds: number;
  running: boolean;
  queue_preview?: string[];
}

export interface SaveMetadata {
  name: string;
  save_name: string;      // 原始存档名
  turn: number;
  turn_index: number;     // 与turn相同，兼容不同格式
  species_count: number;
  timestamp: number;
  scenario: string;       // 剧本/场景名称
  last_saved: string;     // ISO格式的最后保存时间
  created_at?: string;    // ISO格式的创建时间
}

// 辅助函数：清理存档名称显示
export function formatSaveName(rawName: string): { displayName: string; isAutoSave: boolean } {
  // 检测自动保存
  const isAutoSave = rawName.toLowerCase().includes('autosave');
  
  // 清理常见的时间戳模式
  let displayName = rawName
    // 移除 save_ 前缀
    .replace(/^save_/, '')
    // 移除 autosave_ 前缀中的时间戳（保留核心名称）
    .replace(/^autosave_(\d+)_\d{8}_\d{6}$/, '自动存档 #$1')
    // 移除尾部时间戳 _YYYYMMDD_HHMMSS
    .replace(/_\d{8}_\d{6}$/, '')
    // 移除开头的时间戳 YYYYMMDD_HHMMSS_
    .replace(/^\d{8}_\d{6}_/, '');
  
  // 如果清理后为空或纯数字，使用原名
  if (!displayName || /^\d+$/.test(displayName)) {
    if (isAutoSave) {
      const match = rawName.match(/autosave_(\d+)/i);
      displayName = match ? `自动存档 #${match[1]}` : '自动存档';
    } else {
      displayName = rawName;
    }
  }
  
  return { displayName, isAutoSave };
}

// 辅助函数：格式化相对时间
export function formatRelativeTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins} 分钟前`;
    if (diffHours < 24) return `${diffHours} 小时前`;
    if (diffDays < 7) return `${diffDays} 天前`;
    
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return '未知时间';
  }
}

export interface SpeciesSnapshot {
  lineage_code: string;
  latin_name: string;
  common_name: string;
  population: number;  // 本回合结束时的种群数量（经过死亡+繁殖后）
  population_share: number;
  deaths: number;  // 本回合死亡数量
  death_rate: number;  // 死亡率（deaths / initial_population）
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
  ai_narrative?: string | null; // AI生成的物种叙事
  
  // 种群变化完整追踪
  initial_population?: number;  // 回合开始时的种群数量
  births?: number;  // 本回合新出生的个体数量
  survivors?: number;  // 存活的个体数量（initial_population - deaths）
  // 关系：population = survivors + births
  
  // 地块分布统计
  total_tiles?: number;  // 分布的总地块数
  healthy_tiles?: number;  // 健康地块数（死亡率<25%）
  warning_tiles?: number;  // 警告地块数（死亡率25%-50%）
  critical_tiles?: number;  // 危机地块数（死亡率>50%）
  best_tile_rate?: number;  // 最低死亡率
  worst_tile_rate?: number;  // 最高死亡率
  has_refuge?: boolean;  // 是否有避难所
  distribution_status?: string;  // 分布状态
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

// 宜居度分解数据
export interface SuitabilityBreakdown {
  // === 总体分数 ===
  semantic_score: number;   // 语义相似度 (0-1)，来自 Embedding
  feature_score: number;    // 特征相似度 (0-1)，来自 12D 向量
  
  // === 12 维特征分解 ===
  thermal: number;          // 热量匹配 (0-1)
  moisture: number;         // 水分匹配 (0-1)
  altitude: number;         // 海拔匹配 (0-1)
  salinity: number;         // 盐度匹配 (0-1)
  resources: number;        // 资源匹配 (0-1)
  aquatic: number;          // 水域性匹配 (0-1) - 最重要！
  depth: number;            // 深度匹配 (0-1)
  light: number;            // 光照匹配 (0-1)
  volcanic: number;         // 地热匹配 (0-1)
  stability: number;        // 稳定性匹配 (0-1)
  vegetation: number;       // 植被匹配 (0-1)
  river: number;            // 河流匹配 (0-1)
  
  // === 兼容旧字段（可选）===
  temp_score?: number;
  humidity_score?: number;
  food_score?: number;
  biome_score?: number;
  special_bonus?: number;
  has_prey?: boolean;
  prey_abundance?: number;
}

export interface HabitatEntry {
  species_id: number;
  lineage_code: string;
  common_name: string;  // 物种通用名
  latin_name: string;   // 物种学名
  tile_id: number;
  population: number;
  suitability: number;
  breakdown?: SuitabilityBreakdown;  // 【新增】宜居度分解
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
  extinction_count?: number; // 本回合灭绝物种数量
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
  trophic_level: number;  // 营养级，用于确定族谱颜色
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

// --- AI 服务商类型常量 ---
export type ProviderType = "openai" | "anthropic" | "google";

// --- 新增配置接口 ---
export interface ProviderConfig {
  id: string;
  name: string;
  type: string;  // 兼容旧字段
  provider_type: ProviderType;  // API 类型：openai, anthropic, google
  base_url?: string | null;
  api_key?: string | null;
  models: string[];
  selected_models?: string[];  // 用户选择保存的模型列表
}

export interface CapabilityRouteConfig {
  provider_id?: string | null;
  provider_ids?: string[] | null;  // 多服务商池（负载均衡模式）
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
  embedding_dimensions?: number | null;
  
  // 5. 自动保存配置
  autosave_enabled?: boolean;      // 是否启用自动保存
  autosave_interval?: number;      // 每N回合自动保存一次
  autosave_max_slots?: number;     // 最大自动保存槽位数
  
  // 6. AI 推演超时配置
  ai_species_eval_timeout?: number;   // 单物种AI评估超时（秒）
  ai_batch_eval_timeout?: number;     // 整体批量评估超时（秒）
  ai_narrative_timeout?: number;      // 物种叙事生成超时（秒）
  ai_speciation_timeout?: number;     // 物种分化评估超时（秒）
  ai_concurrency_limit?: number;      // AI并发请求数限制
  
  // 7. 负载均衡配置
  load_balance_enabled?: boolean;     // 是否启用多服务商负载均衡
  load_balance_strategy?: "round_robin" | "random" | "least_latency";  // 负载均衡策略

  // 8. AI 叙事开关
  ai_narrative_enabled?: boolean;     // 是否启用 AI 生成物种叙事（默认关闭）

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

// ========== 食物网相关类型 ==========

export interface FoodWebNode {
  id: string;
  name: string;
  trophic_level: number;
  population: number;
  diet_type: string;
  habitat_type: string;
  prey_count: number;
  predator_count: number;
}

export interface FoodWebLink {
  source: string;  // 猎物
  target: string;  // 捕食者
  value: number;   // 偏好比例
  predator_name: string;
  prey_name: string;
}

export interface FoodWebData {
  nodes: FoodWebNode[];
  links: FoodWebLink[];
  keystone_species: string[];
  trophic_levels: Record<number, string[]>;
  total_species: number;
  total_links: number;
}

export interface SpeciesFoodChain {
  species: {
    code: string;
    name: string;
    trophic_level: number;
  };
  prey_chain: FoodChainNode[];
  predator_chain: FoodChainNode[];
  food_dependency: number;
  predation_pressure: number;
}

export interface FoodChainNode {
  code: string;
  name: string;
  trophic_level: number;
  depth: number;
  prey?: FoodChainNode[];
  predators?: FoodChainNode[];
}

export interface ExtinctionImpact {
  extinct_species: string;
  directly_affected: string[];
  indirectly_affected: string[];
  food_chain_collapse_risk: number;
  affected_biomass_percentage: number;
}

// 食物网分析结果
export interface FoodWebAnalysis {
  health_score: number;
  total_species: number;
  total_links: number;
  orphaned_consumers: string[];
  starving_species: string[];
  keystone_species: string[];
  isolated_species: string[];
  avg_prey_per_consumer: number;
  food_web_density: number;
  bottleneck_warnings: string[];
}

// 食物网修复结果
export interface FoodWebRepairResult {
  repaired_count: number;
  changes: FoodWebChange[];
  analysis_after: {
    health_score: number;
    orphaned_consumers: number;
    starving_species: number;
  };
}

export interface FoodWebChange {
  species_code: string;
  species_name: string;
  change_type: string;
  details: string;
  old_prey: string[];
  new_prey: string[];
}