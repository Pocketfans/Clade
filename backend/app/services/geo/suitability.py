"""向量化栖息地适宜度计算模块

提供批量计算物种×地块适宜度矩阵的工具函数，
替代多处重复的逐对计算逻辑，显著提升性能。

使用场景：
- MapStateManager.snapshot_habitats
- HabitatManager 地块筛选
- ReproductionService 承载力计算
- SpeciationService 栖息地初始化
- TileBasedMortalityEngine 死亡率计算

【优化v2】
- 统一所有模块的适宜度计算逻辑
- 新增栖息地类型筛选器
- 新增猎物追踪集成
"""
from __future__ import annotations

import math
from typing import Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.environment import MapTile


# ============ 栖息地类型筛选器 (统一版本) ============

def get_habitat_type_mask(
    tiles: Sequence['MapTile'],
    habitat_type: str
) -> np.ndarray:
    """获取适合某种栖息地类型的地块掩码（向量化）
    
    统一各模块的栖息地类型筛选逻辑，避免重复代码。
    
    Args:
        tiles: 地块列表
        habitat_type: 栖息地类型 (marine, deep_sea, terrestrial, coastal, freshwater, aerial, amphibious)
        
    Returns:
        np.ndarray: bool数组，True表示地块适合该栖息地类型
    """
    n_tiles = len(tiles)
    mask = np.zeros(n_tiles, dtype=bool)
    
    habitat_type = habitat_type.lower() if habitat_type else 'terrestrial'
    
    for idx, tile in enumerate(tiles):
        biome = tile.biome.lower() if tile.biome else ""
        is_lake = getattr(tile, 'is_lake', False)
        
        if habitat_type == "marine":
            if "浅海" in biome or "中层" in biome or ("海" in biome and "深海" not in biome):
                mask[idx] = True
        elif habitat_type == "deep_sea":
            if "深海" in biome:
                mask[idx] = True
        elif habitat_type == "coastal":
            if "海岸" in biome or "浅海" in biome:
                mask[idx] = True
        elif habitat_type == "freshwater":
            if is_lake:
                mask[idx] = True
        elif habitat_type == "amphibious":
            if "海岸" in biome or "浅海" in biome or ("平原" in biome and tile.humidity > 0.4):
                mask[idx] = True
        elif habitat_type == "aerial":
            # 空中物种可以在任何非海洋、非高山地块活动
            if "海" not in biome and "高山" not in biome:
                mask[idx] = True
        elif habitat_type in ("terrestrial", ""):
            # 陆生物种：非海洋地块
            if "海" not in biome:
                mask[idx] = True
        else:
            # 未知类型：默认陆地
            if "海" not in biome:
                mask[idx] = True
    
    return mask


