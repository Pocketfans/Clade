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
    cooldown_turns: int = 3
    # 物种密度软上限：超过此数量后分化概率开始衰减
    species_soft_cap: int = 80
    # 基础分化概率（0-1）- 降低以减缓分化速度
    base_speciation_rate: float = 0.20
    # 单次分化最大子种数量（每次分化产生的后代数）
    max_offspring_count: int = 2
    
    # ========== 直接后代数量限制 ==========
    # 一个物种最多能分化出多少个直接后代
    # 只有当所有后代都灭绝后，才能再次分化
    max_direct_offspring: int = 3
    # 是否只计算存活后代（true=只计存活，false=计算所有历史后代）
    count_only_alive_offspring: bool = True
    
    # ========== 早期分化优化 ==========
    # 早期回合阈值：低于此回合数时使用更宽松的条件
    early_game_turns: int = 15
    # 早期门槛折减系数的最小值（0.5 = 最低降到 50%，不要太宽松）
    early_threshold_min_factor: float = 0.5
    # 早期门槛折减速率（每回合降低多少，降低折减速度）
    early_threshold_decay_rate: float = 0.03
    # 早期跳过冷却期的回合数（只有前2回合跳过冷却）
    early_skip_cooldown_turns: int = 2
    
    # ========== 压力/资源触发阈值 ==========
    # 后期压力阈值
    pressure_threshold_late: float = 0.35
    # 早期压力阈值
    pressure_threshold_early: float = 0.20
    # 后期资源阈值
    resource_threshold_late: float = 0.30
    # 早期资源阈值
    resource_threshold_early: float = 0.18
    # 后期演化潜力阈值
    evo_potential_threshold_late: float = 0.40
    # 早期演化潜力阈值
    evo_potential_threshold_early: float = 0.25
    
    # ========== 候选地块筛选 ==========
    # 候选地块最小种群
    candidate_tile_min_pop: int = 50
    # 候选地块死亡率下限
    candidate_tile_death_rate_min: float = 0.05
    # 候选地块死亡率上限
    candidate_tile_death_rate_max: float = 0.75
    
    # ========== 辐射演化 ==========
    # 辐射演化基础概率
    radiation_base_chance: float = 0.08
    # 早期辐射演化额外加成
    radiation_early_bonus: float = 0.12
    # 早期辐射演化种群比例要求
    radiation_pop_ratio_early: float = 1.2
    # 后期辐射演化种群比例要求
    radiation_pop_ratio_late: float = 1.5
    # 早期辐射演化概率上限
    radiation_max_chance_early: float = 0.25
    # 后期辐射演化概率上限
    radiation_max_chance_late: float = 0.15
    # 早期无隔离惩罚系数
    no_isolation_penalty_early: float = 0.70
    # 后期无隔离惩罚系数
    no_isolation_penalty_late: float = 0.50
    
    # ========== 门槛乘数 ==========
    # 无隔离时门槛乘数
    threshold_multiplier_no_isolation: float = 1.3
    # 高生态位重叠时门槛乘数
    threshold_multiplier_high_overlap: float = 1.15
    # 高资源饱和时门槛乘数
    threshold_multiplier_high_saturation: float = 1.1
    
    # ========== 种群数量门槛（按生物量 kg 计算）==========
    # 物种分化所需的最小生物量（低于此值不允许分化）
    # 考虑到开局物种通常在 20k-200k kg，几回合后达到百万级
    # 设为 100,000 kg (10万) 确保只有较大规模的种群才能分化
    min_population_for_speciation: int = 100000
    # 新物种的最小生物量（分化后子物种生物量不能低于此值）
    # 设为 20,000 kg (2万) 确保新物种有足够的初始规模，避免微型物种
    min_offspring_population: int = 20000
    # 背景物种分化概率惩罚系数（0-1，越小惩罚越重）
    # 例如 0.2 表示背景物种的分化概率降低到普通物种的 20%
    background_speciation_penalty: float = 0.2
    
    # ========== 杂交参数 ==========
    # 自动杂交检测概率（每回合检测同域近缘物种杂交的概率）
    auto_hybridization_chance: float = 0.08
    # 杂交成功率（通过检测后，杂交实际成功的概率）
    hybridization_success_rate: float = 0.35
    # 每回合最多杂交数量
    max_hybrids_per_turn: int = 2
    # 杂交所需的最小生物量（每个亲本物种，kg）
    # 设为 20,000 kg 确保双亲都有足够规模
    min_population_for_hybridization: int = 20000
    
    # ========== 距离型隔离判定 ==========
    # 距离隔离阈值（六边形步数）：候选地块跨度超过此值视为隔离（降低以更容易触发）
    distance_threshold_hex: int = 6
    # 长宽比阈值：长轴/短轴超过此值视为"带状"隔离（降低以更容易触发）
    elongation_ratio_threshold: float = 1.8
    # 是否启用距离型隔离判定
    enable_distance_isolation: bool = True
    # 死亡率梯度阈值（降低以更容易判定为隔离）
    mortality_gradient_threshold: float = 0.08
    # 最小簇间距离（候选块数量>=N且任意两簇间距离>此值也视为隔离）
    min_cluster_gap: int = 2
    
    # ========== 灭绝阈值 ==========
    # 绝对灭绝阈值：种群低于此值直接灭绝（单位：kg 生物量）
    extinction_population_threshold: int = 100
    # 死亡率灭绝阈值：单回合死亡率超过此值触发灭绝
    extinction_death_rate_threshold: float = 0.95
    
    # 最小可存活种群 (MVP)：种群长期低于此值会逐渐走向灭绝
    # 考虑到游戏中生物量单位是 kg，设为 1000 kg
    minimum_viable_population: int = 1000
    # MVP 检测窗口：连续多少回合低于 MVP 触发灭绝警告
    mvp_warning_turns: int = 3
    # MVP 灭绝回合：连续多少回合低于 MVP 直接灭绝
    mvp_extinction_turns: int = 5
    
    # 竞争劣势阈值：种群低于生态系统平均的此比例时，竞争力下降
    # 例如 0.1 表示种群低于平均值的 10% 时竞争力下降
    competition_disadvantage_ratio: float = 0.05
    # 竞争灭绝阈值：种群低于生态系统平均的此比例时，可能被竞争灭绝
    competition_extinction_ratio: float = 0.01
    
    # 近交衰退阈值：种群低于此值时开始受近交衰退影响（额外死亡率）
    inbreeding_depression_threshold: int = 5000
    # 近交衰退系数：低于阈值时的额外死亡率 = (1 - pop/threshold) * coefficient
    inbreeding_depression_coefficient: float = 0.15
    
    # 连续衰退灭绝：连续衰退（种群减少）超过此回合数触发灭绝
    consecutive_decline_extinction_turns: int = 8
    # 衰退检测阈值：种群减少超过此比例才算衰退
    decline_detection_threshold: float = 0.1


