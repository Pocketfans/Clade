"""向量化栖息地适宜度计算模块

提供批量计算物种×地块适宜度矩阵的工具函数，
替代多处重复的逐对计算逻辑，显著提升性能。

使用场景：
- MapStateManager.snapshot_habitats
- HabitatManager 地块筛选
- ReproductionService 承载力计算
- SpeciationService 栖息地初始化
"""
from __future__ import annotations

import math
from typing import Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.environment import MapTile


def compute_suitability_matrix(
    species_list: Sequence['Species'],
    tiles: Sequence['MapTile'],
    weights: dict[str, float] | None = None
) -> np.ndarray:
    """批量计算物种×地块的适宜度矩阵（向量化）
    
    Args:
        species_list: 物种列表 (N个)
        tiles: 地块列表 (M个)
        weights: 各因子权重，默认 {"temp": 0.35, "humidity": 0.30, "resource": 0.35}
        
    Returns:
        np.ndarray: shape (N, M) 的适宜度矩阵，值域 [0, 1]
    """
    if not species_list or not tiles:
        return np.array([])
    
    if weights is None:
        weights = {"temp": 0.35, "humidity": 0.30, "resource": 0.35}
    
    n_species = len(species_list)
    n_tiles = len(tiles)
    
    # ============ 提取物种属性矩阵 (N × K) ============
    heat_pref = np.array([sp.abstract_traits.get("耐热性", 5) for sp in species_list])
    cold_pref = np.array([sp.abstract_traits.get("耐寒性", 5) for sp in species_list])
    drought_pref = np.array([sp.abstract_traits.get("耐旱性", 5) for sp in species_list])
    
    # ============ 提取地块属性矩阵 (M,) ============
    temperatures = np.array([t.temperature for t in tiles])
    humidities = np.array([t.humidity for t in tiles])
    resources = np.array([t.resources for t in tiles])
    
    # ============ 向量化计算温度适应度 ============
    # 热带（>20°C）：使用耐热性
    # 寒冷（<5°C）：使用耐寒性
    # 温和（5-20°C）：基础分0.8
    
    # 创建温度分数矩阵 (N, M)
    temp_score = np.zeros((n_species, n_tiles))
    
    # 使用广播计算
    hot_mask = temperatures > 20  # (M,)
    cold_mask = temperatures < 5  # (M,)
    mild_mask = ~hot_mask & ~cold_mask  # (M,)
    
    # 热区：temp_score = heat_pref / 10
    temp_score[:, hot_mask] = (heat_pref[:, np.newaxis] / 10.0)[:, :np.sum(hot_mask)]
    
    # 冷区：temp_score = cold_pref / 10
    temp_score[:, cold_mask] = (cold_pref[:, np.newaxis] / 10.0)[:, :np.sum(cold_mask)]
    
    # 温和区：固定0.8
    temp_score[:, mild_mask] = 0.8
    
    # ============ 向量化计算湿度适应度 ============
    # 物种偏好湿度 = 1 - drought_pref/10（耐旱性越高，偏好越干燥）
    species_humidity_pref = 1.0 - drought_pref / 10.0  # (N,)
    
    # 湿度匹配度 = 1 - |实际湿度 - 偏好湿度|
    humidity_diff = np.abs(humidities[np.newaxis, :] - species_humidity_pref[:, np.newaxis])
    humidity_score = 1.0 - humidity_diff  # (N, M)
    humidity_score = np.clip(humidity_score, 0.0, 1.0)
    
    # ============ 向量化计算资源适应度 ============
    # 使用对数归一化（资源是指数分布的）
    resource_score = np.minimum(1.0, np.log(resources + 1) / np.log(1001))  # (M,)
    resource_score = resource_score[np.newaxis, :].repeat(n_species, axis=0)  # (N, M)
    
    # ============ 组合得分 ============
    suitability = (
        temp_score * weights["temp"] +
        humidity_score * weights["humidity"] +
        resource_score * weights["resource"]
    )
    
    # 确保非负
    suitability = np.maximum(suitability, 0.0)
    
    return suitability


