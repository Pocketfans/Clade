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

// 生态拟真快照 - 物种级别
export interface EcologicalRealismSnapshot {
  // Allee 效应
  is_below_mvp: boolean;                // 是否低于最小可存活种群
  allee_reproduction_modifier: number;  // 繁殖率修正 (0-1)
  
  // 密度依赖疾病
  disease_pressure: number;             // 疾病压力 (0-1)
  disease_mortality_modifier: number;   // 疾病死亡率修正
  
  // 环境波动
  env_fluctuation_modifier: number;     // 环境波动修正
  
  // 同化效率
  assimilation_efficiency: number;      // 能量同化效率 (0.05-0.35)
  
  // 适应滞后
  adaptation_penalty: number;           // 适应滞后惩罚 (0-0.3)
  
  // 互利共生
  mutualism_benefit: number;            // 共生收益/惩罚
  mutualism_partners: string[];         // 共生伙伴代码列表
}

// 生态拟真汇总 - 回合级别
export interface EcologicalRealismSummary {
  // Allee 效应统计
  allee_affected_count: number;         // 受 Allee 效应影响的物种数
  allee_affected_species: string[];     // 受影响物种代码列表
  
  // 疾病压力统计
  disease_affected_count: number;       // 受疾病压力影响的物种数
  avg_disease_pressure: number;         // 平均疾病压力
  
  // 互利共生统计
  mutualism_links_count: number;        // 共生关系数量
  mutualism_species_count: number;      // 参与共生的物种数
  
  // 环境压力统计
  adaptation_stressed_count: number;    // 受适应滞后影响的物种数
  avg_env_modifier: number;             // 平均环境波动修正
}

export interface SpeciesSnapshot {
  lineage_code: string;
  latin_name: string;
  common_name: string;
  population: number;  // 本回合结束时的种群数量（经过死亡+繁殖后）
  population_share: number;
  deaths: number;  // 本回合死亡数量
  death_rate: number;  // 死亡率（deaths / initial_population）
  net_change_rate?: number; // 净变化率 ((期末-期初)/期初)
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
  
  // 生态拟真状态
  ecological_realism?: EcologicalRealismSnapshot | null;
  
  // 基因数据（用于基因库）
  abstract_traits?: Record<string, number>;
  organs?: Record<string, Record<string, unknown>>;
  capabilities?: string[];
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
  ecological_realism?: EcologicalRealismSummary | null; // 生态拟真统计
  gene_diversity_events?: {
    lineage_code: string;
    name?: string;
    old?: number;
    new?: number;
    reason?: string;
  }[];
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
  total_count?: number;  // 总数（用于分页）
}

// 族谱查询参数
export interface LineageQueryParams {
  status?: "alive" | "extinct";  // 筛选状态
  prefix?: string;               // 按lineage_code前缀筛选
  include_genetic_distances?: boolean;  // 是否包含遗传距离
  limit?: number;                // 分页限制
  offset?: number;               // 分页偏移
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
  models: string[];  // 收藏的模型列表
  disabled_models?: string[];  // 禁用的模型列表（收藏但不启用）
  selected_models?: string[] | null; // 优先使用的模型（首个视为默认）
}

export interface CapabilityRouteConfig {
  provider_id?: string | null;
  provider_ids?: string[] | null;  // 多服务商池（负载均衡模式）
  model?: string | null;
  timeout: number;
  enable_thinking?: boolean;
}

// 物种分化配置
export interface SpeciationConfig {
  // ========== 基础分化参数 ==========
  cooldown_turns?: number;              // 分化冷却期（回合数）
  species_soft_cap?: number;            // 物种密度软上限
  base_speciation_rate?: number;        // 基础分化概率（0-1）
  max_offspring_count?: number;         // 单次分化最大子种数量
  
  // ========== 直接后代数量限制 ==========
  max_direct_offspring?: number;        // 一个物种最多能分化出多少个直接后代
  count_only_alive_offspring?: boolean; // 是否只计算存活后代
  
  // ========== 早期分化优化 ==========
  early_game_turns?: number;            // 早期回合阈值
  early_threshold_min_factor?: number;  // 早期门槛折减系数最小值
  early_threshold_decay_rate?: number;  // 早期门槛折减速率
  early_skip_cooldown_turns?: number;   // 早期跳过冷却期的回合数
  
