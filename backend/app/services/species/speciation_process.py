from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from typing import Any, Callable


logger = logging.getLogger(f"{__package__}.speciation")


@dataclass(frozen=True)
class _CandidateWork:
    candidate_data: dict | None
    candidate_tiles: set
    tile_populations: dict
    tile_mortality: dict
    global_population: int
    candidate_population: int
    death_rate: float
    is_isolated: bool
    mortality_gradient: float
    clusters: list
    survivors: int = 0
    resource_pressure: float = 0.0
    niche_overlap: float = 0.0
    niche_saturation: float = 0.0
    base_threshold: int = 0
    min_population: int = 0
    evo_potential: float = 0.0
    speciation_pressure: float = 0.0
    generations: float = 0.0
    speciation_type: str = ""
    speciation_chance: float = 0.0


@dataclass(frozen=True)
class _OffspringPlan:
    cluster_pressure_data: list[dict]
    num_offspring: int
    pop_splits: list[int]
    new_codes: list[str]
    offspring_tiles: list


def normalize_candidate_state(
    *,
    species: Any,
    lineage_code: str,
    global_population: int,
    result_death_rate: float,
    turn_index: int,
    spec_config: Any,
    speciation_candidates: dict,
    tile_population_cache: dict,
    tile_mortality_cache: dict,
    calculate_speciation_threshold: Callable[[Any, int], int],
) -> _CandidateWork:
    """Normalize pre-screened or legacy tile candidate state."""
    candidate_data = speciation_candidates.get(lineage_code)

    if candidate_data:
        candidate_tiles = candidate_data["candidate_tiles"]
        tile_populations = candidate_data["tile_populations"]
        tile_mortality = candidate_data["tile_mortality"]
        is_isolated = candidate_data["is_isolated"]
        mortality_gradient = candidate_data["mortality_gradient"]
        clusters = candidate_data["clusters"]

        candidate_population = int(
            candidate_data["total_candidate_population"]
        )
        tile_total_population = int(sum(tile_populations.values()))
        if (
            tile_total_population > 0
            and abs(tile_total_population - global_population) > 0
        ):
            logger.warning(
                f"[种群同步] {species.common_name}: "
                f"地块总人口({tile_total_population:,}) "
                f"≠ 全局人口({global_population:,})，以地块总和为准"
            )
            global_population = tile_total_population
            species.morphology_stats["population"] = tile_total_population
        if candidate_population > global_population:
            candidate_population = global_population

        total_pop = sum(
            tile_populations.get(t, 0) for t in candidate_tiles
        )
        if total_pop > 0:
            death_rate = sum(
                tile_mortality.get(t, 0)
                * tile_populations.get(t, 0)
                for t in candidate_tiles
            ) / total_pop
        else:
            death_rate = result_death_rate

        base_threshold_for_cluster = calculate_speciation_threshold(
            species,
            turn_index,
        )
        min_cluster_pop = int(base_threshold_for_cluster * 0.6)

        valid_clusters = []
        for cluster in clusters:
            cluster_pop = sum(
                tile_populations.get(t, 0) for t in cluster
            )
            if cluster_pop >= min_cluster_pop:
                valid_clusters.append(cluster)

        if not valid_clusters and clusters:
            is_isolated = False
            logger.debug(
                f"[簇人口不足] {species.common_name}: "
                f"所有{len(clusters)}个簇人口 < "
                f"门槛60%({min_cluster_pop:,})"
            )
        elif valid_clusters:
            clusters = valid_clusters

        logger.debug(
            f"[地块分化检查] {species.common_name}: "
            f"候选地块={len(candidate_tiles)}, "
            f"候选种群={candidate_population:,}, "
            f"加权死亡率={death_rate:.1%}, 隔离={is_isolated}, "
            f"有效簇={len(valid_clusters) if valid_clusters else 0}/"
            f"{len(clusters) if clusters else 0}"
        )
    else:
        candidate_tiles = set()
        tile_populations = tile_population_cache.get(lineage_code, {})
        tile_mortality = tile_mortality_cache.get(lineage_code, {})
        candidate_population = int(
            species.morphology_stats.get("population", 0) or 0
        )
        tile_total_population = (
            int(sum(tile_populations.values()))
            if tile_populations
            else candidate_population
        )
        if (
            tile_total_population > 0
            and abs(tile_total_population - candidate_population) > 0
        ):
            logger.warning(
                f"[种群同步] {species.common_name}: "
                f"地块总人口({tile_total_population:,}) "
                f"≠ 全局人口({candidate_population:,})，"
                f"以地块总和为准"
            )
            candidate_population = tile_total_population
            species.morphology_stats["population"] = tile_total_population
            global_population = tile_total_population
        death_rate = result_death_rate
        is_isolated = False
        mortality_gradient = 0.0
        clusters = []

        if tile_populations and tile_mortality:
            for tile_id, pop in tile_populations.items():
                rate = tile_mortality.get(tile_id, 0.5)
                if (
                    pop >= spec_config.candidate_tile_min_pop
                    and spec_config.candidate_tile_death_rate_min
                    <= rate
                    <= spec_config.candidate_tile_death_rate_max
                ):
                    candidate_tiles.add(tile_id)
            if candidate_tiles:
                candidate_population = int(
                    sum(
                        tile_populations.get(t, 0)
                        for t in candidate_tiles
                    )
                )

    return _CandidateWork(
        candidate_data=candidate_data,
        candidate_tiles=candidate_tiles,
        tile_populations=tile_populations,
        tile_mortality=tile_mortality,
        global_population=global_population,
        candidate_population=candidate_population,
        death_rate=death_rate,
        is_isolated=is_isolated,
        mortality_gradient=mortality_gradient,
        clusters=clusters,
    )


def evaluate_candidate_eligibility(
    work: _CandidateWork,
    *,
    species: Any,
    result: Any,
    turn_index: int,
    average_pressure: float,
    spec_config: Any,
    calculate_speciation_threshold: Callable[[Any, int], int],
) -> _CandidateWork | None:
    """Apply population, cooldown and evolution-potential gates."""
    candidate_population = work.candidate_population
    survivors = candidate_population
    resource_pressure = result.resource_pressure
    niche_overlap = result.niche_overlap
    niche_saturation = getattr(result, "niche_saturation", 0.0)
    base_threshold = calculate_speciation_threshold(species, turn_index)

    threshold_multiplier = 1.0
    if work.is_isolated:
        threshold_multiplier *= 0.7
    else:
        threshold_multiplier *= 1.1

    if candidate_population > base_threshold * 3:
        threshold_multiplier *= 0.8
    elif candidate_population > base_threshold * 2:
        threshold_multiplier *= 0.9

    if niche_overlap > 0.7:
        threshold_multiplier *= 1.1
    if niche_saturation > 0.85 and not work.is_isolated:
        threshold_multiplier *= 1.1

    min_population = int(base_threshold * threshold_multiplier)
    if candidate_population < min_population:
        logger.debug(
            f"[分化跳过-种群不足] {species.common_name}: "
            f"种群{candidate_population:,} < 门槛{min_population:,}"
        )
        return None

    evo_potential = species.hidden_traits.get(
        "evolution_potential",
        0.5,
    )
    speciation_pressure = (
        species.morphology_stats.get("speciation_pressure", 0.0) or 0.0
    )
    cooldown = spec_config.cooldown_turns
    last_speciation_turn = species.morphology_stats.get(
        "last_speciation_turn",
        -999,
    )
    turns_since_speciation = turn_index - last_speciation_turn

    if (
        turn_index >= spec_config.early_skip_cooldown_turns
        and turns_since_speciation < cooldown
    ):
        logger.debug(
            f"[分化冷却] {species.common_name} 仍在冷却期 "
            f"({turns_since_speciation}/{cooldown}回合)"
        )
        return None
    if (
        turn_index < spec_config.early_skip_cooldown_turns
        and turns_since_speciation < cooldown
    ):
        logger.debug(
            f"[早期分化] turn={turn_index} < "
            f"{spec_config.early_skip_cooldown_turns}"
            "，跳过冷却期检查"
        )

    if evo_potential < 0.15 and speciation_pressure < 0.10:
        logger.debug(
            f"[分化跳过-潜力不足] {species.common_name}: "
            f"演化潜力{evo_potential:.2f} < 0.15, "
            f"累积压力{speciation_pressure:.2f} < 0.10"
        )
        return None

    logger.info(
        f"[分化候选] {species.common_name}: "
        f"turn={turn_index}, 种群={candidate_population:,}, "
        f"门槛={min_population:,} "
        f"(base={base_threshold:,}, "
        f"multiplier={threshold_multiplier:.2f}), "
        f"演化潜力={evo_potential:.2f}, "
        f"累积压力={speciation_pressure:.2f}, "
        f"avg_pressure={average_pressure:.2f}, "
        f"resource_pressure={resource_pressure:.2f}, "
        f"is_isolated={work.is_isolated}, "
        f"early_game={turn_index < 10}"
    )
    return replace(
        work,
        survivors=survivors,
        resource_pressure=resource_pressure,
        niche_overlap=niche_overlap,
        niche_saturation=niche_saturation,
        base_threshold=base_threshold,
        min_population=min_population,
        evo_potential=evo_potential,
        speciation_pressure=speciation_pressure,
    )


