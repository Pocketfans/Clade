from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 服务商 API 类型常量
PROVIDER_TYPE_OPENAI = "openai"       # OpenAI 兼容格式（包括DeepSeek、硅基流动等）
PROVIDER_TYPE_ANTHROPIC = "anthropic"  # Claude 原生 API
PROVIDER_TYPE_GOOGLE = "google"        # Gemini 原生 API


class ProviderConfig(BaseModel):
    """AI 服务商配置"""
    model_config = ConfigDict(extra="ignore")
    
    id: str  # 唯一标识符，如 "provider_123" 或 "openai_main"
    name: str # 显示名称，如 "My OpenAI"
    type: str = "openai"  # 兼容旧字段，实际使用 provider_type
    provider_type: str = PROVIDER_TYPE_OPENAI  # API 类型：openai, anthropic, google
    base_url: str | None = None
    api_key: str | None = None
    
    # 预设模型列表（可选，用于前端自动补全）
    models: list[str] = []
    # 用户选择保存的模型列表
    selected_models: list[str] = []


class CapabilityRouteConfig(BaseModel):
    """功能路由配置"""
    model_config = ConfigDict(extra="ignore")
    
    provider_id: str | None = None  # 引用 ProviderConfig.id（单服务商模式）
    provider_ids: list[str] | None = None  # 多服务商池（负载均衡模式）
    model: str | None = None        # 具体模型名称
    timeout: int = 60
    enable_thinking: bool = False   # 是否开启思考模式（如DeepSeek-R1/SiliconFlow）


class SpeciationConfig(BaseModel):
    """物种分化配置 - 控制分化行为的所有参数"""
    model_config = ConfigDict(extra="ignore")
    
    # ========== 基础分化参数 ==========
    # 分化冷却期（回合数）：分化后多少回合内不能再次分化
    cooldown_turns: int = 0
    # 物种密度软上限：超过此数量后分化概率开始衰减
    species_soft_cap: int = 60
    # 基础分化概率（0-1）
    base_speciation_rate: float = 0.50
    # 最大子种数量
    max_offspring_count: int = 6
    
    # ========== 早期分化优化 ==========
    # 早期回合阈值：低于此回合数时使用更宽松的条件
    early_game_turns: int = 10
    # 早期门槛折减系数的最小值（0.3 = 最低降到 30%）
    early_threshold_min_factor: float = 0.3
    # 早期门槛折减速率（每回合降低多少）
    early_threshold_decay_rate: float = 0.07
    # 早期跳过冷却期的回合数
    early_skip_cooldown_turns: int = 5
    
    # ========== 压力/资源触发阈值 ==========
    # 后期压力阈值
    pressure_threshold_late: float = 0.7
    # 早期压力阈值
    pressure_threshold_early: float = 0.4
    # 后期资源阈值
    resource_threshold_late: float = 0.6
    # 早期资源阈值
    resource_threshold_early: float = 0.35
    # 后期演化潜力阈值
    evo_potential_threshold_late: float = 0.7
    # 早期演化潜力阈值
    evo_potential_threshold_early: float = 0.5
    
    # ========== 候选地块筛选 ==========
    # 候选地块最小种群
    candidate_tile_min_pop: int = 50
    # 候选地块死亡率下限
    candidate_tile_death_rate_min: float = 0.02
    # 候选地块死亡率上限
    candidate_tile_death_rate_max: float = 0.75
    
    # ========== 辐射演化 ==========
    # 辐射演化基础概率
    radiation_base_chance: float = 0.05
    # 早期辐射演化额外加成
    radiation_early_bonus: float = 0.15
    # 早期辐射演化种群比例要求
    radiation_pop_ratio_early: float = 1.2
    # 后期辐射演化种群比例要求
    radiation_pop_ratio_late: float = 1.5
    # 早期辐射演化概率上限
    radiation_max_chance_early: float = 0.35
    # 后期辐射演化概率上限
    radiation_max_chance_late: float = 0.25
    # 早期无隔离惩罚系数
    no_isolation_penalty_early: float = 0.8
    # 后期无隔离惩罚系数
    no_isolation_penalty_late: float = 0.5
    
    # ========== 门槛乘数 ==========
    # 无隔离时门槛乘数
    threshold_multiplier_no_isolation: float = 1.8
    # 高生态位重叠时门槛乘数
    threshold_multiplier_high_overlap: float = 1.2
    # 高资源饱和时门槛乘数（无隔离情况下）
    threshold_multiplier_high_saturation: float = 1.2