  // ========== 压力/资源触发阈值 ==========
  pressure_threshold_late?: number;     // 后期压力阈值
  pressure_threshold_early?: number;    // 早期压力阈值
  resource_threshold_late?: number;     // 后期资源阈值
  resource_threshold_early?: number;    // 早期资源阈值
  evo_potential_threshold_late?: number;   // 后期演化潜力阈值
  evo_potential_threshold_early?: number;  // 早期演化潜力阈值
  
  // ========== 种群数量门槛 ==========
  min_population_for_speciation?: number;   // 物种分化所需的最小种群数量
  min_offspring_population?: number;        // 新物种的最小种群数量
  background_speciation_penalty?: number;   // 背景物种分化概率惩罚系数（0-1）
  
  // ========== 候选地块筛选 ==========
  candidate_tile_min_pop?: number;          // 候选地块最小种群
  candidate_tile_death_rate_min?: number;   // 候选地块死亡率下限
  candidate_tile_death_rate_max?: number;   // 候选地块死亡率上限
  
  // ========== 辐射演化 ==========
  radiation_base_chance?: number;         // 辐射演化基础概率
  radiation_early_bonus?: number;         // 早期辐射演化额外加成
  radiation_pop_ratio_early?: number;     // 早期辐射演化种群比例要求
  radiation_pop_ratio_late?: number;      // 后期辐射演化种群比例要求
  radiation_max_chance_early?: number;    // 早期辐射演化概率上限
  radiation_max_chance_late?: number;     // 后期辐射演化概率上限
  no_isolation_penalty_early?: number;    // 早期无隔离惩罚系数
  no_isolation_penalty_late?: number;     // 后期无隔离惩罚系数
  
  // ========== 门槛乘数 ==========
  threshold_multiplier_no_isolation?: number;      // 无隔离时门槛乘数
  threshold_multiplier_high_overlap?: number;      // 高生态位重叠时门槛乘数
  threshold_multiplier_high_saturation?: number;   // 高资源饱和时门槛乘数
  
  // ========== 杂交参数 ==========
  auto_hybridization_chance?: number;   // 自动杂交检测概率
  hybridization_success_rate?: number;  // 杂交成功率
  max_hybrids_per_turn?: number;        // 每回合最多杂交数量
  max_hybrids_per_parent_per_turn?: number; // 单亲本每回合杂交子代上限
  min_population_for_hybridization?: number;  // 杂交所需的最小种群数量
  
  // ========== 灭绝阈值 ==========
  extinction_population_threshold?: number;  // 绝对灭绝阈值（种群低于此值直接灭绝）
  extinction_death_rate_threshold?: number;  // 死亡率灭绝阈值
  minimum_viable_population?: number;        // 最小可存活种群 (MVP)
  mvp_warning_turns?: number;                // MVP 警告回合数
  mvp_extinction_turns?: number;             // MVP 灭绝回合数
  competition_disadvantage_ratio?: number;   // 竞争劣势阈值（相对平均值比例）
  competition_extinction_ratio?: number;     // 竞争灭绝阈值
  inbreeding_depression_threshold?: number;  // 近交衰退阈值
  inbreeding_depression_coefficient?: number; // 近交衰退系数
  consecutive_decline_extinction_turns?: number; // 连续衰退灭绝回合数
  decline_detection_threshold?: number;      // 衰退检测阈值
}

/**
 * 繁殖配置 - 控制物种繁殖行为
 */
export interface ReproductionConfig {
  // 基础增长
  growth_rate_per_repro_speed?: number;  // 每点繁殖速度的增长率
  growth_multiplier_min?: number;        // 增长倍数下限
  growth_multiplier_max?: number;        // 增长倍数上限
  
  // 体型加成
  size_bonus_microbe?: number;           // 微生物加成
  size_bonus_tiny?: number;              // 小型生物加成
  size_bonus_small?: number;             // 中小型生物加成
  
  // 世代时间加成
  repro_bonus_weekly?: number;           // 极快繁殖加成
  repro_bonus_monthly?: number;          // 快速繁殖加成
  repro_bonus_halfyear?: number;         // 中速繁殖加成
  