def evaluate_environmental_pressure(
    work: _CandidateWork,
    *,
    species: Any,
    is_early_game: bool,
    average_pressure: float,
    spec_config: Any,
    is_plant: Callable[[Any], bool],
    plant_evolution_service: Any,
    random_random: Callable[[], float],
) -> _CandidateWork | None:
    """Apply pressure, plant, radiation and legacy mortality checks."""
    if is_early_game:
        pressure_threshold = spec_config.pressure_threshold_early
        resource_threshold = spec_config.resource_threshold_early
        evo_threshold = spec_config.evo_potential_threshold_early
    else:
        pressure_threshold = spec_config.pressure_threshold_late
        resource_threshold = spec_config.resource_threshold_late
        evo_threshold = spec_config.evo_potential_threshold_late

    if work.is_isolated:
        has_pressure = True
    elif work.candidate_population >= work.base_threshold * 2.5:
        has_pressure = True
        logger.debug(
            f"[巨无霸分化] {species.common_name}: "
            f"种群{work.candidate_population:,} >= 门槛×2.5"
            f"({int(work.base_threshold * 2.5):,})，强制触发分化"
        )
    elif work.speciation_pressure >= 0.05:
        has_pressure = True
    elif (
        average_pressure >= pressure_threshold
        or work.resource_pressure >= resource_threshold
    ):
        if is_early_game:
            has_pressure = True
        elif (
            work.resource_pressure >= 0.35
            or work.niche_saturation > 0.4
        ):
            has_pressure = True
        else:
            has_pressure = False
    elif work.evo_potential >= evo_threshold:
        has_pressure = True
    elif (
        work.speciation_pressure >= 0.03
        and work.candidate_population >= work.min_population * 1.5
    ):
        has_pressure = True
        logger.debug(
            f"[累积压力分化] {species.common_name}: "
            f"speciation_pressure={work.speciation_pressure:.2f}>=0.03"
        )
    else:
        has_pressure = False

    plant = is_plant(species)
    plant_milestone_ready = False
    speciation_pressure = work.speciation_pressure
    if plant:
        milestone_progress = species.morphology_stats.get(
            "milestone_progress",
            0.0,
        )
        next_milestone = plant_evolution_service.get_next_milestone(
            species
        )
        if next_milestone:
            is_met, readiness, _ = (
                plant_evolution_service.check_milestone_requirements(
                    species,
                    next_milestone.id,
                )
            )
            if is_met:
                has_pressure = True
                plant_milestone_ready = True
                speciation_type = (
                    f"里程碑演化：{next_milestone.name}"
                )
                logger.info(
                    f"[植物里程碑] {species.common_name} "
                    f"触发里程碑分化：{next_milestone.name}"
                )
            elif readiness > 0.8:
                speciation_pressure += 0.1 * readiness
                logger.debug(
                    f"[植物里程碑进度] {species.common_name} "
                    f"接近里程碑 {next_milestone.name} "
                    f"(准备度 {readiness:.0%})"
                )

    if not has_pressure:
        pop_ratio = (
            work.survivors / work.min_population
            if work.min_population > 0
            else 0
        )
        radiation_base = spec_config.radiation_base_chance
        early_bonus = 0.0
        min_pop_ratio_for_bonus = (
            spec_config.radiation_pop_ratio_early
            if is_early_game
            else spec_config.radiation_pop_ratio_late
        )
        if (
            is_early_game
            and pop_ratio >= min_pop_ratio_for_bonus
        ):
            early_bonus = spec_config.radiation_early_bonus

        if pop_ratio >= 1.5:
            pop_factor = min(0.20, (pop_ratio - 1.5) * 0.05)
        elif (
            is_early_game
            and pop_ratio >= min_pop_ratio_for_bonus
        ):
            pop_factor = min(0.15, (pop_ratio - 0.5) * 0.10)
        else:
            pop_factor = 0.0

        saturation_factor = 0.0
        if work.niche_saturation > 0.5:
            saturation_factor = (
                work.niche_saturation - 0.5
            ) * 0.25

        pressure_factor = speciation_pressure * 0.40
        radiation_chance = (
            radiation_base
            + early_bonus
            + pop_factor
            + saturation_factor
            + pressure_factor
        )
        if plant:
            radiation_chance += 0.05

        max_radiation = (
            spec_config.radiation_max_chance_early
            if is_early_game
            else spec_config.radiation_max_chance_late
        )
        radiation_chance = min(max_radiation, radiation_chance)
        no_isolation_penalty = (
            spec_config.no_isolation_penalty_early
            if is_early_game
            else spec_config.no_isolation_penalty_late
        )
        if not work.is_isolated:
            radiation_chance *= no_isolation_penalty

        min_pop_ratio = (
            spec_config.radiation_pop_ratio_early
            if is_early_game
            else spec_config.radiation_pop_ratio_late
        )
        if (
            work.survivors >= work.min_population * min_pop_ratio
            and random_random() < radiation_chance
        ):
            has_pressure = True
            speciation_type = "辐射演化"
            logger.info(
                f"[辐射演化] {species.common_name} "
                f"触发辐射演化 "
                f"(种群:{work.survivors:,}/{work.min_population:,}"
                f"={pop_ratio:.1f}x, "
                f"饱和度:{work.niche_saturation:.1%}, "
                f"概率:{radiation_chance:.1%}, "
                f"早期={is_early_game})"
            )
        else:
            has_pressure = False
            speciation_type = "自然分化"
            logger.debug(
                f"[自然分化候选] {species.common_name}: "
                "辐射演化检查未通过，但作为候选进入概率计算 "
                f"(radiation_chance={radiation_chance:.1%})"
            )

    if (
        not work.candidate_data
        and (work.death_rate < 0.03 or work.death_rate > 0.70)
    ):
        return None
    return replace(work, speciation_pressure=speciation_pressure)