class ReproductionConfig(BaseModel):
    """繁殖配置 - 控制物种繁殖行为的参数
    
    【设计理念 v7 优化】
    - 基础增长率由繁殖速度属性决定
    - 【降低】体型和世代加成，避免种群过快恢复
    - 高营养级受更强的能量传递限制
    - 【降低】生存本能加成，极端压力下繁殖效率应显著下降
    - 【新增】高死亡率繁殖惩罚，死亡率>60%时繁殖效率大幅下降
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 基础增长 ==========
    # 每点繁殖速度提供的增长率加成
    growth_rate_per_repro_speed: float = 0.5  # 从0.35提升到0.5，加快基础增长
    # 增长倍数下限（保护濒危物种）
    growth_multiplier_min: float = 0.5
    # 【关键】增长倍数上限（大幅提升以允许种群快速扩张）
    growth_multiplier_max: float = 15.0  # 从8.0回升到15.0，允许指数级爆发
    
    # ========== 体型加成 ==========
    # 【优化v8】恢复体型加成，微小生物应该繁殖极快
    # 微生物（<0.1mm）增长加成
    size_bonus_microbe: float = 2.0  # 从1.6回升到2.0
    # 小型生物（0.1mm-1mm）增长加成
    size_bonus_tiny: float = 1.5  # 从1.3回升到1.5
    # 中小型生物（1mm-1cm）增长加成
    size_bonus_small: float = 1.25  # 从1.1回升到1.25
    
    # ========== 世代时间加成 ==========
    # 【优化v8】恢复世代加成
    # 极快繁殖（<1周）加成
    repro_bonus_weekly: float = 2.0  # 从1.5回升到2.0
    # 快速繁殖（<1月）加成
    repro_bonus_monthly: float = 1.5  # 从1.25回升到1.5
    # 中速繁殖（<半年）加成
    repro_bonus_halfyear: float = 1.25  # 从1.1回升到1.25
    
    # ========== 存活率修正 ==========
    # 【优化v8】提高存活率修正，让存活下来的物种能更好地恢复
    # 存活率修正基础值
    survival_modifier_base: float = 0.4  # 从0.3回升到0.4
    # 存活率修正系数
    survival_modifier_rate: float = 1.2  # 从1.0回升到1.2
    
    # ========== 生存本能 ==========
    # 【优化v8】适度回调生存本能，帮助濒危物种
    # 生存本能激活阈值（死亡率超过此值）
    survival_instinct_threshold: float = 0.6
    # 生存本能最大加成
    survival_instinct_bonus: float = 0.6  # 从0.4提升到0.6
    
    # ========== 资源压力 ==========
    # 【优化v7】增强资源压力惩罚
    # 资源饱和时的惩罚率（饱和度1.0-2.0区间）
    resource_saturation_penalty_mild: float = 0.5  # 从0.4提升到0.5
    # 资源严重不足时的最低效率
    resource_saturation_floor: float = 0.15  # 从0.2降低到0.15
    
    # ========== 承载力超载 ==========
    # 【优化v7】增强超载衰减
    # 超载时的衰减率
    overshoot_decay_rate: float = 0.35  # 从0.25提升到0.35
    # 接近承载力时的增长效率
    near_capacity_efficiency: float = 0.5  # 从0.6降低到0.5
    
    # ========== 营养级惩罚 ==========
    # 【优化v7】增强高营养级惩罚
    # T2 初级消费者繁殖效率
    t2_birth_efficiency: float = 0.90  # 从0.85提升到0.90，帮助早期食草动物存活
    # T3 高级消费者繁殖效率
    t3_birth_efficiency: float = 0.60  # 从0.7降低到0.60
    # T4+ 顶级捕食者繁殖效率
    t4_birth_efficiency: float = 0.40  # 从0.5降低到0.40
    
    # ========== 【新增v7】高死亡率繁殖惩罚 ==========
    # 死亡率惩罚阈值：超过此值开始降低繁殖效率
    mortality_penalty_threshold: float = 0.60  # 【平衡】从0.55提升到0.60，更宽容
    # 死亡率惩罚系数：每超过阈值10%，繁殖效率降低此比例
    mortality_penalty_rate: float = 0.10  # 【平衡】从0.15降低到0.10，减少死亡螺旋

    # 极端死亡率阈值：超过此值繁殖效率直接减半
    extreme_mortality_threshold: float = 0.85  # 【平衡】从0.80提升到0.85


class MortalityConfig(BaseModel):
    """死亡率配置 - 控制物种死亡率计算的参数
    
    【设计理念 v7 优化】
    - 多种压力源叠加计算死亡率
    - 极端环境条件下压力上限提高
    - 降低抗性减免，确保极端压力产生显著效果
    - 乘法模型比重增加，产生更陡峭的压力响应曲线
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 压力上限 ==========
    # 【优化v7】提高压力上限，允许极端条件产生更高压力
    # 环境压力上限
    env_pressure_cap: float = 0.70  # 从0.50提升到0.70
    # 竞争压力上限
    competition_pressure_cap: float = 0.45
    # 营养级压力上限（捕食/被捕食）
    trophic_pressure_cap: float = 0.50
    # 资源压力上限
    resource_pressure_cap: float = 0.45
    # 捕食网压力上限
    predation_pressure_cap: float = 0.55
    # 植物竞争压力上限
    plant_competition_cap: float = 0.35
    
    # ========== 加权求和权重 ==========
    # 【优化v8】平衡各压力源权重
    # 环境压力权重
    env_weight: float = 0.40  # 从0.50降低到0.40
    # 竞争压力权重
    # 【v8优化】降低竞争权重，避免无压力时种群衰退
    competition_weight: float = 0.15  # 从0.18降低到0.15
    # 营养级压力权重
    trophic_weight: float = 0.25  # 从0.35降低到0.25
    # 资源压力权重
    resource_weight: float = 0.25  # 从0.30降低到0.25
    # 捕食网压力权重
    predation_weight: float = 0.25  # 从0.30降低到0.25
    # 植物竞争权重
    plant_competition_weight: float = 0.20  # 从0.25降低到0.20
    
    # ========== 乘法模型系数 ==========
    # 【优化v8】降低乘法系数，减少无压力时的死亡率
    # 环境压力乘法系数
    env_mult_coef: float = 0.45  # 从0.55降低到0.45
    # 竞争压力乘法系数
    # 【v8优化】大幅降低竞争乘法系数
    competition_mult_coef: float = 0.30  # 从0.50降低到0.30
    # 营养级压力乘法系数
    trophic_mult_coef: float = 0.50  # 降低
    # 资源压力乘法系数
    resource_mult_coef: float = 0.40  # 降低
    # 捕食网压力乘法系数
    predation_mult_coef: float = 0.50  # 降低
    # 植物竞争乘法系数
    plant_mult_coef: float = 0.40
    
    # ========== 模型混合 ==========
    # 【优化v7】增加乘法模型比重，产生更陡峭的响应曲线
    # 加权和模型占比（乘法模型占1-此值）
    additive_model_weight: float = 0.55  # 从0.70降低到0.55
    
    # ========== 抗性系数 ==========
    # 【优化v7】降低抗性上限，确保极端压力仍产生显著效果
    # 体型抗性系数（每10cm体长的抗性）
    size_resistance_per_10cm: float = 0.015
    # 世代时间抗性系数
    generation_resistance_coef: float = 0.04
    # 最大抗性上限
    max_resistance: float = 0.18  # 从0.25降低到0.18
    
    # ========== 死亡率边界 ==========
    # 最低死亡率（保证自然死亡）
    # 【v8优化】降低到1.0%，让无压力情况下种群可增长
    min_mortality: float = 0.010
    # 最高死亡率上限
    max_mortality: float = 0.92  # 从0.95降低到0.92，保留一点生存希望


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
    # 消费者分布时搜索的猎物地块数量
    prey_search_top_k: int = 5
    
    # ========== 竞争强度 ==========
    # 基础竞争系数（相似度 × 营养级系数 × 此值）
    competition_base_coefficient: float = 0.60
    # 单个竞争者贡献上限
    competition_per_species_cap: float = 0.35
    # 总竞争压力上限
    competition_total_cap: float = 0.80
    # 同级竞争系数（同营养级物种之间）
    same_level_competition_k: float = 0.15
    # 生态位重叠惩罚系数（基于embedding相似度）
    niche_overlap_penalty_k: float = 0.20
    
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
    # 海岸物种分布地块数上限
    coastal_top_k: int = 3
    # 空中物种分布地块数上限
    aerial_top_k: int = 5
    # 宜居度阈值：低于此值的地块不分配种群
    suitability_cutoff: float = 0.25
    # 宜居度权重指数：pow(suitability, alpha)，alpha>1 更集中
    suitability_weight_alpha: float = 1.5
    # 高营养级扩散阻尼（跨地块成本）
    high_trophic_dispersal_damping: float = 0.7
    # 跨地块扩散基础成本（限制远距离迁移）
    dispersal_cost_base: float = 0.1
    # 迁移偏好：向高宜居度的偏好权重
    migration_suitability_bias: float = 0.6
    # 迁移偏好：向有猎物地块的偏好权重（消费者）
    migration_prey_bias: float = 0.3
    # 栖息地重算频率（每N回合强制重算）
    habitat_recalc_frequency: int = 1
    
    # ========== 承载力 ==========
    # 承载力基础倍数（相对于体型估算值）
    carrying_capacity_base: float = 1.0
    # 承载力随机波动范围（±百分比）
    carrying_capacity_variance: float = 0.1
    
    # ========== 资源再生 ==========
    # 资源最大恢复速率（logistic r）
    resource_recovery_rate: float = 0.15
    # 资源恢复滞后回合数
    resource_recovery_lag: int = 1
    # 过度消耗后的最小恢复率
    resource_min_recovery: float = 0.05
    # 资源上限倍数
    resource_capacity_multiplier: float = 1.0
    
    # ========== 环境扰动 ==========
    # 资源随机扰动幅度
    resource_perturbation: float = 0.05
    # 气候随机扰动幅度
    climate_perturbation: float = 0.02
    # 环境噪声（避免局部不合理稳态）
    environment_noise: float = 0.03
    
    # ========== 防御/逃逸 ==========
    # 基础逃逸成功率（猎物默认）
    base_escape_rate: float = 0.3
    # 体型差异对捕食成功率的影响
    size_advantage_factor: float = 0.1
    
    # ========== 频率依赖选择 ==========
    # 【新增】频率依赖选择：常见型受惩罚，稀有型获优势
    # 是否启用频率依赖选择
    enable_frequency_dependence: bool = True
    # 频率依赖效应强度（0-1）：0=无效应，1=强效应
    frequency_dependence_strength: float = 0.25
    # 常见型阈值：种群占比超过此值被视为"常见型"，受惩罚
    common_type_threshold: float = 0.15
    # 稀有型阈值：种群占比低于此值被视为"稀有型"，获优势
    rare_type_threshold: float = 0.03
    # 常见型最大惩罚（额外死亡率）
    common_type_max_penalty: float = 0.12
    # 稀有型最大优势（死亡率减免）
    rare_type_max_advantage: float = 0.08
    
    # ========== 新物种适应性优势 ==========
    # 【新增】新分化物种在前几回合获得适应性优势
    # 是否启用新物种优势
    enable_new_species_advantage: bool = True
    # 新物种第1回合死亡率减免
    new_species_advantage_turn0: float = 0.10
    # 新物种第2回合死亡率减免
    new_species_advantage_turn1: float = 0.06
    # 新物种第3回合死亡率减免
    new_species_advantage_turn2: float = 0.03
    # 新物种繁殖率加成（第1回合）
    new_species_reproduction_boost: float = 1.15
    
    # ========== 增强版子代压制 ==========
    # 【新增】子代对亲代的压制效果增强
    # 子代压制系数（原0.20，现提高）
    offspring_suppression_coefficient: float = 0.28
    # 亲代演化滞后惩罚第1回合
    parent_lag_penalty_turn0: float = 0.18
    # 亲代演化滞后惩罚第2回合
    parent_lag_penalty_turn1: float = 0.12
    # 亲代演化滞后惩罚第3回合
    parent_lag_penalty_turn2: float = 0.06
    
    # ========== 生态位重叠直接竞争 ==========
    # 【新增】高生态位重叠时的直接竞争效应
    # 高重叠阈值：重叠度超过此值触发直接竞争
    high_overlap_threshold: float = 0.6
    # 高重叠时每0.1重叠度增加的死亡率
    overlap_competition_per_01: float = 0.04
    # 最大重叠竞争惩罚
    overlap_competition_max: float = 0.20