  // 存活率修正
  survival_modifier_base?: number;       // 存活率修正基础
  survival_modifier_rate?: number;       // 存活率修正系数
  
  // 生存本能
  survival_instinct_threshold?: number;  // 激活阈值
  survival_instinct_bonus?: number;      // 最大加成
  
  // 资源压力
  resource_saturation_penalty_mild?: number;  // 饱和惩罚率
  resource_saturation_floor?: number;    // 最低效率
  
  // 承载力超载
  overshoot_decay_rate?: number;         // 衰减率
  near_capacity_efficiency?: number;     // 接近承载力效率
  
  // 营养级惩罚
  t2_birth_efficiency?: number;          // T2繁殖效率
  t3_birth_efficiency?: number;          // T3繁殖效率
  t4_birth_efficiency?: number;          // T4+繁殖效率
}

/**
 * 压力强度配置 - 控制玩家施加的环境压力强度
 */
export interface PressureIntensityConfig {
  // 压力类型倍率 (Tier Modifiers)
  tier1_multiplier?: number;  // 一阶压力（生态波动）倍率，默认 0.5
  tier2_multiplier?: number;  // 二阶压力（气候变迁）倍率，默认 0.7
  tier3_multiplier?: number;  // 三阶压力（天灾降临）倍率，默认 1.5
  
  // 强度滑块倍率 (Intensity Multipliers)
  intensity_low_multiplier?: number;   // 强度 1-3（轻微）倍率，默认 0.3
  intensity_mid_multiplier?: number;   // 强度 4-7（显著）倍率，默认 0.6
  intensity_high_multiplier?: number;  // 强度 8-10（毁灭性）倍率，默认 1.2
  
  // 温度修饰系数
  temperature_effect_per_unit?: number;  // 每单位温度修饰的效果（°C），默认 0.8
  
  // ============ 张量压力桥接参数 ============
  // 各因子基础死亡率
  thermal_multiplier?: number;         // 温度压力乘数（每单位压力=多少°C），默认 3.0
  toxin_base_mortality?: number;       // 毒性基础死亡率，默认 0.06
  drought_base_mortality?: number;     // 干旱基础死亡率，默认 0.05
  anoxic_base_mortality?: number;      // 缺氧基础死亡率，默认 0.08
  direct_mortality_rate?: number;      // 直接死亡率，默认 0.04
  radiation_base_mortality?: number;   // 辐射基础死亡率，默认 0.04
  
  // 特殊机制
  autotroph_toxin_benefit?: number;    // 化能自养生物在毒性环境中的受益系数，默认 0.15
  aerobe_sensitivity?: number;         // 需氧生物对缺氧的敏感度，默认 0.6
  multi_pressure_decay?: number;       // 多压力边际递减系数，默认 0.7
}

/**
 * 死亡率配置 - 控制物种死亡率计算
 */
export interface MortalityConfig {
  // 压力上限
  env_pressure_cap?: number;             // 环境压力上限
  competition_pressure_cap?: number;     // 竞争压力上限
  trophic_pressure_cap?: number;         // 营养级压力上限
  resource_pressure_cap?: number;        // 资源压力上限
  predation_pressure_cap?: number;       // 捕食网压力上限
  plant_competition_cap?: number;        // 植物竞争上限
  
  // 加权求和权重
  env_weight?: number;                   // 环境权重
  competition_weight?: number;           // 竞争权重
  trophic_weight?: number;               // 营养级权重
  resource_weight?: number;              // 资源权重
  predation_weight?: number;             // 捕食网权重
  plant_competition_weight?: number;     // 植物竞争权重
  
  // 乘法模型系数
  env_mult_coef?: number;
  competition_mult_coef?: number;
  trophic_mult_coef?: number;
  resource_mult_coef?: number;
  predation_mult_coef?: number;
  plant_mult_coef?: number;
  
  // 模型混合
  additive_model_weight?: number;        // 加权和占比
  
  // 抗性系数
  size_resistance_per_10cm?: number;     // 体型抗性
  generation_resistance_coef?: number;   // 世代抗性
  max_resistance?: number;               // 抗性上限
  
  // 死亡率边界
  min_mortality?: number;                // 最低死亡率
  max_mortality?: number;                // 最高死亡率
}