def calculate_candidate_speciation_chance(
    work: _CandidateWork,
    *,
    species: Any,
    lineage_code: str,
    mortality_results: list,
    turn_index: int,
    density_damping: float,
    average_pressure: float,
    map_changes: list,
    major_events: list,
    spec_config: Any,
    base_speciation_rate: float,
    ai_speciation_candidates: set,
    detect_geographic_isolation: Callable[[str], dict],
    detect_coevolution: Callable[[Any, list], dict],
) -> _CandidateWork | None:
    """Calculate the final speciation channel and chance."""
    candidate_data = work.candidate_data
    candidate_tiles = work.candidate_tiles
    candidate_population = work.candidate_population
    death_rate = work.death_rate
    is_isolated = work.is_isolated
    mortality_gradient = work.mortality_gradient
    clusters = work.clusters
    survivors = work.survivors
    resource_pressure = work.resource_pressure
    niche_overlap = work.niche_overlap
    niche_saturation = work.niche_saturation
    base_threshold = work.base_threshold
    min_population = work.min_population
    evo_potential = work.evo_potential
    speciation_pressure = work.speciation_pressure

    generation_time = species.morphology_stats.get("generation_time_days", 365)
    total_days = 500_000 * 365
    generations = total_days / max(1.0, generation_time)

    generation_bonus = math.log10(max(10, generations)) * 0.02

    base_rate = base_speciation_rate
    base_chance = ((base_rate + (evo_potential * 0.25)) * 0.8 + generation_bonus) * density_damping

    if turn_index < spec_config.early_game_turns:
        if is_isolated or candidate_population >= base_threshold * 2.0:
            base_chance = max(base_chance, 0.45)
        else:
            base_chance = max(base_chance, 0.20)

    speciation_bonus = 0.0
    speciation_type = "生态隔离"

    death_rate_penalty = 0.0
    if death_rate < 0.05:
        # 死亡率过低，分化动力不足
        death_rate_penalty = -0.1
    elif death_rate <= 0.40:
        # 最优区间，无惩罚
        death_rate_penalty = 0.0
    elif death_rate <= 0.60:
        # 40%-60% 线性衰减
        death_rate_penalty = -0.3 * ((death_rate - 0.40) / 0.20)  # 最多-0.3
    else:
        # >60% 直接跳过（极端死亡率不适合分化）
        logger.debug(
            f"[分化跳过-死亡率过高] {species.common_name}: "
            f"死亡率{death_rate:.1%} > 60%"
        )
        return None
    # ========== 地理隔离通道（主路径）==========
    if candidate_data and is_isolated:
        speciation_bonus += 0.50  # 【强化】从 +0.25 提高到 +0.50
        speciation_type = "地理隔离"

        # 死亡率梯度 >0.2 再 +0.1 概率加成
        if mortality_gradient > 0.2:
            speciation_bonus += 0.10
            logger.info(
                f"[地块级隔离检测] {species.common_name}: "
                f"检测到{len(clusters)}个隔离区域, "
                f"死亡率梯度={mortality_gradient:.1%} (>20%, +10%加成), "
                f"候选地块={len(candidate_tiles)}"
            )
        else:
            logger.info(
                f"[地块级隔离检测] {species.common_name}: "
                f"检测到{len(clusters)}个隔离区域, "
                f"死亡率梯度={mortality_gradient:.1%}, "
                f"候选地块={len(candidate_tiles)}"
            )
    elif not candidate_data:
        # 回退到旧的检测方法
        geo_isolation_data = detect_geographic_isolation(lineage_code)
        if geo_isolation_data["is_isolated"]:
            speciation_bonus += 0.50  # 【强化】
            speciation_type = "地理隔离"
            clusters = geo_isolation_data["clusters"]

            if geo_isolation_data["mortality_gradient"] > 0.2:
                speciation_bonus += 0.10

            logger.info(
                f"[地理隔离检测] {species.common_name}: "
                f"检测到{geo_isolation_data['num_clusters']}个隔离区域, "
                f"死亡率差异={geo_isolation_data['mortality_gradient']:.1%}"
            )

    # ========== 重大地形事件（强触发）==========
    if map_changes:
        for change in (map_changes or []):
            change_type = change.get("change_type", "") if isinstance(change, dict) else getattr(change, "change_type", "")
            if change_type in ["uplift", "volcanic", "glaciation"]:
                speciation_bonus += 0.30  # 【强化】从 +0.15 提高到 +0.30
                if speciation_type != "地理隔离":
                    speciation_type = "地理隔离"
                break

    # ========== 生态隔离/垂直分化通道（同域分层）==========
    # 允许无地理隔离时触发，但条件更严
    ecological_isolation_triggered = False
    if not is_isolated and speciation_type != "地理隔离":
        # 条件：高压力/资源 + 生态信号（overlap/saturation）
        eco_pressure_ok = (average_pressure >= 0.7 or resource_pressure >= 0.65)
        eco_signal_ok = (niche_overlap > 0.6 or niche_saturation > 0.7)

        if eco_pressure_ok and eco_signal_ok:
            speciation_bonus += 0.25  # 中等加成，低于地理隔离
            speciation_type = "生态隔离"
            ecological_isolation_triggered = True
            logger.info(
                f"[生态隔离] {species.common_name}: "
                f"同域分层触发 (overlap={niche_overlap:.1%}, saturation={niche_saturation:.1%})"
            )

    # 检测极端环境特化
    if major_events:
        for event in (major_events or []):
            severity = event.get("severity", "") if isinstance(event, dict) else getattr(event, "severity", "")
            if severity in ["extreme", "catastrophic"]:
                speciation_bonus += 0.10
                if speciation_type == "生态隔离" and not ecological_isolation_triggered:
                    speciation_type = "极端环境特化"
                break

    # 检测协同演化（降低加成）
    if niche_overlap > 0.4 and speciation_type not in ["地理隔离", "生态隔离"]:
        speciation_bonus += 0.05  # 【降低】从 +0.08 降到 +0.05
        speciation_type = "协同演化"

    # 【大浪淘沙v4】自然分化兜底加成
    # 对于通过初步检查的候选，即使没有明显压力也给予基础分化机会
    if speciation_type == "自然分化":
        # 基于种群规模给予加成
        pop_ratio = survivors / min_population if min_population > 0 else 1
        if pop_ratio >= 1.5:
            speciation_bonus += 0.10 + min(0.15, (pop_ratio - 1.5) * 0.05)
            logger.debug(f"[自然分化加成] {species.common_name}: 种群比={pop_ratio:.1f}x, 加成={speciation_bonus:.0%}")

    # 【新增】动植物协同演化检测
    coevolution_result = detect_coevolution(species, mortality_results)
    if coevolution_result["has_coevolution"]:
        speciation_bonus += coevolution_result["bonus"]
        if speciation_type == "生态隔离":  # 只在没有更强触发时更新类型
            speciation_type = coevolution_result["type"]
        logger.debug(
            f"[协同演化] {species.common_name}: {coevolution_result['type']} "
            f"(+{coevolution_result['bonus']:.0%})"
        )

    # 应用死亡率区间惩罚
    speciation_bonus += death_rate_penalty

    # 【修复】将累积分化压力加入概率计算
    # 每回合满足条件但未分化的物种，下回合分化概率+10%
    speciation_chance = base_chance + speciation_bonus + speciation_pressure

    # ========== 【一揽子修改】迁徙抑制 ==========
    # 检查最近 2 回合是否有大规模迁徙
    migration_penalty = 1.0
    recent_migration_turns = species.morphology_stats.get("recent_migration_turns", [])
    if recent_migration_turns:
        # 统计最近2回合的迁徙并保存
        recent_migrations = [t for t in recent_migration_turns if turn_index - t <= 2]
        species.morphology_stats["recent_migration_turns"] = recent_migrations

        # 早期分化不受迁徙抑制，以免新版迁徙更积极导致分化全被压制
        if turn_index >= spec_config.early_game_turns and len(recent_migrations) >= 1:
            # 有迁徙记录，对非地理通道 ×0.5 抑制
            if speciation_type not in ["地理隔离"]:
                migration_penalty = 0.5
                logger.debug(
                    f"[迁徙抑制] {species.common_name}: "
                    f"最近{len(recent_migrations)}回合有迁徙, 概率×0.5"
                )
            else:
                logger.debug(
                    f"[迁徙抑制豁免] {species.common_name}: 地理隔离通道，忽略迁徙惩罚"
                )

    # 生态隔离额外门槛检查
    if ecological_isolation_triggered:
        # 生态隔离通道：种群门槛 ×1.5（在已计算的门槛基础上）
        eco_min_population = int(min_population * 1.5)
        if candidate_population < eco_min_population:
            logger.debug(
                f"[分化跳过-生态隔离门槛] {species.common_name}: "
                f"种群{candidate_population:,} < 生态隔离门槛{eco_min_population:,}"
            )
            return None
    speciation_chance *= migration_penalty

    # 【新增】AI 分化信号加成
    # 如果物种被 ModifierApplicator 识别为高分化信号候选，增加概率
    ai_boost = 0.0
    if lineage_code in ai_speciation_candidates:
        ai_boost = 0.15  # AI 识别的候选获得 15% 加成
        speciation_chance += ai_boost
        if speciation_type == "自然辐射" or speciation_type == "生态隔离":
            speciation_type = "AI辅助" + speciation_type
        logger.info(f"[AI分化] {species.common_name}: AI 分化信号加成 +{ai_boost:.0%}")

    # 【新增】背景物种分化惩罚
    # 背景物种（is_background=True）的分化概率大幅降低
    background_penalty = 1.0
    is_background = getattr(species, 'is_background', False)
    if is_background:
        background_penalty = spec_config.background_speciation_penalty
        speciation_chance *= background_penalty
        logger.debug(
            f"[背景物种惩罚] {species.common_name}: "
            f"分化概率×{background_penalty:.0%} (背景物种)"
        )

    # 记录分化概率计算详情
    ai_info = f" + AI={ai_boost:.1%}" if ai_boost > 0 else ""
    logger.info(
        f"[分化概率] {species.common_name}: "
        f"基础={base_chance:.1%} + 加成={speciation_bonus:.1%} + 累积={speciation_pressure:.1%}{ai_info} "
        f"= 总概率{speciation_chance:.1%} (类型:{speciation_type})"
    )


    return replace(
        work,
        clusters=clusters,
        generations=generations,
        speciation_type=speciation_type,
        speciation_chance=speciation_chance,
    )


def apply_candidate_speciation_roll(
    work: _CandidateWork,
    *,
    species: Any,
    turn_index: int,
    random_random: Callable[[], float],
    upsert_species: Callable[[Any], Any],
) -> _CandidateWork | None:
    """Apply the final roll and its existing pressure side effects."""
    roll = random_random()
    if roll > work.speciation_chance:
        new_pressure = min(0.4, work.speciation_pressure + 0.08)
        species.morphology_stats["speciation_pressure"] = new_pressure
        upsert_species(species)
        logger.info(
            f"[分化失败] {species.common_name}: "
            f"掷骰{roll:.2f} > 概率{work.speciation_chance:.1%}, "
            f"累积压力: {work.speciation_pressure:.1%} → "
            f"{new_pressure:.1%}"
        )
        return None

    logger.info(
        f"[分化成功!] {species.common_name}: "
        f"掷骰{roll:.2f} <= 概率{work.speciation_chance:.1%}"
    )
    species.morphology_stats["speciation_pressure"] = 0.0
    species.morphology_stats["last_speciation_turn"] = turn_index
    return work


