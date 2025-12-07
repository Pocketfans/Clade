"""
混合计算模块 - NumPy + Taichi 分工协作

分工原则：
┌────────────────────────────────────────────────────────────────┐
│                    Taichi 负责（GPU/并行）                       │
├────────────────────────────────────────────────────────────────┤
│ • 大规模空间计算（死亡率、扩散、适应度）                           │
│ • 并行遍历所有格子的操作                                         │
│ • 多物种同时计算                                                │
│ • 需要 GPU 加速的热点代码                                        │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                    NumPy 负责（CPU/简单）                        │
├────────────────────────────────────────────────────────────────┤
│ • 数据预处理和后处理                                             │
│ • 小规模聚合操作（求和、平均、最值）                              │
│ • 索引和切片操作                                                │
│ • 条件筛选和掩码操作                                             │
│ • 与数据库/API 的数据交换                                        │
└────────────────────────────────────────────────────────────────┘

使用方式：
    from app.tensor.hybrid import HybridCompute
    
    compute = HybridCompute()
    
    # 自动选择最佳后端
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
    """延迟加载 Taichi 内核"""
    global _taichi_kernels, _taichi_available
    
    if _taichi_kernels is not None:
        return _taichi_available
    
    try:
        from . import taichi_hybrid_kernels as kernels
        _taichi_kernels = kernels
        _taichi_available = True
        logger.info("[HybridCompute] Taichi 内核已加载")
        return True
    except ImportError as e:
        logger.info(f"[HybridCompute] Taichi 不可用: {e}")
        _taichi_available = False
        return False
    except Exception as e:
        logger.warning(f"[HybridCompute] Taichi 初始化失败: {e}")
        _taichi_available = False
        return False


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
        """初始化 Taichi（如果可用）"""
        self._taichi_ready = _load_taichi_kernels()
        
        if not self._taichi_ready:
            logger.info("[HybridCompute] 使用纯 NumPy 模式")
    
    @property
    def backend(self) -> str:
        """当前后端"""
        return "taichi" if self._taichi_ready else "numpy"
    
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
        """计算死亡率 [Taichi 加速]
        
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
        
        if self._taichi_ready:
            _taichi_kernels.kernel_mortality(
                pop.astype(np.float32),
                env.astype(np.float32),
                params.astype(np.float32),
                result,
                temp_idx, temp_opt, temp_tol,
            )
        else:
            # NumPy 回退
            temp = env[temp_idx]
            deviation = np.abs(temp - temp_opt)
            base_mortality = 1.0 - np.exp(-deviation / temp_tol)
            for s in range(pop.shape[0]):
                mask = pop[s] > 0
                result[s, mask] = np.clip(base_mortality[mask], 0.01, 0.99)
        
        return result
    
    def diffusion(
        self,
        pop: np.ndarray,
        rate: float = 0.1,
    ) -> np.ndarray:
        """种群扩散 [Taichi 加速]
        
        Args:
            pop: 种群张量 (S, H, W)
            rate: 扩散率 (0-1)
        
        Returns:
            扩散后的种群张量 (S, H, W)
        """
        new_pop = np.zeros_like(pop, dtype=np.float32)
        
        if self._taichi_ready:
            _taichi_kernels.kernel_diffusion(
                pop.astype(np.float32),
                new_pop,
                rate,
            )
        else:
            # NumPy 回退（使用 scipy）
            from scipy.ndimage import convolve
            kernel = np.array([
                [0, 1, 0],
                [1, 0, 1],
                [0, 1, 0],
            ], dtype=np.float32) * (rate / 4)
            kernel[1, 1] = 1.0 - rate
            
            for s in range(pop.shape[0]):
                new_pop[s] = convolve(pop[s], kernel, mode='constant', cval=0)
        
        return new_pop
    
    def apply_mortality(
        self,
        pop: np.ndarray,
        mortality: np.ndarray,
    ) -> np.ndarray:
        """应用死亡率 [Taichi 加速]"""
        result = np.zeros_like(pop, dtype=np.float32)
        
        if self._taichi_ready:
            _taichi_kernels.kernel_apply_mortality(
                pop.astype(np.float32),
                mortality.astype(np.float32),
                result,
            )
        else:
            result = (pop * (1.0 - mortality)).astype(np.float32)
        
        return result
    
    def reproduction(
        self,
        pop: np.ndarray,
        fitness: np.ndarray,
        capacity: np.ndarray,
        birth_rate: float = 0.1,
    ) -> np.ndarray:
        """繁殖计算 [Taichi 加速]
        
        Args:
            pop: 种群张量 (S, H, W)
            fitness: 适应度张量 (S, H, W)
            capacity: 承载力 (H, W)
            birth_rate: 基础出生率
        
        Returns:
            繁殖后的种群张量 (S, H, W)
        """
        result = np.zeros_like(pop, dtype=np.float32)
        
        if self._taichi_ready:
            _taichi_kernels.kernel_reproduction(
                pop.astype(np.float32),
                fitness.astype(np.float32),
                capacity.astype(np.float32),
                birth_rate,
                result,
            )
        else:
            # NumPy 回退
            S, H, W = pop.shape
            total_pop = pop.sum(axis=0)
            crowding = np.minimum(1.0, total_pop / (capacity + 1e-6))
            
            for s in range(S):
                mask = pop[s] > 0
                effective_rate = birth_rate * fitness[s] * (1.0 - crowding)
                result[s] = pop[s] * (1.0 + effective_rate)
                result[s, ~mask] = 0
        
        return result
    
    def competition(
        self,
        pop: np.ndarray,
        fitness: np.ndarray,
        strength: float = 0.01,
    ) -> np.ndarray:
        """种间竞争 [Taichi 加速]
        
        Args:
            pop: 种群张量 (S, H, W)
            fitness: 适应度张量 (S, H, W)
            strength: 竞争强度
        
        Returns:
            竞争后的种群张量 (S, H, W)
        """
        result = np.zeros_like(pop, dtype=np.float32)
        
        if self._taichi_ready:
            _taichi_kernels.kernel_competition(
                pop.astype(np.float32),
                fitness.astype(np.float32),
                result,
                strength,
            )
        else:
            # NumPy 回退
            S = pop.shape[0]
            total_pop = pop.sum(axis=0)
            
            for s in range(S):
                mask = pop[s] > 0
                competitor = total_pop - pop[s]
                my_fitness = fitness[s] + 0.1
                pressure = competitor * strength / my_fitness
                loss = np.minimum(0.5, pressure / (pop[s] + 1.0))
                result[s] = pop[s] * (1.0 - loss)
                result[s, ~mask] = 0
        
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
    
    # ========================================================================
    # 迁徙相关操作 [Taichi 加速]
    # ========================================================================
    
    def compute_suitability(
        self,
        env: np.ndarray,
        species_prefs: np.ndarray,
        habitat_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        """批量计算所有物种对所有地块的适宜度 [Taichi 加速]
        
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
        
        if self._taichi_ready:
            _taichi_kernels.kernel_compute_suitability(
                env.astype(np.float32),
                species_prefs.astype(np.float32),
                habitat_mask.astype(np.float32),
                result,
            )
        else:
            # NumPy 回退
            result = self._numpy_suitability(env, species_prefs, habitat_mask)
        
        return result
    
    def _numpy_suitability(
        self,
        env: np.ndarray,
        species_prefs: np.ndarray,
        habitat_mask: np.ndarray,
    ) -> np.ndarray:
        """NumPy 适宜度计算"""
        S = species_prefs.shape[0]
        H, W = env.shape[1], env.shape[2]
        
        # 温度匹配
        temp_diff = np.abs(env[0:1] - species_prefs[:, 0:1, np.newaxis]).reshape(S, H, W)
        temp_match = np.maximum(0.0, 1.0 - temp_diff * 2.0)
        
        # 湿度匹配
        humidity_diff = np.abs(env[1:2] - species_prefs[:, 1:2, np.newaxis]).reshape(S, H, W)
        humidity_match = np.maximum(0.0, 1.0 - humidity_diff * 2.0)
        
        # 资源匹配
        resource_match = np.broadcast_to(env[3:4], (S, H, W))
        
        # 栖息地匹配
        habitat_match = (
            env[4:5] * species_prefs[:, 4:5, np.newaxis] +
            env[5:6] * species_prefs[:, 5:6, np.newaxis] +
            env[6:7] * species_prefs[:, 6:7, np.newaxis]
        ).reshape(S, H, W)
        
        base_score = (
            temp_match * 0.3 + humidity_match * 0.2 +
            resource_match * 0.2 + habitat_match * 0.3
        )
        
        hard_constraint = (temp_match >= 0.05) & (habitat_match >= 0.01)
        return np.where(
            (habitat_mask > 0.5) & hard_constraint,
            np.clip(base_score, 0.0, 1.0),
            0.0
        ).astype(np.float32)
    
    def guided_diffusion(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        rate: float = 0.1,
    ) -> np.ndarray:
        """带适宜度引导的扩散 [Taichi 加速]
        
        Args:
            pop: 种群张量 (S, H, W)
            suitability: 适宜度张量 (S, H, W)
            rate: 扩散率
        
        Returns:
            扩散后的种群 (S, H, W)
        """
        new_pop = np.zeros_like(pop, dtype=np.float32)
        
        if self._taichi_ready:
            _taichi_kernels.kernel_advanced_diffusion(
                pop.astype(np.float32),
                suitability.astype(np.float32),
                new_pop,
                float(rate),
            )
        else:
            # NumPy 回退
            from scipy.ndimage import convolve
            
            kernel = np.array([
                [0, 1, 0],
                [1, 0, 1],
                [0, 1, 0],
            ], dtype=np.float32) * (rate / 4)
            kernel[1, 1] = 1.0 - rate
            
            for s in range(pop.shape[0]):
                diffused = convolve(pop[s], kernel, mode='constant', cval=0)
                suit_weight = suitability[s] + 0.1
                new_pop[s] = diffused * suit_weight
                
                total_before = pop[s].sum()
                total_after = new_pop[s].sum()
                if total_after > 0:
                    new_pop[s] *= total_before / total_after
        
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
        """完整的批量迁徙计算 [Taichi 加速]
        
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
        if self._taichi_ready:
            _taichi_kernels.kernel_compute_distance_weights(
                pop.astype(np.float32),
                distance_weights,
                float(max_distance),
            )
        else:
            # NumPy 回退
            i_coords, j_coords = np.meshgrid(
                np.arange(H), np.arange(W), indexing='ij'
            )
            for s in range(S):
                total_pop = pop[s].sum()
                if total_pop > 0:
                    center_i = (pop[s] * i_coords).sum() / total_pop
                    center_j = (pop[s] * j_coords).sum() / total_pop
                    dist = np.abs(i_coords - center_i) + np.abs(j_coords - center_j)
                    distance_weights[s] = np.maximum(0.0, 1.0 - dist / max_distance)
                else:
                    distance_weights[s] = 1.0
        
        # 3. 计算迁徙分数
        migration_scores = np.zeros((S, H, W), dtype=np.float32)
        if self._taichi_ready:
            _taichi_kernels.kernel_migration_decision(
                pop.astype(np.float32),
                suitability,
                distance_weights,
                death_rates.astype(np.float32),
                migration_scores,
                float(pressure_threshold),
                0.6,  # saturation_threshold
            )
        else:
            base_score = suitability * 0.5 + distance_weights * 0.5
            has_pop = pop > 0
            migration_scores = np.where(has_pop, 0.0, base_score)
            migration_scores *= np.random.uniform(0.85, 1.15, migration_scores.shape)
        
        # 4. 执行迁徙
        migration_rates = np.full(S, migration_rate, dtype=np.float32)
        migration_rates = np.where(
            death_rates > pressure_threshold,
            np.minimum(0.8, migration_rate * 2.0),
            migration_rates
        )
        
        new_pop = np.zeros((S, H, W), dtype=np.float32)
        if self._taichi_ready:
            _taichi_kernels.kernel_execute_migration(
                pop.astype(np.float32),
                migration_scores,
                new_pop,
                migration_rates,
                0.08,  # score_threshold
            )
        else:
            for s in range(S):
                total_pop = pop[s].sum()
                valid = migration_scores[s] > 0.08
                total_score = migration_scores[s][valid].sum()
                migrate_amount = total_pop * migration_rates[s]
                
                new_pop[s] = pop[s] * (1.0 - migration_rates[s])
                if total_score > 0:
                    score_ratio = np.where(valid, migration_scores[s] / total_score, 0.0)
                    new_pop[s] += migrate_amount * score_ratio
        
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