/**
 * 基因多样性配置 - 控制基于 Embedding 的基因多样性半径机制
 * 
 * 核心理念：
 * - 基因库 = 物种在 Embedding 空间中的"可演化范围"
 * - 已激活基因 = 当前 ecological_vector 的位置
 * - 休眠基因 = 向量周围的"可达区域"
 * - 基因多样性 = 可达区域的半径大小
 */
export interface GeneDiversityConfig {
  // ========== 基础参数 ==========
  min_radius?: number;                   // 最小基因多样性半径（保底演化能力）
  max_decay_per_turn?: number;           // 每回合最大衰减率
  activation_cost?: number;              // 激活休眠基因的半径消耗
  bottleneck_coefficient?: number;       // 瓶颈效应系数 k（衰减 = k / sqrt(pop) × 压力系数）
  recovery_threshold?: number;           // 瓶颈恢复种群阈值
  
  // ========== 杂交/发现加成 ==========
  hybrid_bonus_min?: number;             // 杂交半径提升最小值
  hybrid_bonus_max?: number;             // 杂交半径提升最大值
  discovery_bonus_min?: number;          // 新基因发现半径提升最小值
  discovery_bonus_max?: number;          // 新基因发现半径提升最大值
  
  // ========== 太古宙参数（<50回合）==========
  archean_initial_radius?: number;       // 太古宙初始半径
  archean_growth_rate?: number;          // 太古宙增长率/回合
  archean_inherit_min?: number;          // 太古宙分化继承系数最小值
  archean_inherit_max?: number;          // 太古宙分化继承系数最大值
  archean_mutation_chance?: number;      // 太古宙突变发现概率
  
  // ========== 元古宙参数（50-150回合）==========
  proterozoic_initial_radius?: number;   // 元古宙初始半径
  proterozoic_growth_rate?: number;      // 元古宙增长率/回合
  proterozoic_inherit_min?: number;      // 元古宙分化继承系数最小值
  proterozoic_inherit_max?: number;      // 元古宙分化继承系数最大值
  proterozoic_mutation_chance?: number;  // 元古宙突变发现概率
  
  // ========== 古生代及以后参数（>150回合）==========
  phanerozoic_initial_radius?: number;   // 古生代初始半径
  phanerozoic_growth_rate?: number;      // 古生代增长率/回合
  phanerozoic_inherit_min?: number;      // 古生代分化继承系数最小值
  phanerozoic_inherit_max?: number;      // 古生代分化继承系数最大值
  phanerozoic_mutation_chance?: number;  // 古生代突变发现概率
  
  // ========== 激活机制参数 ==========
  activation_chance_per_turn?: number;   // 每回合激活休眠基因的概率
  pressure_match_bonus?: number;         // 压力匹配时的激活加成倍数
  organ_discovery_chance?: number;       // 分化时发现新器官的概率
  activation_death_rate_threshold?: number;  // 激活所需的死亡率阈值
  activation_min_exposure?: number;      // 激活所需的最小暴露次数
  
  // ========== v3.0 基于环境压力的基因继承参数 ==========
  gene_loss_pressure_threshold?: number;     // 基因丢失开始的压力阈值
  gene_loss_rate_per_pressure?: number;      // 每单位压力增加的丢失率
  max_gene_loss_rate?: number;               // 最大基因丢失率上限
  pressure_match_retain_bonus?: number;      // 压力匹配保留率加成
  dominant_harmful_retain_factor?: number;   // 显性有害突变保留系数
  mildly_harmful_retain_factor?: number;     // 轻微有害突变保留系数
  organ_gene_stability_factor?: number;      // 器官基因稳定性系数

  // [DEPRECATED] 以下参数已废弃，保留用于兼容旧存档
  dormant_gene_inherit_chance?: number;      // [废弃] 分化时休眠基因继承概率
  max_inherit_traits_from_library?: number;  // [废弃] 从基因库继承最大特质数（已无上限）
  max_inherit_organs_from_library?: number;  // [废弃] 从基因库继承最大器官数（已无上限）
  
  // ========== v2.0 有害突变（遗传负荷）参数 ==========
  harmful_mutation_chance?: number;           // 新物种携带有害突变概率
  harmful_activation_penalty?: number;        // 有害突变激活概率倍数
  recessive_harmful_inherit_chance?: number;  // 隐性有害突变继承概率
  dominant_harmful_inherit_chance?: number;   // 显性有害突变继承概率
  de_novo_mutation_chance?: number;           // 子代新有害突变概率
  