def plan_candidate_offspring(
    work: _CandidateWork,
    *,
    species: Any,
    mortality_results: list,
    current_species_count: int,
    existing_codes: set[str],
    enable_dynamic_speciation: bool,
    calculate_dynamic_offspring_count: Callable[..., int],
    random_choice: Callable[[list], int],
    random_uniform: Callable[[float, float], float],
    allocate_offspring_population: Callable[[int, int], list[int]],
    generate_multiple_lineage_codes: Callable[..., list[str]],
    allocate_tiles_from_clusters: Callable[..., list],
    allocate_tiles_to_offspring: Callable[..., list],
    upsert_species: Callable[[Any], Any],
) -> _OffspringPlan | None:
    """Plan offspring population, codes and tiles after a successful roll."""
    candidate_data = work.candidate_data
    candidate_tiles = work.candidate_tiles
    tile_populations = work.tile_populations
    tile_mortality = work.tile_mortality
    candidate_population = work.candidate_population
    mortality_gradient = work.mortality_gradient
    clusters = work.clusters
    generations = work.generations
    evo_potential = work.evo_potential

    global_population = int(species.morphology_stats.get("population", 0) or 0)

    # 【关键修复】candidate_population 来自旧的 _population_matrix（死亡率计算前）
    # 而 global_population 来自 morphology_stats（可能已被死亡率和繁殖更新）
    # 必须确保 candidate_population 不超过 global_population，否则会导致负数种群
    if candidate_population > global_population:
        logger.warning(
            f"[种群同步警告] {species.common_name}: "
            f"候选地块种群({candidate_population:,}) > 全局种群({global_population:,})，"
            f"可能由于数据不同步，将候选种群限制为全局种群"
        )
        candidate_population = global_population

    # 【重要】分化只影响候选地块上的种群
    # 非候选地块上的种群保持不变（仍属于父系）
    speciation_pool = candidate_population  # 仅候选地块上的种群参与分化
    non_candidate_population = max(0, global_population - candidate_population)  # 确保不为负数

    # ========== 【改进】基于地块级压力计算分化数量 ==========
    # 计算各隔离区域的压力指标（用于决定分化数量和传递给AI）
    cluster_pressure_data = []
    if candidate_data and clusters:
        for cluster_idx, cluster in enumerate(clusters):
            cluster_pop = sum(tile_populations.get(t, 0) for t in cluster)
            cluster_tiles_with_rate = [(t, tile_mortality.get(t, 0.5)) for t in cluster if t in tile_mortality]

            if cluster_tiles_with_rate:
                # 计算该区域的平均死亡率
                total_pop_in_cluster = sum(tile_populations.get(t, 0) for t, _ in cluster_tiles_with_rate)
                if total_pop_in_cluster > 0:
                    avg_mortality = sum(
                        tile_mortality.get(t, 0.5) * tile_populations.get(t, 0)
                        for t, _ in cluster_tiles_with_rate
                    ) / total_pop_in_cluster
                else:
                    avg_mortality = sum(r for _, r in cluster_tiles_with_rate) / len(cluster_tiles_with_rate)

                # 区域压力描述
                if avg_mortality > 0.5:
                    pressure_level = "高压"
                elif avg_mortality > 0.3:
                    pressure_level = "中压"
                else:
                    pressure_level = "低压"
            else:
                avg_mortality = 0.5
                pressure_level = "未知"

            cluster_pressure_data.append({
                "cluster_idx": cluster_idx,
                "tiles": cluster,
                "population": int(cluster_pop),
                "avg_mortality": avg_mortality,
                "pressure_level": pressure_level,
            })

    if enable_dynamic_speciation:
        sibling_count = sum(
            1 for r in mortality_results
            if r.species.lineage_code.startswith(species.lineage_code[:2])
            and r.species.lineage_code != species.lineage_code
        )

        # 【改进】基于地块级压力决定子代数量
        if candidate_data and clusters:
            # 基础计算
            calculated_offspring = calculate_dynamic_offspring_count(
                generations, speciation_pool, evo_potential,
                current_species_count=current_species_count,
                sibling_count=sibling_count
            )

            # 【改进】考虑隔离区域数量和压力梯度
            # - 更多隔离区域 → 可能产生更多子代
            # - 更大的压力梯度 → 分化动力更强
            num_clusters = len(clusters)

            if num_clusters >= 3 and mortality_gradient > 0.3:
                # 强隔离 + 高梯度：允许更多子代
                num_offspring = min(num_clusters, calculated_offspring + 1)
            elif num_clusters >= 2:
                # 中等隔离：子代数 = min(隔离区域数, 计算值)
                num_offspring = min(num_clusters, calculated_offspring)
            else:
                # 单一区域：使用计算值
                num_offspring = calculated_offspring
        else:
            num_offspring = calculate_dynamic_offspring_count(
                generations, speciation_pool, evo_potential,
                current_species_count=current_species_count,
                sibling_count=sibling_count
            )

        logger.info(
            f"[地块分化] {species.common_name} 将分化出 {num_offspring} 个子种 "
            f"(候选种群:{speciation_pool:,}, 隔离区域:{len(clusters) if clusters else 0}, "
            f"死亡率梯度:{mortality_gradient:.1%})"
        )
    else:
        num_offspring = random_choice([2, 2, 3])
        logger.info(f"[分化] {species.common_name} 将分化出 {num_offspring} 个子种")

    # 种群分配（仅从候选地块的种群中分配）
    # 【v3.1改进】降低父代保留比例，让子代获得更多初始种群
    # 从 60-80% 降低到 40-55%，子代将获得 45-60% 的种群
    retention_ratio = random_uniform(0.40, 0.55)
    proposed_parent_from_candidates = max(50, int(speciation_pool * retention_ratio))
    max_parent_allowed = speciation_pool - num_offspring
    if max_parent_allowed <= 0:
        logger.warning(
            f"[分化终止] {species.common_name} 候选种群不足以生成子种 "
            f"(speciation_pool={speciation_pool}, offspring={num_offspring})"
        )
        return None
    parent_from_candidates = min(proposed_parent_from_candidates, max_parent_allowed)
    child_pool = speciation_pool - parent_from_candidates

    if child_pool < num_offspring:
        needed = num_offspring - child_pool
        transferable = max(0, parent_from_candidates - 50)
        if transferable <= 0:
            logger.warning(
                f"[分化终止] {species.common_name} 无法为子种分配个体 "
                f"(parent_from_candidates={parent_from_candidates})"
            )
            return None
        borrowed = min(needed, transferable)
        parent_from_candidates -= borrowed
        child_pool = speciation_pool - parent_from_candidates

    if child_pool < num_offspring:
        logger.warning(
            f"[分化终止] {species.common_name} 子代可用个体仍不足 "
            f"(child_pool={child_pool}, offspring={num_offspring})"
        )
        return None
    pop_splits = allocate_offspring_population(child_pool, num_offspring)

    # 生成编码
    new_codes = generate_multiple_lineage_codes(
        species.lineage_code, existing_codes, num_offspring
    )
    for code in new_codes:
        existing_codes.add(code)

    # 【改进】更新父系物种种群
    # 父系保留：非候选地块种群 + 候选地块中保留的部分
    parent_remaining = non_candidate_population + parent_from_candidates

    # 【关键修复】最终保护：确保父系种群不为负数
    if parent_remaining < 0:
        logger.error(
            f"[严重错误] {species.common_name} 分化后种群为负数！"
            f"parent_remaining={parent_remaining:,}, "
            f"non_candidate={non_candidate_population:,}, "
            f"parent_from_candidates={parent_from_candidates:,}, "
            f"global={global_population:,}, candidate={candidate_population:,}"
        )
        # 使用合理的最小值：至少保留 50 或 parent_from_candidates 中的较大者
        parent_remaining = max(50, parent_from_candidates)

    species.morphology_stats["population"] = parent_remaining
    upsert_species(species)

    logger.debug(
        f"[种群分配] {species.common_name}: "
        f"全局{global_population:,} → 父系{parent_remaining:,} + 子代{child_pool:,} "
        f"(非候选地块保留{non_candidate_population:,})"
    )

    # 【核心改进】基于候选数据为子代分配地块
    if candidate_data and clusters:
        # 使用候选数据中的隔离区域分配地块
        offspring_tiles = allocate_tiles_from_clusters(
            clusters, candidate_tiles, num_offspring
        )
    else:
        # 回退到旧方法
        offspring_tiles = allocate_tiles_to_offspring(
            species.lineage_code, num_offspring
        )

    # 为每个子种创建任务

    return _OffspringPlan(
        cluster_pressure_data=cluster_pressure_data,
        num_offspring=num_offspring,
        pop_splits=pop_splits,
        new_codes=new_codes,
        offspring_tiles=offspring_tiles,
    )


def append_offspring_plan_entries(
    entries: list[dict],
    plan: _OffspringPlan,
    *,
    build_entry: Callable[..., dict],
    common_kwargs_factory: Callable[[], dict],
) -> None:
    """Append planned entries one at a time to preserve partial progress."""
    for index, (new_code, population) in enumerate(
        zip(plan.new_codes, plan.pop_splits)
    ):
        entries.append(
            build_entry(
                new_code=new_code,
                population=population,
                offspring_index=index,
                num_offspring=plan.num_offspring,
                offspring_tiles=plan.offspring_tiles,
                cluster_pressure_data=plan.cluster_pressure_data,
                **common_kwargs_factory(),
            )
        )