class EcologicalRealismConfig(BaseModel):
    """生态拟真配置 - 控制高级生态学机制
    
    【设计理念】
    基于语义驱动的生态学判断，所有参数通过 embedding 语义匹配实现，
    而非硬编码的类型枚举。
    
    【核心模块】
    1. Allee 效应：小种群困境
    2. 密度依赖疾病：高密度种群的疾病压力
    3. 环境综合变数：长周期环境波动
    4. 空间显式捕食：地理重叠影响捕食效率
    5. 能量同化效率：基于物种特征的动态效率
    6. 垂直生态位分层：减少同层竞争
    7. 适应滞后：环境变化速率与适应能力的匹配
    8. 互利共生网络：自动识别和维护共生关系
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== Allee 效应 ==========
    # 是否启用 Allee 效应
    enable_allee_effect: bool = True
    # MVP 临界比例（相对于承载力）
    allee_critical_ratio: float = 0.1
    # 最大繁殖惩罚
    allee_max_penalty: float = 0.4
    # S型曲线陡峭度
    allee_steepness: float = 5.0
    
    # ========== 密度依赖疾病 ==========
    # 是否启用密度依赖疾病
    enable_density_disease: bool = True
    # 触发疾病的密度阈值
    disease_density_threshold: float = 0.7
    # 基础疾病死亡率
    disease_base_mortality: float = 0.15
    # 群居性影响系数
    disease_social_factor: float = 0.3
    # 抗病性减免系数
    disease_resistance_factor: float = 0.5
    
    # ========== 环境综合变数 ==========
    # 是否启用环境波动
    enable_env_fluctuation: bool = True
    # 波动周期（回合）
    fluctuation_period_turns: int = 20
    # 波动幅度
    fluctuation_amplitude: float = 0.2
    # 高纬度敏感系数
    latitude_sensitivity: float = 1.5
    # 专化物种敏感系数
    specialist_sensitivity: float = 1.3
    
    # ========== 空间显式捕食 ==========
    # 是否启用空间显式捕食
    enable_spatial_predation: bool = True
    # 最小重叠度才能捕食
    min_overlap_for_predation: float = 0.1
    # 重叠度对效率的影响
    overlap_efficiency_factor: float = 0.6
    
    # ========== 能量同化效率 ==========
    # 是否启用动态同化效率
    enable_dynamic_assimilation: bool = True
    # 草食基础效率
    herbivore_base_efficiency: float = 0.12
    # 肉食基础效率
    carnivore_base_efficiency: float = 0.25
    # 腐食基础效率
    detritivore_base_efficiency: float = 0.20
    # 滤食效率
    filter_feeder_efficiency: float = 0.15
    # 恒温动物效率惩罚
    endotherm_penalty: float = 0.7
    
    # ========== 垂直生态位 ==========
    # 是否启用垂直生态位分层
    enable_vertical_niche: bool = True
    # 同层竞争系数
    same_layer_competition: float = 1.0
    # 相邻层竞争系数
    adjacent_layer_competition: float = 0.3
    # 远层竞争系数
    distant_layer_competition: float = 0.05
    
    # ========== 适应滞后 ==========
    # 是否启用适应滞后
    enable_adaptation_lag: bool = True
    # 环境变化追踪窗口（回合）
    env_change_tracking_window: int = 5
    # 最大适应惩罚
    max_adaptation_penalty: float = 0.3
    # 高可塑性保护系数
    plasticity_protection: float = 0.5
    # 世代时间影响
    generation_time_factor: float = 0.1
    
    # ========== 互利共生 ==========
    # 是否启用互利共生
    enable_mutualism: bool = True
    # 共生匹配阈值
    mutualism_threshold: float = 0.6
    # 共生伙伴存在时的加成
    mutualism_benefit: float = 0.1
    # 共生伙伴灭绝时的惩罚
    mutualism_penalty: float = 0.15


class ResourceSystemConfig(BaseModel):
    """资源系统配置 - 控制 NPP、承载力和能量流动
    
    【设计理念】
    基于净初级生产力 (NPP) 的资源模型，统一能量单位，
    支持资源再生、过采惩罚和事件脉冲。
    
    【单位说明】
    - NPP: kg 生物量 / 地块 / 回合
    - 承载力: 个体数
    - 能量效率: 无量纲 (0-1)
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== NPP 基准与转换 ==========
    # NPP 到 T1 承载力转换系数（每 kg NPP 支持的 T1 生物量 kg）
    npp_to_capacity_factor: float = 50.0
    # 地块资源基值 → NPP 转换系数
    # tile.resources (1-1000) × 此系数 = NPP (kg/turn)
    resource_to_npp_factor: float = 100.0
    # NPP 上限 (kg/地块/回合)
    max_npp_per_tile: float = 100000.0
    
    # ========== 气候-NPP 耦合 ==========
    # 是否启用气候驱动 NPP
    enable_climate_npp: bool = True
    # 温度最优范围 (℃)
    optimal_temp_min: float = 15.0
    optimal_temp_max: float = 28.0
    # 温度偏离最优时的 NPP 衰减速率 (每℃)
    temp_deviation_penalty: float = 0.03
    # 湿度对 NPP 的影响系数
    humidity_npp_factor: float = 0.5
    # 最低湿度阈值（低于此值 NPP 大幅下降）
    humidity_min_threshold: float = 0.2
    
    # ========== 资源再生与过采 ==========
    # 是否启用资源再生动态
    enable_resource_dynamics: bool = True
    # 资源恢复速率 (Logistic r)
    resource_recovery_rate: float = 0.3
    # 过度采食惩罚阈值（需求/供给比）
    overgrazing_threshold: float = 1.0
    # 过度采食时下回合 NPP 折减系数
    overgrazing_penalty: float = 0.15
    # 资源恢复上限倍数（相对于基准）
    resource_capacity_multiplier: float = 1.2
    # 季节/年际波动幅度 (0-1)
    resource_fluctuation_amplitude: float = 0.1
    
    # ========== 能量传递效率 ==========
    # T1→T2 生态效率（草食）
    efficiency_t1_to_t2: float = 0.12
    # T2→T3 生态效率（初级肉食）
    efficiency_t2_to_t3: float = 0.10
    # T3→T4 生态效率（次级肉食）
    efficiency_t3_to_t4: float = 0.10
    # T4→T5 生态效率（顶级）
    efficiency_t4_to_t5: float = 0.08
    # 默认生态效率（用于未指定的营养级）
    default_ecological_efficiency: float = 0.10
    
    # ========== 资源压力计算 ==========
    # 代谢率系数（体重 kg → 每回合代谢需求 kg）
    metabolic_rate_coefficient: float = 0.1
    # 代谢率体重指数（异速生长：需求 ∝ 体重^指数）
    metabolic_weight_exponent: float = 0.75
    # 可采份额（避免完全消耗资源）
    harvestable_fraction: float = 0.7
    # 资源压力上限
    resource_pressure_cap: float = 0.65
    # 资源压力下限（保底）
    resource_pressure_floor: float = 0.0
    
    # ========== 空间异质性 ==========
    # 水体 NPP 倍率（相对于陆地）
    aquatic_npp_multiplier: float = 0.6
    # 深海 NPP 倍率
    deep_sea_npp_multiplier: float = 0.1
    # 浅海 NPP 倍率
    shallow_sea_npp_multiplier: float = 0.8
    # 沙漠 NPP 倍率
    desert_npp_multiplier: float = 0.1
    # 苔原 NPP 倍率
    tundra_npp_multiplier: float = 0.2
    # 温带森林 NPP 倍率
    temperate_forest_npp_multiplier: float = 1.0
    # 热带雨林 NPP 倍率
    tropical_forest_npp_multiplier: float = 1.5
    
    # ========== 事件脉冲 ==========
    # 火山灰短期资源提升倍率
    volcanic_ash_boost: float = 1.3
    # 火山灰衰减速率（每回合）
    volcanic_ash_decay: float = 0.2
    # 洪水后肥力提升倍率
    flood_fertility_boost: float = 1.2
    # 洪水初期资源损失
    flood_initial_loss: float = 0.3
    # 干旱资源下降倍率
    drought_resource_penalty: float = 0.5
    
    # ========== 缓存与性能 ==========
    # 资源压力计算缓存 TTL（回合内）
    pressure_cache_ttl_turns: int = 1
    # 是否启用向量化计算
    use_vectorized_calculation: bool = True