  // ========== v2.0 显隐性遗传参数 ==========
  dominant_expression_factor?: number;        // 显性基因表达系数
  codominant_expression_factor?: number;      // 共显性基因表达系数
  recessive_expression_factor?: number;       // 隐性基因表达系数
  overdominant_expression_factor?: number;    // 超显性基因表达系数
  
  // ========== v2.0 器官渐进发育参数 ==========
  enable_organ_development?: boolean;         // 启用器官4阶段渐进发育
  organ_stage_0_turns?: number;               // 原基→初级发育回合数
  organ_stage_1_turns?: number;               // 初级→功能发育回合数
  organ_stage_2_turns?: number;               // 功能→成熟发育回合数
  organ_failure_chance_primordium?: number;   // 原基阶段发育失败概率
  organ_failure_chance_primitive?: number;    // 初级阶段发育失败概率
  organ_failure_chance_functional?: number;   // 功能阶段发育失败概率
  
  // ========== v2.0 基因连锁参数 ==========
  enable_gene_linkage?: boolean;              // 启用基因连锁效应
  linkage_activation_chance?: number;         // 连锁基因同时激活概率
  linkage_tradeoff_multiplier?: number;       // 连锁代价效果倍数
  
  // ========== v2.0 水平基因转移 (HGT) 参数 ==========
  enable_hgt?: boolean;                       // 启用水平基因转移（微生物）
  hgt_max_trophic_level?: number;             // HGT最大营养级
  hgt_base_chance?: number;                   // HGT基础概率/回合
  hgt_sympatric_bonus?: number;               // 同域物种HGT加成
  hgt_efficiency_min?: number;                // HGT转移效率下限
  hgt_efficiency_max?: number;                // HGT转移效率上限
  hgt_integration_stability?: number;         // HGT整合稳定概率
}

/**
 * 生态平衡配置 - 控制种群动态平衡的参数
 */
export interface EcologyBalanceConfig {
  // ========== 食物匮乏惩罚 ==========
  food_scarcity_threshold?: number;    // 猎物丰富度阈值
  food_scarcity_penalty?: number;      // 食物匮乏惩罚系数
  scarcity_weight?: number;            // 稀缺压力权重
  prey_search_top_k?: number;          // 消费者搜索猎物地块数
  
  // ========== 竞争强度 ==========
  competition_base_coefficient?: number;   // 基础竞争系数
  competition_per_species_cap?: number;    // 单个竞争者贡献上限
  competition_total_cap?: number;          // 总竞争压力上限
  same_level_competition_k?: number;       // 同级竞争系数
  niche_overlap_penalty_k?: number;        // 生态位重叠惩罚系数
  
  // ========== 营养传递效率 ==========
  trophic_transfer_efficiency?: number;    // 能量传递效率
  high_trophic_birth_penalty?: number;     // 高营养级出生效率惩罚
  apex_predator_penalty?: number;          // 顶级捕食者额外惩罚
  
  // ========== 扩散行为 ==========
  terrestrial_top_k?: number;              // 陆生物种分布地块数
  marine_top_k?: number;                   // 海洋物种分布地块数
  coastal_top_k?: number;                  // 海岸物种分布地块数
  aerial_top_k?: number;                   // 空中物种分布地块数
  suitability_cutoff?: number;             // 宜居度截断阈值
  suitability_weight_alpha?: number;       // 宜居度权重指数
  high_trophic_dispersal_damping?: number; // 高营养级扩散阻尼
  dispersal_cost_base?: number;            // 跨地块扩散基础成本
  migration_suitability_bias?: number;     // 迁移偏好：宜居度权重
  migration_prey_bias?: number;            // 迁移偏好：猎物权重
  habitat_recalc_frequency?: number;       // 栖息地重算频率
  
  // ========== 承载力 ==========
  carrying_capacity_base?: number;         // 承载力基础倍数
  carrying_capacity_variance?: number;     // 承载力波动范围
  
  // ========== 资源再生 ==========
  resource_recovery_rate?: number;         // 资源恢复速率
  resource_recovery_lag?: number;          // 资源恢复滞后
  resource_min_recovery?: number;          // 最小恢复率
  resource_capacity_multiplier?: number;   // 资源上限倍数
  