def filter_tiles_by_habitat_type(
    tiles: Sequence['MapTile'],
    habitat_type: str
) -> list['MapTile']:
    """根据栖息地类型筛选地块（列表版本）
    
    Args:
        tiles: 候选地块列表
        habitat_type: 栖息地类型
        
    Returns:
        适合该栖息地类型的地块列表
    """
    tiles = list(tiles)
    mask = get_habitat_type_mask(tiles, habitat_type)
    return [t for i, t in enumerate(tiles) if mask[i]]


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
    
    # ============ v2.0 参数配置（极端收紧版）============
    TEMP_COEF = 1.0          # 温度容忍系数（5-10°C范围）
    TEMP_PENALTY = 0.4       # 温度惩罚率
    HUMIDITY_PENALTY = 4.0   # 湿度惩罚率
    RESOURCE_THRESHOLD = 900.0  # 资源门槛
    
    # ============ 向量化计算温度适应度 (v2.0 收紧版) ============
    # 最优温度 = 15 + (heat - cold) * 2
    # 容忍范围 = (cold + heat) * coef，默认5-10°C
    
    optimal_temp = 15.0 + (heat_pref - cold_pref) * 2.0  # (N,)
    tolerance_range = (cold_pref + heat_pref) * TEMP_COEF  # (N,)
    
    min_temp = optimal_temp - tolerance_range / 2  # (N,)
    max_temp = optimal_temp + tolerance_range / 2  # (N,)
    
    # 计算温度分数矩阵 (N, M)
    temp_diff_low = np.maximum(0, min_temp[:, np.newaxis] - temperatures[np.newaxis, :])
    temp_diff_high = np.maximum(0, temperatures[np.newaxis, :] - max_temp[:, np.newaxis])
    temp_diff = np.minimum(temp_diff_low, temp_diff_high)  # 取较小的偏差
    temp_diff = np.where(
        (temperatures[np.newaxis, :] >= min_temp[:, np.newaxis]) & 
        (temperatures[np.newaxis, :] <= max_temp[:, np.newaxis]),
        0.0,
        np.maximum(temp_diff_low, temp_diff_high)
    )
    
    # 每度扣0.4，超过2.5度归零
    temp_score = np.maximum(0.0, 1.0 - temp_diff * TEMP_PENALTY)
    
    # ============ 向量化计算湿度适应度 (v2.0 收紧版) ============
    # 物种偏好湿度 = 1 - drought_pref*0.08
    species_humidity_pref = 1.0 - drought_pref * 0.08  # (N,)
    
    # 湿度匹配度（v2.0：系数从1.0提升到4.0）
    humidity_diff = np.abs(humidities[np.newaxis, :] - species_humidity_pref[:, np.newaxis])
    humidity_score = np.maximum(0.0, 1.0 - humidity_diff * HUMIDITY_PENALTY)  # (N, M)
    
    # ============ 向量化计算资源适应度 (v2.0 收紧版) ============
    # 资源门槛从500提升到900
    resource_score = np.minimum(1.0, resources / RESOURCE_THRESHOLD)  # (M,)
    resource_score = resource_score[np.newaxis, :].repeat(n_species, axis=0)  # (N, M)
    
    # ============ 组合得分 (v2.0 调整权重) ============
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
    """计算单个物种对所有地块的适宜度 (v2.0 收紧版)
    
    【v2.0 改进】
    - 温度范围：5-10°C（极窄）
    - 温度惩罚：0.4/度
    - 湿度惩罚：4.0系数
    - 资源门槛：900
    
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
    
    # v2.0 参数配置
    TEMP_COEF = 1.0
    TEMP_PENALTY = 0.4
    HUMIDITY_PENALTY = 4.0
    RESOURCE_THRESHOLD = 900.0
    
    # 提取物种属性
    heat_pref = species.abstract_traits.get("耐热性", 5)
    cold_pref = species.abstract_traits.get("耐寒性", 5)
    drought_pref = species.abstract_traits.get("耐旱性", 5)
    
    # 提取地块属性
    temperatures = np.array([t.temperature for t in tiles])
    humidities = np.array([t.humidity for t in tiles])
    
    # 温度适应度 (v2.0 收紧版)
    optimal_temp = 15.0 + (heat_pref - cold_pref) * 2.0
    tolerance_range = (cold_pref + heat_pref) * TEMP_COEF
    min_temp = optimal_temp - tolerance_range / 2
    max_temp = optimal_temp + tolerance_range / 2
    
    in_range = (temperatures >= min_temp) & (temperatures <= max_temp)
    temp_diff = np.where(
        temperatures < min_temp,
        min_temp - temperatures,
        np.where(temperatures > max_temp, temperatures - max_temp, 0.0)
    )
    temp_score = np.where(in_range, 1.0, np.maximum(0.0, 1.0 - temp_diff * TEMP_PENALTY))
    
    # 湿度适应度 (v2.0 收紧版)
    humidity_pref = 1.0 - drought_pref * 0.08
    humidity_diff = np.abs(humidities - humidity_pref)
    humidity_score = np.maximum(0.0, 1.0 - humidity_diff * HUMIDITY_PENALTY)
    
    if include_resource:
        resources = np.array([t.resources for t in tiles])
        resource_score = np.minimum(1.0, resources / RESOURCE_THRESHOLD)
        suitability = temp_score * 0.35 + humidity_score * 0.25 + resource_score * 0.40
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


# ============ 消费者感知的适宜度计算 ============

from dataclasses import dataclass


@dataclass
class SuitabilityResult:
    """宜居度计算结果（包含分解数据）"""
    total: float
    temp_score: float
    humidity_score: float
    food_score: float
    biome_score: float
    special_bonus: float
    has_prey: bool | None = None
    prey_abundance: float | None = None


def compute_suitability_with_breakdown(
    species: 'Species',
    tile: 'MapTile',
    prey_tile_population: float | None = None,
    consumer_population: float = 0,
    weights: dict[str, float] | None = None
) -> SuitabilityResult:
    """计算单个物种在单个地块的宜居度（含分解数据）
    
    【关键改进】消费者食物分基于猎物丰富度，而非简单的有/无
    
    Args:
        species: 目标物种
        tile: 目标地块
        prey_tile_population: 该地块上猎物的总种群（仅消费者需要）
        consumer_population: 该地块上消费者的种群（用于计算竞争）
        weights: 权重配置
        
    Returns:
        SuitabilityResult 包含总分和各因子分数
    """
    if weights is None:
        weights = {"temp": 0.20, "humidity": 0.15, "food": 0.30, "biome": 0.25, "special": 0.10}
    
    # 物种属性
    traits = getattr(species, 'abstract_traits', {}) or {}
    trophic_level = getattr(species, 'trophic_level', 1.0) or 1.0
    habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
    is_consumer = trophic_level >= 2.0
    
    heat_tolerance = traits.get("耐热性", 5)
    cold_tolerance = traits.get("耐寒性", 5)
    drought_tolerance = traits.get("耐旱性", 5)
    
    # ===== 温度适应性 =====
    ideal_temp_min = -10 + (15 - cold_tolerance) * 2
    ideal_temp_max = 10 + heat_tolerance * 2
    
    tile_temp = tile.temperature
    if ideal_temp_min <= tile_temp <= ideal_temp_max:
        temp_score = 1.0
    elif tile_temp < ideal_temp_min:
        diff = ideal_temp_min - tile_temp
        temp_score = max(0.2, 1.0 - diff / 30)
    else:
        diff = tile_temp - ideal_temp_max
        temp_score = max(0.2, 1.0 - diff / 30)
    
    # ===== 湿度适应性 =====
    ideal_humidity = 0.7 - drought_tolerance * 0.04
    humidity_diff = abs(tile.humidity - ideal_humidity)
    humidity_score = max(0.3, 1.0 - humidity_diff * 1.5)
    
    # ===== 食物/资源适应性（关键改进） =====
    has_prey = None
    prey_abundance = None
    
    if is_consumer:
        # 【改进】消费者的食物分基于猎物丰富度，而非简单的有/无
        if prey_tile_population is not None and prey_tile_population > 0:
            has_prey = True
            # 猎物丰富度 = 猎物种群 / (消费者种群 + 100)
            # 这样当消费者太多时，猎物就显得不够了
            prey_abundance = prey_tile_population / (consumer_population + 100)
            
            # 基于丰富度计算食物分（使用对数曲线）
            # 丰富度 0.1 → 食物分 0.3
            # 丰富度 1.0 → 食物分 0.7
            # 丰富度 10+ → 食物分 1.0
            if prey_abundance >= 10:
                food_score = 1.0
            elif prey_abundance >= 1:
                food_score = 0.7 + 0.3 * math.log10(prey_abundance)
            elif prey_abundance >= 0.1:
                food_score = 0.3 + 0.4 * (math.log10(prey_abundance) + 1)
            else:
                # 猎物太少，几乎等于没有
                food_score = max(0.15, 0.3 * prey_abundance / 0.1)
        else:
            # 没有猎物
            has_prey = False
            prey_abundance = 0.0
            food_score = 0.15  # 【改进】从0.2降到0.15，无猎物更难生存
    else:
        # 生产者：使用地块资源
        if tile.resources > 0:
            food_score = min(1.0, 0.3 + 0.7 * math.log(tile.resources + 1) / math.log(1001))
        else:
            food_score = 0.3
    
    # ===== 生物群系匹配 =====
    biome_lower = (tile.biome or "").lower()
    biome_score = 0.6  # 基础分
    
    if habitat_type == "marine" and "海" in biome_lower and "深海" not in biome_lower:
        biome_score = 1.0
    elif habitat_type == "deep_sea" and "深海" in biome_lower:
        biome_score = 1.0
    elif habitat_type == "terrestrial" and "海" not in biome_lower:
        biome_score = 0.9
    elif habitat_type == "coastal" and ("海岸" in biome_lower or "浅海" in biome_lower):
        biome_score = 1.0
    elif habitat_type == "freshwater" and getattr(tile, 'is_lake', False):
        biome_score = 1.0
    
    # ===== 特殊栖息地加成 =====
    special_bonus = 0.0
    if habitat_type == "hydrothermal":
        volcanic = getattr(tile, 'volcanic_potential', 0.0)
        if volcanic > 0.3:
            special_bonus = 0.3
    elif habitat_type == "deep_sea":
        if tile.elevation < -2000:
            special_bonus = 0.2
    
    # ===== 综合评分 =====
    total = (
        temp_score * weights["temp"] +
        humidity_score * weights["humidity"] +
        food_score * weights["food"] +
        biome_score * weights["biome"] +
        special_bonus * weights["special"]
    )
    
    # 保证最低适宜度
    total = max(0.15, min(1.0, total))
    
    return SuitabilityResult(
        total=total,
        temp_score=temp_score,
        humidity_score=humidity_score,
        food_score=food_score,
        biome_score=biome_score,
        special_bonus=special_bonus,
        has_prey=has_prey,
        prey_abundance=prey_abundance,
    )


def compute_consumer_aware_suitability(
    species: 'Species',
    tiles: Sequence['MapTile'],
    prey_tile_ids: set[int] | None = None,
    prey_tile_populations: dict[int, float] | None = None,
    consumer_tile_populations: dict[int, float] | None = None,
    weights: dict[str, float] | None = None
) -> np.ndarray:
    """计算消费者的适宜度（考虑猎物分布和丰富度）
    
    【改进】对于消费者，食物分不再是简单的有/无，而是基于猎物丰富度
    
    Args:
        species: 目标物种
        tiles: 地块列表
        prey_tile_ids: 猎物所在的地块ID集合（兼容旧版）
        prey_tile_populations: {tile_id: prey_population} 猎物种群分布（新版）
        consumer_tile_populations: {tile_id: consumer_population} 消费者种群分布
        weights: 权重配置
        
    Returns:
        np.ndarray: shape (M,) 的适宜度数组
    """
    if not tiles:
        return np.array([])
    
    tiles = list(tiles)
    n_tiles = len(tiles)
    
    if weights is None:
        weights = {"temp": 0.20, "humidity": 0.15, "food": 0.30, "biome": 0.25, "special": 0.10}
    
    # 物种属性
    traits = getattr(species, 'abstract_traits', {}) or {}
    trophic_level = getattr(species, 'trophic_level', 1.0) or 1.0
    habitat_type = (getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
    is_consumer = trophic_level >= 2.0
    
    heat_tolerance = traits.get("耐热性", 5)
    cold_tolerance = traits.get("耐寒性", 5)
    drought_tolerance = traits.get("耐旱性", 5)
    
    # 提取地块属性
    temperatures = np.array([t.temperature for t in tiles])
    humidities = np.array([t.humidity for t in tiles])
    resources = np.array([t.resources for t in tiles])
    tile_ids = [t.id for t in tiles]
    
    # ===== 温度适应性 =====
    ideal_temp_min = -10 + (15 - cold_tolerance) * 2
    ideal_temp_max = 10 + heat_tolerance * 2
    
    temp_score = np.ones(n_tiles)
    too_cold = temperatures < ideal_temp_min
    too_hot = temperatures > ideal_temp_max
    
    temp_score[too_cold] = np.maximum(0.2, 1.0 - (ideal_temp_min - temperatures[too_cold]) / 30)
    temp_score[too_hot] = np.maximum(0.2, 1.0 - (temperatures[too_hot] - ideal_temp_max) / 30)
    
    # ===== 湿度适应性 =====
    ideal_humidity = 0.7 - drought_tolerance * 0.04
    humidity_diff = np.abs(humidities - ideal_humidity)
    humidity_score = np.maximum(0.3, 1.0 - humidity_diff * 1.5)
    
    # ===== 食物/资源适应性 =====
    if is_consumer:
        food_score = np.full(n_tiles, 0.15)  # 【改进】默认无猎物分从0.2降到0.15
        
        if prey_tile_populations is not None:
            # 【新版】基于猎物丰富度计算
            consumer_pops = consumer_tile_populations or {}
            for i, tid in enumerate(tile_ids):
                prey_pop = prey_tile_populations.get(tid, 0)
                if prey_pop > 0:
                    consumer_pop = consumer_pops.get(tid, 0)
                    prey_abundance = prey_pop / (consumer_pop + 100)
                    
                    if prey_abundance >= 10:
                        food_score[i] = 1.0
                    elif prey_abundance >= 1:
                        food_score[i] = 0.7 + 0.3 * np.log10(prey_abundance)
                    elif prey_abundance >= 0.1:
                        food_score[i] = 0.3 + 0.4 * (np.log10(prey_abundance) + 1)
                    else:
                        food_score[i] = max(0.15, 0.3 * prey_abundance / 0.1)
        elif prey_tile_ids is not None:
            # 【兼容旧版】简单的有/无判断，但降低有猎物时的分数
            for i, tid in enumerate(tile_ids):
                if tid in prey_tile_ids:
                    food_score[i] = 0.7  # 【改进】从1.0降到0.7
    else:
        # 生产者：使用地块资源
        food_score = np.where(
            resources > 0,
            np.minimum(1.0, 0.3 + 0.7 * np.log(resources + 1) / np.log(1001)),
            0.3
        )
    
    # ===== 生物群系匹配 =====
    biome_score = np.full(n_tiles, 0.6)  # 基础分
    habitat_mask = get_habitat_type_mask(tiles, habitat_type)
    biome_score[habitat_mask] = 1.0
    
    # ===== 特殊栖息地加成 =====
    special_bonus = np.zeros(n_tiles)
    if habitat_type == "hydrothermal":
        for i, tile in enumerate(tiles):
            volcanic = getattr(tile, 'volcanic_potential', 0.0)
            if volcanic > 0.3:
                special_bonus[i] = 0.3
    elif habitat_type == "deep_sea":
        for i, tile in enumerate(tiles):
            if tile.elevation < -2000:
                special_bonus[i] = 0.2
    
    # ===== 综合评分 =====
    suitability = (
        temp_score * weights["temp"] +
        humidity_score * weights["humidity"] +
        food_score * weights["food"] +
        biome_score * weights["biome"] +
        special_bonus * weights["special"]
    )
    
    # 保证最低适宜度
    return np.maximum(0.15, np.minimum(1.0, suitability))


def separate_producers_consumers(
    species_list: Sequence['Species']
) -> tuple[list['Species'], list['Species']]:
    """将物种列表分为生产者和消费者
    
    用于分两阶段处理栖息地分布：先生产者，再消费者。
    
    Args:
        species_list: 物种列表
        
    Returns:
        (producers, consumers) 两个列表
    """
    producers = []
    consumers = []
    
    for sp in species_list:
        if getattr(sp, 'status', 'alive') != 'alive':
            continue
        trophic = getattr(sp, 'trophic_level', 1.0) or 1.0
        if trophic < 2.0:
            producers.append(sp)
        else:
            consumers.append(sp)
    
    return producers, consumers

