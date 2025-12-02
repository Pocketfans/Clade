/**
 * SettingsDrawer 常量定义
 */

import type { ProviderType, SpeciationConfig, ReproductionConfig, MortalityConfig, EcologyBalanceConfig, MapEnvironmentConfig } from "@/services/api.types";
import type { CapabilityDef, ProviderPreset } from "./types";

// ============ API 类型 ============
export const PROVIDER_API_TYPES: { value: ProviderType; label: string; desc: string }[] = [
  { value: "openai", label: "OpenAI 兼容", desc: "适用于 OpenAI、DeepSeek、硅基流动等" },
  { value: "anthropic", label: "Claude 原生", desc: "Anthropic Claude 官方 API" },
  { value: "google", label: "Gemini 原生", desc: "Google Gemini 官方 API" },
];

// ============ 服务商预设 ============
export const PROVIDER_PRESETS: readonly ProviderPreset[] = [
  // OpenAI 兼容格式
  {
    id: "deepseek_official",
    name: "DeepSeek",
    provider_type: "openai",
    base_url: "https://api.deepseek.com/v1",
    description: "DeepSeek 官方 API",
    models: [],
    logo: "🔮",
    color: "#6366f1",
    category: "openai",
  },
  {
    id: "siliconflow",
    name: "硅基流动",
    provider_type: "openai",
    base_url: "https://api.siliconflow.cn/v1",
    description: "硅基流动 API，支持思维链",
    models: [],
    logo: "⚡",
    color: "#f59e0b",
    supportsThinking: true,
    category: "openai",
  },
  {
    id: "volcengine",
    name: "火山引擎（豆包）",
    provider_type: "openai",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    description: "火山引擎 API，需填写端点ID作为模型名",
    models: [],
    logo: "🌋",
    color: "#ef4444",
    supportsThinking: true,
    category: "openai",
  },
  {
    id: "openai_official",
    name: "OpenAI",
    provider_type: "openai",
    base_url: "https://api.openai.com/v1",
    description: "OpenAI 官方 API",
    models: [],
    logo: "🤖",
    color: "#10b981",
    category: "openai",
  },
  // Claude 原生 API
  {
    id: "claude_official",
    name: "Claude",
    provider_type: "anthropic",
    base_url: "https://api.anthropic.com/v1",
    description: "Anthropic Claude 官方 API",
    models: [],
    logo: "🎭",
    color: "#d97706",
    category: "anthropic",
  },
  // Gemini 原生 API
  {
    id: "gemini_official",
    name: "Gemini",
    provider_type: "google",
    base_url: "https://generativelanguage.googleapis.com/v1beta",
    description: "Google Gemini 官方 API",
    models: [],
    logo: "💎",
    color: "#3b82f6",
    category: "google",
  },
  // 聚合服务
  {
    id: "openrouter",
    name: "OpenRouter",
    provider_type: "openai",
    base_url: "https://openrouter.ai/api/v1",
    description: "聚合 API，一个 Key 访问多种模型",
    models: [],
    logo: "🔀",
    color: "#8b5cf6",
    category: "openai",
  },
];