  // ========== 环境扰动 ==========
  resource_perturbation?: number;          // 资源扰动幅度
  climate_perturbation?: number;           // 气候扰动幅度
  environment_noise?: number;              // 环境噪声
  
  // ========== 防御/逃逸 ==========
  base_escape_rate?: number;               // 基础逃逸成功率
  size_advantage_factor?: number;          // 体型优势因子
  
  // ========== 世代更替（加速前代物种淘汰）==========
  lifespan_limit?: number;                 // 基因衰老阈值（回合）
  lifespan_decay_rate?: number;            // 衰老速率（每回合增加的死亡率）
  dead_end_threshold?: number;             // 进化死胡同阈值（回合）
  dead_end_penalty?: number;               // 进化死胡同惩罚
  obsolescence_penalty?: number;           // 亲代让位惩罚（有子代时）
  allee_threshold?: number;                // 阿利效应阈值（种群数量）
  
  // ========== 子代压制 ==========
  offspring_suppression_coefficient?: number;  // 子代压制系数
  parent_lag_penalty_turn0?: number;           // 亲代滞后惩罚T0
  parent_lag_penalty_turn1?: number;           // 亲代滞后惩罚T1
  parent_lag_penalty_turn2?: number;           // 亲代滞后惩罚T2
  
  // ========== 新物种优势 ==========
  enable_new_species_advantage?: boolean;      // 是否启用新物种优势
  new_species_advantage_turn0?: number;        // 新物种T0死亡率减免
  new_species_advantage_turn1?: number;        // 新物种T1死亡率减免
  new_species_advantage_turn2?: number;        // 新物种T2死亡率减免
}

/**
 * 游戏模式配置 - 控制整体游戏难度和风格
 */
export interface GameplayConfig {
  // 游戏模式
  game_mode?: "casual" | "balanced" | "hardcore" | "custom";
  
  // 难度系数
  mortality_multiplier?: number;           // 死亡率倍率
  competition_multiplier?: number;         // 竞争强度倍率
  reproduction_multiplier?: number;        // 繁殖效率倍率
  resource_abundance_multiplier?: number;  // 资源丰富度倍率
  
  // 显示选项
  show_prey_abundance?: boolean;           // 显示猎物丰富度
  show_food_score?: boolean;               // 显示食物分数
  show_competition_penalty?: boolean;      // 显示竞争惩罚
  show_mortality_breakdown?: boolean;      // 显示死亡率分解
  show_advanced_metrics?: boolean;         // 显示高级指标
}

/**
 * 地图环境配置 - 控制地块、气候和地理参数
 */
export interface MapEnvironmentConfig {
  // 气候偏移
  global_temperature_offset?: number;      // 全局温度偏移
  global_humidity_offset?: number;         // 全局湿度偏移
  extreme_climate_frequency?: number;      // 极端气候频率
  extreme_climate_amplitude?: number;      // 极端气候幅度
  
  // 海平面与地形
  sea_level_offset?: number;               // 海平面偏移
  sea_level_change_rate?: number;          // 海平面变化速率
  terrain_erosion_rate?: number;           // 地形侵蚀速率
  
  // 栖息地适宜度阈值
  coastal_temp_tolerance?: number;         // 海岸温度容差
  shallow_sea_salinity_tolerance?: number; // 浅海盐度容差
  freshwater_min_humidity?: number;        // 淡水湿度要求
  terrestrial_min_temp?: number;           // 陆生最低温度
  terrestrial_max_temp?: number;           // 陆生最高温度
  
  // 生物群系承载力倍数
  biome_capacity_rainforest?: number;      // 热带雨林
  biome_capacity_temperate?: number;       // 温带森林
  biome_capacity_grassland?: number;       // 草原
  biome_capacity_desert?: number;          // 沙漠
  biome_capacity_tundra?: number;          // 苔原
  biome_capacity_deep_sea?: number;        // 深海
  biome_capacity_shallow_sea?: number;     // 浅海
  