class ReproductionConfig(BaseModel):
    """繁殖配置 - 控制物种繁殖行为的参数
    
    【设计理念】
    - 基础增长率由繁殖速度属性决定
    - 体型和世代时间提供额外加成
    - 高营养级受能量传递效率限制
    - 生存本能在危机时提高繁殖效率
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 基础增长 ==========
    # 每点繁殖速度提供的增长率加成
    growth_rate_per_repro_speed: float = 0.4
    # 增长倍数下限（保护濒危物种）
    growth_multiplier_min: float = 0.6
    # 增长倍数上限（限制爆发）
    growth_multiplier_max: float = 15.0
    
    # ========== 体型加成 ==========
    # 微生物（<0.1mm）增长加成
    size_bonus_microbe: float = 2.0
    # 小型生物（0.1mm-1mm）增长加成
    size_bonus_tiny: float = 1.5
    # 中小型生物（1mm-1cm）增长加成
    size_bonus_small: float = 1.2
    
    # ========== 世代时间加成 ==========
    # 极快繁殖（<1周）加成
    repro_bonus_weekly: float = 1.8
    # 快速繁殖（<1月）加成
    repro_bonus_monthly: float = 1.4
    # 中速繁殖（<半年）加成
    repro_bonus_halfyear: float = 1.2
    
    # ========== 存活率修正 ==========
    # 存活率修正基础值
    survival_modifier_base: float = 0.4
    # 存活率修正系数
    survival_modifier_rate: float = 1.2
    
    # ========== 生存本能 ==========
    # 生存本能激活阈值（死亡率超过此值）
    survival_instinct_threshold: float = 0.5
    # 生存本能最大加成
    survival_instinct_bonus: float = 0.8
    
    # ========== 资源压力 ==========
    # 资源饱和时的惩罚率（饱和度1.0-2.0区间）
    resource_saturation_penalty_mild: float = 0.4
    # 资源严重不足时的最低效率
    resource_saturation_floor: float = 0.2
    
    # ========== 承载力超载 ==========
    # 超载时的衰减率
    overshoot_decay_rate: float = 0.25
    # 接近承载力时的增长效率
    near_capacity_efficiency: float = 0.6
    
    # ========== 营养级惩罚 ==========
    # T2 初级消费者繁殖效率
    t2_birth_efficiency: float = 0.9
    # T3 高级消费者繁殖效率
    t3_birth_efficiency: float = 0.7
    # T4+ 顶级捕食者繁殖效率
    t4_birth_efficiency: float = 0.5


class MortalityConfig(BaseModel):
    """死亡率配置 - 控制物种死亡率计算的参数
    
    【设计理念】
    - 多种压力源叠加计算死亡率
    - 各压力有独立上限避免极端值
    - 抗性机制降低压力影响
    - 权重系统平衡各因素贡献
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 压力上限 ==========
    # 环境压力上限
    env_pressure_cap: float = 0.50
    # 竞争压力上限
    competition_pressure_cap: float = 0.40
    # 营养级压力上限（捕食/被捕食）
    trophic_pressure_cap: float = 0.45
    # 资源压力上限
    resource_pressure_cap: float = 0.40
    # 捕食网压力上限
    predation_pressure_cap: float = 0.50
    # 植物竞争压力上限
    plant_competition_cap: float = 0.30
    
    # ========== 加权求和权重 ==========
    # 环境压力权重
    env_weight: float = 0.40
    # 竞争压力权重
    competition_weight: float = 0.30
    # 营养级压力权重
    trophic_weight: float = 0.40
    # 资源压力权重
    resource_weight: float = 0.35
    # 捕食网压力权重
    predation_weight: float = 0.35
    # 植物竞争权重
    plant_competition_weight: float = 0.25
    
    # ========== 乘法模型系数 ==========
    # 环境压力乘法系数
    env_mult_coef: float = 0.50
    # 竞争压力乘法系数
    competition_mult_coef: float = 0.45
    # 营养级压力乘法系数
    trophic_mult_coef: float = 0.55
    # 资源压力乘法系数
    resource_mult_coef: float = 0.45
    # 捕食网压力乘法系数
    predation_mult_coef: float = 0.55
    # 植物竞争乘法系数
    plant_mult_coef: float = 0.35
    
    # ========== 模型混合 ==========
    # 加权和模型占比（乘法模型占1-此值）
    additive_model_weight: float = 0.70
    
    # ========== 抗性系数 ==========
    # 体型抗性系数（每10cm体长的抗性）
    size_resistance_per_10cm: float = 0.02
    # 世代时间抗性系数
    generation_resistance_coef: float = 0.05
    # 最大抗性上限
    max_resistance: float = 0.25
    
    # ========== 死亡率边界 ==========
    # 最低死亡率（保证自然死亡）
    min_mortality: float = 0.02
    # 最高死亡率上限
    max_mortality: float = 0.95


