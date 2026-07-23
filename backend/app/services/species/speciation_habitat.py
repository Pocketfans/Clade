from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ...models.species import Species

logger = logging.getLogger(f"{__package__}.speciation")

SuitabilityCalculator = Callable[[Species, Any], float]
InitialHabitatCalculator = Callable[
    [Species, Species, int, set[int] | None],
    None,
]
ConnectedClusterFinder = Callable[[set[int]], list[set[int]]]
IsolationDetector = Callable[[str], dict]


def find_connected_clusters(
    tile_ids: set[int],
    tile_adjacency: dict[int, set[int]],
) -> list[set[int]]:
    """使用并查集找出连通的地块群

    Args:
        tile_ids: 物种占据的地块ID集合
        tile_adjacency: 地块邻接表

    Returns:
        连通地块群列表
    """
    if not tile_ids:
        return []

    if not tile_adjacency:
        # 没有邻接信息，假设所有地块连通
        return [tile_ids]

    # 并查集
    parent = {t: t for t in tile_ids}

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # 合并相邻地块
    for tile_id in tile_ids:
        neighbors = tile_adjacency.get(tile_id, set())
        for neighbor in neighbors:
            if neighbor in tile_ids:
                union(tile_id, neighbor)

    # 收集各连通分量
    clusters_map: dict[int, set[int]] = {}
    for tile_id in tile_ids:
        root = find(tile_id)
        if root not in clusters_map:
            clusters_map[root] = set()
        clusters_map[root].add(tile_id)

    return list(clusters_map.values())