// ============ AI 能力定义 ============
export const AI_CAPABILITIES: Record<string, CapabilityDef[]> = {
  core: [
    { key: "turn_report", label: "回合报告", desc: "生成每回合的整体生态演化总结", defaultTimeout: 120, parallel: "single", parallelNote: "流式输出，无需并行" },
    { key: "focus_batch", label: "重点批次", desc: "关键物种分块并行处理（max_concurrent=3）", defaultTimeout: 90, parallel: "batch", parallelNote: "staggered_gather 分块并行" },
    { key: "critical_detail", label: "关键分析", desc: "分析濒危或优势物种的详细状态", defaultTimeout: 90, parallel: "concurrent", parallelNote: "多物种并发评估" },
  ],
  speciation: [
    { key: "speciation", label: "物种分化", desc: "单物种分化判定，回合内多物种并发", defaultTimeout: 60, parallel: "concurrent", parallelNote: "staggered_gather 并发控制" },
    { key: "speciation_batch", label: "批量分化", desc: "同批多物种一次请求处理", defaultTimeout: 90, parallel: "batch", parallelNote: "批量接口，高并发场景" },
    { key: "plant_speciation", label: "植物分化", desc: "植物专用分化，支持批量模式", defaultTimeout: 60, parallel: "batch", parallelNote: "植物批量分化" },
    { key: "species_generation", label: "物种生成", desc: "生成初始物种或新物种的属性", defaultTimeout: 60, parallel: "single" },
  ],
  narrative: [
    { key: "pressure_adaptation", label: "压力适应", desc: "多物种并行评估适应能力", defaultTimeout: 60, parallel: "concurrent", parallelNote: "staggered_gather 带并发上限" },
    { key: "species_status_eval", label: "状态评估", desc: "分批并行评估，单个超时有fallback", defaultTimeout: 60, parallel: "batch", parallelNote: "批量评估接口" },
    { key: "species_narrative", label: "物种叙事", desc: "批量组装提示并并行请求", defaultTimeout: 60, parallel: "batch", parallelNote: "staggered_gather 批量叙事" },
    { key: "narrative", label: "描述重写", desc: "多物种并行执行描述更新", defaultTimeout: 45, parallel: "concurrent", parallelNote: "staggered_gather 并发" },
  ],
  advanced: [
    { key: "hybridization", label: "自然杂交", desc: "回合内多组杂交并发执行", defaultTimeout: 60, parallel: "concurrent", parallelNote: "并发杂交判定" },
    { key: "forced_hybridization", label: "强制杂交", desc: "玩家触发的杂交事件判定", defaultTimeout: 60, parallel: "single" },
    { key: "biological_assessment_a", label: "智能体A档", desc: "生态智能体高精度评估，A/B可并行", defaultTimeout: 90, parallel: "batch", parallelNote: "A/B两批可并行gather" },
    { key: "biological_assessment_b", label: "智能体B档", desc: "生态智能体快速评估，与A档并行", defaultTimeout: 60, parallel: "batch", parallelNote: "A/B两批可并行gather" },
  ],
};

export const ALL_CAPABILITIES: CapabilityDef[] = [
  ...AI_CAPABILITIES.core,
  ...AI_CAPABILITIES.speciation,
  ...AI_CAPABILITIES.narrative,
  ...AI_CAPABILITIES.advanced,
];

// 简化版能力定义（用于模型路由）
export const CAPABILITY_DEFS: CapabilityDef[] = ALL_CAPABILITIES;

// ============ Embedding 预设 ============
export const EMBEDDING_PRESETS = [
  { id: "qwen3", name: "Qwen/Qwen3-Embedding-4B", dimensions: 4096 },
  { id: "bge-m3", name: "BAAI/bge-m3", dimensions: 1024 },
  { id: "text-embedding-3-small", name: "text-embedding-3-small", dimensions: 1536 },
];

// ============ 默认配置 ============

export const DEFAULT_SPECIATION_CONFIG: SpeciationConfig = {
  cooldown_turns: 0,
  species_soft_cap: 60,
  base_speciation_rate: 0.5,
  max_offspring_count: 6,
  early_game_turns: 10,
  early_threshold_min_factor: 0.3,
  early_threshold_decay_rate: 0.07,
  early_skip_cooldown_turns: 5,
  pressure_threshold_late: 0.7,
  pressure_threshold_early: 0.4,
  resource_threshold_late: 0.6,
  resource_threshold_early: 0.35,
  evo_potential_threshold_late: 0.7,
  evo_potential_threshold_early: 0.5,
  candidate_tile_min_pop: 50,
  candidate_tile_death_rate_min: 0.02,
  candidate_tile_death_rate_max: 0.75,
  radiation_base_chance: 0.05,
  radiation_early_bonus: 0.15,
  radiation_pop_ratio_early: 1.2,
  radiation_pop_ratio_late: 1.5,
  radiation_max_chance_early: 0.35,
  radiation_max_chance_late: 0.25,
  no_isolation_penalty_early: 0.8,
  no_isolation_penalty_late: 0.5,
  threshold_multiplier_no_isolation: 1.8,
  threshold_multiplier_high_overlap: 1.2,
  threshold_multiplier_high_saturation: 1.2,
};

export const DEFAULT_REPRODUCTION_CONFIG: ReproductionConfig = {
  growth_rate_per_repro_speed: 0.35,
  growth_multiplier_min: 0.5,
  growth_multiplier_max: 8.0,
  size_bonus_microbe: 1.6,
  size_bonus_tiny: 1.3,
  size_bonus_small: 1.1,
  repro_bonus_weekly: 1.5,
  repro_bonus_monthly: 1.25,
  repro_bonus_halfyear: 1.1,
  survival_modifier_base: 0.3,
  survival_modifier_rate: 1.0,
  survival_instinct_threshold: 0.6,
  survival_instinct_bonus: 0.4,
  resource_saturation_penalty_mild: 0.5,
  resource_saturation_floor: 0.15,
  overshoot_decay_rate: 0.35,
  near_capacity_efficiency: 0.5,
  t2_birth_efficiency: 0.85,
  t3_birth_efficiency: 0.60,
  t4_birth_efficiency: 0.40,
};