def collect_candidate_entries(
    service: Any, mortality_results: list, existing_codes: set[str], *,
    direct_offspring_map: dict, turn_offspring_counts: dict,
    spec_config: Any, current_species_count: int, turn_index: int,
    is_early_game: bool,
    average_pressure: float, pressure_summary: str, density_damping: float,
    map_changes: list, major_events: list, settings: Any,
    species_repository: Any, plant_evolution_service: Any, random_source: Any,
    is_plant: Callable[[Any], bool],
) -> list[dict]:
    """Run the already-bounded candidate phases in stable candidate order."""
    entries: list[dict[str, Any]] = []
    for result in mortality_results:
        species = result.species
        lineage_code = species.lineage_code

        max_direct_offspring = spec_config.max_direct_offspring
        count_only_alive = spec_config.count_only_alive_offspring
        max_offspring_per_parent_per_turn = (
            spec_config.max_hybrids_per_parent_per_turn
        )

        direct_children = direct_offspring_map.get(lineage_code, [])
        if count_only_alive:
            alive_children_count = sum(
                1 for c in direct_children if c.status == "alive"
            )
        else:
            alive_children_count = len(direct_children)

        if alive_children_count >= max_direct_offspring:
            logger.debug(
                f"[分化限制] {species.common_name}: "
                f"直接后代数量({alive_children_count})已达上限"
                f"({max_direct_offspring})，跳过分化"
            )
            continue

        if (
            max_offspring_per_parent_per_turn
            and max_offspring_per_parent_per_turn > 0
        ):
            turn_children = turn_offspring_counts.get(lineage_code, 0)
            if turn_children >= max_offspring_per_parent_per_turn:
                logger.debug(
                    f"[分化限制-本回合] {species.common_name}: "
                    f"本回合子代数({turn_children})已达上限"
                    f"({max_offspring_per_parent_per_turn})，跳过分化"
                )
                continue

        global_population = int(
            species.morphology_stats.get("population", 0) or 0
        )
        min_pop_for_speciation = spec_config.min_population_for_speciation
        if global_population < min_pop_for_speciation:
            logger.debug(
                f"[分化跳过-种群门槛] {species.common_name}: "
                f"全局种群{global_population:,} < "
                f"门槛{min_pop_for_speciation:,}"
            )
            continue

        candidate_work = normalize_candidate_state(
            species=species,
            lineage_code=lineage_code,
            global_population=global_population,
            result_death_rate=result.death_rate,
            turn_index=turn_index,
            spec_config=spec_config,
            speciation_candidates=service._speciation_candidates,
            tile_population_cache=service._tile_population_cache,
            tile_mortality_cache=service._tile_mortality_cache,
            calculate_speciation_threshold=(
                service._calculate_speciation_threshold
            ),
        )
        candidate_data = candidate_work.candidate_data
        candidate_tiles = candidate_work.candidate_tiles
        tile_populations = candidate_work.tile_populations
        tile_mortality = candidate_work.tile_mortality
        global_population = candidate_work.global_population
        candidate_population = candidate_work.candidate_population
        death_rate = candidate_work.death_rate
        is_isolated = candidate_work.is_isolated
        mortality_gradient = candidate_work.mortality_gradient
        clusters = candidate_work.clusters

        candidate_work = evaluate_candidate_eligibility(
            candidate_work,
            species=species,
            result=result,
            turn_index=turn_index,
            average_pressure=average_pressure,
            spec_config=spec_config,
            calculate_speciation_threshold=(
                service._calculate_speciation_threshold
            ),
        )
        if candidate_work is None:
            continue

        candidate_work = evaluate_environmental_pressure(
            candidate_work,
            species=species,
            is_early_game=is_early_game,
            average_pressure=average_pressure,
            spec_config=spec_config,
            is_plant=is_plant,
            plant_evolution_service=plant_evolution_service,
            random_random=random_source.random,
        )
        if candidate_work is None:
            continue

        survivors = candidate_work.survivors
        resource_pressure = candidate_work.resource_pressure
        niche_overlap = candidate_work.niche_overlap
        niche_saturation = candidate_work.niche_saturation
        base_threshold = candidate_work.base_threshold
        min_population = candidate_work.min_population
        evo_potential = candidate_work.evo_potential
        speciation_pressure = candidate_work.speciation_pressure

        candidate_work = calculate_candidate_speciation_chance(
            candidate_work,
            species=species,
            lineage_code=lineage_code,
            mortality_results=mortality_results,
            turn_index=turn_index,
            density_damping=density_damping,
            average_pressure=average_pressure,
            map_changes=map_changes,
            major_events=major_events,
            spec_config=spec_config,
            base_speciation_rate=settings.base_speciation_rate,
            ai_speciation_candidates=service._ai_speciation_candidates,
            detect_geographic_isolation=(
                service._detect_geographic_isolation
            ),
            detect_coevolution=service._detect_coevolution,
        )
        if candidate_work is None:
            continue

        candidate_work = apply_candidate_speciation_roll(
            candidate_work,
            species=species,
            turn_index=turn_index,
            random_random=random_source.random,
            upsert_species=species_repository.upsert,
        )
        if candidate_work is None:
            continue

        clusters = candidate_work.clusters
        generations = candidate_work.generations
        speciation_type = candidate_work.speciation_type

        offspring_plan = plan_candidate_offspring(
            candidate_work,
            species=species,
            mortality_results=mortality_results,
            current_species_count=current_species_count,
            existing_codes=existing_codes,
            enable_dynamic_speciation=settings.enable_dynamic_speciation,
            calculate_dynamic_offspring_count=(
                service._calculate_dynamic_offspring_count
            ),
            random_choice=random_source.choice,
            random_uniform=random_source.uniform,
            allocate_offspring_population=(
                service._allocate_offspring_population
            ),
            generate_multiple_lineage_codes=(
                service._generate_multiple_lineage_codes
            ),
            allocate_tiles_from_clusters=(
                service._allocate_tiles_from_clusters
            ),
            allocate_tiles_to_offspring=(
                service._allocate_tiles_to_offspring
            ),
            upsert_species=species_repository.upsert,
        )
        if offspring_plan is None:
            continue

        append_offspring_plan_entries(
            entries,
            offspring_plan,
            build_entry=build_offspring_ai_entry,
            common_kwargs_factory=lambda: {
                "species": species,
                "clusters": clusters,
                "tile_populations": tile_populations,
                "tile_mortality": tile_mortality,
                "mortality_gradient": mortality_gradient,
                "is_isolated": is_isolated,
                "death_rate": death_rate,
                "candidate_data": candidate_data,
                "average_pressure": average_pressure,
                "pressure_summary": pressure_summary,
                "generations": generations,
                "speciation_type": speciation_type,
                "map_changes": map_changes,
                "major_events": major_events,
                "food_chain_summary": service._food_chain_summary,
                "current_pressures": getattr(
                    service, "_current_pressures", None
                ),
                "current_pressure_types": (
                    service._current_pressure_types
                ),
                "organ_catalog": service._organ_catalog,
                "turn_index": turn_index,
                "infer_biological_domain": (
                    service._infer_biological_domain
                ),
                "generate_tile_context": (
                    service._generate_tile_context
                ),
                "rules": service.rules,
                "naming_hint_generator": service.naming_hint_generator,
                "summarize_organs": service._summarize_organs,
                "summarize_map_changes": (
                    service._summarize_map_changes
                ),
                "summarize_major_events": (
                    service._summarize_major_events
                ),
                "summarize_prey_species": (
                    service._summarize_prey_species
                ),
                "summarize_dormant_genes": (
                    service._summarize_dormant_genes
                ),
                "organ_evolution_service": (
                    service.organ_evolution_service
                ),
            },
        )

    return entries


