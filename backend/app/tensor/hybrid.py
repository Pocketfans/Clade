"""
GPU-only 混合计算模块 - Taichi GPU + NumPy 数据交换

【GPU-only 模式】
本模块强制使用 Taichi GPU 后端，无 NumPy fallback。
如果 GPU/Taichi 不可用，会直接抛出 RuntimeError。

分工原则：
┌────────────────────────────────────────────────────────────────┐
│                    Taichi GPU（计算核心）                        │
├────────────────────────────────────────────────────────────────┤
│ • 大规模空间计算（死亡率、扩散、适应度）                           │
│ • 并行遍历所有格子的操作                                         │
│ • 多物种同时计算                                                │
│ • 全部计算热点代码                                              │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                    NumPy（数据交换层）                           │
├────────────────────────────────────────────────────────────────┤
│ • 数据预处理和后处理                                             │
│ • 小规模聚合操作（sum, mean, max）                               │
│ • 索引和切片操作                                                │
│ • 与数据库/API 的数据交换                                        │
└────────────────────────────────────────────────────────────────┘

使用方式：
    from app.tensor.hybrid import HybridCompute
    
    compute = HybridCompute()  # 无GPU时抛错
    
    # Taichi GPU 加速计算
    mortality = compute.mortality(pop, env, params)
    new_pop = compute.diffusion(pop, rate=0.1)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================================
# Taichi 内核（延迟导入）
# ============================================================================

_taichi_kernels = None
_taichi_available = False


def _load_taichi_kernels():
    """加载 Taichi 内核 - GPU-only 模式，无 fallback"""
    global _taichi_kernels, _taichi_available
    
    if _taichi_kernels is not None:
        return _taichi_available
    
    try:
        from . import taichi_hybrid_kernels as kernels
        _taichi_kernels = kernels
        _taichi_available = True
        logger.info("[HybridCompute] Taichi GPU 内核已加载")
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


# ============================================================================
# 混合计算类
# ============================================================================

@dataclass
class HybridCompute:
    """混合计算引擎 - NumPy + Taichi 分工协作
    
    Taichi 负责：
    - mortality: 死亡率计算（大规模并行）
    - diffusion: 种群扩散（空间计算）
    - reproduction: 繁殖计算（并行）
    - competition: 种间竞争（并行）
    
    NumPy 负责：
    - 数据预处理/后处理
    - 聚合统计（sum, mean, max）
    - 条件筛选和掩码
    - 小规模操作
    
    Example:
        compute = HybridCompute()
        
        # Taichi 加速的大规模计算
        mortality = compute.mortality(pop, env, params)
        new_pop = compute.diffusion(pop, rate=0.1)
        
        # NumPy 的简单操作
        total = compute.sum_population(pop)
        alive = compute.filter_alive(pop, threshold=10)
    """
    
    arch: str = "auto"
    _taichi_ready: bool = field(default=False, repr=False)
    
    def __post_init__(self):
        """初始化 Taichi - GPU-only 模式"""
        self._taichi_ready = _load_taichi_kernels()
        
        if not self._taichi_ready:
            raise RuntimeError("[GPU-only] Taichi GPU 初始化失败，无 NumPy fallback")
    
    @property
    def backend(self) -> str:
        """当前后端 - GPU-only 模式始终为 taichi"""
        return "taichi"
    
    # ========================================================================
    # Taichi 加速操作（大规模并行）
    # ========================================================================
    
    def mortality(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        params: np.ndarray,
        temp_idx: int = 1,
        temp_opt: float = 20.0,
        temp_tol: float = 15.0,
    ) -> np.ndarray:
        """计算死亡率 [Taichi GPU]
        
        Args:
            pop: 种群张量 (S, H, W)
            env: 环境张量 (C, H, W)
            params: 物种参数 (S, F)
            temp_idx: 温度通道索引
            temp_opt: 最适温度
            temp_tol: 温度容忍度
        
        Returns:
            死亡率张量 (S, H, W)
        """
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_mortality(
            pop.astype(np.float32),
            env.astype(np.float32),
            params.astype(np.float32),
            result,
            temp_idx, temp_opt, temp_tol,
        )
        return result
    
    def diffusion(
        self,
        pop: np.ndarray,
        rate: float = 0.1,
    ) -> np.ndarray:
        """种群扩散 [Taichi GPU]
        
        Args:
            pop: 种群张量 (S, H, W)
            rate: 扩散率 (0-1)
        
        Returns:
            扩散后的种群张量 (S, H, W)
        """
        new_pop = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_diffusion(
            pop.astype(np.float32),
            new_pop,
            rate,
        )
        return new_pop
    
    def apply_mortality(
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
    
    def reproduction(
        self,
        pop: np.ndarray,
        fitness: np.ndarray,
        capacity: np.ndarray,
        birth_rate: float = 0.1,
    ) -> np.ndarray:
        """繁殖计算 [Taichi GPU]
        
        Args:
            pop: 种群张量 (S, H, W)
            fitness: 适应度张量 (S, H, W)
            capacity: 承载力 (H, W)
            birth_rate: 基础出生率
        
        Returns:
            繁殖后的种群张量 (S, H, W)
        """
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_reproduction(
            pop.astype(np.float32),
            fitness.astype(np.float32),
            capacity.astype(np.float32),
            birth_rate,
            result,
        )
        return result
    
    def competition(
        self,
        pop: np.ndarray,
        fitness: np.ndarray,
        strength: float = 0.01,
    ) -> np.ndarray:
        """种间竞争 [Taichi GPU]
        
        Args:
            pop: 种群张量 (S, H, W)
            fitness: 适应度张量 (S, H, W)
            strength: 竞争强度
        
        Returns:
            竞争后的种群张量 (S, H, W)
        """
        result = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_competition(
            pop.astype(np.float32),
            fitness.astype(np.float32),
            result,
            strength,
        )
        return result
    
    # ========================================================================
    # NumPy 简单操作（CPU 足够）
    # ========================================================================
    
    def sum_population(self, pop: np.ndarray) -> np.ndarray:
        """每个物种的总种群 [NumPy]"""
        return pop.sum(axis=(1, 2))
    
    def mean_population(self, pop: np.ndarray) -> np.ndarray:
        """每个物种的平均种群密度 [NumPy]"""
        mask = pop > 0
        counts = mask.sum(axis=(1, 2))
        sums = pop.sum(axis=(1, 2))
        return np.where(counts > 0, sums / counts, 0)
    
    def max_population(self, pop: np.ndarray) -> np.ndarray:
        """每个物种的最大种群 [NumPy]"""
        return pop.max(axis=(1, 2))
    
    def filter_alive(
        self,
        pop: np.ndarray,
        threshold: float = 1.0,
    ) -> list[int]:
        """筛选存活物种索引 [NumPy]"""
        totals = self.sum_population(pop)
        return [i for i, t in enumerate(totals) if t >= threshold]
    
    def get_presence_mask(self, pop: np.ndarray) -> np.ndarray:
        """获取种群存在掩码 [NumPy]"""
        return pop > 0
    
    def get_species_distribution(
        self,
        pop: np.ndarray,
        species_idx: int,
    ) -> np.ndarray:
        """获取单个物种的分布 [NumPy]"""
        return pop[species_idx].copy()
    
    def clip_population(
        self,
        pop: np.ndarray,
        min_val: float = 0,
        max_val: float = 1e9,
    ) -> np.ndarray:
        """裁剪种群数值 [NumPy]"""
        return np.clip(pop, min_val, max_val)
    
    def normalize_population(self, pop: np.ndarray) -> np.ndarray:
        """归一化种群分布 [NumPy]"""
        max_vals = pop.max(axis=(1, 2), keepdims=True)
        max_vals = np.where(max_vals > 0, max_vals, 1)
        return pop / max_vals
    
    def redistribute_population(
        self,
        pop: np.ndarray,
        new_totals: np.ndarray,
    ) -> np.ndarray:
        """将新总数按旧分布权重/均匀方式写回张量 [Taichi GPU]"""
        if new_totals.shape[0] != pop.shape[0]:
            raise ValueError("new_totals length must match species dimension")
        
        pop_f32 = pop.astype(np.float32, copy=False)
        new_totals = new_totals.astype(np.float32, copy=False)
        
        current_totals = pop_f32.sum(axis=(1, 2), dtype=np.float32)
        out = np.zeros_like(pop_f32, dtype=np.float32)
        tile_count = int(pop_f32.shape[1] * pop_f32.shape[2])
        _taichi_kernels.kernel_redistribute_population(
            pop_f32,
            current_totals,
            new_totals,
            out,
            tile_count,
        )
        return out

    # ========================================================================
    # 迁徙相关操作 [Taichi 加速]
    # ========================================================================
    
    def compute_suitability(
        self,
        env: np.ndarray,
        species_prefs: np.ndarray,
        habitat_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        """批量计算所有物种对所有地块的适宜度 [Taichi GPU]
        
        Args:
            env: 环境张量 (C, H, W)
            species_prefs: 物种偏好 (S, 7)
            habitat_mask: 栖息地掩码 (S, H, W)
        
        Returns:
            适宜度张量 (S, H, W)
        """
        S = species_prefs.shape[0]
        C, H, W = env.shape
        
        # 确保环境张量有足够的通道
        if C < 7:
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            if C <= 4:
                padded_env[4] = 1.0
            env = padded_env
        
        if habitat_mask is None:
            habitat_mask = np.ones((S, H, W), dtype=np.float32)
        
        result = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_compute_suitability(
            env.astype(np.float32),
            species_prefs.astype(np.float32),
            habitat_mask.astype(np.float32),
            result,
        )
        return result
    
    
    def guided_diffusion(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        rate: float = 0.1,
    ) -> np.ndarray:
        """带适宜度引导的扩散 [Taichi GPU]
        
        Args:
            pop: 种群张量 (S, H, W)
            suitability: 适宜度张量 (S, H, W)
            rate: 扩散率
        
        Returns:
            扩散后的种群 (S, H, W)
        """
        new_pop = np.zeros_like(pop, dtype=np.float32)
        _taichi_kernels.kernel_advanced_diffusion(
            pop.astype(np.float32),
            suitability.astype(np.float32),
            new_pop,
            float(rate),
        )
        return new_pop
    
    def batch_migration(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_prefs: np.ndarray,
        death_rates: np.ndarray,
        max_distance: float = 15.0,
        pressure_threshold: float = 0.12,
        migration_rate: float = 0.15,
    ) -> np.ndarray:
        """完整的批量迁徙计算 [Taichi GPU]
        
        一次调用完成所有物种的迁徙计算。
        
        Args:
            pop: 种群张量 (S, H, W)
            env: 环境张量 (C, H, W)
            species_prefs: 物种偏好 (S, 7)
            death_rates: 死亡率 (S,)
            max_distance: 最大迁徙距离
            pressure_threshold: 压力迁徙阈值
            migration_rate: 基础迁徙率
        
        Returns:
            迁徙后的种群张量 (S, H, W)
        """
        S, H, W = pop.shape
        
        # 1. 计算适宜度
        suitability = self.compute_suitability(env, species_prefs)
        
        # 2. 计算距离权重
        distance_weights = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_compute_distance_weights(
            pop.astype(np.float32),
            distance_weights,
            float(max_distance),
        )
        
        # 3. 计算迁徙分数
        migration_scores = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_migration_decision(
            pop.astype(np.float32),
            suitability,
            distance_weights,
            death_rates.astype(np.float32),
            migration_scores,
            float(pressure_threshold),
            0.6,  # saturation_threshold
        )
        
        # 4. 执行迁徙
        migration_rates = np.full(S, migration_rate, dtype=np.float32)
        migration_rates = np.where(
            death_rates > pressure_threshold,
            np.minimum(0.8, migration_rate * 2.0),
            migration_rates
        )
        
        new_pop = np.zeros((S, H, W), dtype=np.float32)
        _taichi_kernels.kernel_execute_migration(
            pop.astype(np.float32),
            migration_scores,
            distance_weights,
            new_pop,
            migration_rates,
            0.08,  # score_threshold
            0.01,  # long_jump_prob
        )
        
        # 5. 带引导的扩散
        new_pop = self.guided_diffusion(new_pop, suitability, rate=0.1)
        
        return new_pop


# ============================================================================
# 便捷函数
# ============================================================================

_global_compute: HybridCompute | None = None


def get_compute(arch: str = "auto") -> HybridCompute:
    """获取全局混合计算实例"""
    global _global_compute
    if _global_compute is None:
        _global_compute = HybridCompute(arch=arch)
    return _global_compute


def reset_compute() -> None:
    """重置全局计算实例"""
    global _global_compute
    _global_compute = None