  // 地质/灾害事件
  volcano_frequency?: number;              // 火山频率
  volcano_impact_radius?: number;          // 火山影响半径
  volcano_damage_intensity?: number;       // 火山破坏强度
  flood_frequency?: number;                // 洪水频率
  flood_impact_radius?: number;            // 洪水影响范围
  drought_frequency?: number;              // 干旱频率
  drought_duration?: number;               // 干旱持续时间
  earthquake_frequency?: number;           // 地震频率
  
  // 密度与拥挤惩罚
  same_tile_density_penalty?: number;      // 同地块密度惩罚
  overcrowding_threshold?: number;         // 过度拥挤阈值
  overcrowding_max_penalty?: number;       // 拥挤惩罚上限
  
  // 地图视图叠加层
  show_resource_overlay?: boolean;         // 资源热力图
  show_prey_overlay?: boolean;             // 猎物丰度热力图
  show_suitability_overlay?: boolean;      // 宜居度热力图
  show_competition_overlay?: boolean;      // 竞争压力热力图
  show_temperature_overlay?: boolean;      // 温度分布
  show_humidity_overlay?: boolean;         // 湿度分布
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
  embedding_concurrency_enabled?: boolean;
  embedding_concurrency_limit?: number;
  embedding_semantic_hotspot_only?: boolean;
  embedding_semantic_hotspot_limit?: number;
  
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
  ai_narrative_enabled?: boolean;     // 是否启用 AI 生成物种叙事（默认开启）
  
  // 9. 回合报告 LLM 开关（与物种叙事分开）
  turn_report_llm_enabled?: boolean;  // 是否启用 LLM 生成回合总结（默认开启）
  
  // 10. 物种分化配置
  speciation?: SpeciationConfig;
  
  // 11. 生态平衡配置
  ecology_balance?: EcologyBalanceConfig;
  
  // 12. 繁殖配置
  reproduction?: ReproductionConfig;
  
  // 13. 死亡率配置
  mortality?: MortalityConfig;
  
  // 14. 压力强度配置
  pressure_intensity?: PressureIntensityConfig;
  
  // 15. 游戏模式配置
  gameplay?: GameplayConfig;
  
  // 15. 地图环境配置
  map_environment?: MapEnvironmentConfig;
  
  // 16. 基因多样性配置
  gene_diversity?: GeneDiversityConfig;

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
  tier: number;
  base_cost: number;
  narrative_template?: string; // Optional template for the description
  default_intensity?: number; // Optional default intensity
}
// 显隐性类型
export type DominanceType = 'recessive' | 'codominant' | 'dominant' | 'overdominant';

// 突变效果类型
export type MutationEffect = 'beneficial' | 'neutral' | 'mildly_harmful' | 'harmful' | 'lethal';

// 器官发育阶段
export type OrganStage = 0 | 1 | 2 | 3; // 0=原基, 1=初级, 2=功能, 3=成熟

// 休眠基因数据结构 v2.0
export interface DormantGeneData {
  potential_value?: number;         // 特质潜力值 (0-15)
  organ_data?: {                    // 器官数据
    category: string;
    type: string;
    parameters: Record<string, number>;
  };
  pressure_types?: string[];        // 触发压力类型
  exposure_count?: number;          // 暴露次数
  max_death_rate?: number;          // 最大死亡率
  activated: boolean;               // 是否已激活
  activated_turn?: number | null;   // 激活回合
  
  // v2.0 新增字段
  dominance?: DominanceType;        // 显隐性类型
  mutation_effect?: MutationEffect; // 突变效果（有益/中性/有害）
  target_trait?: string;            // 有害突变的目标特质
  value_modifier?: number;          // 有害突变的数值修正
  description?: string;             // 基因描述
  inherited_from?: string;          // 来源（initial/ecological/mutation/hgt）
  expressed_value?: number;         // 实际表达值（受显隐性影响）
  
  // 器官发育阶段（渐进发育系统）
  development_stage?: OrganStage | null;  // 发育阶段 (null=未开始)
  stage_start_turn?: number | null;       // 当前阶段开始回合
}

export interface DormantGenes {
  traits: Record<string, DormantGeneData>;
  organs: Record<string, DormantGeneData>;
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
  gene_diversity_radius?: number;
  gene_stability?: number;
  explored_directions?: number[];
  // 休眠基因
  dormant_genes?: DormantGenes;
  stress_exposure?: Record<string, { count: number; max_death_rate: number }>;
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