def build_offspring_ai_entry(
    *,
    species: Any, new_code: str, population: int,
    offspring_index: int, num_offspring: int, offspring_tiles: list,
    cluster_pressure_data: list[dict], clusters: list,
    tile_populations: dict, tile_mortality: dict,
    mortality_gradient: float, is_isolated: bool, death_rate: float,
    candidate_data: dict | None, average_pressure: float,
    pressure_summary: str, generations: float, speciation_type: str,
    map_changes: list, major_events: list, food_chain_summary: str,
    current_pressures: list | None, current_pressure_types: list,
    organ_catalog: list[dict], turn_index: int,
    infer_biological_domain: Callable[[Any], str],
    generate_tile_context: Callable[..., str], rules: Any,
    naming_hint_generator: Any,
    summarize_organs: Callable[[Any], str],
    summarize_map_changes: Callable[[list], str],
    summarize_major_events: Callable[[list], str],
    summarize_prey_species: Callable[[Any], str],
    summarize_dormant_genes: Callable[..., str],
    organ_evolution_service: Any,
) -> dict:
    """Build one offspring AI request entry from an existing plan."""
    safe_history = []
    if species.history_highlights:
        for event in species.history_highlights[-2:]:
            safe_history.append(
                event[:80] + "..." if len(event) > 80 else event
            )

    biological_domain = infer_biological_domain(species)
    assigned_tiles = offspring_tiles[offspring_index] if (
        offspring_index < len(offspring_tiles)
    ) else set()

    if cluster_pressure_data and offspring_index < len(cluster_pressure_data):
        region_data = cluster_pressure_data[offspring_index]
        region_mortality = region_data["avg_mortality"]
        region_pressure_level = region_data["pressure_level"]
        region_population = region_data["population"]
    else:
        if assigned_tiles and tile_mortality:
            region_mortality = sum(
                tile_mortality.get(t, 0.5)
                for t in assigned_tiles
            ) / len(assigned_tiles)
        else:
            region_mortality = death_rate

        if region_mortality > 0.5:
            region_pressure_level = "高压"
        elif region_mortality > 0.3:
            region_pressure_level = "中压"
        else:
            region_pressure_level = "低压"
        region_population = population

    cluster_environment = None
    tile_environment = candidate_data.get(
        "tile_environment"
    ) if candidate_data else None
    cluster_environments = candidate_data.get(
        "cluster_environments", []
    ) if candidate_data else []
    if cluster_environments and offspring_index < len(cluster_environments):
        cluster_environment = cluster_environments[offspring_index]

    tile_context = generate_tile_context(
        assigned_tiles,
        tile_populations,
        tile_mortality,
        mortality_gradient,
        is_isolated,
        tile_environment=tile_environment,
        cluster_environment=cluster_environment,
    )

    environment_pressure_dict = {
        "temperature": 0,
        "humidity": 0,
        "salinity": 0,
    }
    if current_pressures:
        for p in current_pressures:
            if hasattr(p, "modifiers"):
                environment_pressure_dict.update(p.modifiers)

    rule_constraints = rules.preprocess(
        parent_species=species,
        offspring_index=offspring_index + 1,
        total_offspring=num_offspring,
        environment_pressure=environment_pressure_dict,
        pressure_context=pressure_summary,
    )

    naming_seed = abs(hash(
        f"{new_code}-{species.lineage_code}-{offspring_index}"
    )) % 1_000_000_007
    naming_hint_generator.set_seed(naming_seed)
    naming_hints = naming_hint_generator.generate_compact_hint()

    ai_payload = {
        "parent_lineage": species.lineage_code,
        "latin_name": species.latin_name,
        "common_name": species.common_name,
        "habitat_type": species.habitat_type,
        "biological_domain": biological_domain,
        "current_organs_summary": summarize_organs(species),
        "environment_pressure": average_pressure,
        "pressure_summary": pressure_summary,
        "evolutionary_generations": int(generations),
        "traits": species.description,
        "history_highlights": "; ".join(safe_history) if safe_history else "无",
        "survivors": population,
        "speciation_type": speciation_type,
        "map_changes_summary": summarize_map_changes(
            map_changes
        ) if map_changes else "",
        "major_events_summary": summarize_major_events(
            major_events
        ) if major_events else "",
        "parent_trophic_level": species.trophic_level,
        "offspring_index": offspring_index + 1,
        "total_offspring": num_offspring,
        "food_chain_status": food_chain_summary,
        "tile_context": tile_context,
        "region_mortality": region_mortality,
        "region_pressure_level": region_pressure_level,
        "mortality_gradient": mortality_gradient,
        "num_isolation_regions": len(clusters) if clusters else 1,
        "is_geographic_isolation": (
            is_isolated and len(clusters) >= 2 if clusters else False
        ),
        "trait_budget_summary": rule_constraints["trait_budget_summary"],
        "organ_constraints_summary": rule_constraints[
            "organ_constraints_summary"],
        "evolution_direction": rule_constraints["evolution_direction"],
        "direction_description": rule_constraints["direction_description"],
        "suggested_increases": ", ".join(rule_constraints["suggested_increases"]),
        "suggested_decreases": ", ".join(rule_constraints["suggested_decreases"]),
        "habitat_options": ", ".join(rule_constraints["habitat_options"]),
        "trophic_range": rule_constraints["trophic_range"],
        "niche_exploration_strategy": rule_constraints.get(
            "niche_exploration_strategy", "保守继承型"),
        "niche_exploration_description": rule_constraints.get(
            "niche_exploration_description", ""),
        "niche_exploration_full": rule_constraints.get(
            "niche_exploration_full", ""),
        "target_diet_focus": rule_constraints.get(
            "target_diet_focus", "与父代相同"),
        "target_body_size_trend": rule_constraints.get(
            "target_body_size_trend", "similar"),
        "target_ecological_role": rule_constraints.get(
            "target_ecological_role", ""),
        "competition_with_parent": rule_constraints.get(
            "competition_with_parent", "direct"),
        "era_summary": rule_constraints.get("era_summary", ""),
        "era_single_cap": rule_constraints.get("era_single_cap", 15),
        "era_total_cap": rule_constraints.get("era_total_cap", 100),
        "diminishing_returns_context": rule_constraints.get(
            "diminishing_returns_context", ""),
        "breakthrough_opportunities": rule_constraints.get(
            "breakthrough_opportunities", ""),
        "habitat_specialization_bonus": rule_constraints.get(
            "habitat_specialization_bonus", ""),
        "strategy_recommendation": rule_constraints.get(
            "strategy_recommendation", ""),
        "budget_usage_percent": rule_constraints.get(
            "budget_usage_percent", 0.5),
        "remaining_budget": rule_constraints.get("remaining_budget", 50),
        "diet_type": species.diet_type or "omnivore",
        "prey_species_summary": summarize_prey_species(species),
        "gene_diversity_radius": getattr(
            species, "gene_diversity_radius", 0.35) or 0.35,
        "gene_stability": getattr(
            species, "gene_stability", 0.5) or 0.5,
        "explored_directions": len(
            getattr(species, "explored_directions", []) or []
        ),
        "dormant_genes_summary": summarize_dormant_genes(
            species,
            pressure_types=current_pressure_types,
            pressure_strength=average_pressure,
        ),
        "organ_key_catalog": "\n".join(
            [
                f"- {c['organ_key']} ({c['category']})："
                f"{c['default_name']}"
                for c in organ_catalog
            ]
        ),
        "mature_organs_context": (
            organ_evolution_service.build_mature_organs_context(species)
        ),
        "naming_hints": naming_hints,
    }

    return {
        "ctx": {
            "parent": species,
            "new_code": new_code,
            "population": population,
            "ai_payload_input": ai_payload,
            "speciation_type": speciation_type,
            "assigned_tiles": assigned_tiles,
            "average_pressure": average_pressure,
        },
        "payload": ai_payload,
        "request_turn": turn_index,
    }


def prepare_active_result(
    result: Any,
    entry: dict,
    *,
    turn_index: int,
    average_pressure: float,
    environment_pressure: dict,
    queue_deferred_request: Callable[[dict], Any],
    normalize_ai_content: Callable[[Any], dict],
    generate_rule_based_fallback: Callable[..., dict],
) -> tuple[dict, dict] | None:
    """Prepare one active AI result or preserve its existing skip decision."""
    request_turn = entry.get("request_turn", -1)
    if request_turn != turn_index:
        logger.warning(
            f"[分化跳过-过期] {entry.get('ctx', {}).get('new_code', '?')}: "
            f"请求来自回合 {request_turn}，当前回合 {turn_index}，丢弃"
        )
        return None

    ctx = entry["ctx"]
    retry_count = entry.get("_retry_count", 0)
    use_fallback = False

    if isinstance(result, Exception):
        logger.error(f"[分化AI异常] {result}")
        if retry_count >= 2:
            use_fallback = True
            logger.info(
                f"[分化] 重试{retry_count}次后AI仍失败，使用规则fallback"
            )
        else:
            queue_deferred_request(entry)
            return None

    ai_content = result
    if not use_fallback and not isinstance(ai_content, dict):
        logger.warning(
            f"[分化警告] AI返回的content不是dict类型: "
            f"{type(ai_content)}, 内容: {ai_content}"
        )
        if retry_count >= 2:
            use_fallback = True
        else:
            queue_deferred_request(entry)
            return None
    if not use_fallback:
        ai_content = normalize_ai_content(ai_content)

    required_fields = ["latin_name", "common_name", "description"]
    if not use_fallback and any(
        not ai_content.get(field) for field in required_fields
    ):
        logger.warning(
            "[分化警告] AI返回缺少必要字段: %s",
            {field: ai_content.get(field) for field in required_fields},
        )
        if retry_count >= 2:
            use_fallback = True
        else:
            queue_deferred_request(entry)
            return None

    if use_fallback:
        ai_content = generate_rule_based_fallback(
            parent=ctx["parent"],
            new_code=ctx["new_code"],
            survivors=ctx["population"],
            speciation_type=ctx["speciation_type"],
            average_pressure=average_pressure,
            environment_pressure=environment_pressure,
            turn_index=turn_index,
        )
        ai_content = normalize_ai_content(ai_content)

    logger.info(
        "[分化AI返回] latin_name: %s, common_name: %s, description长度: %s",
        ai_content.get("latin_name"),
        ai_content.get("common_name"),
        len(str(ai_content.get("description", ""))),
    )
    return ctx, ai_content


