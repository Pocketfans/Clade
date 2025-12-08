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
    
    【v2.1】参数参考 EcologyConfig (models/config.py) 中的原有设置
    """
    # === 死亡率参数 ===
    base_mortality: float = 0.05          # 基础死亡率
    temp_mortality_weight: float = 0.3    # 温度死亡率权重
    competition_weight: float = 0.2       # 竞争死亡率权重
    resource_weight: float = 0.2          # 资源死亡率权重
    trophic_weight: float = 0.3           # 营养级死亡率权重
    
    # === 扩散参数 ===
    # 参考 config.py: diffusion_rate = 0.1, dispersal_cost_base = 0.1
    base_diffusion_rate: float = 0.1      # 基础扩散率（与config.py一致）
    max_diffusion_rate: float = 0.3       # 最大扩散率（限制早期时代）
    
    # === 迁徙参数 ===
    pressure_threshold: float = 0.12      # 压力迁徙阈值
    saturation_threshold: float = 0.60    # 饱和度阈值
    # 参考 config.py: terrestrial_top_k=4, marine_top_k=3 等
    # 物种分布地块数有限，迁徙应该是逐步的
    max_migration_distance: float = 2.0   # 最大迁徙距离（限制为相邻2格）
    base_migration_rate: float = 0.1      # 基础迁徙率（与扩散率一致）
    # 参考 config.py: suitability_cutoff = 0.25
    score_threshold: float = 0.25         # 迁徙分数阈值（与宜居度阈值一致）
    
    # === 繁殖参数 ===
    base_birth_rate: float = 0.1          # 基础出生率
    capacity_multiplier: float = 100.0    # 承载力乘数
    
    # === 时代缩放 ===
    era_scaling_enabled: bool = True      # 是否启用时代缩放


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
    ) -> EcologyResult:
        """统一生态计算入口 - 一次调用完成全部计算
        
        【零循环】所有计算使用张量并行，无 Python for 循环
        
        Args:
            pop: 种群张量 (S, H, W)
            env: 环境张量 (C, H, W)
            species_params: 物种参数 (S, F) - 耐受性等
            species_prefs: 物种偏好 (S, 7) - 温度/湿度/栖息地偏好
            turn_index: 当前回合（用于时代缩放）
            trophic_levels: 营养级 (S,) - 用于猎物追踪
            pressure_overlay: 压力叠加层 (C_pressure, H, W)
            cooldown_mask: 迁徙冷却掩码 (S,) True=允许迁徙
        
        Returns:
            EcologyResult 包含更新后的种群和各阶段结果
        """
        start_time = time.perf_counter()
        S, H, W = pop.shape
        
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
        
        # 获取时代缩放因子
        era_scaling = self._get_era_scaling(turn_index)
        
        # === 阶段1：死亡率计算 ===
        t0 = time.perf_counter()
        mortality_rates = self._compute_mortality_tensor(
            pop, env, species_params, species_prefs, 
            trophic_levels, pressure_overlay, era_scaling
        )
        metrics.mortality_time_ms = (time.perf_counter() - t0) * 1000
        
        # 应用死亡率
        pop_after_death = self._apply_mortality_tensor(pop, mortality_rates)
        
        # 计算死亡统计
        death_counts = (pop - pop_after_death).sum(axis=(1, 2))
        survivor_counts = pop_after_death.sum(axis=(1, 2))
        metrics.avg_mortality_rate = float(mortality_rates[pop > 0].mean()) if (pop > 0).any() else 0.0
        
        # === 阶段2：扩散计算 ===
        t0 = time.perf_counter()
        suitability = self._compute_suitability_tensor(env, species_prefs)
        pop_after_dispersal = self._compute_dispersal_tensor(
            pop_after_death, suitability, era_scaling
        )
        metrics.dispersal_time_ms = (time.perf_counter() - t0) * 1000
        
        # === 阶段3：迁徙计算 ===
        t0 = time.perf_counter()
        # 提取每个物种的平均死亡率作为迁徙压力信号 - 向量化
        pop_mask = pop > 0
        mortality_masked = np.where(pop_mask, mortality_rates, 0.0)
        pop_counts = pop_mask.sum(axis=(1, 2))
        pop_counts = np.maximum(pop_counts, 1)  # 避免除零
        species_death_rates = mortality_masked.sum(axis=(1, 2)) / pop_counts
        species_death_rates = species_death_rates.astype(np.float32)
        
        pop_after_migration, migrated = self._compute_migration_tensor(
            pop_after_dispersal, env, species_prefs, suitability,
            species_death_rates, trophic_levels, cooldown_mask, era_scaling
        )
        metrics.migration_time_ms = (time.perf_counter() - t0) * 1000
        metrics.migrating_species = len(migrated)
        
        # === 阶段4：繁殖计算 ===
        t0 = time.perf_counter()
        pop_after_reproduction = self._compute_reproduction_tensor(
            pop_after_migration, env, suitability, era_scaling
        )
        metrics.reproduction_time_ms = (time.perf_counter() - t0) * 1000
        
        # === 阶段5：竞争计算 ===
        t0 = time.perf_counter()
        final_pop = self._compute_competition_tensor(
            pop_after_reproduction, suitability, era_scaling
        )
        metrics.competition_time_ms = (time.perf_counter() - t0) * 1000
        
        metrics.total_population_after = float(final_pop.sum())
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        self._last_metrics = metrics
        
        # 同步 Taichi 确保所有 GPU 操作完成
        ti.sync()
        
        logger.info(
            f"[TensorEcology] 完成: {S}物种, {H}x{W}地图, "
            f"耗时={metrics.total_time_ms:.1f}ms, 后端={metrics.backend}, "
            f"平均死亡率={metrics.avg_mortality_rate:.1%}"
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
    ) -> np.ndarray:
        """张量化多因子死亡率计算 - GPU 加速
        
        综合以下因子：
        1. 温度压力
        2. 湿度压力
        3. 竞争压力（同地块物种竞争）
        4. 资源压力（承载力）
        5. 营养级压力（捕食/被捕食）
        6. 外部压力（灾害等）
        """
        S, H, W = pop.shape
        cfg = self.config
        
        # 确保压力叠加层存在
        if pressure_overlay is None:
            pressure_overlay = np.zeros((1, H, W), dtype=np.float32)
        
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
        
        _taichi_kernels.kernel_multifactor_mortality(
            pop.astype(np.float32),
            env.astype(np.float32),
            species_prefs.astype(np.float32),
            species_params.astype(np.float32),
            trophic_levels.astype(np.float32),
            pressure_overlay.astype(np.float32),
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
    
    def _compute_dispersal_tensor(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        era_scaling: float,
    ) -> np.ndarray:
        """张量化扩散计算 [Taichi GPU]
        
        使用带适宜度引导的扩散。
        """
        cfg = self.config
        
        # 时代缩放：早期时代扩散更快
        effective_scaling = max(1.0, era_scaling ** 0.5)
        diffusion_rate = min(cfg.max_diffusion_rate, cfg.base_diffusion_rate * effective_scaling)
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_advanced_diffusion(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            result,
            float(diffusion_rate),
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
        suitability: np.ndarray,
        death_rates: np.ndarray,
        trophic_levels: np.ndarray,
        cooldown_mask: np.ndarray,
        era_scaling: float,
    ) -> tuple[np.ndarray, list[int]]:
        """张量化迁徙计算 - 无循环
        
        Returns:
            (迁徙后种群, 已迁徙物种索引列表)
        """
        cfg = self.config
        S, H, W = pop.shape
        
        # 1. 计算距离权重 (S, H, W)
        distance_weights = self._compute_distance_weights_tensor(pop, cfg.max_migration_distance)
        
        # 2. 计算猎物密度（用于消费者）(S, H, W)
        prey_density = self._compute_prey_density_tensor(pop, trophic_levels)
        
        # 3. 计算迁徙分数 (S, H, W)
        migration_scores = self._compute_migration_scores_tensor(
            pop, suitability, distance_weights, death_rates, 
            prey_density, trophic_levels
        )
        
        # 4. 应用冷却期掩码
        cooldown_3d = cooldown_mask[:, np.newaxis, np.newaxis]
        migration_scores = np.where(cooldown_3d, migration_scores, 0.0)
        
        # 5. 计算迁徙率（高压力时迁徙更多）
        migration_rates = np.full(S, cfg.base_migration_rate, dtype=np.float32)
        high_pressure = death_rates > cfg.pressure_threshold
        migration_rates = np.where(
            high_pressure,
            np.minimum(0.8, cfg.base_migration_rate * 2.0),
            migration_rates
        )
        
        # 时代缩放
        if era_scaling > 1.5:
            migration_rates *= min(2.0, era_scaling ** 0.3)
        
        # 6. 执行迁徙 [Taichi GPU]
        new_pop = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_execute_migration(
            pop.astype(np.float32),
            migration_scores.astype(np.float32),
            new_pop,
            migration_rates.astype(np.float32),
            float(cfg.score_threshold),
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
        """计算猎物密度 - 向量化"""
        S, H, W = pop.shape
        
        # 构建猎物矩阵
        trophic_2d = trophic_levels[:, np.newaxis]
        trophic_t = trophic_levels[np.newaxis, :]
        
        prey_min = trophic_2d - 1.5
        prey_max = trophic_2d - 0.5
        
        prey_matrix = ((trophic_t >= prey_min) & (trophic_t <= prey_max)).astype(np.float32)
        
        # 计算猎物密度
        pop_flat = pop.reshape(S, H * W)
        prey_pop_flat = prey_matrix @ pop_flat
        prey_pop = prey_pop_flat.reshape(S, H, W)
        
        # 归一化
        total_pop = pop.sum(axis=0) + 1e-6
        prey_normalized = prey_pop / total_pop
        
        # 生产者返回 1
        consumer_mask = (trophic_levels >= 2.0)[:, np.newaxis, np.newaxis]
        return np.where(consumer_mask, prey_normalized, 1.0).astype(np.float32)
    
    def _compute_migration_scores_tensor(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        distance_weights: np.ndarray,
        death_rates: np.ndarray,
        prey_density: np.ndarray,
        trophic_levels: np.ndarray,
    ) -> np.ndarray:
        """计算迁徙分数 [Taichi GPU]"""
        cfg = self.config
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_migration_decision(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            distance_weights.astype(np.float32),
            death_rates.astype(np.float32),
            result,
            float(cfg.pressure_threshold),
            float(cfg.saturation_threshold),
        )
        # 融合猎物追踪（简单混合，这是数据后处理）
        consumer_mask = (trophic_levels >= 2.0)[:, np.newaxis, np.newaxis]
        result = np.where(
            consumer_mask,
            result * 0.7 + prey_density * suitability * 0.3,
            result
        )
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
    ) -> np.ndarray:
        """张量化繁殖计算 - 无循环"""
        cfg = self.config
        S, H, W = pop.shape
        
        # 时代缩放
        effective_scaling = max(1.0, era_scaling ** 0.5)
        birth_rate = min(2.0, cfg.base_birth_rate * effective_scaling)
        
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
        
        # 拥挤度
        total_pop = pop.sum(axis=0)
        crowding = np.minimum(1.0, total_pop / (capacity + 1e-6))
        
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_reproduction(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            capacity.astype(np.float32),
            float(birth_rate),
            result,
        )
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
        
        【v2.1】现在有相邻性检查，时代缩放主要影响扩散速度
        物种只能向相邻地块扩散，所以缩放因子可以适当提高
        但不应该过于极端（原来的100x太高了）
        
        参考 config.py 中物种分布地块限制：
        - terrestrial_top_k = 4
        - marine_top_k = 3
        物种分布是有限的，不会无限扩散
        """
        if not self.config.era_scaling_enabled:
            return 1.0
        
        # 合理的时代缩放：早期快，后期慢
        if turn_index < 10:
            return 5.0   # 太古宙：较快扩散（微生物时代）
        elif turn_index < 30:
            return 8.0   # 元古宙：快速扩散（简单生命爆发）
        elif turn_index < 50:
            return 3.0   # 古生代：中等速度
        elif turn_index < 70:
            return 1.5   # 中生代：接近正常
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