class EcologyBalanceConfig(BaseModel):
    """生态平衡配置 - 控制种群动态平衡的所有参数
    
    【设计理念】
    通过调整这些参数可以控制生态系统的稳定性：
    - 食物匮乏惩罚：消费者在猎物稀缺时死亡率上升
    - 竞争强度：同生态位物种之间的竞争压力
    - 营养传递效率：限制高营养级总量
    - 扩散行为：控制物种分布范围
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 食物匮乏惩罚 ==========
    # 猎物丰富度阈值：低于此值开始惩罚
    food_scarcity_threshold: float = 0.3
    # 食物匮乏惩罚系数：death_rate += penalty * (threshold - abundance)
    food_scarcity_penalty: float = 0.4
    # 稀缺压力在死亡率中的权重
    scarcity_weight: float = 0.5
    
    # ========== 竞争强度 ==========
    # 基础竞争系数（相似度 × 营养级系数 × 此值）
    competition_base_coefficient: float = 0.60
    # 单个竞争者贡献上限
    competition_per_species_cap: float = 0.35
    # 总竞争压力上限
    competition_total_cap: float = 0.80
    # 同级竞争系数（同营养级物种之间）
    same_level_competition_k: float = 0.15
    
    # ========== 营养传递效率 ==========
    # 能量传递效率（10%规则）：每升一个营养级，可用能量降至此比例
    trophic_transfer_efficiency: float = 0.15
    # 高营养级出生效率惩罚（T3+）- 已移至 ReproductionConfig
    high_trophic_birth_penalty: float = 0.7
    # 顶级捕食者（T4+）额外效率惩罚 - 已移至 ReproductionConfig
    apex_predator_penalty: float = 0.5
    
    # ========== 扩散行为 ==========
    # 陆生物种分布地块数上限
    terrestrial_top_k: int = 4
    # 海洋物种分布地块数上限
    marine_top_k: int = 3
    # 宜居度阈值：低于此值的地块不分配种群
    suitability_cutoff: float = 0.25
    # 宜居度权重指数：pow(suitability, alpha)，alpha>1 更集中
    suitability_weight_alpha: float = 1.5
    # 高营养级扩散阻尼（跨地块成本）
    high_trophic_dispersal_damping: float = 0.7
    
    # ========== 资源再生 ==========
    # 资源最大恢复速率（logistic r）
    resource_recovery_rate: float = 0.15
    # 资源恢复滞后回合数
    resource_recovery_lag: int = 1
    # 过度消耗后的最小恢复率
    resource_min_recovery: float = 0.05
    
    # ========== 环境扰动 ==========
    # 资源随机扰动幅度
    resource_perturbation: float = 0.05
    # 气候随机扰动幅度
    climate_perturbation: float = 0.02
    
    # ========== 防御/逃逸 ==========
    # 基础逃逸成功率（猎物默认）
    base_escape_rate: float = 0.3
    # 体型差异对捕食成功率的影响
    size_advantage_factor: float = 0.1


class UIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 1. 服务商库 (Provider Library)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    
    # 2. 全局默认设置
    default_provider_id: str | None = None
    default_model: str | None = None
    ai_concurrency_limit: int = 15  # AI 并发限制
    
    # 3. 功能路由表 (Routing Table)
    # Key: capability_name (e.g., "turn_report", "speciation")
    capability_routes: dict[str, CapabilityRouteConfig] = Field(default_factory=dict)
    
    # 4. Embedding 配置
    embedding_provider_id: str | None = None
    embedding_model: str | None = None
    
    # 5. 自动保存配置
    autosave_enabled: bool = True  # 是否启用自动保存
    autosave_interval: int = 1     # 每N回合自动保存一次
    autosave_max_slots: int = 5    # 最大自动保存槽位数
    
    # 6. AI 推演超时配置
    ai_species_eval_timeout: int = 60    # 单物种AI评估超时（秒）
    ai_batch_eval_timeout: int = 180     # 整体批量评估超时（秒）
    ai_narrative_timeout: int = 60       # 物种叙事生成超时（秒）
    ai_speciation_timeout: int = 120     # 物种分化评估超时（秒）
    
    # 7. 负载均衡配置
    load_balance_enabled: bool = False   # 是否启用多服务商负载均衡
    load_balance_strategy: str = "round_robin"  # 负载均衡策略: round_robin, random, least_latency
    
    # 8. AI 叙事开关
    ai_narrative_enabled: bool = False   # 是否启用 AI 生成物种叙事（默认关闭，节省 API 调用）
    
    # 9. 回合报告 LLM 开关（与物种叙事分开）
    turn_report_llm_enabled: bool = True  # 是否启用 LLM 生成回合总结（默认开启）
    
    # 10. 物种分化配置
    speciation: SpeciationConfig = Field(default_factory=SpeciationConfig)
    
    # 11. 生态平衡配置
    ecology_balance: EcologyBalanceConfig = Field(default_factory=EcologyBalanceConfig)
    
    # 12. 繁殖配置
    reproduction: ReproductionConfig = Field(default_factory=ReproductionConfig)
    
    # 13. 死亡率配置
    mortality: MortalityConfig = Field(default_factory=MortalityConfig)
    
    # --- Legacy Fields (Keep for migration) ---
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_timeout: int = 60
    # 旧版 capability_configs (dict[str, CapabilityModelConfig])
    capability_configs: dict | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