def compute_suitability_for_species(
    species: 'Species',
    tiles: Sequence['MapTile'],
    include_resource: bool = True
) -> np.ndarray:
    """计算单个物种对所有地块的适宜度（向量化）
    
    Args:
        species: 目标物种
        tiles: 地块列表
        include_resource: 是否包含资源因子
        
    Returns:
        np.ndarray: shape (M,) 的适宜度数组
    """
    if not tiles:
        return np.array([])
    
    n_tiles = len(tiles)
    
    # 提取物种属性
    heat_pref = species.abstract_traits.get("耐热性", 5)
    cold_pref = species.abstract_traits.get("耐寒性", 5)
    drought_pref = species.abstract_traits.get("耐旱性", 5)
    
    # 提取地块属性
    temperatures = np.array([t.temperature for t in tiles])
    humidities = np.array([t.humidity for t in tiles])
    
    # 温度适应度
    temp_score = np.zeros(n_tiles)
    hot_mask = temperatures > 20
    cold_mask = temperatures < 5
    mild_mask = ~hot_mask & ~cold_mask
    
    temp_score[hot_mask] = heat_pref / 10.0
    temp_score[cold_mask] = cold_pref / 10.0
    temp_score[mild_mask] = 0.8
    
    # 湿度适应度
    humidity_pref = 1.0 - drought_pref / 10.0
    humidity_score = 1.0 - np.abs(humidities - humidity_pref)
    humidity_score = np.clip(humidity_score, 0.0, 1.0)
    
    if include_resource:
        resources = np.array([t.resources for t in tiles])
        resource_score = np.minimum(1.0, resources / 500.0)
        suitability = temp_score * 0.4 + humidity_score * 0.3 + resource_score * 0.3
    else:
        suitability = temp_score * 0.5 + humidity_score * 0.5
    
    return np.maximum(suitability, 0.0)


def filter_suitable_tiles(
    species: 'Species',
    tiles: Sequence['MapTile'],
    min_suitability: float = 0.3,
    top_k: int | None = None
) -> list[tuple['MapTile', float]]:
    """筛选适宜的地块并返回排序结果
    
    Args:
        species: 目标物种
        tiles: 候选地块列表
        min_suitability: 最小适宜度阈值
        top_k: 返回前k个结果（None表示全部）
        
    Returns:
        [(tile, suitability), ...] 按适宜度降序排列
    """
    if not tiles:
        return []
    
    tiles = list(tiles)
    suitability = compute_suitability_for_species(species, tiles)
    
    # 过滤低于阈值的
    valid_indices = np.where(suitability >= min_suitability)[0]
    
    if len(valid_indices) == 0:
        # 如果没有合适的，返回最佳的几个
        top_indices = np.argsort(suitability)[-min(5, len(tiles)):][::-1]
        return [(tiles[i], float(suitability[i])) for i in top_indices]
    
    # 按适宜度排序
    sorted_indices = valid_indices[np.argsort(suitability[valid_indices])[::-1]]
    
    if top_k is not None:
        sorted_indices = sorted_indices[:top_k]
    
    return [(tiles[i], float(suitability[i])) for i in sorted_indices]


def compute_batch_suitability_dict(
    species_list: Sequence['Species'],
    tiles: Sequence['MapTile']
) -> dict[tuple[int, int], float]:
    """批量计算物种×地块适宜度并返回字典格式
    
    Args:
        species_list: 物种列表
        tiles: 地块列表
        
    Returns:
        {(species_id, tile_id): suitability} 字典
    """
    if not species_list or not tiles:
        return {}
    
    species_list = list(species_list)
    tiles = list(tiles)
    
    matrix = compute_suitability_matrix(species_list, tiles)
    
    result = {}
    for i, sp in enumerate(species_list):
        if sp.id is None:
            continue
        for j, tile in enumerate(tiles):
            if tile.id is None:
                continue
            result[(sp.id, tile.id)] = float(matrix[i, j])
    
    return result