class FoodWebConfig(BaseModel):
    """食物网配置 - 控制食物链关系维护和猎物分配
    
    【设计理念】
    提供食物网自动维护的参数调整，确保生态系统食物链的完整性和动态平衡。
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 猎物多样性阈值 ==========
    # 按营养级设定的最低猎物数量目标
    # T2 初级消费者（吃生产者）
    min_prey_count_t2: int = 2
    # T3 次级消费者
    min_prey_count_t3: int = 3
    # T4 三级消费者
    min_prey_count_t4: int = 3
    # T5 顶级捕食者
    min_prey_count_t5: int = 2
    
    # ========== 猎物补充触发条件 ==========
    # 猎物过少时触发补充的阈值比例（相对于目标的百分比）
    prey_shortage_threshold: float = 0.5
    # 是否在猎物仍存活但过少时也触发补充
    enable_prey_diversity_补充: bool = True
    # 每回合最大补充猎物数量（每个物种）
    max_prey_additions_per_turn: int = 2
    
    # ========== 新物种集成 ==========
    # 是否自动将新 T1/T2 物种加入现有消费者的候选猎物
    auto_integrate_new_producers: bool = True
    # 新物种集成时的栖息地重叠阈值
    new_species_habitat_overlap_threshold: float = 0.3
    # 新物种集成时的 embedding 相似度阈值
    new_species_embedding_threshold: float = 0.5
    # 对猎物不足的消费者优先集成（≤此数量）
    integrate_priority_when_prey_below: int = 3
    
    # ========== 区域权重 ==========
    # 是否启用区域（瓦片）权重偏好
    enable_tile_weight: bool = True
    # 同瓦片猎物权重加成
    same_tile_prey_weight_boost: float = 0.4
    # 饥饿区域（高死亡率）的区域权重额外加成
    hungry_region_weight_boost: float = 0.3
    # 孤立区域（低连通性）的区域权重额外加成
    isolated_region_weight_boost: float = 0.2
    
    # ========== 生物量约束 ==========
    # 是否启用生物量约束（避免高营养级依赖微小生产者）
    enable_biomass_constraint: bool = True
    # 猎物最小群体生物量（人口×体重 克）
    min_prey_biomass_g: float = 100.0
    # 每高一个营养级，最小生物量乘以此系数
    biomass_trophic_multiplier: float = 10.0
    # 能量转换效率（每级约10%）
    energy_transfer_efficiency: float = 0.1
    
    # ========== 反馈与压力耦合 ==========
    # 饥饿物种的额外死亡率惩罚系数
    starving_mortality_coefficient: float = 0.25
    # 孤立消费者的额外死亡率惩罚系数
    orphaned_mortality_coefficient: float = 0.15
    # 无猎物时触发迁徙的概率加成
    no_prey_migration_boost: float = 0.4
    # 猎物丰富区域的死亡率减免
    prey_rich_mortality_reduction: float = 0.05
    
    # ========== 快照恢复 ==========
    # 加载存档时是否重建食物网
    rebuild_food_web_on_load: bool = True
    # 重建食物网时保留现有有效链接
    preserve_valid_links_on_rebuild: bool = True
    
    # ========== 审计与日志 ==========
    # 是否记录详细的食物网变更
    log_food_web_changes: bool = True
    # 保留变更历史的回合数
    change_history_turns: int = 10


class MapEnvironmentConfig(BaseModel):
    """地图环境配置 - 控制地块、气候和地理参数
    
    【设计理念】
    提供地图级别的环境调整，影响物种分布和生态平衡。
    包括气候、资源、事件等全局设置。
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 气候偏移 ==========
    # 全局温度偏移（℃）：正值升温，负值降温
    global_temperature_offset: float = 0.0
    # 全局湿度偏移（%）：正值增湿，负值干旱
    global_humidity_offset: float = 0.0
    # 极端气候事件频率（每回合概率）
    extreme_climate_frequency: float = 0.05
    # 极端气候影响幅度
    extreme_climate_amplitude: float = 0.3
    
    # ========== 海平面与地形 ==========
    # 海平面偏移（米）：正值海进，负值海退
    sea_level_offset: float = 0.0
    # 海平面变化速率（米/回合）
    sea_level_change_rate: float = 0.0
    # 地形侵蚀速率
    terrain_erosion_rate: float = 0.01
    
    # ========== 栖息地适宜度阈值 ==========
    # 海岸生物温度容差范围（±℃）
    coastal_temp_tolerance: float = 15.0
    # 浅海生物盐度容差
    shallow_sea_salinity_tolerance: float = 0.8
    # 淡水生物对湿度的要求下限
    freshwater_min_humidity: float = 0.5
    # 陆生生物最低温度（℃）
    terrestrial_min_temp: float = -20.0
    # 陆生生物最高温度（℃）
    terrestrial_max_temp: float = 50.0
    
    # ========== 生物群系承载力倍数 ==========
    # 热带雨林承载力倍数
    biome_capacity_rainforest: float = 1.5
    # 温带森林承载力倍数
    biome_capacity_temperate: float = 1.2
    # 草原承载力倍数
    biome_capacity_grassland: float = 1.0
    # 沙漠承载力倍数
    biome_capacity_desert: float = 0.3
    # 苔原承载力倍数
    biome_capacity_tundra: float = 0.4
    # 深海承载力倍数
    biome_capacity_deep_sea: float = 0.5
    # 浅海承载力倍数
    biome_capacity_shallow_sea: float = 1.3
    
    # ========== 地质/灾害事件 ==========
    # 火山爆发频率（每回合概率）
    volcano_frequency: float = 0.02
    # 火山影响半径（地块数）
    volcano_impact_radius: int = 3
    # 火山破坏强度
    volcano_damage_intensity: float = 0.8
    # 洪水频率
    flood_frequency: float = 0.03
    # 洪水影响范围
    flood_impact_radius: int = 2
    # 干旱频率
    drought_frequency: float = 0.04
    # 干旱持续回合数
    drought_duration: int = 2
    # 地震频率
    earthquake_frequency: float = 0.01
    
    # ========== 密度与拥挤惩罚 ==========
    # 同地块同营养级密度惩罚系数
    same_tile_density_penalty: float = 0.15
    # 过度拥挤阈值（超过此密度开始惩罚）
    overcrowding_threshold: float = 0.7
    # 拥挤惩罚最大值
    overcrowding_max_penalty: float = 0.4
    
    # ========== 地图视图叠加层 ==========
    # 显示资源分布热力图
    show_resource_overlay: bool = False
    # 显示猎物丰度热力图
    show_prey_overlay: bool = False
    # 显示宜居度热力图
    show_suitability_overlay: bool = False
    # 显示竞争压力热力图
    show_competition_overlay: bool = False
    # 显示温度分布
    show_temperature_overlay: bool = False
    # 显示湿度分布
    show_humidity_overlay: bool = False