def allocate_tiles_from_clusters(
    clusters: list[set[int]],
    candidate_tiles: set[int],
    num_offspring: int,
) -> list[set[int]]:
    """基于预计算的隔离区域为子代分配地块

    【核心功能】直接使用候选数据中的 clusters，无需重新计算

    Args:
        clusters: 预计算的隔离区域列表
        candidate_tiles: 候选地块集合
        num_offspring: 子代数量

    Returns:
        每个子代的地块ID集合列表
    """
    import random

    if not clusters:
        # 没有隔离区域，将所有候选地块平均分配
        if not candidate_tiles:
            return [set() for _ in range(num_offspring)]

        tile_list = list(candidate_tiles)
        random.shuffle(tile_list)
        allocations = [set() for _ in range(num_offspring)]
        for i, tile in enumerate(tile_list):
            allocations[i % num_offspring].add(tile)
        return allocations

    # 只保留候选地块中的区域
    filtered_clusters = []
    for cluster in clusters:
        filtered = cluster & candidate_tiles
        if filtered:
            filtered_clusters.append(filtered)

    if not filtered_clusters:
        # 过滤后没有区域，回退到候选地块平均分配
        tile_list = list(candidate_tiles)
        random.shuffle(tile_list)
        allocations = [set() for _ in range(num_offspring)]
        for i, tile in enumerate(tile_list):
            allocations[i % num_offspring].add(tile)
        return allocations

    # 按区域大小排序（大的优先）
    filtered_clusters.sort(key=len, reverse=True)

    # 策略1：如果隔离区域数 >= 子代数，每个子代获得一个区域
    if len(filtered_clusters) >= num_offspring:
        random.shuffle(filtered_clusters)
        return [filtered_clusters[i] for i in range(num_offspring)]

    # 策略2：隔离区域不足，需要分割大区域
    allocations = [set() for _ in range(num_offspring)]

    # 先分配已有的区域
    for i, cluster in enumerate(filtered_clusters):
        if i < num_offspring:
            allocations[i] = cluster

    # 从最大区域分割出额外的
    remaining_slots = [i for i in range(num_offspring) if not allocations[i]]
    if remaining_slots and allocations[0]:
        largest = list(allocations[0])
        random.shuffle(largest)

        split_size = max(1, len(largest) // (len(remaining_slots) + 1))

        for slot_idx in remaining_slots:
            take = set(largest[:split_size])
            largest = largest[split_size:]
            allocations[slot_idx] = take

        # 更新最大区域
        allocations[0] = set(largest)

    return allocations


def detect_geographic_isolation(
    lineage_code: str,
    tile_mortality_cache: dict[str, dict[int, float]],
    connected_cluster_finder: ConnectedClusterFinder,
) -> dict:
    """检测物种是否存在地理隔离

    【核心功能】基于地块死亡率差异判断是否存在地理隔离

    地理隔离判定条件：
    1. 物种分布在多个不连通的地块群（物理隔离）
    2. 或者不同地块的死亡率差异显著（生态隔离）

    Returns:
        {
            "is_isolated": bool,  # 是否存在隔离
            "num_clusters": int,  # 隔离区域数量
            "mortality_gradient": float,  # 死亡率梯度
            "clusters": list[set[int]],  # 各区域的地块ID集合
            "best_cluster": set[int],  # 最适宜分化的区域
        }
    """
    tile_rates = tile_mortality_cache.get(lineage_code, {})

    if len(tile_rates) < 2:
        return {
            "is_isolated": False,
            "num_clusters": 1,
            "mortality_gradient": 0.0,
            "clusters": [set(tile_rates.keys())],
            "best_cluster": set(tile_rates.keys()),
        }

    # 1. 计算死亡率梯度
    rates = list(tile_rates.values())
    mortality_gradient = max(rates) - min(rates)

    # 2. 基于连通性检测物理隔离
    clusters = connected_cluster_finder(set(tile_rates.keys()))

    # 3. 基于死亡率差异检测生态隔离
    # 如果连通但死亡率差异大，也算隔离
    ecological_isolation = mortality_gradient > 0.25
    physical_isolation = len(clusters) >= 2

    is_isolated = physical_isolation or ecological_isolation

    # 4. 确定最佳分化区域（死亡率最低的地块群）
    if clusters:
        # 计算每个群的平均死亡率
        cluster_avg_rates = []
        for cluster in clusters:
            avg_rate = sum(tile_rates.get(t, 0.5) for t in cluster) / len(cluster)
            cluster_avg_rates.append((cluster, avg_rate))

        # 选择死亡率最低的群作为分化起源地
        cluster_avg_rates.sort(key=lambda x: x[1])
        best_cluster = cluster_avg_rates[0][0]
    else:
        best_cluster = set(tile_rates.keys())

    return {
        "is_isolated": is_isolated,
        "num_clusters": len(clusters),
        "mortality_gradient": mortality_gradient,
        "clusters": clusters,
        "best_cluster": best_cluster,
    }


def allocate_tiles_to_offspring(
    parent_lineage_code: str,
    num_offspring: int,
    isolation_detector: IsolationDetector,
) -> list[set[int]]:
    """为子代分配地块（旧方法，用于回退）

    【核心功能】实现基于地块的分化：
    - 每个子代只获得部分地块
    - 优先按地理隔离区域分配
    - 如果没有隔离，则随机划分

    Args:
        parent_lineage_code: 父代谱系编码
        num_offspring: 子代数量

    Returns:
        每个子代的地块ID集合列表
    """
    import random

    geo_data = isolation_detector(parent_lineage_code)
    clusters = geo_data["clusters"]

    if not clusters:
        return [set() for _ in range(num_offspring)]

    # 所有地块
    all_tiles = set()
    for cluster in clusters:
        all_tiles.update(cluster)

    if len(all_tiles) < num_offspring:
        # 地块太少，每个子代至少分一个
        tile_list = list(all_tiles)
        random.shuffle(tile_list)
        allocations = [set() for _ in range(num_offspring)]
        for i, tile in enumerate(tile_list):
            allocations[i % num_offspring].add(tile)
        return allocations

    # 策略1：如果存在物理隔离，按隔离区域分配
    if len(clusters) >= num_offspring:
        # 每个子代获得一个独立区域
        random.shuffle(clusters)
        allocations = [clusters[i] for i in range(num_offspring)]
        return allocations

    # 策略2：如果隔离区域不足，在大区域内随机划分
    if len(clusters) < num_offspring:
        allocations = [set() for _ in range(num_offspring)]

        # 先分配已有的隔离区域
        for i, cluster in enumerate(clusters):
            if i < num_offspring:
                allocations[i] = cluster

        # 从最大区域中分割出额外的区域
        largest_idx = max(
            range(len(allocations)),
            key=lambda i: len(allocations[i]),
        )
        largest_cluster = list(allocations[largest_idx])

        # 需要分割出的区域数量
        need_more = num_offspring - len(clusters)
        if need_more > 0 and len(largest_cluster) > 1:
            random.shuffle(largest_cluster)
            split_size = max(1, len(largest_cluster) // (need_more + 1))

            # 从最大区域中分割
            remaining = set(largest_cluster)
            for i in range(num_offspring):
                if not allocations[i]:  # 空的slot
                    take = set(list(remaining)[:split_size])
                    allocations[i] = take
                    remaining -= take
                    if not remaining:
                        break

            # 更新最大区域
            allocations[largest_idx] = remaining

        return allocations

    return [all_tiles.copy() for _ in range(num_offspring)]


def inherit_habitat_distribution(
    parent: Species,
    child: Species,
    turn_index: int,
    assigned_tiles: set[int] | None = None,
    reproduction_bonus: float = 0.0,
    initial_habitat_calculator: InitialHabitatCalculator | None = None,
) -> None:
    """子代继承父代的栖息地分布

    【v3.1核心改进】基于地块的真实种群分配：
    - 如果指定了 assigned_tiles，子代直接获得这些地块上父代的种群（地理隔离分化）
    - 父代在这些地块上的种群会被减少
    - 这模拟了"因地理隔离，某个区域的种群独立演化成新物种"
    - 【v3.1新增】繁殖补偿：给新物种补偿当前回合的繁殖增长

    Args:
        parent: 父代物种
        child: 子代物种
        turn_index: 当前回合
        assigned_tiles: 分配给该子代的地块集合（可选）
        reproduction_bonus: 繁殖补偿因子（0.0-1.0），用于补偿新物种在当前回合未能繁殖的损失
        initial_habitat_calculator: 现有服务的初始栖息地计算入口
    """
    from ...models.environment import HabitatPopulation
    from ...repositories.environment_repository import environment_repository

    if initial_habitat_calculator is None:
        initial_habitat_calculator = calculate_initial_habitat_for_child

    # 获取父代的栖息地分布
    all_habitats = environment_repository.latest_habitats()
    parent_habitats = [h for h in all_habitats if h.species_id == parent.id]

    if not parent_habitats:
        logger.warning(
            f"[栖息地继承] 父代 {parent.common_name} 没有栖息地数据，立即为子代计算初始栖息地"
        )
        # 【风险修复】立即计算子代的初始栖息地，而不是等待下次快照
        initial_habitat_calculator(child, parent, turn_index, assigned_tiles)
        return

    if child.id is None:
        logger.error(
            f"[栖息地继承] 严重错误：子代 {child.common_name} 没有 ID，无法继承栖息地"
        )
        return

    # 【v3.1核心改进】根据 assigned_tiles 过滤并分配地块种群
    child_habitats = []
    parent_updated_habitats = []
    inherited_count = 0
    total_inherited_pop = 0
    total_parent_reduced = 0

    for parent_hab in parent_habitats:
        # 如果指定了分配地块，只继承在分配范围内的地块
        if assigned_tiles and parent_hab.tile_id not in assigned_tiles:
            continue

        # 【v3.1改进】子代直接获得该地块上的种群（地理隔离分化）
        # 地理隔离意味着这个区域的种群"属于"新物种了
        tile_pop = parent_hab.population if parent_hab.population else 0

        if assigned_tiles:
            # 地理隔离分化：子代获得该地块的全部种群，父代退出
            base_child_pop = tile_pop
            parent_remaining_pop = 0
        else:
            # 非地理隔离（回退到旧行为）：种群平分
            base_child_pop = int(tile_pop * 0.5)
            parent_remaining_pop = tile_pop - base_child_pop

        # 【v3.1新增】应用繁殖补偿
        # 新物种分化时父代已经繁殖过了，给新物种补偿这个增长
        if reproduction_bonus > 0 and base_child_pop > 0:
            # 补偿因子应用：new_pop = base_pop * (1 + bonus * suitability)
            # 考虑适宜度：适宜度高的地块繁殖补偿更多
            suitability_factor = (
                parent_hab.suitability if parent_hab.suitability else 0.5
            )
            effective_bonus = reproduction_bonus * suitability_factor
            child_pop = int(base_child_pop * (1 + effective_bonus))
        else:
            child_pop = base_child_pop

        child_habitats.append(
            HabitatPopulation(
                tile_id=parent_hab.tile_id,
                species_id=child.id,
                population=child_pop,  # 【v3.1】直接获得该地块种群 + 繁殖补偿
                suitability=parent_hab.suitability,  # 继承父代的适宜度
                turn_index=turn_index,
            )
        )

        # 【v3.1】同步减少父代在该地块的种群
        if assigned_tiles and tile_pop > 0:
            parent_updated_habitats.append(
                HabitatPopulation(
                    tile_id=parent_hab.tile_id,
                    species_id=parent.id,
                    population=parent_remaining_pop,
                    suitability=parent_hab.suitability,
                    turn_index=turn_index,
                )
            )
            total_parent_reduced += tile_pop

        inherited_count += 1
        total_inherited_pop += child_pop

    # 如果分配了地块但一个都没继承到（可能父代不在这些地块），使用分配的地块
    if assigned_tiles and not child_habitats:
        logger.warning(
            f"[栖息地继承] {child.common_name} 分配的地块与父代不重叠，"
            f"将使用分配的地块: {assigned_tiles}"
        )
        # 从 child.morphology_stats 获取分配的种群，按地块均分
        child_total_pop = int(child.morphology_stats.get("population", 0) or 0)
        pop_per_tile = (
            max(1, child_total_pop // len(assigned_tiles))
            if assigned_tiles
            else 0
        )

        for tile_id in assigned_tiles:
            child_habitats.append(
                HabitatPopulation(
                    tile_id=tile_id,
                    species_id=child.id,
                    population=pop_per_tile,  # 【v3.1】均分分配的种群
                    suitability=0.5,  # 默认适宜度
                    turn_index=turn_index,
                )
            )

    if child_habitats:
        environment_repository.write_habitats(child_habitats)
        if assigned_tiles:
            logger.info(
                f"[基于地块分化] {child.common_name} 继承了 {len(child_habitats)}/{len(parent_habitats)} 个地块 "
                f"(种群:{total_inherited_pop:,}, 地理隔离分化)"
            )
        else:
            logger.info(
                f"[栖息地继承] {child.common_name} 继承了 {len(child_habitats)} 个栖息地"
            )

    # 【v3.1】更新父代在分配地块上的种群（清零）
    if parent_updated_habitats:
        environment_repository.write_habitats(parent_updated_habitats)
        logger.debug(
            f"[地块分化] 父代 {parent.common_name} 在 {len(parent_updated_habitats)} 个地块上"
            f"减少种群 {total_parent_reduced:,}（已转移给子代）"
        )


def calculate_initial_habitat_for_child(
    child: Species,
    parent: Species,
    turn_index: int,
    assigned_tiles: set[int] | None = None,
    suitability_calculator: SuitabilityCalculator | None = None,
) -> None:
    """为没有栖息地的子代计算初始栖息地分布

    【核心改进】现在支持基于地块的分化：
    - 如果指定了 assigned_tiles，只在这些地块中选择
    - 如果未指定，则在所有合适地块中选择

    Args:
        child: 子代物种
        parent: 父代物种（用于参考）
        turn_index: 当前回合
        assigned_tiles: 分配给该子代的地块集合（可选）
        suitability_calculator: 现有服务的适宜度计算入口
    """
    from ...models.environment import HabitatPopulation
    from ...repositories.environment_repository import environment_repository

    if suitability_calculator is None:
        suitability_calculator = calculate_suitability_for_species

    logger.info(f"[栖息地计算] 为 {child.common_name} 计算初始栖息地")

    # 1. 获取所有地块
    all_tiles = environment_repository.list_tiles()
    if not all_tiles:
        logger.error(
            f"[栖息地计算] 没有可用地块，无法为 {child.common_name} 计算栖息地"
        )
        return

    # 【核心改进】如果指定了分配地块，只在这些地块中计算
    if assigned_tiles:
        all_tiles = [t for t in all_tiles if t.id in assigned_tiles]
        if not all_tiles:
            logger.warning(
                f"[栖息地计算] {child.common_name} 分配的地块在数据库中不存在，"
                f"使用全部地块"
            )
            all_tiles = environment_repository.list_tiles()

    # 2. 根据栖息地类型筛选地块
    habitat_type = getattr(child, "habitat_type", "terrestrial")
    suitable_tiles = []

    for tile in all_tiles:
        biome = tile.biome.lower()
        is_suitable = False

        if habitat_type == "marine" and ("浅海" in biome or "中层" in biome):
            is_suitable = True
        elif habitat_type == "deep_sea" and "深海" in biome:
            is_suitable = True
        elif habitat_type == "coastal" and ("海岸" in biome or "浅海" in biome):
            is_suitable = True
        elif habitat_type == "freshwater" and getattr(tile, "is_lake", False):
            is_suitable = True
        elif habitat_type == "terrestrial" and "海" not in biome:
            is_suitable = True
        elif habitat_type == "amphibious" and (
            "海岸" in biome or ("平原" in biome and tile.humidity > 0.4)
        ):
            is_suitable = True
        elif habitat_type == "aerial" and "海" not in biome and "山" not in biome:
            is_suitable = True

        if is_suitable:
            suitable_tiles.append(tile)

    if not suitable_tiles:
        logger.warning(
            f"[栖息地计算] {child.common_name} ({habitat_type}) 没有合适的地块"
        )
        # 回退：使用分配的地块或前10个地块
        suitable_tiles = all_tiles[:10] if all_tiles else []

    # 3. 计算适宜度
    tile_suitability = []
    for tile in suitable_tiles:
        suitability = suitability_calculator(child, tile)
        if suitability > 0.1:  # 只保留适宜度>0.1的地块
            tile_suitability.append((tile, suitability))

    if not tile_suitability:
        logger.warning(
            f"[栖息地计算] {child.common_name} 没有适宜度>0.1的地块，使用前10个"
        )
        tile_suitability = [(tile, 0.5) for tile in suitable_tiles[:10]]

    # 4. 选择top 10地块（如果有分配限制，可能更少）
    tile_suitability.sort(key=lambda x: x[1], reverse=True)
    max_tiles = min(10, len(tile_suitability))
    top_tiles = tile_suitability[:max_tiles]

    # 5. 归一化适宜度（总和=1.0）
    total_suitability = sum(s for _, s in top_tiles)
    if total_suitability == 0:
        total_suitability = 1.0

    # 6. 创建栖息地记录
    child_habitats = []
    for tile, raw_suitability in top_tiles:
        normalized_suitability = raw_suitability / total_suitability
        child_habitats.append(
            HabitatPopulation(
                tile_id=tile.id,
                species_id=child.id,
                population=0,
                suitability=normalized_suitability,
                turn_index=turn_index,
            )
        )

    if child_habitats:
        environment_repository.write_habitats(child_habitats)
        if assigned_tiles:
            logger.info(
                f"[基于地块分化] {child.common_name} 在分配区域内计算得到 "
                f"{len(child_habitats)} 个栖息地"
            )
        else:
            logger.info(
                f"[栖息地计算] {child.common_name} 计算得到 "
                f"{len(child_habitats)} 个栖息地"
            )


def calculate_suitability_for_species(species: Species, tile: Any) -> float:
    """计算物种对地块的适宜度 (v2.0 收紧版)

    【v2.0 改进】
    - 温度范围：5-10°C（极窄）
    - 温度惩罚：0.4/度
    - 湿度惩罚：4.0系数
    - 资源门槛：900
    """
    # 温度适应性 (v2.0 收紧)
    heat_res = species.abstract_traits.get("耐热性", 5)
    cold_res = species.abstract_traits.get("耐寒性", 5)

    # 最优温度和容忍范围
    optimal_temp = 15.0 + (heat_res - cold_res) * 2.0
    tolerance_range = (cold_res + heat_res) * 1.0  # coef=1.0，5-10°C范围

    min_temp = optimal_temp - tolerance_range / 2
    max_temp = optimal_temp + tolerance_range / 2

    if min_temp <= tile.temperature <= max_temp:
        temp_score = 1.0
    else:
        diff = min(
            abs(tile.temperature - min_temp),
            abs(tile.temperature - max_temp),
        )
        # 每度扣0.4，超过2.5度归零
        temp_score = max(0.0, 1.0 - diff * 0.4)

    if temp_score == 0.0:
        return 0.0

    # 湿度适应性 (v2.0 收紧)
    drought_pref = species.abstract_traits.get("耐旱性", 5)
    best_humidity = 1.0 - (drought_pref * 0.08)
    hum_diff = abs(tile.humidity - best_humidity)
    humidity_score = max(0.0, 1.0 - hum_diff * 4.0)  # 系数从1.0增加到4.0

    # 资源可用性 (v2.0 收紧)
    resource_score = min(1.0, tile.resources / 900.0)  # 门槛从500增加到900

    # 综合评分
    return max(
        0.0,
        temp_score * 0.35 + humidity_score * 0.25 + resource_score * 0.40,
    )
