"""
张量化生态位计算模块

将 O(n²) 的循环计算优化为矩阵运算，支持 GPU 加速。

主要优化：
1. 地块重叠因子计算：使用二进制矩阵 + 矩阵乘法
2. 谱系前缀匹配：向量化字符比较
3. 栖息地类型匹配：类别编码 + 广播
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)


@dataclass
class NicheTensorMetrics:
    """生态位张量计算性能指标"""
    total_time_ms: float = 0.0
    tile_overlap_time_ms: float = 0.0
    lineage_bonus_time_ms: float = 0.0
    habitat_bonus_time_ms: float = 0.0
    species_count: int = 0
    tile_count: int = 0
    backend: str = "numpy"


class NicheTensorCompute:
    """张量化生态位计算引擎
    
    将 NicheAnalyzer 中的 O(n²) 循环优化为矩阵运算。
    
    使用方法：
        compute = NicheTensorCompute()
        
        # 计算地块重叠因子矩阵
        overlap_matrix = compute.compute_tile_overlap_matrix(
            species_ids, habitat_cache, max_tile_id
        )
        
        # 计算谱系bonus矩阵
        lineage_bonus = compute.compute_lineage_bonus_matrix(lineage_codes)
        
        # 计算栖息地类型bonus矩阵
        habitat_bonus = compute.compute_habitat_bonus_matrix(habitat_types)
    """
    
    # 栖息地类型编码
    HABITAT_ENCODING = {
        "marine": 0,
        "terrestrial": 1,
        "freshwater": 2,
        "aerial": 3,
        "coastal": 4,
        "deep_sea": 5,
        "unknown": 6,
    }
    
    # 兼容栖息地对（双向）
    COMPATIBLE_HABITATS = {
        (0, 4), (0, 5),  # marine <-> coastal, deep_sea
        (1, 2),          # terrestrial <-> freshwater（两栖）
        (1, 3),          # terrestrial <-> aerial
    }
    
    def __init__(self):
        """初始化生态位张量计算引擎"""
        self._taichi_available = False
        self._kernels = None
        
        # 尝试加载 Taichi 内核
        try:
            from .taichi_hybrid_kernels import (
                kernel_tile_overlap_matrix,
                kernel_lineage_prefix_match,
            )
            self._taichi_available = True
            self._kernels = {
                "tile_overlap": kernel_tile_overlap_matrix,
                "lineage_prefix": kernel_lineage_prefix_match,
            }
            logger.debug("[NicheTensor] Taichi 内核加载成功")
        except ImportError:
            logger.debug("[NicheTensor] Taichi 不可用，使用 NumPy")
    
    def compute_tile_overlap_matrix(
        self,
        species_ids: list[int | None],
        habitat_cache: dict[int, set[int]],
        max_tile_id: int | None = None,
        min_overlap_factor: float = 0.1,
    ) -> tuple[np.ndarray, NicheTensorMetrics]:
        """计算地块重叠因子矩阵（向量化）
        
        使用二进制矩阵表示物种-地块关系，然后通过矩阵运算计算 Jaccard 系数。
        
        Args:
            species_ids: 物种 ID 列表（与物种列表顺序一致）
            habitat_cache: {species_id: set(tile_ids)} 映射
            max_tile_id: 最大地块 ID（用于确定矩阵大小）
            min_overlap_factor: 无共享地块时的最小重叠因子
            
        Returns:
            (overlap_matrix, metrics) - N×N 的重叠因子矩阵和性能指标
        """
        start_time = time.perf_counter()
        metrics = NicheTensorMetrics(backend="numpy")
        
        n = len(species_ids)
        metrics.species_count = n
        
        if n <= 1:
            return np.ones((n, n)), metrics
        
        # 收集所有地块 ID
        all_tiles: set[int] = set()
        for sp_id in species_ids:
            if sp_id is not None and sp_id in habitat_cache:
                all_tiles.update(habitat_cache[sp_id])
        
        if not all_tiles:
            # 没有栖息地数据，返回默认中等重叠
            return np.full((n, n), 0.5), metrics
        
        # 创建地块 ID 到索引的映射
        tile_list = sorted(all_tiles)
        tile_to_idx = {tile_id: idx for idx, tile_id in enumerate(tile_list)}
        num_tiles = len(tile_list)
        metrics.tile_count = num_tiles
        
        # 构建物种-地块二进制矩阵 (S × T)
        species_tile_matrix = np.zeros((n, num_tiles), dtype=np.float32)
        
        for i, sp_id in enumerate(species_ids):
            if sp_id is not None and sp_id in habitat_cache:
                for tile_id in habitat_cache[sp_id]:
                    if tile_id in tile_to_idx:
                        species_tile_matrix[i, tile_to_idx[tile_id]] = 1.0
        
        # 计算每个物种的地块数量
        tile_counts = species_tile_matrix.sum(axis=1)  # (S,)
        
        # 计算共享地块数：A ∩ B = A @ B.T（对于二进制矩阵）
        intersection = species_tile_matrix @ species_tile_matrix.T  # (S, S)
        
        # 计算总地块数：|A ∪ B| = |A| + |B| - |A ∩ B|
        union = (
            tile_counts[:, np.newaxis] +  # |A|
            tile_counts[np.newaxis, :] -  # |B|
            intersection                   # - |A ∩ B|
        )
        
        # 计算 Jaccard 系数
        # 避免除零：当 union 为 0 时，设置为 min_overlap_factor
        with np.errstate(divide='ignore', invalid='ignore'):
            overlap_matrix = np.where(
                union > 0,
                intersection / union,
                min_overlap_factor
            )
        
        # 无共享地块时使用最小重叠因子
        overlap_matrix = np.where(
            intersection == 0,
            min_overlap_factor,
            overlap_matrix
        )
        
        # 对角线设为 1
        np.fill_diagonal(overlap_matrix, 1.0)
        
        metrics.tile_overlap_time_ms = (time.perf_counter() - start_time) * 1000
        metrics.total_time_ms = metrics.tile_overlap_time_ms
        
        return overlap_matrix.astype(np.float64), metrics
    
    def compute_lineage_bonus_matrix(
        self,
        lineage_codes: list[str],
        min_common_prefix: int = 2,
        bonus_value: float = 0.15,
    ) -> tuple[np.ndarray, float]:
        """计算谱系前缀匹配的 bonus 矩阵（向量化）
        
        如果两个物种共享 >= min_common_prefix 个前缀字符，给予 bonus。
        
        Args:
            lineage_codes: 物种谱系代码列表
            min_common_prefix: 最小共同前缀长度
            bonus_value: bonus 值
            
        Returns:
            (bonus_matrix, time_ms) - N×N 的 bonus 矩阵和计算耗时
        """
        start_time = time.perf_counter()
        
        n = len(lineage_codes)
        if n <= 1:
            return np.zeros((n, n)), 0.0
        
        # 计算最大代码长度
        max_len = max(len(code) for code in lineage_codes) if lineage_codes else 0
        if max_len < min_common_prefix:
            return np.zeros((n, n)), (time.perf_counter() - start_time) * 1000
        
        # 将代码转换为字符数组
        # 使用 ASCII 编码，填充为相同长度
        code_array = np.zeros((n, max_len), dtype=np.int32)
        for i, code in enumerate(lineage_codes):
            for j, char in enumerate(code):
                code_array[i, j] = ord(char)
        
        # 向量化比较：对每个位置检查是否相等
        # (n, 1, max_len) == (1, n, max_len) -> (n, n, max_len)
        char_match = code_array[:, np.newaxis, :] == code_array[np.newaxis, :, :]
        
        # 计算累积匹配（从开头连续匹配的长度）
        # 使用 cumprod 检测连续匹配
        cumulative_match = np.cumprod(char_match, axis=2)
        
        # 计算共同前缀长度
        common_prefix_length = cumulative_match.sum(axis=2)  # (n, n)
        
        # 生成 bonus 矩阵
        bonus_matrix = np.where(
            common_prefix_length >= min_common_prefix,
            bonus_value,
            0.0
        )
        
        # 对角线设为 0（自己与自己不算）
        np.fill_diagonal(bonus_matrix, 0.0)
        
        time_ms = (time.perf_counter() - start_time) * 1000
        return bonus_matrix, time_ms
    
    def compute_habitat_bonus_matrix(
        self,
        habitat_types: list[str],
        same_habitat_bonus: float = 0.10,
        compatible_bonus: float = 0.05,
    ) -> tuple[np.ndarray, float]:
        """计算栖息地类型匹配的 bonus 矩阵（向量化）
        
        Args:
            habitat_types: 栖息地类型列表
            same_habitat_bonus: 相同栖息地的 bonus
            compatible_bonus: 兼容栖息地的 bonus
            
        Returns:
            (bonus_matrix, time_ms) - N×N 的 bonus 矩阵和计算耗时
        """
        start_time = time.perf_counter()
        
        n = len(habitat_types)
        if n <= 1:
            return np.zeros((n, n)), 0.0
        
        # 将栖息地类型转换为数字编码
        habitat_codes = np.array([
            self.HABITAT_ENCODING.get(h.lower(), 6)  # 6 = unknown
            for h in habitat_types
        ], dtype=np.int32)
        
        # 计算相同栖息地矩阵
        same_habitat = habitat_codes[:, np.newaxis] == habitat_codes[np.newaxis, :]
        
        # 计算兼容栖息地矩阵
        compatible = np.zeros((n, n), dtype=bool)
        for (h1, h2) in self.COMPATIBLE_HABITATS:
            # 双向兼容
            compatible |= (
                (habitat_codes[:, np.newaxis] == h1) & 
                (habitat_codes[np.newaxis, :] == h2)
            )
            compatible |= (
                (habitat_codes[:, np.newaxis] == h2) & 
                (habitat_codes[np.newaxis, :] == h1)
            )
        
        # 生成 bonus 矩阵
        bonus_matrix = np.where(same_habitat, same_habitat_bonus, 0.0)
        bonus_matrix = np.where(
            (~same_habitat) & compatible,
            compatible_bonus,
            bonus_matrix
        )
        
        # 对角线设为 0
        np.fill_diagonal(bonus_matrix, 0.0)
        
        time_ms = (time.perf_counter() - start_time) * 1000
        return bonus_matrix, time_ms
    
    def compute_full_ecological_bonus(
        self,
        species_list: Sequence['Species'],
        habitat_cache: dict[int, set[int]],
        max_bonus: float = 0.30,
    ) -> tuple[np.ndarray, NicheTensorMetrics]:
        """计算完整的生态位 bonus 矩阵
        
        整合所有规则的 bonus 计算：
        1. 营养级相似度
        2. 栖息地类型匹配
        3. 体型相近
        4. 谱系前缀匹配
        
        Args:
            species_list: 物种列表
            habitat_cache: 栖息地缓存
            max_bonus: 最大 bonus 上限
            
        Returns:
            (bonus_matrix, metrics) - N×N 的总 bonus 矩阵
        """
        start_time = time.perf_counter()
        species_list = list(species_list)
        n = len(species_list)
        
        metrics = NicheTensorMetrics(species_count=n)
        
        if n <= 1:
            return np.zeros((n, n)), metrics
        
        # 提取特征
        trophic_levels = np.array([sp.trophic_level for sp in species_list])
        habitat_types = [
            getattr(sp, 'habitat_type', 'unknown') or 'unknown' 
            for sp in species_list
        ]
        sizes = np.array([
            sp.morphology_stats.get("body_length_cm", 0.01) 
            for sp in species_list
        ])
        lineage_codes = [sp.lineage_code for sp in species_list]
        
        # 1. 营养级 bonus（向量化）
        trophic_diff = np.abs(
            trophic_levels[:, np.newaxis] - trophic_levels[np.newaxis, :]
        )
        functional_bonus = np.where(trophic_diff < 0.5, 0.12, 0.0)
        functional_bonus = np.where(
            (trophic_diff >= 0.5) & (trophic_diff < 1.0),
            0.06,
            functional_bonus
        )
        
        # 2. 栖息地类型 bonus（向量化）
        habitat_bonus, hab_time = self.compute_habitat_bonus_matrix(habitat_types)
        metrics.habitat_bonus_time_ms = hab_time
        
        # 3. 体型相近 bonus（向量化）
        sizes = np.maximum(sizes, 0.001)
        size_min = np.minimum.outer(sizes, sizes)
        size_max = np.maximum.outer(sizes, sizes)
        size_ratio = size_max / size_min
        size_bonus = np.where(size_ratio <= 2.0, 0.06, 0.0)
        size_bonus = np.where(
            (size_ratio > 2.0) & (size_ratio <= 5.0),
            0.03,
            size_bonus
        )
        
        # 4. 谱系前缀 bonus（向量化）
        lineage_bonus, lin_time = self.compute_lineage_bonus_matrix(lineage_codes)
        metrics.lineage_bonus_time_ms = lin_time
        
        # 合并 bonus
        total_bonus = functional_bonus + habitat_bonus + size_bonus + lineage_bonus
        total_bonus = np.minimum(total_bonus, max_bonus)
        np.fill_diagonal(total_bonus, 0.0)
        
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        
        return total_bonus, metrics


# 全局单例
_niche_tensor_compute: NicheTensorCompute | None = None


def get_niche_tensor_compute() -> NicheTensorCompute:
    """获取生态位张量计算引擎单例"""
    global _niche_tensor_compute
    if _niche_tensor_compute is None:
        _niche_tensor_compute = NicheTensorCompute()
    return _niche_tensor_compute


def reset_niche_tensor_compute() -> None:
    """重置生态位张量计算引擎"""
    global _niche_tensor_compute
    _niche_tensor_compute = None
