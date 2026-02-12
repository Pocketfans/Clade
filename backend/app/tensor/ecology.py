"""
GPU-only 统一张量生态计算引擎

【GPU-only 模式】
本模块强制使用 Taichi GPU 后端，无 NumPy fallback。
如果 GPU/Taichi 不可用，会直接抛出 RuntimeError。

【核心优化】
将原本分散在多个模块中的循环计算统一为张量并行计算：
1. 死亡率：Taichi GPU 并行计算多因子死亡率
2. 扩散：Taichi GPU 并行计算带适宜度引导的扩散
3. 迁徙：Taichi GPU 并行计算压力驱动+猎物追踪迁徙

【性能提升】
- 原方案：逐物种串行计算，50物种 × 64×64地图 ≈ 2000ms
- 新方案：Taichi GPU 张量并行，50物种 × 64×64地图 ≈ 50ms
- 加速比：10-50x

【设计原则】
1. GPU-only：所有计算通过 Taichi 内核执行
2. 零循环：Python 层无显式循环
3. 一次调用：process_ecology() 完成全部生态计算

使用方式：
    from app.tensor.ecology import get_ecology_engine
    
    engine = get_ecology_engine()  # 无 GPU 时抛错
    result = engine.process_ecology(
        pop=tensor_state.pop,
        env=tensor_state.env,
        species_params=species_params,
        species_prefs=species_prefs,
        turn_index=turn_index,
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Sequence

import numpy as np

if TYPE_CHECKING:
    from ..models.species import Species
    from .state import TensorState

logger = logging.getLogger(__name__)

# Taichi 内核（延迟导入）
_taichi_kernels = None
_taichi_available = False


def _load_ecology_kernels():
    """加载 Taichi 内核 - GPU-only 模式，无 fallback"""
    global _taichi_kernels, _taichi_available
    
    if _taichi_kernels is not None:
        return _taichi_available
    
    try:
        from . import taichi_hybrid_kernels as kernels
        _taichi_kernels = kernels
        _taichi_available = True
        logger.info("[TensorEcology] Taichi GPU 内核已加载")
        return True
    except ImportError as e:
        raise RuntimeError(
            f"[GPU-only] Taichi 导入失败: {e}\n"
            "请确保已安装 taichi-gpu 并且有可用的 GPU 设备"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"[GPU-only] Taichi GPU 初始化失败: {e}\n"
            "请检查 GPU 驱动是否正确安装"
        ) from e


@dataclass
class EcologyConfig:
    """生态计算配置
    
    【v3.0】全面重构：
    - 扩散：多轮迭代 + 背景扩散 + 世代缩放
    - 迁徙：动态阈值 + 全局拥挤加成 + 栖息地衰减
    - 繁殖/死亡：世代时间缩放（effective_steps）
    """
    # === 死亡率参数 ===
    base_mortality: float = 0.06          # 基础死亡率
    temp_mortality_weight: float = 0.25   # 温度死亡率权重
    competition_weight: float = 0.20      # 竞争死亡率权重
    resource_weight: float = 0.25         # 资源死亡率权重
    trophic_weight: float = 0.25          # 营养级死亡率权重
    suitability_weight: float = 0.35      # 宜居度死亡权重
    
    # === 扩散参数 ===
    # 【v3.0】增强扩散：多轮迭代 + 背景扩散
    base_diffusion_rate: float = 0.18     # 基础扩散率（提高）
    max_diffusion_rate: float = 0.50      # 最大扩散率（提高上限）
    density_pressure_threshold: float = 15.0  # 【降低】触发密度驱动扩散的阈值
    background_diffusion_rate: float = 0.08   # 【新增】背景扩散率（梯度为零时）
    early_dispersal_iterations: int = 3       # 【新增】早期时代扩散迭代次数
    suit_escape_threshold: float = 0.22       # 【新增】低宜居度逃逸阈值
    
    # === 迁徙参数 ===
    # 【v3.0】动态阈值 + 全局拥挤 + 栖息地衰减
    pressure_threshold: float = 0.08      # 压力迁徙阈值
    saturation_threshold: float = 0.50    # 饱和度阈值
    max_migration_distance: float = 3.5   # 最大迁徙距离（提高）
    base_migration_rate: float = 0.18     # 基础迁徙率（提高）
    score_threshold: float = 0.15         # 迁徙分数阈值（默认）
    early_score_threshold: float = 0.08   # 【新增】早期时代迁徙分数阈值
    crowding_migration_bonus: float = 0.12  # 【新增】全局拥挤时迁徙加成
    base_long_jump_rate: float = 0.02     # 【新增】基础长跳概率
    early_long_jump_rate: float = 0.05    # 【新增】早期时代长跳概率
    habitat_attenuation_factor: float = 0.5  # 【新增】栖息地衰减因子（非硬屏蔽）
    
    # === 繁殖参数 ===
    base_birth_rate: float = 0.12         # 基础出生率
    capacity_multiplier: float = 100.0    # 承载力乘数
    min_suitability_for_reproduction: float = 0.15  # 繁殖的最低宜居度
    
    # === 时代/世代缩放 ===
    era_scaling_enabled: bool = True      # 是否启用时代缩放
    generation_scaling_enabled: bool = True  # 是否启用世代缩放
    default_generation_time_days: float = 365.0  # 默认世代时间（天）
    turn_years: int = 500_000             # 默认回合年数
    
    # 【v3.1】缓冲参数：防止微生物爆炸/瞬灭
    effective_steps_clip_max: float = 20.0  # effective_steps 上限截断
    effective_steps_clip_min: float = 1.0   # effective_steps 下限
    
    # 分层缩放幂指数（按体型/繁殖速度）
    small_species_exponent: float = 0.25    # 小体型/快繁殖物种的幂指数
    medium_species_exponent: float = 0.35   # 中等物种的幂指数
    large_species_exponent: float = 0.50    # 大体型/慢繁殖物种的幂指数
    
    # 各阶段放大系数上限
    birth_scale_max: float = 3.0            # 繁殖率放大系数上限
    mortality_scale_max: float = 2.5        # 死亡率放大系数上限
    diffusion_scale_max: float = 2.5        # 扩散率放大系数上限
    migration_scale_max: float = 2.5        # 迁徙率放大系数上限
    
    # 多世代衰减参数
    multi_gen_decay_threshold: float = 10.0 # 触发多世代衰减的阈值
    multi_gen_decay_power: float = 0.15     # 衰减幂指数
    
    # 净变化钳制
    max_net_growth_ratio: float = 0.60      # 单步最大净增长比例
    max_net_decline_ratio: float = 0.60     # 单步最大净减少比例
    
    # 容量归一上限
    overcapacity_birth_clamp: float = 0.5   # 超容量时繁殖放大系数钳制
    overcapacity_threshold: float = 1.2     # 超容量触发阈值（容量的倍数）


@dataclass
class EcologyMetrics:
    """生态计算性能指标"""
    total_time_ms: float = 0.0
    mortality_time_ms: float = 0.0
    dispersal_time_ms: float = 0.0
    migration_time_ms: float = 0.0
    reproduction_time_ms: float = 0.0
    competition_time_ms: float = 0.0
    species_count: int = 0
    tile_count: int = 0
    backend: str = "numpy"
    
    # 生态统计
    avg_mortality_rate: float = 0.0
    migrating_species: int = 0
    total_population_before: float = 0.0
    total_population_after: float = 0.0


@dataclass
class EcologyResult:
    """生态计算结果"""
    # 更新后的种群张量
    pop: np.ndarray
    
    # 各阶段结果
    mortality_rates: np.ndarray      # (S, H, W) 死亡率
    death_counts: np.ndarray         # (S,) 死亡数
    survivor_counts: np.ndarray      # (S,) 存活数
    
    # 迁徙结果
    migrated_species: list[int] = field(default_factory=list)
    migration_changes: np.ndarray | None = None
    
    # 性能指标
    metrics: EcologyMetrics = field(default_factory=EcologyMetrics)
    
    # 兼容旧系统的结果格式
    tile_mortality: dict[str, dict[int, float]] = field(default_factory=dict)


class TensorEcologyEngine:
    """统一张量生态计算引擎
    
    【核心功能】
    一次调用完成所有物种的：
    1. 死亡率计算（多因子）
    2. 扩散计算（带适宜度引导）
    3. 迁徙计算（压力驱动+猎物追踪）
    4. 繁殖计算（承载力约束）
    5. 竞争计算（种间竞争）
    
    【零循环设计】
    所有计算使用向量化操作，无 Python 循环。
    
    【性能对比】
    - 50物种, 64x64地图:
      - 旧系统: ~2000ms
      - 新系统: ~50ms (Taichi GPU) / ~150ms (NumPy)
    """
    
    def __init__(self, config: EcologyConfig | None = None):
        self.config = config or EcologyConfig()
        self._taichi_ready = _load_ecology_kernels()
        
        # 缓存
        self._species_prefs_cache: np.ndarray | None = None
        self._suitability_cache: np.ndarray | None = None
        self._last_metrics: EcologyMetrics | None = None
        
        if not self._taichi_ready:
            raise RuntimeError("[GPU-only] Taichi GPU 初始化失败，无 NumPy fallback")
        
        logger.info("[TensorEcology] 使用 Taichi GPU 加速")
    
    @property
    def backend(self) -> str:
        """当前计算后端 - GPU-only 模式始终为 taichi"""
        return "taichi"
    
    @property
    def last_metrics(self) -> EcologyMetrics | None:
        """上次计算的性能指标"""
        return self._last_metrics
    
    # ========================================================================
    # 核心：统一生态计算入口
    # ========================================================================
    
    def process_ecology(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_params: np.ndarray,
        species_prefs: np.ndarray,
        turn_index: int = 0,
        trophic_levels: np.ndarray | None = None,
        pressure_overlay: np.ndarray | None = None,
        cooldown_mask: np.ndarray | None = None,
        external_bonus: np.ndarray | None = None,
        decline_streaks: np.ndarray | None = None,
        species_traits: np.ndarray | None = None,
        turn_years: int | None = None,
    ) -> EcologyResult:
        """统一生态计算入口 - 一次调用完成全部计算
        
        【零循环】所有计算使用张量并行，无 Python for 循环
        【v3.0】支持世代缩放：根据 turn_years 和 generation_time 计算 effective_steps
        
        Args:
            pop: 种群张量 (S, H, W)
            env: 环境张量 (C, H, W)
            species_params: 物种参数 (S, F) - 耐受性等
            species_prefs: 物种偏好 (S, 7) - 温度/湿度/栖息地偏好
            turn_index: 当前回合（用于时代缩放）
            trophic_levels: 营养级 (S,) - 用于猎物追踪
            pressure_overlay: 压力叠加层 (C_pressure, H, W)
            cooldown_mask: 迁徙冷却掩码 (S,) True=允许迁徙
            external_bonus: 外部加成 (S, H, W) - 来自重大事件/embedding 的迁徙引导
            decline_streaks: 慢性衰退计数 (S,) - 可选
            species_traits: 物种特质 (S, 14) - 完整特质矩阵，用于精确宜居度计算
            turn_years: 【新】当前回合代表的年数（用于世代缩放）
        
        Returns:
            EcologyResult 包含更新后的种群和各阶段结果
        """
        start_time = time.perf_counter()
        S, H, W = pop.shape
        
        # 【v3.0】获取回合年数
        if turn_years is None:
            turn_years = self.config.turn_years
        
        # 同步 Taichi 运行时（确保与主线程编译的内核兼容）
        import taichi as ti
        ti.sync()
        
        metrics = EcologyMetrics(
            species_count=S,
            tile_count=H * W,
            backend=self.backend,
            total_population_before=float(pop.sum()),
        )
        
        # 确保数据类型
        pop = pop.astype(np.float32)
        env = env.astype(np.float32)
        species_params = species_params.astype(np.float32)
        species_prefs = species_prefs.astype(np.float32)
        
        if trophic_levels is None:
            trophic_levels = np.ones(S, dtype=np.float32)
        else:
            trophic_levels = trophic_levels.astype(np.float32)
        
        if cooldown_mask is None:
            cooldown_mask = np.ones(S, dtype=bool)
        if external_bonus is not None:
            external_bonus = external_bonus.astype(np.float32, copy=False)
        if decline_streaks is None:
            decline_streaks = np.zeros((S,), dtype=np.int32)
        else:
            decline_streaks = decline_streaks.astype(np.int32, copy=False)
        
        # 【新】处理特质矩阵
        use_trait_system = species_traits is not None
        if use_trait_system:
            species_traits = species_traits.astype(np.float32)
        
        # 获取时代缩放因子
        era_scaling = self._get_era_scaling(turn_index)
        
        # 【v3.1】计算 effective_steps（世代缩放 + 缓冲机制）
        # 防止微生物过度膨胀或瞬灭
        cfg = self.config
        
        # 获取世代时间
        if use_trait_system and cfg.generation_scaling_enabled:
            # 从 species_traits[:, 5] 获取繁殖速度（1-10），转换为世代时间
            reproduction_speed = np.clip(species_traits[:, 5], 1.0, 10.0)
            generation_time_days = 3650.0 / reproduction_speed  # 天
            body_size = np.clip(species_traits[:, 6], 1.0, 10.0)  # 体型
        elif species_params.shape[1] >= 6:
            generation_time_days = np.maximum(species_params[:, 5], 1.0)
            body_size = np.clip(species_params[:, 4], 1.0, 100.0) if species_params.shape[1] >= 5 else np.full(S, 10.0)
            # 归一化体型到 1-10
            body_size = np.clip(np.log1p(body_size) / np.log1p(100) * 10, 1.0, 10.0)
        else:
            generation_time_days = np.full(S, cfg.default_generation_time_days, dtype=np.float32)
            body_size = np.full(S, 5.0, dtype=np.float32)
        
        # 计算原始 effective_steps（回合年数 / 世代年数）
        generation_time_years = generation_time_days / 365.0
        raw_effective_steps = np.maximum(1.0, turn_years / (generation_time_years * 365.0))
        
        # 【缓冲1】使用 p90 分位数截断极端值（跨物种平滑）
        p90_steps = np.percentile(raw_effective_steps, 90)
        smoothed_steps = np.minimum(raw_effective_steps, p90_steps * 1.5)
        
        # 【缓冲2】全局上限截断
        smoothed_steps = np.clip(smoothed_steps, cfg.effective_steps_clip_min, cfg.effective_steps_clip_max)
        
        # 【缓冲3】按体型/繁殖速度分层缩放幂指数
        # 小体型/快繁殖用更低的幂，大体型/慢繁殖用更高的幂
        exponents = np.where(
            body_size < 3.0, cfg.small_species_exponent,  # 小体型：0.25
            np.where(body_size < 7.0, cfg.medium_species_exponent, cfg.large_species_exponent)  # 中/大体型
        )
        
        # 应用分层幂函数
        effective_steps = np.power(smoothed_steps, exponents)
        
        # 【缓冲4】多世代衰减：effective_steps > 10 时附加衰减
        high_gen_mask = smoothed_steps > cfg.multi_gen_decay_threshold
        decay_factor = np.where(
            high_gen_mask,
            np.power(smoothed_steps / cfg.multi_gen_decay_threshold, -cfg.multi_gen_decay_power),
            1.0
        )
        effective_steps = effective_steps * decay_factor
        
        # 最终钳制
        effective_steps = np.clip(effective_steps, 1.0, 15.0).astype(np.float32)
        
        # 平均 effective_steps（用于全局参数）
        mean_effective_steps = float(np.mean(effective_steps))
        
        # 【新增】计算各阶段专用的缩放因子（带独立上限）
        birth_scale = np.clip(1.0 + np.log1p(effective_steps - 1) * 0.8, 1.0, cfg.birth_scale_max)
        mortality_scale = np.clip(1.0 + np.log1p(effective_steps - 1) * 0.5, 1.0, cfg.mortality_scale_max)
        diffusion_scale = np.clip(1.0 + np.log1p(effective_steps - 1) * 0.6, 1.0, cfg.diffusion_scale_max)
        migration_scale = np.clip(1.0 + np.log1p(effective_steps - 1) * 0.5, 1.0, cfg.migration_scale_max)
        
        logger.debug(
            f"[TensorEcology] 世代缩放(v3.1): turn_years={turn_years}, "
            f"mean_gen_time={generation_time_days.mean():.1f}天, "
            f"raw_steps_p90={p90_steps:.1f}, mean_eff_steps={mean_effective_steps:.2f}, "
            f"birth_scale=[{birth_scale.min():.2f}, {birth_scale.max():.2f}]"
        )
        
        # 资源压力 & 机动性 & 预估增长率
        resource_pressure = pop.sum(axis=(1, 2))
        if env.shape[0] > 3:
            total_resource = float(np.maximum(env[3].sum(), 1e-6))
            resource_pressure = np.clip(resource_pressure / total_resource, 0.0, 2.0).astype(np.float32)
        else:
            resource_pressure = np.zeros((S,), dtype=np.float32)
        
        species_mobility = np.ones((S,), dtype=np.float32)
        if use_trait_system:
            species_mobility = np.clip(species_traits[:, 7], 1.0, 10.0).astype(np.float32)
        elif species_params.shape[1] >= 3:
            species_mobility = np.clip(species_params[:, 2], 0.5, 3.0).astype(np.float32)
        
        growth_rates = np.zeros((S,), dtype=np.float32)
        if use_trait_system:
            growth_rates = np.clip(species_traits[:, 5] / 5.0, 0.0, 2.0).astype(np.float32)
        elif species_params.shape[1] >= 4:
            growth_rates = np.clip(species_params[:, 3], 0.0, 5.0).astype(np.float32)
        
        # === 阶段1：宜居度计算（先于死亡率）===
        t0 = time.perf_counter()
        if use_trait_system:
            # 使用精确特质匹配
            suitability = self._compute_trait_suitability_tensor(env, species_traits)
        else:
            # 使用旧的简化匹配
            suitability = self._compute_suitability_tensor(env, species_prefs)
        
        # === 阶段2：死亡率计算 ===
        # 【v3.1】使用独立的 mortality_scale（带上限）
        if use_trait_system:
            mortality_rates = self._compute_trait_mortality_tensor(
                pop, env, species_traits, suitability, pressure_overlay, era_scaling, 
                mortality_scale  # 使用缓冲后的 mortality_scale
            )
        else:
            mortality_rates = self._compute_mortality_tensor(
                pop, env, species_params, species_prefs, 
                trophic_levels, pressure_overlay, era_scaling, 
                mortality_scale  # 使用缓冲后的 mortality_scale
            )
        metrics.mortality_time_ms = (time.perf_counter() - t0) * 1000
        
        # 应用死亡率
        pop_after_death = self._apply_mortality_tensor(pop, mortality_rates)
        
        # 计算死亡统计
        death_counts = (pop - pop_after_death).sum(axis=(1, 2))
        survivor_counts = pop_after_death.sum(axis=(1, 2))
        metrics.avg_mortality_rate = float(mortality_rates[pop > 0].mean()) if (pop > 0).any() else 0.0
        
        # === 阶段3：扩散计算 ===
        # 【v3.1】使用缓冲后的 diffusion_scale，迭代次数限制
        t0 = time.perf_counter()
        
        # 计算扩散迭代次数（限制最大次数）
        if turn_index < 30 and cfg.era_scaling_enabled:
            dispersal_iterations = min(
                cfg.early_dispersal_iterations,
                max(1, int(np.mean(diffusion_scale) ** 0.5))
            )
        else:
            dispersal_iterations = 1
        
        # 调整基础扩散率（使用缓冲后的 diffusion_scale）
        mean_diffusion_scale = float(np.mean(diffusion_scale))
        adjusted_diffusion_rate = min(
            cfg.max_diffusion_rate,
            cfg.base_diffusion_rate * mean_diffusion_scale
        )
        
        logger.debug(
            f"turn={turn_index}, "
            f"pop_nonzero_tiles={(pop > 0).any(axis=0).sum()}, "
            f"dispersal_iterations={dispersal_iterations}, "
            f"diffusion_rate={adjusted_diffusion_rate:.4f}"
        )
        
        pop_after_dispersal = pop_after_death.copy()
        for disp_iter in range(dispersal_iterations):
            if use_trait_system:
                pop_after_dispersal = self._compute_trait_dispersal_tensor(
                    pop_after_dispersal, suitability, species_traits, env, 
                    era_scaling, diffusion_scale, adjusted_diffusion_rate
                )
            else:
                pop_after_dispersal = self._compute_dispersal_tensor(
                    pop_after_dispersal, suitability, era_scaling,
                    diffusion_scale, adjusted_diffusion_rate
                )
        
        if dispersal_iterations > 1:
            logger.debug(f"[TensorEcology] 扩散迭代 {dispersal_iterations} 次")
        
        metrics.dispersal_time_ms = (time.perf_counter() - t0) * 1000
        
        logger.info(
            f"扩散后地块数: {((pop_after_dispersal > 0).any(axis=0).sum())}, "
        )

        # === 阶段4：迁徙计算 ===
        t0 = time.perf_counter()
        # 提取每个物种的平均死亡率作为迁徙压力信号 - 向量化
        pop_mask = pop > 0
        mortality_masked = np.where(pop_mask, mortality_rates, 0.0)
        pop_counts = pop_mask.sum(axis=(1, 2))
        pop_counts = np.maximum(pop_counts, 1)  # 避免除零
        species_death_rates = mortality_masked.sum(axis=(1, 2)) / pop_counts
        species_death_rates = species_death_rates.astype(np.float32)
        
        pop_after_migration, migrated = self._compute_migration_tensor(
            pop_after_dispersal, env, species_prefs, species_traits, suitability,
            species_death_rates, trophic_levels, cooldown_mask, era_scaling,
            resource_pressure, growth_rates, species_mobility,
            mortality_rates, external_bonus, decline_streaks,
            turn_index, migration_scale  # 【v3.1】使用缓冲后的 migration_scale
        )
        metrics.migration_time_ms = (time.perf_counter() - t0) * 1000
        metrics.migrating_species = len(migrated)

        logger.info(f"迁徙后地块数: {((pop_after_migration > 0).any(axis=0).sum())}, 迁徙物种数: {len(migrated)}")
        
        # === 阶段5：繁殖计算 ===
        # 【v3.1】使用缓冲后的 birth_scale + 压力-繁殖反相扣 + 容量归一
        t0 = time.perf_counter()
        
        # 【缓冲5】压力-繁殖反相扣：高死亡时降低繁殖放大
        avg_mortality_per_species = np.where(
            (pop_after_migration > 0).sum(axis=(1, 2)) > 0,
            np.where(pop_after_migration > 0, mortality_rates, 0).sum(axis=(1, 2)) / 
            np.maximum((pop_after_migration > 0).sum(axis=(1, 2)), 1),
            0.0
        )
        pressure_discount = np.clip(1.0 - avg_mortality_per_species, 0.3, 1.0)
        adjusted_birth_scale = birth_scale * pressure_discount
        
        pop_after_reproduction = self._compute_reproduction_tensor(
            pop_after_migration, env, suitability, era_scaling, adjusted_birth_scale
        )
        metrics.reproduction_time_ms = (time.perf_counter() - t0) * 1000
        
        # === 阶段6：竞争计算 ===
        t0 = time.perf_counter()
        if use_trait_system:
            # 使用基于特质的竞争系统
            final_pop = self._compute_trait_competition_tensor(
                pop_after_reproduction, suitability, species_traits, era_scaling
            )
        else:
            final_pop = self._compute_competition_tensor(
                pop_after_reproduction, suitability, era_scaling
            )
        metrics.competition_time_ms = (time.perf_counter() - t0) * 1000
        
        # === 阶段7：净变化钳制 ===
        # 【v3.1 缓冲6】防止单步爆炸或瞬灭
        # 对每个格子的净变化设置 [-max_decline, +max_growth] 比例上限
        net_change = final_pop - pop
        
        # 【关键修复】对于已有种群的地块，使用比例钳制
        # 对于新地块（原种群为0），使用绝对值钳制
        has_pop_mask = pop > 0
        
        # 已有种群的地块：按比例钳制
        max_growth_existing = pop * cfg.max_net_growth_ratio
        max_decline_existing = pop * cfg.max_net_decline_ratio
        
        # 新地块（原种群为0）：允许合理的初始种群
        # 使用邻居平均值或全局平均值作为参考
        pop_per_species = pop.sum(axis=(1, 2), keepdims=True) / np.maximum((pop > 0).sum(axis=(1, 2), keepdims=True), 1)
        # 新地块的最大增长 = 该物种平均每地块种群的 max_net_growth_ratio
        # 这允许扩散/迁徙建立新据点，但不会爆炸
        max_growth_new = pop_per_species * cfg.max_net_growth_ratio * np.ones_like(pop)
        # 新地块没有种群，所以 decline 为 0
        max_decline_new = np.zeros_like(pop)
        
        # 合并：已有种群用比例钳制，新地块用绝对值钳制
        max_growth = np.where(has_pop_mask, max_growth_existing, max_growth_new)
        max_decline = np.where(has_pop_mask, max_decline_existing, max_decline_new)
        
        
        # 钳制净变化
        clamped_change = np.clip(net_change, -max_decline, max_growth)
        logger.debug(
            f"[TensorEcology] 净变化钳制前: 增长={net_change[net_change > 0].sum():.1f}, "
            f"减少={-net_change[net_change < 0].sum():.1f}, "
            f"有变化地块={(net_change != 0).any(axis=0).sum()}, "
            f"钳制后: 增长={clamped_change[clamped_change > 0].sum():.1f}, "
            f"减少={-clamped_change[clamped_change < 0].sum():.1f}, "
            f"有变化地块={(clamped_change != 0).any(axis=0).sum()}"
        )
        
        # 应用钳制后的变化
        final_pop = np.maximum(0.0, pop + clamped_change)
        
        # 统计被钳制的程度
        clamp_ratio = np.abs(net_change - clamped_change).sum() / (np.abs(net_change).sum() + 1e-6)
        if clamp_ratio > 0.05:
            logger.debug(f"[TensorEcology] 净变化钳制: {clamp_ratio:.1%} 的变化被限制")
        
        metrics.total_population_after = float(final_pop.sum())
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        self._last_metrics = metrics
        
        # 同步 Taichi 确保所有 GPU 操作完成
        ti.sync()
        
        logger.info(
            f"[TensorEcology] 完成: {S}物种, {H}x{W}地图, "
            f"耗时={metrics.total_time_ms:.1f}ms, 后端={metrics.backend}, "
            f"平均死亡率={metrics.avg_mortality_rate:.1%}, "
            f"特质系统={'启用' if use_trait_system else '禁用'}, "
            f"最终地块数: {((final_pop > 0).any(axis=0).sum())}, "
            f"总人口: {final_pop.sum():.1f}"
        )
        
        return EcologyResult(
            pop=final_pop,
            mortality_rates=mortality_rates,
            death_counts=death_counts.astype(np.int32),
            survivor_counts=survivor_counts.astype(np.int32),
            migrated_species=migrated,
            metrics=metrics,
        )
    
    # ========================================================================
    # 张量化死亡率计算
    # ========================================================================
    
    def _compute_mortality_tensor(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_params: np.ndarray,
        species_prefs: np.ndarray,
        trophic_levels: np.ndarray,
        pressure_overlay: np.ndarray | None,
        era_scaling: float,
        mortality_scale: np.ndarray | None = None,
    ) -> np.ndarray:
        """张量化多因子死亡率计算 - GPU 加速
        
        【v3.1】使用缓冲后的 mortality_scale（已带上限）
        """
        S, H, W = pop.shape
        cfg = self.config
        
        # 确保压力叠加层存在
        if pressure_overlay is None:
            pressure_overlay = np.zeros((1, H, W), dtype=np.float32)
        
        # 准备 mortality_scale（已在上层计算时带上限）
        if mortality_scale is None:
            mortality_scale_arr = np.ones(S, dtype=np.float32)
        else:
            mortality_scale_arr = mortality_scale.astype(np.float32)
        
        # === Taichi GPU 计算 ===
        result = np.zeros((S, H, W), dtype=np.float32)
        
        # 确保环境张量有足够的通道
        C = env.shape[0]
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0  # 默认陆地
            env = padded_env
        
        _taichi_kernels.kernel_multifactor_mortality_v2(
            pop.astype(np.float32),
            env.astype(np.float32),
            species_prefs.astype(np.float32),
            species_params.astype(np.float32),
            trophic_levels.astype(np.float32),
            pressure_overlay.astype(np.float32),
            mortality_scale_arr,  # 【v3.1】使用缓冲后的 mortality_scale
            result,
            float(cfg.base_mortality),
            float(cfg.temp_mortality_weight),
            float(cfg.competition_weight),
            float(cfg.resource_weight),
            float(cfg.capacity_multiplier),
            float(era_scaling),
        )
        
        total_mortality = result
        
        return np.clip(total_mortality, 0.01, 0.95).astype(np.float32)
    
    def _apply_mortality_tensor(
        self,
        pop: np.ndarray,
        mortality: np.ndarray,
    ) -> np.ndarray:
        """应用死亡率 [Taichi GPU]"""
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_apply_mortality(
            pop.astype(np.float32),
            mortality.astype(np.float32),
            result,
        )
        return result
    
    # ========================================================================
    # 张量化扩散计算
    # ========================================================================
    
    def _compute_suitability_tensor(
        self,
        env: np.ndarray,
        species_prefs: np.ndarray,
    ) -> np.ndarray:
        """计算适宜度矩阵 [Taichi GPU]"""
        S = species_prefs.shape[0]
        C, H, W = env.shape
        
        # 确保环境张量有足够的通道
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0  # 默认陆地
            env = padded_env
        
        habitat_mask = np.ones((S, H, W), dtype=np.float32)
        result = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_compute_suitability(
            env.astype(np.float32),
            species_prefs.astype(np.float32),
            habitat_mask,
            result,
        )
        return result
    
    def _compute_trait_suitability_tensor(
        self,
        env: np.ndarray,
        species_traits: np.ndarray,
    ) -> np.ndarray:
        """计算基于特质的精确适宜度矩阵 [Taichi GPU]
        
        【新】使用完整特质矩阵进行精确环境-特质匹配
        """
        S = species_traits.shape[0]
        C, H, W = env.shape
        
        # 确保环境张量有足够的通道
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0  # 默认陆地
            env = padded_env
        
        result = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_compute_trait_suitability(
            env.astype(np.float32),
            species_traits.astype(np.float32),
            result,
        )
        return result
    
    def _compute_trait_mortality_tensor(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_traits: np.ndarray,
        suitability: np.ndarray,
        pressure_overlay: np.ndarray | None,
        era_scaling: float,
        mortality_scale: np.ndarray | None = None,
    ) -> np.ndarray:
        """基于特质的精确死亡率计算 [Taichi GPU]
        
        【v3.1】使用缓冲后的 mortality_scale（已带上限）
        """
        S, H, W = pop.shape
        cfg = self.config
        
        # 确保压力叠加层存在
        if pressure_overlay is None:
            pressure_overlay = np.zeros((1, H, W), dtype=np.float32)
        
        # 准备 mortality_scale
        if mortality_scale is None:
            mortality_scale_arr = np.ones(S, dtype=np.float32)
        else:
            mortality_scale_arr = mortality_scale.astype(np.float32)
        
        # 确保环境张量有足够的通道
        C = env.shape[0]
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0
            env = padded_env
        
        result = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_trait_mortality_v2(
            pop.astype(np.float32),
            env.astype(np.float32),
            species_traits.astype(np.float32),
            suitability.astype(np.float32),
            pressure_overlay.astype(np.float32),
            mortality_scale_arr,  # 【v3.1】使用缓冲后的 mortality_scale
            result,
            float(cfg.base_mortality),
            float(era_scaling),
        )
        
        return np.clip(result, 0.01, 0.95).astype(np.float32)
    
    def _compute_trait_dispersal_tensor(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        species_traits: np.ndarray,
        env: np.ndarray,
        era_scaling: float,
        diffusion_scale: np.ndarray | None = None,
        override_diffusion_rate: float | None = None,
    ) -> np.ndarray:
        """基于特质的扩散计算 [Taichi GPU]
        
        【v3.1】使用缓冲后的 diffusion_scale + 背景扩散 + 栖息地连通性检查
        """
        cfg = self.config
        S = pop.shape[0]
        
        # 时代缩放
        effective_scaling = max(1.0, era_scaling ** 0.5)
        
        if override_diffusion_rate is not None:
            diffusion_rate = override_diffusion_rate
        else:
            diffusion_rate = min(cfg.max_diffusion_rate, cfg.base_diffusion_rate * effective_scaling)
        
        # 确保环境张量有足够的通道
        C, H, W = env.shape
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0  # 默认陆地
            env = padded_env
        
        # 准备 diffusion_scale（已在上层计算时带上限）
        if diffusion_scale is None:
            diffusion_scale_arr = np.ones(S, dtype=np.float32)
        else:
            diffusion_scale_arr = diffusion_scale.astype(np.float32)
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_trait_diffusion_v2(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            species_traits.astype(np.float32),
            env.astype(np.float32),
            diffusion_scale_arr,  # 【v3.1】使用缓冲后的 diffusion_scale
            result,
            float(diffusion_rate),
            float(cfg.background_diffusion_rate),
            float(cfg.density_pressure_threshold),
            float(cfg.suit_escape_threshold),
        )
        return result
    
    def _compute_trait_competition_tensor(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        species_traits: np.ndarray,
        era_scaling: float,
    ) -> np.ndarray:
        """基于特质的竞争计算 [Taichi GPU]
        
        【新】使用局部适应度和生态位重叠决定竞争结果
        """
        S, H, W = pop.shape
        
        # 竞争强度（随时代调整）
        base_strength = 0.08
        if era_scaling > 1.5:
            base_strength *= max(0.6, 1.0 / (era_scaling ** 0.15))
        
        # 1. 计算局部适应度
        local_fitness = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_compute_local_fitness(
            suitability.astype(np.float32),
            species_traits.astype(np.float32),
            pop.astype(np.float32),
            local_fitness,
        )
        
        # 2. 计算生态位重叠矩阵
        niche_overlap = np.zeros((S, S), dtype=np.float32)
        _taichi_kernels.kernel_compute_niche_overlap_matrix(
            species_traits.astype(np.float32),
            niche_overlap,
        )
        
        # 3. 应用基于特质的竞争
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_apply_trait_competition(
            pop.astype(np.float32),
            local_fitness,
            niche_overlap,
            result,
            float(base_strength),
        )
        
        return result
    
    def _compute_dispersal_tensor(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        era_scaling: float,
        diffusion_scale: np.ndarray | None = None,
        override_diffusion_rate: float | None = None,
    ) -> np.ndarray:
        """张量化扩散计算 [Taichi GPU]
        
        【v3.1】使用缓冲后的 diffusion_scale（已带上限）
        """
        cfg = self.config
        S = pop.shape[0]
        
        # 时代缩放：早期时代扩散更快
        effective_scaling = max(1.0, era_scaling ** 0.5)
        
        if override_diffusion_rate is not None:
            diffusion_rate = override_diffusion_rate
        else:
            diffusion_rate = min(cfg.max_diffusion_rate, cfg.base_diffusion_rate * effective_scaling)
        
        # 准备背景扩散率
        background_rate = cfg.background_diffusion_rate
        
        # 准备 diffusion_scale（已在上层计算时带上限）
        if diffusion_scale is None:
            diffusion_scale_arr = np.ones(S, dtype=np.float32)
        else:
            diffusion_scale_arr = diffusion_scale.astype(np.float32)
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_advanced_diffusion_v2(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            diffusion_scale_arr,  # 【v3.1】使用缓冲后的 diffusion_scale
            result,
            float(diffusion_rate),
            float(background_rate),
            float(cfg.density_pressure_threshold),
            float(cfg.suit_escape_threshold),
        )
        return result
    
    # ========================================================================
    # 张量化迁徙计算
    # ========================================================================
    
    def _compute_migration_tensor(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_prefs: np.ndarray,
        species_traits: np.ndarray | None,
        suitability: np.ndarray,
        death_rates: np.ndarray,
        trophic_levels: np.ndarray,
        cooldown_mask: np.ndarray,
        era_scaling: float,
        resource_pressure: np.ndarray,
        growth_rates: np.ndarray,
        species_mobility: np.ndarray,
        mortality_rates: np.ndarray,
        external_bonus: np.ndarray | None,
        decline_streaks: np.ndarray,
        turn_index: int = 0,
        migration_scale: np.ndarray | None = None,
    ) -> tuple[np.ndarray, list[int]]:
        """张量化迁徙计算 v3.1 - 使用缓冲后的 migration_scale
        
        【v3.0 新增】
        - 早期时代降低 score_threshold
        - 全局拥挤加成（total_pop / total_capacity > 0.6）
        - 栖息地掩码改为衰减式
        - 根据世代时间放大 max_distance
        
        Returns:
            (迁徙后种群, 已迁徙物种索引列表)
        """
        cfg = self.config
        S, H, W = pop.shape
        
        # 【v3.0】计算全局拥挤度
        total_pop = pop.sum()
        if env.shape[0] > 3:
            vegetation = env[3]
            total_capacity = float(np.maximum(vegetation.sum() * cfg.capacity_multiplier, 1e-6))
        else:
            total_capacity = float(H * W * 100)
        global_crowding = total_pop / total_capacity
        
        # 【v3.0】动态 score_threshold（早期时代更低）
        if turn_index < 30:
            current_score_threshold = cfg.early_score_threshold
        else:
            current_score_threshold = cfg.score_threshold
        
        # 【v3.1】根据世代缩放/机动性放大 max_distance
        # 高机动性或快繁殖物种可以迁徙更远
        mobility_factor = np.clip(species_mobility.max(), 0.5, 3.0)
        if migration_scale is not None:
            generation_factor = 1.0 + 0.15 * np.log1p(migration_scale.mean())
        else:
            generation_factor = 1.0
        max_distance = float(
            np.clip(cfg.max_migration_distance * mobility_factor * generation_factor, 1.0, 25.0)
        )
        
        # 1. 计算距离权重 (S, H, W)
        distance_weights = self._compute_distance_weights_tensor(pop, max_distance)
        
        # 【v3.0】栖息地掩码改为衰减式而非硬屏蔽
        if env.shape[0] >= 6 and species_prefs.shape[1] >= 6:
            is_land = env[4] > 0.5  # (H, W)
            is_sea = env[5] > 0.5   # (H, W)
            land_pref = species_prefs[:, 4]  # (S,)
            sea_pref = species_prefs[:, 5]   # (S,)
            coast_pref = species_prefs[:, 6] if species_prefs.shape[1] > 6 else np.zeros(S, dtype=np.float32)
            
            land_only = (land_pref > sea_pref + 0.2)[:, None, None]
            sea_only = (sea_pref > land_pref + 0.2)[:, None, None]
            amphibious = ((coast_pref > 0.3) | ((land_pref > 0.3) & (sea_pref > 0.3)))[:, None, None]
            
            land_mask = is_land[None, ...]
            sea_mask = is_sea[None, ...]
            
            # 【v3.0】使用衰减而非硬屏蔽
            attenuation = cfg.habitat_attenuation_factor  # 0.5
            # 陆地物种在海洋：衰减而非 0
            distance_weights = np.where(
                land_only & ~land_mask,
                distance_weights * attenuation,
                distance_weights
            )
            # 海洋物种在陆地：衰减而非 0
            distance_weights = np.where(
                sea_only & ~sea_mask,
                distance_weights * attenuation,
                distance_weights
            )
            # 两栖物种：陆地 1.0，海洋 0.7
            amphibious_mask = amphibious.astype(np.float32)
            distance_weights = distance_weights * (
                1.0 - amphibious_mask + amphibious_mask * (land_mask * 1.0 + sea_mask * 0.7)
            )
        
        distance_weights = distance_weights.reshape(S, H, W)
        
        # 2. 计算猎物密度（用于消费者）(S, H, W)
        prey_density = self._compute_prey_density_tensor(pop, trophic_levels)
        
        # 3. 计算迁徙分数 (S, H, W) - 【v3.0】传递species_traits用于栖息地检查
        migration_scores = self._compute_migration_scores_tensor(
            pop, env, species_prefs, species_traits, suitability, distance_weights, death_rates, 
            prey_density, trophic_levels,
            resource_pressure, growth_rates, species_mobility,
            mortality_rates, external_bonus, decline_streaks
        )
        
        # 4. 应用冷却期掩码
        cooldown_3d = cooldown_mask[:, np.newaxis, np.newaxis]
        migration_scores = np.where(cooldown_3d, migration_scores, 0.0)
        
        # 【v3.0】全局拥挤加成
        if global_crowding > 0.6:
            crowding_bonus = cfg.crowding_migration_bonus * (global_crowding - 0.6) / 0.4
            migration_scores = migration_scores + crowding_bonus
            logger.debug(f"[迁徙] 全局拥挤={global_crowding:.2f}, 加成={crowding_bonus:.3f}")
        
        # 5. 计算迁徙率（高压力时迁徙更多）
        migration_rates = np.full(S, cfg.base_migration_rate, dtype=np.float32)
        high_pressure = death_rates > cfg.pressure_threshold
        # 模式化迁徙率：压力>溢出>饱和>常规
        overflow = (growth_rates > 1.10) & (resource_pressure > cfg.saturation_threshold)
        oversat = resource_pressure > cfg.saturation_threshold * 1.2
        migration_rates = np.where(
            overflow,
            np.minimum(0.85, cfg.base_migration_rate * 2.2),
            migration_rates,
        )
        migration_rates = np.where(
            oversat & (~overflow),
            np.minimum(0.65, cfg.base_migration_rate * 1.6),
            migration_rates,
        )
        migration_rates = np.where(
            high_pressure & (~oversat) & (~overflow),
            np.minimum(0.75, cfg.base_migration_rate * 1.9),
            migration_rates,
        )
        
        # 时代缩放
        if era_scaling > 1.5:
            migration_rates *= min(2.5, era_scaling ** 0.35)
        
        # 【v3.1】世代缩放：使用缓冲后的 migration_scale（已带上限）
        if migration_scale is not None:
            # migration_scale 已在上层计算时带了上限（cfg.migration_scale_max）
            migration_rates = migration_rates * migration_scale.astype(np.float32)
        
        # 6. 执行迁徙 [Taichi GPU]
        new_pop = np.zeros_like(pop, dtype=np.float32)
        
        # 【v3.0】动态 base_long_jump
        if turn_index < 30:
            base_long_jump = cfg.early_long_jump_rate  # 早期时代更高
        else:
            base_long_jump = cfg.base_long_jump_rate
        
        # 飞行物种进一步提升长跳概率
        if env.shape[0] >= 6 and species_prefs.shape[1] >= 6:
            land_pref = species_prefs[:, 4]
            sea_pref = species_prefs[:, 5]
            coast_pref = species_prefs[:, 6] if species_prefs.shape[1] > 6 else np.zeros_like(land_pref)
            flying = (land_pref > 0.3) & (sea_pref > 0.3) & (coast_pref > 0.3)
            if flying.any():
                base_long_jump = min(0.08, base_long_jump * 1.8)
        
        # 确保 species_traits 存在（如果没有，从 species_prefs 构造）
        if species_traits is None:
            # 构造默认特质矩阵
            traits_for_migration = np.zeros((S, 14), dtype=np.float32)
            traits_for_migration[:, 7] = 5.0  # 默认机动性
            if species_prefs.shape[1] >= 7:
                traits_for_migration[:, 8] = species_prefs[:, 4]  # land_pref
                traits_for_migration[:, 9] = species_prefs[:, 5]  # ocean_pref
                traits_for_migration[:, 10] = species_prefs[:, 6]  # coast_pref
            else:
                traits_for_migration[:, 8] = 1.0  # 默认陆地
        else:
            traits_for_migration = species_traits.astype(np.float32)
        
        # 确保环境张量有足够的通道
        C = env.shape[0]
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0  # 默认陆地
            env_for_migration = padded_env
        else:
            env_for_migration = env.astype(np.float32)
        
        _taichi_kernels.kernel_execute_migration(
            pop.astype(np.float32),
            migration_scores.astype(np.float32),
            distance_weights.astype(np.float32),
            traits_for_migration,
            env_for_migration,
            new_pop,
            migration_rates.astype(np.float32),
            float(current_score_threshold),  # 【v3.0】使用动态阈值
            float(base_long_jump),
        )
        
        # 识别已迁徙的物种 - 向量化
        change_per_species = np.abs(new_pop - pop).sum(axis=(1, 2))
        pop_per_species = pop.sum(axis=(1, 2)) + 1e-6
        change_ratio = change_per_species / pop_per_species
        migrated = np.where(change_ratio > 0.05)[0].tolist()
        
        return new_pop, migrated
    
    def _compute_distance_weights_tensor(
        self,
        pop: np.ndarray,
        max_distance: float,
    ) -> np.ndarray:
        """计算距离权重 [Taichi GPU]"""
        S, H, W = pop.shape
        result = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_compute_distance_weights(
            pop.astype(np.float32),
            result,
            float(max_distance),
        )
        return result
    
    def _compute_prey_density_tensor(
        self,
        pop: np.ndarray,
        trophic_levels: np.ndarray,
    ) -> np.ndarray:
        """计算猎物密度 - 向量化，排除同营养级/自食"""
        S, H, W = pop.shape
        
        trophic_2d = trophic_levels[:, np.newaxis]
        trophic_t = trophic_levels[np.newaxis, :]
        
        prey_min = trophic_2d - 1.5
        prey_max = trophic_2d - 0.5
        
        prey_matrix = ((trophic_t >= prey_min) & (trophic_t <= prey_max)).astype(np.float32)
        # 排除同营养级与自身
        prey_matrix *= (np.abs(trophic_t - trophic_2d) > 1e-3).astype(np.float32)
        
        pop_flat = pop.reshape(S, H * W)
        prey_pop_flat = prey_matrix @ pop_flat
        prey_pop = prey_pop_flat.reshape(S, H, W)
        
        total_pop = pop.sum(axis=0) + 1e-6
        prey_normalized = prey_pop / total_pop
        
        consumer_mask = (trophic_levels >= 2.0)[:, np.newaxis, np.newaxis]
        return np.where(consumer_mask, prey_normalized, 1.0).astype(np.float32)
    
    def _compute_migration_scores_tensor(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_prefs: np.ndarray,
        species_traits: np.ndarray | None,
        suitability: np.ndarray,
        distance_weights: np.ndarray,
        death_rates: np.ndarray,
        prey_density: np.ndarray,
        trophic_levels: np.ndarray,
        resource_pressure: np.ndarray,
        growth_rates: np.ndarray,
        species_mobility: np.ndarray,
        mortality_rates: np.ndarray,
        external_bonus: np.ndarray | None,
        decline_streaks: np.ndarray,
    ) -> np.ndarray:
        """计算迁徙分数 [Taichi GPU] - 【v3.0】加入栖息地类型约束"""
        cfg = self.config
        S, H, W = pop.shape
        
        # 确保距离权重维度正确 (S, H, W)
        distance_weights = distance_weights.reshape(S, H, W)
        
        # 确保 species_traits 存在
        if species_traits is None:
            traits_for_scores = np.zeros((S, 14), dtype=np.float32)
            traits_for_scores[:, 7] = 5.0  # 默认机动性
            if species_prefs.shape[1] >= 7:
                traits_for_scores[:, 8] = species_prefs[:, 4]
                traits_for_scores[:, 9] = species_prefs[:, 5]
                traits_for_scores[:, 10] = species_prefs[:, 6]
            else:
                traits_for_scores[:, 8] = 1.0
        else:
            traits_for_scores = species_traits.astype(np.float32)
        
        # 确保环境张量有足够的通道
        C = env.shape[0]
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0
            env_for_scores = padded_env
        else:
            env_for_scores = env.astype(np.float32)
        
        result = np.zeros_like(pop, dtype=np.float32)
        if hasattr(_taichi_kernels, "kernel_migration_decision_v2"):
            _taichi_kernels.kernel_migration_decision_v2(
                pop.astype(np.float32),
                suitability.astype(np.float32),
                distance_weights.astype(np.float32),
                death_rates.astype(np.float32),
                resource_pressure.astype(np.float32),
                prey_density.astype(np.float32),
                trophic_levels.astype(np.float32),
                traits_for_scores,
                env_for_scores,
                result,
                float(cfg.pressure_threshold),
                float(cfg.saturation_threshold),
                float(cfg.saturation_threshold * 1.2),
                float(0.35),  # prey_scarcity_threshold fallback
                float(0.3),   # prey_weight fallback
                float(0.1),   # oversat bonus fallback
                float(2.0),   # consumer trophic threshold
            )
        else:
            _taichi_kernels.kernel_migration_decision(
                pop.astype(np.float32),
                suitability.astype(np.float32),
                distance_weights.astype(np.float32),
                death_rates.astype(np.float32),
                result,
                float(cfg.pressure_threshold),
                float(cfg.saturation_threshold),
            )
            # 旧内核：融合猎物追踪（数据后处理）
            consumer_mask = (trophic_levels >= 2.0)[:, np.newaxis, np.newaxis]
            result = np.where(
                consumer_mask,
                result * 0.7 + prey_density * suitability * 0.3,
                result
            )
        
        # === 梯度/避难所/外部加成（CPU 后处理，保持轻量） ===
        if mortality_rates is not None:
            death_max = mortality_rates.max(axis=(1, 2))
            death_min = mortality_rates.min(axis=(1, 2))
            gradient = death_max - death_min
            valid_grad = gradient >= 0.10
            grad_bonus = np.where(
                death_max[:, np.newaxis, np.newaxis] > 1e-6,
                (death_max[:, np.newaxis, np.newaxis] - mortality_rates) / (death_max[:, np.newaxis, np.newaxis] + 1e-6),
                0.0,
            )
            grad_bonus *= valid_grad[:, np.newaxis, np.newaxis]
            result += grad_bonus.astype(np.float32) * 0.3
            
            critical_mask = mortality_rates >= 0.50
            critical_ratio = critical_mask.mean(axis=(1, 2))
            refuge_trigger = critical_ratio >= 0.50
            refuge_bonus = (1.0 - mortality_rates) * refuge_trigger[:, np.newaxis, np.newaxis]
            result += refuge_bonus.astype(np.float32) * 0.5
        
        # 外部事件/embedding 加成
        if external_bonus is not None:
            result += external_bonus.astype(np.float32)
        
        # 慢性衰退：提升整体迁徙意愿
        decline_mask = (decline_streaks >= 2)[:, np.newaxis, np.newaxis]
        result = np.where(decline_mask, result * 1.3, result)
        
        # 栖息地连通性：陆/海偏好与环境通道匹配
        if env.shape[0] >= 6 and species_prefs is not None and species_prefs.shape[1] >= 6:
            is_land = env[4] > 0.5
            is_sea = env[5] > 0.5
            land_pref = species_prefs[:, 4][:, None, None]
            sea_pref = species_prefs[:, 5][:, None, None]
            habitat_mask = np.ones_like(result, dtype=bool)
            land_only = (land_pref > 0.5) & (sea_pref < 0.1)
            sea_only = (sea_pref > 0.5) & (land_pref < 0.1)
            habitat_mask = np.where(land_only, is_land[None, ...], habitat_mask)
            habitat_mask = np.where(sea_only, is_sea[None, ...], habitat_mask)
            result *= habitat_mask.astype(np.float32)
        
        # 保留非相邻地块用于长跳：按距离权重与机动性衰减
        mobility_scale = np.clip(species_mobility[:, None, None], 0.5, 3.0)
        result *= (0.5 + 0.5 * distance_weights * mobility_scale)
        return result
    
    
    # ========================================================================
    # 张量化繁殖计算
    # ========================================================================
    
    def _compute_reproduction_tensor(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        suitability: np.ndarray,
        era_scaling: float,
        birth_scale: np.ndarray | None = None,
    ) -> np.ndarray:
        """张量化繁殖计算 - 世代缩放
        
        【v3.1】使用缓冲后的 birth_scale + 容量归一 + 压力-繁殖反相扣
        """
        cfg = self.config
        S, H, W = pop.shape
        
        # 时代缩放
        effective_scaling = max(1.0, era_scaling ** 0.5)
        base_birth = cfg.base_birth_rate * effective_scaling
        
        # 【v3.1】使用缓冲后的 birth_scale
        if birth_scale is not None and cfg.generation_scaling_enabled:
            mean_scale = float(np.mean(birth_scale))
            birth_rate = min(cfg.birth_scale_max * base_birth, base_birth * mean_scale)
        else:
            birth_rate = min(2.0, base_birth)
        
        # 承载力
        if env.shape[0] > 3:
            vegetation = env[3]
        elif env.shape[0] > 4:
            vegetation = env[4]
        else:
            vegetation = np.ones((H, W), dtype=np.float32) * 0.5
        
        capacity = vegetation * cfg.capacity_multiplier
        if era_scaling > 1.5:
            capacity *= max(1.0, era_scaling ** 0.3)
        
        # 【v3.1 缓冲7】容量归一：超容量时钳制繁殖放大系数
        total_pop_per_tile = pop.sum(axis=0)  # (H, W)
        overcapacity_mask = total_pop_per_tile > capacity * cfg.overcapacity_threshold
        
        # 准备 birth_scale（已在上层计算时带上限和压力折扣）
        if birth_scale is None:
            birth_scale_arr = np.ones(S, dtype=np.float32)
        else:
            birth_scale_arr = birth_scale.astype(np.float32)
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_reproduction_v2(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            capacity.astype(np.float32),
            birth_scale_arr,  # 【v3.1】使用缓冲后的 birth_scale
            float(birth_rate),
            result,
        )
        
        # 【v3.1】超容量格子的繁殖结果额外钳制
        if overcapacity_mask.any():
            # 对超容量格子，限制净增长
            clamp_factor = np.where(
                overcapacity_mask[np.newaxis, ...],
                cfg.overcapacity_birth_clamp,
                1.0
            )
            net_growth = result - pop
            clamped_growth = net_growth * clamp_factor
            result = np.maximum(0.0, pop + clamped_growth)
        
        return result
    
    # ========================================================================
    # 张量化竞争计算
    # ========================================================================
    
    def _compute_competition_tensor(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        era_scaling: float,
    ) -> np.ndarray:
        """张量化种间竞争 [Taichi GPU]"""
        # 竞争强度（随时间降低）
        base_strength = 0.05
        if era_scaling > 1.5:
            base_strength *= max(0.5, 1.0 / (era_scaling ** 0.2))
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_competition(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            result,
            float(base_strength),
        )
        return result
    
    # ========================================================================
    # 辅助方法
    # ========================================================================
    
    def _get_era_scaling(self, turn_index: int) -> float:
        """获取时代缩放因子
        
        【v2.2】调整时代缩放：
        - 保持早期时代的扩散速度优势
        - 但不再过度降低死亡率（在 kernel_multifactor_mortality 中已调整）
        - 缩放因子主要影响扩散和迁徙，对死亡率的影响减小
        
        参考 config.py 中物种分布地块限制：
        - terrestrial_top_k = 4
        - marine_top_k = 3
        物种分布是有限的，不会无限扩散
        """
        if not self.config.era_scaling_enabled:
            return 1.0
        
        # 【v2.2 调整】降低时代缩放的极端值
        # 这样早期时代不会让死亡率过低
        if turn_index < 10:
            return 3.0   # 太古宙：快速扩散（微生物时代）
        elif turn_index < 30:
            return 4.0   # 元古宙：较快扩散（简单生命爆发）
        elif turn_index < 50:
            return 2.0   # 古生代：中等速度
        elif turn_index < 70:
            return 1.3   # 中生代：接近正常
        else:
            return 1.0   # 新生代：正常速度
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._species_prefs_cache = None
        self._suitability_cache = None


# ============================================================================
# 全局实例管理
# ============================================================================

_global_engine: TensorEcologyEngine | None = None


def get_ecology_engine(config: EcologyConfig | None = None) -> TensorEcologyEngine:
    """获取全局生态计算引擎实例"""
    global _global_engine
    if _global_engine is None:
        _global_engine = TensorEcologyEngine(config)
    return _global_engine


def reset_ecology_engine() -> None:
    """重置全局生态计算引擎"""
    global _global_engine
    if _global_engine is not None:
        _global_engine.clear_cache()
    _global_engine = None


# ============================================================================
# 辅助函数：从 Species 对象提取参数
# ============================================================================

def extract_species_params(
    species_list: list,
    species_map: dict[str, int],
) -> np.ndarray:
    """从物种列表提取参数矩阵
    
    Args:
        species_list: Species 对象列表
        species_map: {lineage_code: tensor_index}
    
    Returns:
        物种参数矩阵 (S, 8)
        [耐热性, 耐寒性, 耐旱性, 盐度耐受, body_size, generation_time, trophic_level, population]
    """
    S = len(species_map)
    params = np.zeros((S, 8), dtype=np.float32)
    
    for species in species_list:
        lineage = species.lineage_code
        if lineage not in species_map:
            continue
        
        idx = species_map[lineage]
        traits = species.abstract_traits or {}
        morph = species.morphology_stats or {}
        
        params[idx, 0] = traits.get("耐热性", 5) / 10.0
        params[idx, 1] = traits.get("耐寒性", 5) / 10.0
        params[idx, 2] = traits.get("耐旱性", 5) / 10.0
        params[idx, 3] = traits.get("耐盐性", 5) / 10.0
        params[idx, 4] = morph.get("body_length_cm", 10.0)
        params[idx, 5] = morph.get("generation_time_days", 30)
        params[idx, 6] = getattr(species, 'trophic_level', 1.0) or 1.0
        params[idx, 7] = morph.get("population", 0) or 0
    
    return params


def extract_species_prefs(
    species_list: list,
    species_map: dict[str, int],
) -> np.ndarray:
    """从物种列表提取偏好矩阵
    
    Args:
        species_list: Species 对象列表
        species_map: {lineage_code: tensor_index}
    
    Returns:
        物种偏好矩阵 (S, 7)
        [温度偏好, 湿度偏好, 海拔偏好, 资源需求, 陆地, 海洋, 海岸]
    """
    S = len(species_map)
    prefs = np.zeros((S, 7), dtype=np.float32)
    
    for species in species_list:
        lineage = species.lineage_code
        if lineage not in species_map:
            continue
        
        idx = species_map[lineage]
        traits = species.abstract_traits or {}
        habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
        trophic = getattr(species, 'trophic_level', 1.0) or 1.0
        
        # 温度偏好 [-1, 1]
        heat_pref = traits.get("耐热性", 5) / 10.0
        cold_pref = traits.get("耐寒性", 5) / 10.0
        prefs[idx, 0] = heat_pref - cold_pref
        
        # 湿度偏好 [0, 1]
        drought_pref = traits.get("耐旱性", 5) / 10.0
        prefs[idx, 1] = 1.0 - drought_pref
        
        # 海拔偏好（中性）
        prefs[idx, 2] = 0.0
        
        # 资源需求
        prefs[idx, 3] = min(1.0, trophic / 3.0)
        
        # 栖息地类型
        is_aquatic = habitat_type in ('marine', 'deep_sea', 'freshwater', 'hydrothermal')
        is_terrestrial = habitat_type in ('terrestrial', 'aerial')
        is_coastal = habitat_type in ('coastal', 'amphibious')
        
        prefs[idx, 4] = 1.0 if is_terrestrial else 0.0
        prefs[idx, 5] = 1.0 if is_aquatic else 0.0
        prefs[idx, 6] = 1.0 if is_coastal else 0.0
    
    return prefs


def extract_species_traits(
    species_list: list,
    species_map: dict[str, int],
) -> np.ndarray:
    """从物种列表提取完整特质矩阵（用于精确宜居度计算）
    
    Args:
        species_list: Species 对象列表
        species_map: {lineage_code: tensor_index}
    
    Returns:
        物种特质矩阵 (S, 14)
        [0] 耐热性 1-10
        [1] 耐寒性 1-10
        [2] 耐旱性 1-10
        [3] 耐盐性 1-10
        [4] 光照需求 1-10
        [5] 繁殖速度 1-10
        [6] 体型 1-10
        [7] 机动性 1-10
        [8] 陆地偏好 0-1
        [9] 海洋偏好 0-1
        [10] 海岸偏好 0-1
        [11] 营养级 1-5
        [12] 年龄(回合) 0+
        [13] 专化度 0-1 (由特质方差计算)
    """
    S = len(species_map)
    traits = np.zeros((S, 14), dtype=np.float32)
    
    for species in species_list:
        lineage = species.lineage_code
        if lineage not in species_map:
            continue
        
        idx = species_map[lineage]
        abs_traits = species.abstract_traits or {}
        morph = species.morphology_stats or {}
        habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
        
        # 环境耐受特质 (0-4)
        traits[idx, 0] = float(abs_traits.get("耐热性", 5))
        traits[idx, 1] = float(abs_traits.get("耐寒性", 5))
        traits[idx, 2] = float(abs_traits.get("耐旱性", 5))
        traits[idx, 3] = float(abs_traits.get("耐盐性", 5))
        traits[idx, 4] = float(abs_traits.get("光照需求", 5))
        
        # 生命史特质 (5-7)
        traits[idx, 5] = float(abs_traits.get("繁殖速度", 5))
        traits[idx, 6] = float(abs_traits.get("体型", 5))
        traits[idx, 7] = float(abs_traits.get("机动性", 5))
        
        # 栖息地偏好 (8-10)
        is_aquatic = habitat_type in ('marine', 'deep_sea', 'freshwater', 'hydrothermal')
        is_terrestrial = habitat_type in ('terrestrial', 'aerial')
        is_coastal = habitat_type in ('coastal', 'amphibious')
        
        traits[idx, 8] = 1.0 if is_terrestrial else (0.3 if is_coastal else 0.0)
        traits[idx, 9] = 1.0 if is_aquatic else (0.3 if is_coastal else 0.0)
        traits[idx, 10] = 1.0 if is_coastal else 0.0
        
        # 营养级 (11)
        traits[idx, 11] = float(getattr(species, 'trophic_level', 1.0) or 1.0)
        
        # 年龄 (12)
        traits[idx, 12] = float(morph.get("age_turns", 0) or 0)
        
        # 专化度 (13) - 由环境特质的方差计算
        env_traits = traits[idx, 0:5]
        mean_trait = env_traits.mean()
        variance = ((env_traits - mean_trait) ** 2).mean()
        # 方差越大 = 越专化（某些特质高，某些低）
        traits[idx, 13] = min(1.0, 1.0 - np.exp(-variance / 8.0))
    
    return traits


def extract_trophic_levels(
    species_list: list,
    species_map: dict[str, int],
) -> np.ndarray:
    """从物种列表提取营养级数组"""
    S = len(species_map)
    trophic = np.ones(S, dtype=np.float32)
    
    for species in species_list:
        lineage = species.lineage_code
        if lineage not in species_map:
            continue
        idx = species_map[lineage]
        trophic[idx] = getattr(species, 'trophic_level', 1.0) or 1.0
    
    return trophic