export const DEFAULT_MORTALITY_CONFIG: MortalityConfig = {
  env_pressure_cap: 0.70,
  competition_pressure_cap: 0.45,
  trophic_pressure_cap: 0.50,
  resource_pressure_cap: 0.45,
  predation_pressure_cap: 0.55,
  plant_competition_cap: 0.35,
  env_weight: 0.55,
  competition_weight: 0.30,
  trophic_weight: 0.40,
  resource_weight: 0.35,
  predation_weight: 0.35,
  plant_competition_weight: 0.25,
  env_mult_coef: 0.65,
  competition_mult_coef: 0.50,
  trophic_mult_coef: 0.60,
  resource_mult_coef: 0.50,
  predation_mult_coef: 0.60,
  plant_mult_coef: 0.40,
  additive_model_weight: 0.55,
  size_resistance_per_10cm: 0.015,
  generation_resistance_coef: 0.04,
  max_resistance: 0.18,
  min_mortality: 0.03,
  max_mortality: 0.92,
};

export const DEFAULT_ECOLOGY_BALANCE_CONFIG: EcologyBalanceConfig = {
  food_scarcity_threshold: 0.3,
  food_scarcity_penalty: 0.4,
  scarcity_weight: 0.5,
  prey_search_top_k: 5,
  competition_base_coefficient: 0.60,
  competition_per_species_cap: 0.35,
  competition_total_cap: 0.80,
  same_level_competition_k: 0.15,
  niche_overlap_penalty_k: 0.20,
  trophic_transfer_efficiency: 0.15,
  high_trophic_birth_penalty: 0.7,
  apex_predator_penalty: 0.5,
  terrestrial_top_k: 4,
  marine_top_k: 3,
  coastal_top_k: 3,
  aerial_top_k: 5,
  suitability_cutoff: 0.25,
  suitability_weight_alpha: 1.5,
  high_trophic_dispersal_damping: 0.7,
  dispersal_cost_base: 0.1,
  migration_suitability_bias: 0.6,
  migration_prey_bias: 0.3,
  habitat_recalc_frequency: 1,
  carrying_capacity_base: 1.0,
  carrying_capacity_variance: 0.1,
  resource_recovery_rate: 0.15,
  resource_recovery_lag: 1,
  resource_min_recovery: 0.05,
  resource_capacity_multiplier: 1.0,
  resource_perturbation: 0.05,
  climate_perturbation: 0.02,
  environment_noise: 0.03,
  base_escape_rate: 0.3,
  size_advantage_factor: 0.1,
};

export const DEFAULT_MAP_ENVIRONMENT_CONFIG: MapEnvironmentConfig = {
  global_temperature_offset: 0.0,
  global_humidity_offset: 0.0,
  extreme_climate_frequency: 0.05,
  extreme_climate_amplitude: 0.3,
  sea_level_offset: 0.0,
  sea_level_change_rate: 0.0,
  terrain_erosion_rate: 0.01,
  coastal_temp_tolerance: 15.0,
  shallow_sea_salinity_tolerance: 0.8,
  freshwater_min_humidity: 0.5,
  terrestrial_min_temp: -20.0,
  terrestrial_max_temp: 50.0,
  biome_capacity_rainforest: 1.5,
  biome_capacity_temperate: 1.2,
  biome_capacity_grassland: 1.0,
  biome_capacity_desert: 0.3,
  biome_capacity_tundra: 0.4,
  biome_capacity_deep_sea: 0.5,
  biome_capacity_shallow_sea: 1.3,
  volcano_frequency: 0.02,
  volcano_impact_radius: 3,
  volcano_damage_intensity: 0.8,
  flood_frequency: 0.03,
  flood_impact_radius: 2,
  drought_frequency: 0.04,
  drought_duration: 2,
  earthquake_frequency: 0.01,
  same_tile_density_penalty: 0.15,
  overcrowding_threshold: 0.7,
  overcrowding_max_penalty: 0.4,
  show_resource_overlay: false,
  show_prey_overlay: false,
  show_suitability_overlay: false,
  show_competition_overlay: false,
  show_temperature_overlay: false,
  show_humidity_overlay: false,
};