def materialize_active_result(
    ctx: dict,
    ai_content: dict,
    *,
    turn_index: int,
    average_pressure: float,
    validate_and_fix: Callable[..., dict],
    create_species: Callable[..., Any],
    turn_offspring_counts: dict,
    rule_fallback_species: list[tuple[Any, Any, str]],
    random_uniform: Callable[[float, float], float],
    inherit_habitat_distribution: Callable[..., Any],
    update_genetic_distances: Callable[..., Any],
    gene_library_service_owner: Any,
    genus_repository: Any,
    process_ai_activated_genes: Callable[..., int],
    process_ai_new_dormant_genes: Callable[..., int],
    try_speciation_breakthrough: Callable[..., Any],
    check_and_trigger_plant_milestones: Callable[..., Any],
    evaluate_new_species_viability: Callable[..., dict],
    upsert_species: Callable[[Any], Any],
    log_lineage_event: Callable[[Any], Any],
    lineage_event_factory: Callable[..., Any],
    branching_event_factory: Callable[..., Any],
    utcnow: Callable[[], Any],
) -> Any:
    """Persist one prepared active result and return its branching event."""
    ai_content = validate_and_fix(
        ai_content,
        ctx["parent"],
        preprocess_result=None,
    )

    new_species = create_species(
        parent=ctx["parent"],
        new_code=ctx["new_code"],
        survivors=ctx["population"],
        turn_index=turn_index,
        ai_payload=ai_content,
        average_pressure=average_pressure,
        speciation_type=ctx["speciation_type"],
    )
    logger.info(
        f"[分化] 新物种 {new_species.common_name} "
        f"created_turn={new_species.created_turn} "
        f"(传入的turn_index={turn_index})"
    )
    new_species = upsert_species(new_species)

    parent_code = ctx["parent"].lineage_code
    try:
        turn_offspring_counts[parent_code] += 1
        ctx.turn_offspring_counts = turn_offspring_counts  # type: ignore[attr-defined]
    except Exception:
        pass
    logger.info(
        f"[分化] upsert后 {new_species.common_name} "
        f"created_turn={new_species.created_turn}"
    )
    parent_code = ctx["parent"].lineage_code
    try:
        turn_offspring_counts[parent_code] += 1
        ctx.turn_offspring_counts = turn_offspring_counts  # type: ignore[attr-defined]
    except Exception:
        pass

    if ai_content.get("_is_rule_fallback"):
        rule_fallback_species.append(
            (new_species, ctx["parent"], ctx["speciation_type"])
        )

    assigned_tiles = ctx.get("assigned_tiles", set())
    reproduction_bonus = random_uniform(0.30, 0.50)
    inherit_habitat_distribution(
        parent=ctx["parent"],
        child=new_species,
        turn_index=turn_index,
        assigned_tiles=assigned_tiles,
        reproduction_bonus=reproduction_bonus,
    )

    update_genetic_distances(new_species, ctx["parent"], turn_index)

    if ai_content.get("genetic_discoveries") and new_species.genus_code:
        gene_library_service_owner.gene_library_service.record_discovery(
            genus_code=new_species.genus_code,
            discoveries=ai_content["genetic_discoveries"],
            discoverer_code=new_species.lineage_code,
            turn=turn_index,
        )

    genus = (
        genus_repository.get_by_code(new_species.genus_code)
        if new_species.genus_code
        else None
    )
    gene_library_service_owner.gene_library_service.inherit_dormant_genes(
        ctx["parent"],
        new_species,
        genus,
    )
    upsert_species(new_species)

    ai_activated_genes = (
        ai_content.get("activated_genes", []) if ai_content else []
    )
    if ai_activated_genes:
        activated_count = process_ai_activated_genes(
            new_species,
            ai_activated_genes,
            turn_index,
        )
        if activated_count > 0:
            upsert_species(new_species)
            logger.info(
                f"[AI基因激活] {new_species.common_name} "
                f"激活了 {activated_count} 个AI指定的基因"
            )

    ai_new_genes = (
        ai_content.get("new_dormant_genes") if ai_content else None
    )
    if ai_new_genes:
        added_count = process_ai_new_dormant_genes(
            new_species,
            ai_new_genes,
            turn_index,
        )
        if added_count > 0:
            upsert_species(new_species)
            logger.info(
                f"[LLM新基因] {new_species.common_name} "
                f"获得了 {added_count} 个LLM生成的新休眠基因"
            )

    breakthrough_result = try_speciation_breakthrough(
        new_species,
        turn_index,
    )
    if breakthrough_result:
        upsert_species(new_species)
        logger.info(
            f"[分化突破] {new_species.common_name} 在分化中激活休眠基因: "
            f"{breakthrough_result}"
        )

    milestone_result = check_and_trigger_plant_milestones(
        new_species,
        turn_index,
    )
    if milestone_result:
        upsert_species(new_species)
        logger.info(
            f"[植物里程碑] {new_species.common_name} 触发里程碑: "
            f"{milestone_result.get('milestone_name', 'unknown')}"
        )

    if gene_library_service_owner._tensor_state is not None:
        species_map = {}
        if hasattr(gene_library_service_owner._tensor_state, "species_map"):
            species_map = (
                gene_library_service_owner._tensor_state.species_map
            )

        viability = evaluate_new_species_viability(
            new_species,
            gene_library_service_owner._tensor_state,
            species_map,
            turn_index,
        )

        if viability["recommendation"] == "extinct":
            new_species.morphology_stats["viability_risk"] = "critical"
            upsert_species(new_species)
            logger.warning(
                f"[新种筛选] {new_species.common_name} 被标记为高灭绝风险: "
                f"适宜度={viability['avg_suitability']:.3f}, "
                f"分布={viability['tile_count']}格"
            )
        elif viability["recommendation"] == "penalize":
            new_species.morphology_stats["viability_risk"] = "low"
            upsert_species(new_species)

    log_lineage_event(
        lineage_event_factory(
            lineage_code=ctx["new_code"],
            event_type="speciation",
            payload={
                "parent": ctx["parent"].lineage_code,
                "turn": turn_index,
            },
        )
    )

    event_desc = ai_content.get("event_description") if ai_content else None
    if not event_desc:
        event_desc = (
            f"{ctx['parent'].common_name}在压力{average_pressure:.1f}"
            f"条件下分化出{ctx['new_code']}"
        )

    reason_text = ai_content.get("reason") or ai_content.get(
        "speciation_reason"
    )
    if not reason_text:
        if ctx["speciation_type"] == "地理隔离":
            reason_text = (
                f"{ctx['parent'].common_name}因地形剧变导致种群地理隔离，"
                f"各隔离群体独立演化产生生殖隔离"
            )
        elif ctx["speciation_type"] == "极端环境特化":
            reason_text = (
                f"{ctx['parent'].common_name}在极端环境压力下，"
                f"部分种群演化出特化适应能力，与原种群形成生态分离"
            )
        elif ctx["speciation_type"] == "协同演化":
            reason_text = (
                f"{ctx['parent'].common_name}与竞争物种的生态位重叠"
                f"导致竞争排斥，促使种群分化到不同资源梯度"
            )
        else:
            reason_text = (
                f"{ctx['parent'].common_name}种群在演化压力下"
                f"发生生态位分化"
            )

    return branching_event_factory(
        parent_lineage=ctx["parent"].lineage_code,
        new_lineage=ctx["new_code"],
        description=event_desc,
        timestamp=utcnow(),
        reason=reason_text,
    )


def materialize_active_results(
    results: list,
    active_batch: list[dict],
    *,
    result_events: list[Any],
    preparation_kwargs: dict[str, Any],
    materialization_kwargs: dict[str, Any],
) -> None:
    """Prepare and materialize active results in stable zip order."""
    for result, entry in zip(results, active_batch):
        prepared = prepare_active_result(
            result,
            entry,
            **preparation_kwargs,
        )
        if prepared is None:
            continue
        ctx, ai_content = prepared
        result_events.append(
            materialize_active_result(
                ctx,
                ai_content,
                **materialization_kwargs,
            )
        )


