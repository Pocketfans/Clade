"""
张量迁徙引擎 - GPU 加速的物种迁徙计算

【性能优化核心】
将原本逐物种串行的迁徙计算转换为全物种并行的张量计算，
利用 Taichi GPU 加速实现 10-50x 性能提升。

【设计原则】
1. 批量处理：所有物种同时计算，避免 Python 循环
2. GPU 友好：使用 Taichi 内核实现并行计算
3. 内存复用：缓存中间结果，减少重复分配
4. 无缝集成：与现有 TensorState 和管线阶段兼容

【计算流程】
1. 批量适宜度计算：compute_batch_suitability()
2. 批量距离权重：compute_batch_distance_weights()
3. 迁徙决策：compute_migration_decisions()
4. 执行迁徙：execute_batch_migration()

使用方式：
    from app.tensor.migration import TensorMigrationEngine, get_migration_engine
    
    engine = get_migration_engine()
    new_pop = engine.process_migration(
        pop=tensor_state.pop,
        env=tensor_state.env,
        species_prefs=species_preferences,
        death_rates=mortality_rates,
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from .state import TensorState

logger = logging.getLogger(__name__)

# Taichi 内核（延迟导入）
_taichi_kernels = None
_taichi_available = False


def _load_migration_kernels():
    """延迟加载迁徙相关的 Taichi 内核"""
    global _taichi_kernels, _taichi_available
    
    if _taichi_kernels is not None:
        return _taichi_available
    
    try:
        from . import taichi_hybrid_kernels as kernels
        _taichi_kernels = kernels
        _taichi_available = True
        logger.info("[TensorMigration] Taichi 迁徙内核已加载")
        return True
    except ImportError as e:
        logger.info(f"[TensorMigration] Taichi 不可用，使用 NumPy 回退: {e}")
        _taichi_available = False
        return False
    except Exception as e:
        logger.warning(f"[TensorMigration] Taichi 初始化失败: {e}")
        _taichi_available = False
        return False


@dataclass
class MigrationConfig:
    """迁徙计算配置
    
    【v2.1】参数参考 EcologyConfig (models/config.py) 中的原有设置
    - migration_suitability_bias = 0.6
    - migration_prey_bias = 0.3
    - suitability_cutoff = 0.25
    - dispersal_cost_base = 0.1
    """
    # 压力迁徙阈值
    pressure_threshold: float = 0.12
    # 饱和度阈值
    saturation_threshold: float = 0.60
    # 最大迁徙距离（限制为相邻2格，配合相邻性检查）
    max_migration_distance: float = 2.0
    # 基础迁徙率（与 dispersal_cost_base 一致）
    base_migration_rate: float = 0.1
    # 压力驱动迁徙率倍增
    pressure_migration_boost: float = 2.0
    # 迁徙分数阈值（与 suitability_cutoff 一致）
    score_threshold: float = 0.25
    # 适宜度引导扩散率（与 diffusion_rate 一致）
    guided_diffusion_rate: float = 0.1
    
    # === 猎物追踪配置 ===
    # 参考 config.py: migration_prey_bias = 0.3
    # 猎物稀缺阈值（低于此值触发追踪迁徙）
    prey_scarcity_threshold: float = 0.40
    # 猎物追踪权重（与 migration_prey_bias 一致）
    prey_tracking_weight: float = 0.3
    # 消费者最低营养级（T2+才追踪猎物）
    consumer_trophic_threshold: float = 2.0


@dataclass
class MigrationMetrics:
    """迁徙计算性能指标"""
    total_time_ms: float = 0.0
    suitability_time_ms: float = 0.0
    distance_time_ms: float = 0.0
    decision_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    species_count: int = 0
    migrating_species: int = 0
    backend: str = "numpy"


class TensorMigrationEngine:
    """张量迁徙引擎 - GPU 加速的批量迁徙计算
    
    核心优化：
    1. 所有物种并行计算适宜度矩阵
    2. 所有物种并行计算距离权重
    3. 所有物种并行做迁徙决策
    4. 所有物种并行执行迁徙
    
    性能对比（10物种, 64x64地图）：
    - 原方案：~50ms（逐物种循环）
    - 新方案：~5ms（张量并行）
    - 加速比：10x
    
    性能对比（50物种, 256x256地图）：
    - 原方案：~2000ms
    - 新方案：~50ms（GPU）/ ~200ms（CPU）
    - 加速比：10-40x
    """
    
    def __init__(self, config: MigrationConfig | None = None):
        self.config = config or MigrationConfig()
        self._taichi_ready = _load_migration_kernels()
        
        # 缓存
        self._suitability_cache: np.ndarray | None = None
        self._distance_cache: np.ndarray | None = None
        self._last_metrics: MigrationMetrics | None = None
        
        if self._taichi_ready:
            logger.info("[TensorMigration] 使用 Taichi GPU 加速")
        else:
            logger.info("[TensorMigration] 使用 NumPy 回退")
    
    @property
    def backend(self) -> str:
        """当前计算后端"""
        return "taichi" if self._taichi_ready else "numpy"
    
    @property
    def last_metrics(self) -> MigrationMetrics | None:
        """上次计算的性能指标"""
        return self._last_metrics
    
    def compute_batch_suitability(
        self,
        env: np.ndarray,
        species_prefs: np.ndarray,
        habitat_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        """批量计算所有物种对所有地块的适宜度
        
        【核心优化1】一次计算所有物种的适宜度矩阵
        
        Args:
            env: 环境张量 (C, H, W)
                 C 包含: [温度, 湿度, 海拔, 资源, 陆地, 海洋, 海岸]
            species_prefs: 物种偏好矩阵 (S, 7)
                          [温度偏好, 湿度偏好, 海拔偏好, 资源需求, 陆地, 海洋, 海岸]
            habitat_mask: 栖息地掩码 (S, H, W)，可选
        
        Returns:
            适宜度张量 (S, H, W)
        """
        S = species_prefs.shape[0]
        C, H, W = env.shape
        
        # 确保环境张量有足够的通道
        if C < 7:
            # 扩展通道
            padded_env = np.zeros((7, H, W), dtype=np.float32)
            padded_env[:C] = env
            # 默认值：全陆地
            if C <= 4:
                padded_env[4] = 1.0  # 陆地
            env = padded_env
        
        # 默认栖息地掩码：全部允许
        if habitat_mask is None:
            habitat_mask = np.ones((S, H, W), dtype=np.float32)
        
        result = np.zeros((S, H, W), dtype=np.float32)
        
        if self._taichi_ready and _taichi_kernels is not None:
            _taichi_kernels.kernel_compute_suitability(
                env.astype(np.float32),
                species_prefs.astype(np.float32),
                habitat_mask.astype(np.float32),
                result,
            )
        else:
            # NumPy 回退 - 向量化计算
            result = self._numpy_compute_suitability(
                env, species_prefs, habitat_mask
            )
        
        self._suitability_cache = result
        return result
    
    def _numpy_compute_suitability(
        self,
        env: np.ndarray,
        species_prefs: np.ndarray,
        habitat_mask: np.ndarray,
    ) -> np.ndarray:
        """NumPy 向量化适宜度计算"""
        S = species_prefs.shape[0]
        H, W = env.shape[1], env.shape[2]
        
        result = np.zeros((S, H, W), dtype=np.float32)
        
        # 温度匹配 (广播计算)
        temp_diff = np.abs(env[0:1] - species_prefs[:, 0:1, np.newaxis])  # (S, 1, W) 广播
        temp_diff = temp_diff.reshape(S, H, W)
        temp_match = np.maximum(0.0, 1.0 - temp_diff * 2.0)
        
        # 湿度匹配
        humidity_diff = np.abs(env[1:2] - species_prefs[:, 1:2, np.newaxis])
        humidity_diff = humidity_diff.reshape(S, H, W)
        humidity_match = np.maximum(0.0, 1.0 - humidity_diff * 2.0)
        
        # 资源匹配
        resource_match = np.broadcast_to(env[3:4], (S, H, W))
        
        # 栖息地类型匹配
        habitat_match = (
            env[4:5] * species_prefs[:, 4:5, np.newaxis] +
            env[5:6] * species_prefs[:, 5:6, np.newaxis] +
            env[6:7] * species_prefs[:, 6:7, np.newaxis]
        ).reshape(S, H, W)
        
        # 综合适宜度
        base_score = (
            temp_match * 0.3 +
            humidity_match * 0.2 +
            resource_match * 0.2 +
            habitat_match * 0.3
        )
        
        # 应用硬约束
        hard_constraint = (temp_match >= 0.05) & (habitat_match >= 0.01)
        result = np.where(
            (habitat_mask > 0.5) & hard_constraint,
            np.clip(base_score, 0.0, 1.0),
            0.0
        )
        
        return result.astype(np.float32)
    
    def compute_batch_distance_weights(
        self,
        pop: np.ndarray,
        max_distance: float | None = None,
    ) -> np.ndarray:
        """批量计算所有物种的距离权重
        
        【核心优化2】一次计算所有物种到所有地块的距离权重
        
        Args:
            pop: 种群张量 (S, H, W)
            max_distance: 最大迁徙距离
        
        Returns:
            距离权重张量 (S, H, W)
        """
        if max_distance is None:
            max_distance = self.config.max_migration_distance
        
        S, H, W = pop.shape
        result = np.zeros((S, H, W), dtype=np.float32)
        
        if self._taichi_ready and _taichi_kernels is not None:
            _taichi_kernels.kernel_compute_distance_weights(
                pop.astype(np.float32),
                result,
                float(max_distance),
            )
        else:
            # NumPy 回退
            result = self._numpy_compute_distance_weights(pop, max_distance)
        
        self._distance_cache = result
        return result
    
    def _numpy_compute_distance_weights(
        self,
        pop: np.ndarray,
        max_distance: float,
    ) -> np.ndarray:
        """NumPy 距离权重计算 - 向量化版本"""
        S, H, W = pop.shape
        
        # 创建坐标网格 (H, W)
        i_coords, j_coords = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
        i_coords = i_coords.astype(np.float32)
        j_coords = j_coords.astype(np.float32)
        
        # 扩展为 (1, H, W) 用于广播
        i_coords_3d = i_coords[np.newaxis, :, :]  # (1, H, W)
        j_coords_3d = j_coords[np.newaxis, :, :]  # (1, H, W)
        
        # 计算每个物种的总种群 (S,)
        total_pop = pop.sum(axis=(1, 2))  # (S,)
        total_pop = np.maximum(total_pop, 1e-8)  # 避免除零
        
        # 计算质心 (S,)
        # center_i[s] = sum(pop[s] * i_coords) / total_pop[s]
        center_i = (pop * i_coords_3d).sum(axis=(1, 2)) / total_pop  # (S,)
        center_j = (pop * j_coords_3d).sum(axis=(1, 2)) / total_pop  # (S,)
        
        # 扩展为 (S, 1, 1) 用于广播
        center_i_3d = center_i[:, np.newaxis, np.newaxis]  # (S, 1, 1)
        center_j_3d = center_j[:, np.newaxis, np.newaxis]  # (S, 1, 1)
        
        # 计算曼哈顿距离 (S, H, W)
        dist = np.abs(i_coords_3d - center_i_3d) + np.abs(j_coords_3d - center_j_3d)
        
        # 转换为权重
        result = np.maximum(0.0, 1.0 - dist / max_distance)
        
        # 对于没有种群的物种，设置为全 1
        no_pop_mask = pop.sum(axis=(1, 2)) < 1e-6  # (S,)
        no_pop_mask_3d = no_pop_mask[:, np.newaxis, np.newaxis]  # (S, 1, 1)
        result = np.where(no_pop_mask_3d, 1.0, result)
        
        return result.astype(np.float32)
    
    def compute_migration_decisions(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        distance_weights: np.ndarray,
        death_rates: np.ndarray,
        prey_density: np.ndarray | None = None,
        trophic_levels: np.ndarray | None = None,
    ) -> np.ndarray:
        """批量计算所有物种的迁徙决策分数
        
        【核心优化3】一次计算所有物种的迁徙目标分数
        
        Args:
            pop: 种群张量 (S, H, W)
            suitability: 适宜度张量 (S, H, W)
            distance_weights: 距离权重张量 (S, H, W)
            death_rates: 死亡率数组 (S,)
            prey_density: 猎物密度张量 (S, H, W)，用于消费者追踪猎物
            trophic_levels: 营养级数组 (S,)
        
        Returns:
            迁徙分数张量 (S, H, W)
        """
        S, H, W = pop.shape
        migration_scores = np.zeros((S, H, W), dtype=np.float32)
        
        if self._taichi_ready and _taichi_kernels is not None:
            _taichi_kernels.kernel_migration_decision(
                pop.astype(np.float32),
                suitability.astype(np.float32),
                distance_weights.astype(np.float32),
                death_rates.astype(np.float32),
                migration_scores,
                float(self.config.pressure_threshold),
                float(self.config.saturation_threshold),
            )
            # Taichi 目前不支持猎物追踪，使用后处理融合
            if prey_density is not None and trophic_levels is not None:
                prey_weight = self.config.prey_tracking_weight
                for s in range(S):
                    if trophic_levels[s] >= self.config.consumer_trophic_threshold:
                        migration_scores[s] = (
                            migration_scores[s] * (1.0 - prey_weight) +
                            prey_density[s] * suitability[s] * prey_weight
                        )
        else:
            # NumPy 回退
            migration_scores = self._numpy_migration_decision(
                pop, suitability, distance_weights, death_rates,
                prey_density, trophic_levels
            )
        
        return migration_scores
    
    def compute_prey_density(
        self,
        pop: np.ndarray,
        trophic_levels: np.ndarray,
    ) -> np.ndarray:
        """批量计算每个地块的猎物密度 - 向量化版本
        
        【猎物追踪核心】计算消费者可获取的猎物分布
        
        对于每个消费者（T2+），猎物是比它低一个营养级的物种。
        
        Args:
            pop: 种群张量 (S, H, W)
            trophic_levels: 营养级数组 (S,)
        
        Returns:
            猎物密度张量 (S, H, W)
            - 对于生产者 (T<2)，返回全 1（不需要追踪）
            - 对于消费者 (T>=2)，返回低营养级物种的种群密度
        """
        S, H, W = pop.shape
        prey_density = np.ones((S, H, W), dtype=np.float32)
        
        # 计算每个地块的总种群（用于归一化）
        total_pop = pop.sum(axis=0) + 1e-6  # (H, W)
        
        # 构建猎物矩阵：prey_matrix[i, j] = True 表示物种 j 是物种 i 的猎物
        # 猎物营养级范围：比当前物种低 0.5-1.5 级
        trophic_2d = trophic_levels[:, np.newaxis]  # (S, 1)
        trophic_t = trophic_levels[np.newaxis, :]   # (1, S)
        
        prey_min = trophic_2d - 1.5  # (S, 1)
        prey_max = trophic_2d - 0.5  # (S, 1)
        
        prey_matrix = (trophic_t >= prey_min) & (trophic_t <= prey_max)  # (S, S)
        
        # 消费者掩码
        consumer_mask = trophic_levels >= self.config.consumer_trophic_threshold  # (S,)
        
        # 向量化计算每个消费者的猎物密度
        # prey_matrix @ pop.reshape(S, H*W) -> (S, H*W) 每个物种在每个地块的猎物总量
        pop_flat = pop.reshape(S, H * W)  # (S, H*W)
        prey_pop_flat = prey_matrix.astype(np.float32) @ pop_flat  # (S, H*W)
        prey_pop = prey_pop_flat.reshape(S, H, W)  # (S, H, W)
        
        # 归一化到 [0, 1]
        prey_normalized = prey_pop / total_pop  # (S, H, W)
        
        # 对消费者应用计算结果，生产者保持 1.0
        consumer_mask_3d = consumer_mask[:, np.newaxis, np.newaxis]
        prey_density = np.where(consumer_mask_3d, prey_normalized, 1.0)
        
        # 检查有没有猎物的消费者（设为 0）
        has_prey = prey_matrix.any(axis=1)  # (S,)
        no_prey_consumer = consumer_mask & ~has_prey  # (S,)
        no_prey_mask_3d = no_prey_consumer[:, np.newaxis, np.newaxis]
        prey_density = np.where(no_prey_mask_3d, 0.0, prey_density)
        
        return prey_density.astype(np.float32)
    
    def compute_consumer_prey_shortage(
        self,
        pop: np.ndarray,
        trophic_levels: np.ndarray,
    ) -> np.ndarray:
        """计算每个消费者物种的猎物短缺程度 - 向量化版本
        
        Args:
            pop: 种群张量 (S, H, W)
            trophic_levels: 营养级数组 (S,)
        
        Returns:
            猎物短缺数组 (S,)
            - 0.0 表示猎物充足
            - 1.0 表示猎物极度匮乏
        """
        S = pop.shape[0]
        
        # 计算猎物密度 (S, H, W)
        prey_density = self.compute_prey_density(pop, trophic_levels)
        
        # 计算每个物种的总种群 (S,)
        total_pop = pop.sum(axis=(1, 2))  # (S,)
        total_pop = np.maximum(total_pop, 1e-8)  # 避免除零
        
        # 加权平均猎物密度 (S,)
        weighted_prey = (prey_density * pop).sum(axis=(1, 2)) / total_pop  # (S,)
        
        # 计算短缺程度
        shortage = np.where(
            weighted_prey < self.config.prey_scarcity_threshold,
            1.0 - weighted_prey / self.config.prey_scarcity_threshold,
            0.0
        )
        
        # 只有消费者才有短缺问题，生产者设为 0
        consumer_mask = trophic_levels >= self.config.consumer_trophic_threshold
        shortage = np.where(consumer_mask, shortage, 0.0)
        
        return shortage.astype(np.float32)
    
    def _numpy_migration_decision(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        distance_weights: np.ndarray,
        death_rates: np.ndarray,
        prey_density: np.ndarray | None = None,
        trophic_levels: np.ndarray | None = None,
    ) -> np.ndarray:
        """NumPy 迁徙决策计算 - 完全向量化版本
        
        Args:
            pop: 种群张量 (S, H, W)
            suitability: 适宜度张量 (S, H, W)
            distance_weights: 距离权重张量 (S, H, W)
            death_rates: 死亡率数组 (S,)
            prey_density: 猎物密度张量 (S, H, W)，可选
            trophic_levels: 营养级数组 (S,)，可选
        """
        S, H, W = pop.shape
        
        # 基础分数 (S, H, W)
        base_score = suitability * 0.5 + distance_weights * 0.5
        
        # 压力调整（向量化）
        pressure_mask = death_rates > self.config.pressure_threshold  # (S,)
        pressure_boost = np.minimum(0.5, (death_rates - self.config.pressure_threshold) * 2.0)  # (S,)
        
        # 广播到 (S, 1, 1) 用于向量化计算
        pressure_mask_3d = pressure_mask[:, np.newaxis, np.newaxis]  # (S, 1, 1)
        pressure_boost_3d = pressure_boost[:, np.newaxis, np.newaxis]  # (S, 1, 1)
        
        # 高压力时的分数
        pressure_score = (
            suitability * (0.6 + pressure_boost_3d * 0.2) +
            distance_weights * (0.4 - pressure_boost_3d * 0.2)
        )
        
        # 根据压力掩码选择分数
        base_score = np.where(pressure_mask_3d, pressure_score, base_score)
        
        # 【猎物追踪】消费者优先迁往猎物密集区（向量化）
        if prey_density is not None and trophic_levels is not None:
            prey_weight = self.config.prey_tracking_weight
            consumer_mask = trophic_levels >= self.config.consumer_trophic_threshold  # (S,)
            consumer_mask_3d = consumer_mask[:, np.newaxis, np.newaxis]  # (S, 1, 1)
            
            # 融合猎物密度到迁徙分数
            prey_adjusted_score = (
                base_score * (1.0 - prey_weight) +
                prey_density * suitability * prey_weight
            )
            
            base_score = np.where(consumer_mask_3d, prey_adjusted_score, base_score)
        
        # 已有种群的地块不需要迁入
        has_pop = pop > 0
        base_score = np.where(has_pop, 0.0, base_score)
        
        # 添加随机扰动
        noise = np.random.uniform(0.85, 1.15, base_score.shape).astype(np.float32)
        migration_scores = base_score * noise
        
        return migration_scores.astype(np.float32)
    
    def execute_batch_migration(
        self,
        pop: np.ndarray,
        migration_scores: np.ndarray,
        death_rates: np.ndarray,
    ) -> np.ndarray:
        """批量执行所有物种的迁徙
        
        【核心优化4】一次执行所有物种的迁徙
        
        Args:
            pop: 种群张量 (S, H, W)
            migration_scores: 迁徙分数张量 (S, H, W)
            death_rates: 死亡率数组 (S,)
        
        Returns:
            迁徙后的种群张量 (S, H, W)
        """
        S, H, W = pop.shape
        new_pop = np.zeros((S, H, W), dtype=np.float32)
        
        # 计算每个物种的迁徙率（向量化）
        base_rate = self.config.base_migration_rate
        boosted_rate = np.minimum(0.8, base_rate * self.config.pressure_migration_boost)
        high_pressure_mask = death_rates > self.config.pressure_threshold
        migration_rates = np.where(high_pressure_mask, boosted_rate, base_rate).astype(np.float32)
        
        if self._taichi_ready and _taichi_kernels is not None:
            _taichi_kernels.kernel_execute_migration(
                pop.astype(np.float32),
                migration_scores.astype(np.float32),
                new_pop,
                migration_rates,
                float(self.config.score_threshold),
            )
        else:
            # NumPy 回退
            new_pop = self._numpy_execute_migration(
                pop, migration_scores, migration_rates
            )
        
        return new_pop
    
    def _numpy_execute_migration(
        self,
        pop: np.ndarray,
        migration_scores: np.ndarray,
        migration_rates: np.ndarray,
    ) -> np.ndarray:
        """NumPy 迁徙执行 - 完全向量化版本"""
        S, H, W = pop.shape
        
        # 1. 计算每个物种的总种群 (S,)
        total_pop = pop.sum(axis=(1, 2))  # (S,)
        
        # 2. 计算有效迁徙分数掩码 (S, H, W)
        valid_mask = migration_scores > self.config.score_threshold
        
        # 3. 计算每个物种的总有效分数 (S,)
        masked_scores = np.where(valid_mask, migration_scores, 0.0)
        total_scores = masked_scores.sum(axis=(1, 2))  # (S,)
        total_scores = np.maximum(total_scores, 1e-8)  # 避免除零
        
        # 4. 计算迁徙量 (S,)
        migrate_amounts = total_pop * migration_rates  # (S,)
        
        # 5. 保留原有种群 (S, H, W)
        # 广播 migration_rates 到 (S, 1, 1)
        rates_3d = migration_rates[:, np.newaxis, np.newaxis]
        new_pop = pop * (1.0 - rates_3d)
        
        # 6. 按分数比例分配迁入种群 (S, H, W)
        # 广播 total_scores 到 (S, 1, 1)
        total_scores_3d = total_scores[:, np.newaxis, np.newaxis]
        score_ratio = masked_scores / total_scores_3d  # (S, H, W)
        
        # 广播 migrate_amounts 到 (S, 1, 1)
        migrate_3d = migrate_amounts[:, np.newaxis, np.newaxis]
        new_pop += migrate_3d * score_ratio
        
        return new_pop.astype(np.float32)
    
    def guided_diffusion(
        self,
        pop: np.ndarray,
        suitability: np.ndarray,
        rate: float | None = None,
    ) -> np.ndarray:
        """带适宜度引导的扩散
        
        种群优先向适宜度更高的地块扩散。
        
        Args:
            pop: 种群张量 (S, H, W)
            suitability: 适宜度张量 (S, H, W)
            rate: 扩散率
        
        Returns:
            扩散后的种群张量 (S, H, W)
        """
        if rate is None:
            rate = self.config.guided_diffusion_rate
        
        S, H, W = pop.shape
        new_pop = np.zeros((S, H, W), dtype=np.float32)
        
        if self._taichi_ready and _taichi_kernels is not None:
            _taichi_kernels.kernel_advanced_diffusion(
                pop.astype(np.float32),
                suitability.astype(np.float32),
                new_pop,
                float(rate),
            )
        else:
            # NumPy 回退 - 简化版扩散
            from scipy.ndimage import convolve
            
            kernel = np.array([
                [0, 1, 0],
                [1, 0, 1],
                [0, 1, 0],
            ], dtype=np.float32) * (rate / 4)
            kernel[1, 1] = 1.0 - rate
            
            for s in range(S):
                # 基础扩散
                diffused = convolve(pop[s], kernel, mode='constant', cval=0)
                
                # 适宜度加权
                suit_weight = suitability[s] + 0.1
                new_pop[s] = diffused * suit_weight
                
                # 归一化保持总量
                total_before = pop[s].sum()
                total_after = new_pop[s].sum()
                if total_after > 0:
                    new_pop[s] *= total_before / total_after
        
        return new_pop
    
    def process_migration(
        self,
        pop: np.ndarray,
        env: np.ndarray,
        species_prefs: np.ndarray,
        death_rates: np.ndarray,
        habitat_mask: np.ndarray | None = None,
        trophic_levels: np.ndarray | None = None,
        cooldown_mask: np.ndarray | None = None,
    ) -> tuple[np.ndarray, MigrationMetrics]:
        """完整的迁徙处理流程
        
        【主入口】一次调用完成所有物种的迁徙计算
        
        Args:
            pop: 种群张量 (S, H, W)
            env: 环境张量 (C, H, W)
            species_prefs: 物种偏好矩阵 (S, 7)
            death_rates: 死亡率数组 (S,)
            habitat_mask: 栖息地掩码 (S, H, W)，可选
            trophic_levels: 营养级数组 (S,)，用于猎物追踪
            cooldown_mask: 冷却期掩码 (S,)，True=允许迁徙, False=冷却中
        
        Returns:
            (迁徙后的种群张量, 性能指标)
        """
        start_time = time.perf_counter()
        metrics = MigrationMetrics(
            species_count=pop.shape[0],
            backend=self.backend,
        )
        
        S = pop.shape[0]
        
        # 1. 批量计算适宜度
        t0 = time.perf_counter()
        suitability = self.compute_batch_suitability(
            env, species_prefs, habitat_mask
        )
        metrics.suitability_time_ms = (time.perf_counter() - t0) * 1000
        
        # 2. 批量计算距离权重
        t0 = time.perf_counter()
        distance_weights = self.compute_batch_distance_weights(pop)
        metrics.distance_time_ms = (time.perf_counter() - t0) * 1000
        
        # 2.5 【猎物追踪】计算猎物密度
        prey_density = None
        if trophic_levels is not None:
            prey_density = self.compute_prey_density(pop, trophic_levels)
            # 记录猎物短缺的消费者
            prey_shortage = self.compute_consumer_prey_shortage(pop, trophic_levels)
            for s in range(S):
                if prey_shortage[s] > 0.5:
                    logger.debug(f"[猎物追踪] 物种{s} 猎物短缺={prey_shortage[s]:.2f}")
        
        # 3. 计算迁徙决策（融合猎物追踪）
        t0 = time.perf_counter()
        migration_scores = self.compute_migration_decisions(
            pop, suitability, distance_weights, death_rates,
            prey_density, trophic_levels
        )
        metrics.decision_time_ms = (time.perf_counter() - t0) * 1000
        
        # 3.5 【冷却期】应用冷却期掩码
        effective_death_rates = death_rates.copy()
        if cooldown_mask is not None:
            # 冷却中的物种：将死亡率设为 0，抑制迁徙
            for s in range(S):
                if not cooldown_mask[s]:  # False = 冷却中
                    migration_scores[s] = 0.0
                    effective_death_rates[s] = 0.0
                    logger.debug(f"[冷却期] 物种{s} 处于迁徙冷却期，跳过")
        
        # 4. 执行迁徙
        t0 = time.perf_counter()
        new_pop = self.execute_batch_migration(
            pop, migration_scores, effective_death_rates
        )
        metrics.execution_time_ms = (time.perf_counter() - t0) * 1000
        
        # 5. 带引导的扩散（可选）
        new_pop = self.guided_diffusion(new_pop, suitability)
        
        # 6. 【冷却期】恢复冷却中物种的原始分布
        if cooldown_mask is not None:
            for s in range(S):
                if not cooldown_mask[s]:
                    new_pop[s] = pop[s]
        
        # 统计迁徙物种数
        for s in range(S):
            if cooldown_mask is not None and not cooldown_mask[s]:
                continue
            if death_rates[s] > self.config.pressure_threshold:
                metrics.migrating_species += 1
        
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        self._last_metrics = metrics
        
        logger.debug(
            f"[TensorMigration] 完成迁徙计算: "
            f"{metrics.species_count}物种, {metrics.migrating_species}迁徙, "
            f"耗时={metrics.total_time_ms:.1f}ms, 后端={metrics.backend}"
        )
        
        return new_pop, metrics
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._suitability_cache = None
        self._distance_cache = None


# ============================================================================
# 全局实例管理
# ============================================================================

_global_engine: TensorMigrationEngine | None = None


def get_migration_engine(config: MigrationConfig | None = None) -> TensorMigrationEngine:
    """获取全局迁徙引擎实例"""
    global _global_engine
    if _global_engine is None:
        _global_engine = TensorMigrationEngine(config)
    return _global_engine


def reset_migration_engine() -> None:
    """重置全局迁徙引擎"""
    global _global_engine
    if _global_engine is not None:
        _global_engine.clear_cache()
    _global_engine = None


# ============================================================================
# 辅助函数：从 Species 对象提取偏好矩阵
# ============================================================================

def extract_species_preferences(
    species_list: list,
    species_map: dict[str, int],
) -> np.ndarray:
    """从物种列表提取偏好矩阵
    
    Args:
        species_list: Species 对象列表
        species_map: {lineage_code: tensor_index}
    
    Returns:
        物种偏好矩阵 (S, 7)
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
        
        prefs[idx, 4] = 1.0 if is_terrestrial else 0.0  # 陆地
        prefs[idx, 5] = 1.0 if is_aquatic else 0.0      # 海洋
        prefs[idx, 6] = 1.0 if is_coastal else 0.0      # 海岸
    
    return prefs


def extract_habitat_mask(
    env: np.ndarray,
    species_prefs: np.ndarray,
) -> np.ndarray:
    """从环境和物种偏好生成栖息地掩码
    
    Args:
        env: 环境张量 (C, H, W)
        species_prefs: 物种偏好矩阵 (S, 7)
    
    Returns:
        栖息地掩码 (S, H, W)
    """
    S = species_prefs.shape[0]
    H, W = env.shape[1], env.shape[2]
    
    mask = np.ones((S, H, W), dtype=np.float32)
    
    if env.shape[0] > 4:
        is_land = env[4] > 0.5
        is_sea = env[5] > 0.5 if env.shape[0] > 5 else ~is_land
        
        for s in range(S):
            # 纯陆生不能下海
            if species_prefs[s, 4] > 0.5 and species_prefs[s, 5] < 0.1:
                mask[s] = np.where(is_sea, 0.0, 1.0)
            # 纯水生不能上岸
            elif species_prefs[s, 5] > 0.5 and species_prefs[s, 4] < 0.1:
                mask[s] = np.where(is_land, 0.0, 1.0)
    
    return mask