class PressureIntensityConfig(BaseModel):
    """压力强度配置 - 控制玩家施加的环境压力效果强度
    
    【设计理念】
    压力分为三个等级：
    - 一阶（生态波动）：影响轻微
    - 二阶（气候变迁）：影响显著但可控  
    - 三阶（天灾降临）：可造成大灭绝
    
    最终效果 = 基础系数 × 类型倍率 × 强度倍率
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 压力类型倍率 ==========
    # 一阶压力：生态波动，几乎无害
    tier1_multiplier: float = 0.5
    # 二阶压力：气候变迁，可控
    tier2_multiplier: float = 0.7
    # 三阶压力：天灾降临，大浪淘沙
    tier3_multiplier: float = 1.5
    
    # ========== 强度滑块倍率 ==========
    # 强度 1-3：轻微
    intensity_low_multiplier: float = 0.3
    # 强度 4-7：显著
    intensity_mid_multiplier: float = 0.6
    # 强度 8-10：毁灭性
    intensity_high_multiplier: float = 1.2
    
    # ========== 温度修饰系数 ==========
    # 每单位温度修饰的效果（°C）
    temperature_effect_per_unit: float = 0.8


class GameplayConfig(BaseModel):
    """游戏模式配置 - 控制整体游戏难度和风格
    
    【设计理念】
    提供预设模式快速切换游戏风格，
    以及调试选项帮助理解生态系统运作。
    """
    model_config = ConfigDict(extra="ignore")
    
    # ========== 游戏模式 ==========
    # 当前游戏模式：casual/balanced/hardcore/custom
    game_mode: str = "balanced"
    
    # ========== 难度系数 ==========
    # 全局死亡率倍率（1.0=正常，<1休闲，>1硬核）
    mortality_multiplier: float = 1.0
    # 全局竞争强度倍率
    competition_multiplier: float = 1.0
    # 全局繁殖效率倍率
    reproduction_multiplier: float = 1.0
    # 全局资源丰富度倍率
    resource_abundance_multiplier: float = 1.0
    
    # ========== 显示选项 ==========
    # 是否显示猎物丰富度详情
    show_prey_abundance: bool = True
    # 是否显示食物分数详情
    show_food_score: bool = True
    # 是否显示竞争惩罚详情
    show_competition_penalty: bool = True
    # 是否显示死亡率分解
    show_mortality_breakdown: bool = False
    # 是否显示高级生态指标
    show_advanced_metrics: bool = False


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
    embedding_concurrency_enabled: bool = False
    embedding_concurrency_limit: int = 1
    embedding_semantic_hotspot_only: bool = False
    embedding_semantic_hotspot_limit: int = 512
    
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
    
    # 14. 压力强度配置
    pressure_intensity: PressureIntensityConfig = Field(default_factory=PressureIntensityConfig)
    
    # 15. 游戏模式配置
    gameplay: GameplayConfig = Field(default_factory=GameplayConfig)
    
    # 15. 地图环境配置
    map_environment: MapEnvironmentConfig = Field(default_factory=MapEnvironmentConfig)
    
    # 16. 食物网配置
    food_web: FoodWebConfig = Field(default_factory=FoodWebConfig)
    
    # 17. 资源系统配置
    resource_system: ResourceSystemConfig = Field(default_factory=ResourceSystemConfig)
    
    # 18. 生态拟真配置
    ecological_realism: EcologicalRealismConfig = Field(default_factory=EcologicalRealismConfig)
    
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