def materialize_background_result(
    entry: dict,
    ai_content: dict,
    *,
    turn_index: int,
    average_pressure: float,
    validate_and_fix: Callable[..., dict],
    create_species: Callable[..., Any],
    rule_fallback_species: list[tuple[Any, Any, str]],
    random_uniform: Callable[[float, float], float],
    inherit_habitat_distribution: Callable[..., Any],
    gene_library_service_owner: Any,
    genus_repository: Any,
    try_speciation_breakthrough: Callable[..., Any],
    upsert_species: Callable[[Any], Any],
    log_lineage_event: Callable[[Any], Any],
    lineage_event_factory: Callable[..., Any],
    branching_event_factory: Callable[..., Any],
    utcnow: Callable[[], Any],
) -> Any:
    """Create and persist one background species result and its event."""
    ctx = entry["ctx"]

    logger.info(
        f"[规则分化结果] 背景物种: {ai_content.get('common_name')}, description长度: {len(str(ai_content.get('description', '')))}"
    )

    # 【新增】规则引擎后验证：验证并修正输出
    ai_content = validate_and_fix(
        ai_content,
        ctx["parent"],
        preprocess_result=None,
    )

    new_species = create_species(
        parent=ctx["parent"],
        new_code=ctx["new_code"],
        survivors=ctx["population"],
        turn_index=turn_index,
        ai_payload=ai_content,
        average_pressure=average_pressure,
        speciation_type=ctx["speciation_type"],
    )

    # 背景物种子代也标记为背景
    new_species.is_background = True

    logger.info(
        f"[规则分化] 新背景物种 {new_species.common_name} created_turn={new_species.created_turn}"
    )
    new_species = upsert_species(new_species)

    # 将背景物种加入增强队列（用于模板描述和向量遗传）
    rule_fallback_species.append(
        (new_species, ctx["parent"], ctx["speciation_type"])
    )

    # 处理分配地块
    assigned_tiles = ctx.get("assigned_tiles", set())

    # 【v3.1】背景物种也给予繁殖补偿
    reproduction_bonus = random_uniform(0.30, 0.50)

    inherit_habitat_distribution(
        parent=ctx["parent"],
        child=new_species,
        turn_index=turn_index,
        assigned_tiles=assigned_tiles,
        reproduction_bonus=reproduction_bonus,
    )

    # 【修复】即使没有 genus 也调用继承方法（处理新突变和额外基因）
    if (
        hasattr(gene_library_service_owner, "gene_library_service")
        and gene_library_service_owner.gene_library_service
    ):
        genus = (
            genus_repository.get_by_code(new_species.genus_code)
            if new_species.genus_code
            else None
        )
        gene_library_service_owner.gene_library_service.inherit_dormant_genes(
            ctx["parent"],
            new_species,
            genus,
        )
        upsert_species(new_species)

    # 【分化突破】背景物种仅激活已有休眠基因（不生成新基因）
    breakthrough_result = try_speciation_breakthrough(
        new_species,
        turn_index,
    )
    if breakthrough_result:
        upsert_species(new_species)
        logger.info(
            f"[分化突破-背景] {new_species.common_name} 在分化中激活休眠基因: "
            f"{breakthrough_result}"
        )

    log_lineage_event(
        lineage_event_factory(
            lineage_code=ctx["new_code"],
            event_type="speciation",
            payload={
                "parent": ctx["parent"].lineage_code,
                "turn": turn_index,
            },
        )
    )

    event_desc = (
        f"{ctx['parent'].common_name}在压力{average_pressure:.1f}条件下"
        f"分化出{ctx['new_code']}（背景物种）"
    )
    reason_text = (
        f"{ctx['parent'].common_name}种群在演化压力下发生生态位分化"
    )

    return branching_event_factory(
        parent_lineage=ctx["parent"].lineage_code,
        new_lineage=ctx["new_code"],
        description=event_desc,
        timestamp=utcnow(),
        reason=reason_text,
    )


def materialize_background_results(
    background_results: list[tuple[dict, dict]],
    *,
    result_events: list[Any],
    **kwargs: Any,
) -> None:
    """Materialize background results in their existing stable order."""
    for entry, ai_content in background_results:
        result_events.append(
            materialize_background_result(entry, ai_content, **kwargs)
        )


async def enhance_rule_fallback_descriptions(
    rule_fallback_species: list[tuple[Any, Any, str]],
    *,
    description_enhancer: Any,
    upsert_species: Callable[[Any], Any],
) -> None:
    """Enhance queued rule-generated species and always clear attempted work."""
    if rule_fallback_species:
        logger.info(
            f"[描述增强] 开始处理 {len(rule_fallback_species)} 个规则生成物种的描述增强"
        )
        try:
            # 将物种加入增强队列
            for species, parent, speciation_type in rule_fallback_species:
                description_enhancer.queue_for_enhancement(
                    species=species,
                    parent=parent,
                    speciation_type=speciation_type,
                    is_hybrid=False,
                )

            # 批量处理增强队列
            enhanced_list = await description_enhancer.process_queue_async(
                max_items=20,  # 每回合最多处理20个
                timeout_per_item=25.0,
            )

            # 保存增强后的物种描述
            for enhanced_species in enhanced_list:
                upsert_species(enhanced_species)

            logger.info(
                f"[描述增强] 完成 {len(enhanced_list)}/{len(rule_fallback_species)} 个物种描述增强"
            )
        except Exception as e:
            logger.error(f"[描述增强] 处理失败: {e}")
        finally:
            rule_fallback_species.clear()


async def execute_active_ai_batches(
    active_batch: list[dict],
    *,
    average_pressure: float,
    pressure_summary: str,
    map_changes: list,
    major_events: list,
    turn_index: int,
    stream_callback: Any,
    build_batch_payload: Callable[..., dict],
    call_batch_ai: Callable[..., Any],
    parse_batch_results: Callable[..., list],
    staggered_gather: Callable[..., Any],
) -> list:
    """Execute fixed-size AI batches and flatten their matched results."""
    results = []
    if active_batch:
        # 【优化】小批次 + 高并发策略
        # 每批 2 个物种，降低单次延迟
        # 同时 20 个批次并行，提高整体吞吐量
        batch_size = 2

        # 分割成多个批次
        batches = []
        for batch_start in range(0, len(active_batch), batch_size):
            batch_entries = active_batch[batch_start:batch_start + batch_size]
            batches.append(batch_entries)

        logger.info(
            f"[分化] 共 {len(batches)} 个AI批次（每批≤{batch_size}个），开始高并发执行"
        )

        async def process_batch(batch_entries: list) -> list:
            """处理单个批次"""
            batch_payload = build_batch_payload(
                batch_entries,
                average_pressure,
                pressure_summary,
                map_changes,
                major_events,
                turn_index,
            )
            # 【混合模式】传入entries用于判断是否为植物批次
            batch_results = await call_batch_ai(
                batch_payload, stream_callback, batch_entries
            )
            return parse_batch_results(batch_results, batch_entries)

        # 【优化】小批次 + 高并发：间隔更短，并发更高
        coroutines = [process_batch(batch) for batch in batches]
        batch_results_list = await staggered_gather(
            coroutines,
            interval=1.5,  # 调整批次启动间隔
            max_concurrent=20,  # 提升并发批次数
            task_name="分化批次",
            event_callback=stream_callback,  # 【新增】传递心跳回调
        )

        # 合并所有批次的结果
        for batch_idx, batch_result in enumerate(batch_results_list):
            if isinstance(batch_result, Exception):
                logger.error(
                    f"[分化] 批次 {batch_idx + 1} 失败: {batch_result}"
                )
                results.extend([batch_result] * len(batches[batch_idx]))
            else:
                success_count = len(
                    [r for r in batch_result if not isinstance(r, Exception)]
                )
                logger.info(
                    f"[分化] 批次 {batch_idx + 1} 完成，成功解析 {success_count} 个结果"
                )
                results.extend(batch_result)

    return results


def generate_background_results(
    background_entries: list[dict],
    pressures: list[Any] | None,
    *,
    average_pressure: float,
    turn_index: int,
    generate_rule_based_fallback: Callable[..., dict],
) -> list[tuple[dict, dict]]:
    """Generate deterministic rule results for background species."""
    background_results: list[tuple[dict, dict]] = []

    # 构建环境压力字典（用于规则引擎）
    env_pressure_dict = {}
    if pressures:
        for p in pressures:
            if hasattr(p, "category") and hasattr(p, "intensity"):
                env_pressure_dict[p.category] = p.intensity

    for entry in background_entries:
        ctx = entry["ctx"]
        ai_content = generate_rule_based_fallback(
            parent=ctx["parent"],
            new_code=ctx["new_code"],
            survivors=ctx["population"],
            speciation_type=ctx["speciation_type"],
            average_pressure=average_pressure,
            environment_pressure=env_pressure_dict,
            turn_index=turn_index,
        )
        background_results.append((entry, ai_content))
        logger.debug(
            f"[规则分化] 背景物种 {ctx['parent'].common_name} -> {ai_content.get('common_name')} "
            f"({ai_content.get('_evolution_direction', '自然分化')})"
        )

    if background_results:
        logger.info(
            f"[规则分化] 完成 {len(background_results)} 个背景物种的规则生成"
        )

    return background_results


def partition_speciation_entries(
    entries: list[dict],
    deferred_requests: list[dict],
    *,
    max_deferred_requests: int,
    max_speciation_per_turn: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split prepared entries into background, active and deferred work."""
    background_entries: list[dict] = []
    ai_entries: list[dict] = []

    for entry in entries:
        parent = entry["ctx"]["parent"]
        if getattr(parent, "is_background", False):
            background_entries.append(entry)
        else:
            ai_entries.append(entry)

    pending = deferred_requests + ai_entries
    if len(pending) > max_deferred_requests:
        pending = pending[:max_deferred_requests]
    active_batch = pending[:max_speciation_per_turn]
    remaining_deferred = pending[max_speciation_per_turn:]

    return background_entries, active_batch, remaining_deferred
