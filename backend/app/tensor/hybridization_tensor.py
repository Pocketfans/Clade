"""
张量化杂交候选筛选模块

将 O(n²) 的物种对遍历优化为矩阵运算，支持 GPU 加速。

主要优化：
1. 批量计算同域矩阵（地块重叠）
2. 批量计算遗传距离矩阵
3. 向量化筛选杂交候选
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..models.species import Species
    from ..models.environment import HabitatPopulation

logger = logging.getLogger(__name__)


@dataclass
class HybridCandidate:
    """杂交候选对"""
    species1_idx: int
    species2_idx: int
    species1_code: str
    species2_code: str
    shared_tiles: int
    total_tiles: int
    sympatry_ratio: float
    genetic_distance: float
    fertility: float
    hybrid_score: float  # 综合杂交得分


@dataclass
class HybridizationTensorMetrics:
    """杂交张量计算性能指标"""
    total_time_ms: float = 0.0
    sympatry_time_ms: float = 0.0
    genetic_distance_time_ms: float = 0.0
    filtering_time_ms: float = 0.0
    species_count: int = 0
    candidate_pairs: int = 0
    filtered_pairs: int = 0
    backend: str = "numpy"


class HybridizationTensorCompute:
    """张量化杂交候选筛选引擎
    
    将 AutoHybridizationStage 中的 O(n²) 循环优化为矩阵运算。
    
    使用方法：
        compute = HybridizationTensorCompute()
        
        candidates, metrics = compute.find_hybrid_candidates(
            species_list=alive_species,
            habitat_data=all_habitats,
            min_population=500,
            max_genetic_distance=0.7,
            min_shared_tiles=1,
        )
    """
    
    # 杂交遗传距离阈值（低于此值才能杂交）
    MAX_HYBRIDIZATION_DISTANCE = 0.7
    
    # 可育性计算参数
    FERTILITY_OPTIMAL_DISTANCE = 0.15  # 最佳遗传距离
    FERTILITY_MAX_DISTANCE = 0.70      # 最大可杂交距离
    
    def __init__(self):
        """初始化杂交张量计算引擎"""
        self._taichi_available = False
        
        try:
            from .taichi_hybrid_kernels import TAICHI_AVAILABLE
            self._taichi_available = TAICHI_AVAILABLE
            if self._taichi_available:
                logger.debug("[HybridTensor] Taichi 可用")
        except ImportError:
            pass
    
    def build_sympatry_matrix(
        self,
        species_list: Sequence['Species'],
        habitat_data: list['HabitatPopulation'] | None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """构建同域矩阵（物种间的地块重叠情况）
        
        Args:
            species_list: 物种列表
            habitat_data: 栖息地数据
            
        Returns:
            (shared_tiles_matrix, total_tiles_matrix, sympatry_ratio_matrix)
            - shared_tiles_matrix: N×N 共享地块数矩阵
            - total_tiles_matrix: N×N 总地块数矩阵（分母）
            - sympatry_ratio_matrix: N×N 同域比例矩阵
        """
        species_list = list(species_list)
        n = len(species_list)
        
        if n == 0:
            return np.array([]), np.array([]), np.array([])
        
        # 构建 species_id -> index 映射
        id_to_idx: dict[int, int] = {}
        for i, sp in enumerate(species_list):
            if sp.id is not None:
                id_to_idx[sp.id] = i
        
        # 收集所有地块 ID
        all_tiles: set[int] = set()
        species_tiles: list[set[int]] = [set() for _ in range(n)]
        
        if habitat_data:
            for hab in habitat_data:
                idx = id_to_idx.get(hab.species_id)
                if idx is not None:
                    species_tiles[idx].add(hab.tile_id)
                    all_tiles.add(hab.tile_id)
        
        if not all_tiles:
            # 没有栖息地数据
            return (
                np.zeros((n, n)),
                np.ones((n, n)),
                np.zeros((n, n))
            )
        
        # 创建地块映射
        tile_list = sorted(all_tiles)
        tile_to_idx = {t: i for i, t in enumerate(tile_list)}
        num_tiles = len(tile_list)
        
        # 构建物种-地块二进制矩阵
        species_tile_matrix = np.zeros((n, num_tiles), dtype=np.float32)
        for i, tiles in enumerate(species_tiles):
            for tile_id in tiles:
                if tile_id in tile_to_idx:
                    species_tile_matrix[i, tile_to_idx[tile_id]] = 1.0
        
        # 计算每个物种的地块数
        tile_counts = species_tile_matrix.sum(axis=1)  # (n,)
        
        # 共享地块数：矩阵乘法
        shared_tiles_matrix = species_tile_matrix @ species_tile_matrix.T
        
        # 计算分母：min(|A|, |B|)，用于同域比例
        # sympatry_ratio = shared / min(tiles1, tiles2)
        min_tiles_matrix = np.minimum.outer(tile_counts, tile_counts)
        min_tiles_matrix = np.maximum(min_tiles_matrix, 1)  # 避免除零
        
        # 同域比例
        sympatry_ratio_matrix = shared_tiles_matrix / min_tiles_matrix
        sympatry_ratio_matrix = np.clip(sympatry_ratio_matrix, 0, 1)
        
        # 总地块数（用于 Jaccard）
        total_tiles_matrix = (
            tile_counts[:, np.newaxis] +
            tile_counts[np.newaxis, :] -
            shared_tiles_matrix
        )
        total_tiles_matrix = np.maximum(total_tiles_matrix, 1)
        
        return shared_tiles_matrix, total_tiles_matrix, sympatry_ratio_matrix
    
    def build_genetic_distance_matrix(
        self,
        species_list: Sequence['Species'],
    ) -> np.ndarray:
        """构建遗传距离矩阵
        
        使用简化的快速计算方法，主要基于：
        1. 形态差异（体长、体重）
        2. 营养级差异
        3. 谱系距离
        
        Args:
            species_list: 物种列表
            
        Returns:
            N×N 遗传距离矩阵
        """
        species_list = list(species_list)
        n = len(species_list)
        
        if n == 0:
            return np.array([])
        
        # 提取特征向量
        lengths = np.array([
            sp.morphology_stats.get("body_length_cm", 1.0)
            for sp in species_list
        ], dtype=np.float64)
        
        weights = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0)
            for sp in species_list
        ], dtype=np.float64)
        
        trophic_levels = np.array([
            sp.trophic_level for sp in species_list
        ], dtype=np.float64)
        
        created_turns = np.array([
            sp.created_turn for sp in species_list
        ], dtype=np.float64)
        
        lineage_codes = [sp.lineage_code for sp in species_list]
        
        # 确保非零
        lengths = np.maximum(lengths, 0.001)
        weights = np.maximum(weights, 0.001)
        
        # 1. 形态差异（30%）
        length_ratio = np.minimum.outer(lengths, lengths) / np.maximum.outer(lengths, lengths)
        weight_ratio = np.minimum.outer(weights, weights) / np.maximum.outer(weights, weights)
        morphology_diff = ((1 - length_ratio) + (1 - weight_ratio)) / 2
        
        # 2. 营养级差异（20%）
        trophic_diff = np.abs(
            trophic_levels[:, np.newaxis] - trophic_levels[np.newaxis, :]
        ) / 4.0  # 营养级最大差 ~4
        trophic_diff = np.clip(trophic_diff, 0, 1)
        
        # 3. 时间分化（20%）
        max_turn_diff = max(created_turns.max() - created_turns.min(), 1)
        turn_diff = np.abs(
            created_turns[:, np.newaxis] - created_turns[np.newaxis, :]
        ) / max(max_turn_diff, 40)  # 40回合达到最大
        turn_diff = np.clip(turn_diff, 0, 1)
        
        # 4. 谱系距离（30%）- 基于共同前缀长度
        lineage_diff = self._compute_lineage_distance_matrix(lineage_codes)
        
        # 组合
        distance_matrix = (
            morphology_diff * 0.30 +
            trophic_diff * 0.20 +
            turn_diff * 0.20 +
            lineage_diff * 0.30
        )
        
        np.fill_diagonal(distance_matrix, 0)
        return np.clip(distance_matrix, 0, 1)
    
    def _compute_lineage_distance_matrix(
        self,
        lineage_codes: list[str],
    ) -> np.ndarray:
        """计算谱系距离矩阵
        
        基于共同前缀长度计算距离：
        - 完全相同：0
        - 无共同前缀：1
        - 部分共同前缀：按比例
        """
        n = len(lineage_codes)
        if n == 0:
            return np.array([])
        
        max_len = max(len(c) for c in lineage_codes) if lineage_codes else 1
        
        # 转换为字符数组
        code_array = np.zeros((n, max_len), dtype=np.int32)
        code_lengths = np.zeros(n, dtype=np.int32)
        
        for i, code in enumerate(lineage_codes):
            code_lengths[i] = len(code)
            for j, char in enumerate(code):
                code_array[i, j] = ord(char)
        
        # 计算共同前缀长度
        char_match = code_array[:, np.newaxis, :] == code_array[np.newaxis, :, :]
        cumulative_match = np.cumprod(char_match, axis=2)
        common_prefix_length = cumulative_match.sum(axis=2)  # (n, n)
        
        # 计算最大可能前缀长度
        max_possible = np.minimum.outer(code_lengths, code_lengths)
        max_possible = np.maximum(max_possible, 1)  # 避免除零
        
        # 距离 = 1 - (共同前缀 / 最大可能前缀)
        distance = 1.0 - (common_prefix_length / max_possible)
        np.fill_diagonal(distance, 0)
        
        return distance
    
    def compute_fertility(self, genetic_distance: np.ndarray) -> np.ndarray:
        """计算可育性矩阵
        
        基于遗传距离计算可育性：
        - 距离 < 0.15: 高可育性（接近1.0）
        - 距离 0.15-0.70: 线性下降
        - 距离 > 0.70: 不可杂交（0）
        
        Args:
            genetic_distance: N×N 遗传距离矩阵
            
        Returns:
            N×N 可育性矩阵
        """
        fertility = np.zeros_like(genetic_distance)
        
        # 距离 < 0.15: 高可育性
        mask_high = genetic_distance < self.FERTILITY_OPTIMAL_DISTANCE
        fertility[mask_high] = 1.0 - genetic_distance[mask_high] * 0.5
        
        # 距离 0.15-0.70: 线性下降
        mask_mid = (
            (genetic_distance >= self.FERTILITY_OPTIMAL_DISTANCE) &
            (genetic_distance <= self.FERTILITY_MAX_DISTANCE)
        )
        # 从 ~0.93 线性下降到 0
        range_size = self.FERTILITY_MAX_DISTANCE - self.FERTILITY_OPTIMAL_DISTANCE
        fertility[mask_mid] = (
            (self.FERTILITY_MAX_DISTANCE - genetic_distance[mask_mid]) / 
            range_size * 0.93
        )
        
        # 距离 > 0.70: 不可杂交
        # fertility 默认为 0
        
        np.fill_diagonal(fertility, 0)
        return np.clip(fertility, 0, 1)
    
    def find_hybrid_candidates(
        self,
        species_list: Sequence['Species'],
        habitat_data: list['HabitatPopulation'] | None,
        min_population: int = 500,
        max_genetic_distance: float = 0.70,
        min_shared_tiles: int = 1,
        max_candidates: int = 100,
    ) -> tuple[list[HybridCandidate], HybridizationTensorMetrics]:
        """批量查找杂交候选对
        
        使用张量计算批量筛选所有可能的杂交候选，然后按得分排序。
        
        Args:
            species_list: 物种列表
            habitat_data: 栖息地数据
            min_population: 最小种群要求
            max_genetic_distance: 最大遗传距离
            min_shared_tiles: 最少共享地块数
            max_candidates: 最多返回候选数
            
        Returns:
            (candidates, metrics) - 杂交候选列表和性能指标
        """
        start_time = time.perf_counter()
        metrics = HybridizationTensorMetrics(backend="numpy")
        
        # 过滤种群不足的物种
        species_list = [
            sp for sp in species_list
            if (sp.morphology_stats.get("population", 0) or 0) >= min_population
        ]
        
        n = len(species_list)
        metrics.species_count = n
        
        if n < 2:
            return [], metrics
        
        # 1. 计算同域矩阵
        t0 = time.perf_counter()
        shared_tiles, total_tiles, sympatry_ratio = self.build_sympatry_matrix(
            species_list, habitat_data
        )
        metrics.sympatry_time_ms = (time.perf_counter() - t0) * 1000
        
        # 2. 计算遗传距离矩阵
        t0 = time.perf_counter()
        genetic_distance = self.build_genetic_distance_matrix(species_list)
        fertility = self.compute_fertility(genetic_distance)
        metrics.genetic_distance_time_ms = (time.perf_counter() - t0) * 1000
        
        # 3. 向量化筛选
        t0 = time.perf_counter()
        
        # 创建有效候选掩码
        # 只取上三角（避免重复）
        upper_mask = np.triu(np.ones((n, n), dtype=bool), k=1)
        
        # 条件1：有共享地块
        sympatry_mask = shared_tiles >= min_shared_tiles
        
        # 条件2：遗传距离在阈值内
        distance_mask = genetic_distance <= max_genetic_distance
        
        # 条件3：可育性 > 0
        fertility_mask = fertility > 0
        
        # 组合所有条件
        valid_mask = upper_mask & sympatry_mask & distance_mask & fertility_mask
        
        # 计算综合得分
        # 得分 = 同域比例 × 可育性 × (1 - 遗传距离)
        hybrid_score = sympatry_ratio * fertility * (1 - genetic_distance)
        hybrid_score[~valid_mask] = 0
        
        # 找到所有有效候选的索引
        valid_indices = np.argwhere(valid_mask)
        metrics.candidate_pairs = len(valid_indices)
        
        # 按得分排序
        scores = hybrid_score[valid_mask]
        sorted_order = np.argsort(scores)[::-1]  # 降序
        
        # 提取候选
        candidates = []
        lineage_codes = [sp.lineage_code for sp in species_list]
        
        for rank in range(min(len(sorted_order), max_candidates)):
            idx = sorted_order[rank]
            i, j = valid_indices[idx]
            
            candidate = HybridCandidate(
                species1_idx=int(i),
                species2_idx=int(j),
                species1_code=lineage_codes[i],
                species2_code=lineage_codes[j],
                shared_tiles=int(shared_tiles[i, j]),
                total_tiles=int(total_tiles[i, j]),
                sympatry_ratio=float(sympatry_ratio[i, j]),
                genetic_distance=float(genetic_distance[i, j]),
                fertility=float(fertility[i, j]),
                hybrid_score=float(hybrid_score[i, j]),
            )
            candidates.append(candidate)
        
        metrics.filtered_pairs = len(candidates)
        metrics.filtering_time_ms = (time.perf_counter() - t0) * 1000
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        
        logger.debug(
            f"[杂交张量] 物种={n}, 候选={metrics.candidate_pairs}, "
            f"筛选={metrics.filtered_pairs}, 耗时={metrics.total_time_ms:.1f}ms"
        )
        
        return candidates, metrics


# 全局单例
_hybridization_tensor_compute: HybridizationTensorCompute | None = None


def get_hybridization_tensor_compute() -> HybridizationTensorCompute:
    """获取杂交张量计算引擎单例"""
    global _hybridization_tensor_compute
    if _hybridization_tensor_compute is None:
        _hybridization_tensor_compute = HybridizationTensorCompute()
    return _hybridization_tensor_compute


def reset_hybridization_tensor_compute() -> None:
    """重置杂交张量计算引擎"""
    global _hybridization_tensor_compute
    _hybridization_tensor_compute = None
