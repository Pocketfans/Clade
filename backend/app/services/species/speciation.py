from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Sequence, Callable, Awaitable, Any

from ...models.species import LineageEvent, Species
from ...ai.model_router import staggered_gather

logger = logging.getLogger(__name__)
from ...repositories.genus_repository import genus_repository
from ...repositories.species_repository import species_repository
from ...schemas.responses import BranchingEvent
from .gene_library import GeneLibraryService
from .genetic_distance import GeneticDistanceCalculator
from .trait_config import TraitConfig
from .trophic import TrophicLevelCalculator
from .speciation_rules import SpeciationRules, speciation_rules  # 【新增】规则引擎
from ...core.config import get_settings

# 获取配置
_settings = get_settings()


class SpeciationService:
    """根据存活数据和演化潜力，生成新的谱系并记录事件。
    
    【核心改进】现在支持基于地块的分化：
    - 分化发生在特定区域（地块集群），而非全局
    - 子代物种只在分化起源区域出现
    - 不同子代可以分配到不同地块（模拟地理隔离）
    """

    def __init__(self, router) -> None:
        self.router = router
        self.trophic_calculator = TrophicLevelCalculator()
        self.genetic_calculator = GeneticDistanceCalculator()
        self.gene_library_service = GeneLibraryService()
        self.rules = speciation_rules  # 【新增】规则引擎实例
        self.max_speciation_per_turn = 20
        self.max_deferred_requests = 60
        self._deferred_requests: list[dict[str, Any]] = []
        
        # 【新增】地块级数据缓存
        self._tile_mortality_cache: dict[str, dict[int, float]] = {}  # {lineage_code: {tile_id: death_rate}}
        self._tile_population_cache: dict[str, dict[int, float]] = {}  # {lineage_code: {tile_id: population}}
        self._tile_adjacency: dict[int, set[int]] = {}  # {tile_id: {adjacent_tile_ids}}
        self._speciation_candidates: dict[str, dict] = {}  # 预筛选的分化候选数据
        
        # 【Embedding集成】演化提示缓存
        self._evolution_hints: dict[str, dict] = {}  # {lineage_code: {reference_species, predicted_traits, ...}}
    
    def set_tile_mortality_data(
        self, 
        lineage_code: str, 
        tile_death_rates: dict[int, float]
    ) -> None:
        """设置物种在各地块的死亡率数据
        
        由 TileBasedMortalityEngine 调用
        """
        self._tile_mortality_cache[lineage_code] = tile_death_rates
    
    def set_tile_population_data(
        self, 
        lineage_code: str, 
        tile_populations: dict[int, float]
    ) -> None:
        """设置物种在各地块的种群分布数据
        
        由 TileBasedMortalityEngine 调用
        """
        self._tile_population_cache[lineage_code] = tile_populations
    
    def set_speciation_candidates(self, candidates: dict[str, dict]) -> None:
        """设置预筛选的分化候选数据
        
        由 engine.py 从 TileBasedMortalityEngine.get_speciation_candidates() 获取后传入
        """
        self._speciation_candidates = candidates
    
    def set_tile_adjacency(self, adjacency: dict[int, set[int]]) -> None:
        """设置地块邻接关系"""
        self._tile_adjacency = adjacency
    
    def clear_tile_cache(self) -> None:
        """清空地块缓存（每回合开始时调用）"""
        self._tile_mortality_cache.clear()
        self._tile_population_cache.clear()
        self._speciation_candidates.clear()
        self._evolution_hints.clear()
    
    def set_evolution_hints(self, hints: dict[str, dict]) -> None:
        """设置演化提示（由 EmbeddingIntegrationService 提供）
        
        Args:
            hints: {lineage_code: {reference_species, predicted_traits, confidence}}
        """
        self._evolution_hints = hints
    
    def get_evolution_hint(self, lineage_code: str) -> dict | None:
        """获取特定物种的演化提示"""
        return self._evolution_hints.get(lineage_code)

    async def process_async(
        self,
        mortality_results,
        existing_codes: set[str],
        average_pressure: float,
        turn_index: int,
        map_changes: list = None,
        major_events: list = None,
        pressures: Sequence = None,  # 新增：ParsedPressure 列表
        trophic_interactions: dict[str, float] = None,  # 新增：营养级互动信息
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> list[BranchingEvent]:
        """处理物种分化 (异步并发版)"""
        import random
        import math
        
        # 保存营养级互动信息，供后续使用
        self._current_trophic_interactions = trophic_interactions or {}
        
        # 提取压力描述摘要
        pressure_summary = "无显著环境压力"
        if pressures:
            # 使用 set 去重描述，避免重复
            narratives = sorted(list(set(p.narrative for p in pressures)))
            pressure_summary = "; ".join(narratives)
        elif major_events:
            pressure_summary = "重大地质/气候变迁"
        elif average_pressure > 5.0:
            pressure_summary = f"高环境压力 ({average_pressure:.1f}/10)"
        
        # 生成食物链状态描述（用于AI）
        self._food_chain_summary = self._summarize_food_chain_status(trophic_interactions)
        
        # 动态分化限制 (Dynamic Speciation Limiting)
        # 【优化】收紧限制，依赖淘汰机制来控制物种数量
        current_species_count = len(mortality_results)
        # 软上限从配置读取，默认40
        soft_cap = _settings.species_soft_cap
        density_damping = 1.0 / (1.0 + max(0, current_species_count - soft_cap) / float(soft_cap))
        
        # 1. 准备阶段：筛选候选并生成任务
        entries: list[dict[str, Any]] = []
        
        for result in mortality_results:
            species = result.species
            lineage_code = species.lineage_code
            
            # ========== 【基于地块的分化检查】==========
            # 优先使用预筛选的分化候选数据
            candidate_data = self._speciation_candidates.get(lineage_code)
            
            if candidate_data:
                # 使用地块级数据
                candidate_tiles = candidate_data["candidate_tiles"]
                tile_populations = candidate_data["tile_populations"]
                tile_mortality = candidate_data["tile_mortality"]
                is_isolated = candidate_data["is_isolated"]
                mortality_gradient = candidate_data["mortality_gradient"]
                clusters = candidate_data["clusters"]
                
                # 计算候选地块上的总种群
                candidate_population = int(candidate_data["total_candidate_population"])
                
                # 计算候选地块的加权平均死亡率
                total_pop = sum(tile_populations.get(t, 0) for t in candidate_tiles)
                if total_pop > 0:
                    death_rate = sum(
                        tile_mortality.get(t, 0) * tile_populations.get(t, 0) 
                        for t in candidate_tiles
                    ) / total_pop
                else:
                    death_rate = result.death_rate
                
                logger.debug(
                    f"[地块分化检查] {species.common_name}: "
                    f"候选地块={len(candidate_tiles)}, 候选种群={candidate_population:,}, "
                    f"加权死亡率={death_rate:.1%}, 隔离={is_isolated}"
                )
            else:
                # 回退到全局数据（兼容旧逻辑）
                candidate_tiles = set()
                tile_populations = self._tile_population_cache.get(lineage_code, {})
                tile_mortality = self._tile_mortality_cache.get(lineage_code, {})
                candidate_population = int(species.morphology_stats.get("population", 0) or 0)
                death_rate = result.death_rate
                is_isolated = False
                mortality_gradient = 0.0
                clusters = []
                
                # 如果有地块数据，尝试筛选候选地块
                if tile_populations and tile_mortality:
                    for tile_id, pop in tile_populations.items():
                        rate = tile_mortality.get(tile_id, 0.5)
                        if pop >= 100 and 0.03 <= rate <= 0.70:
                            candidate_tiles.add(tile_id)
                    if candidate_tiles:
                        candidate_population = int(sum(tile_populations.get(t, 0) for t in candidate_tiles))
            
            # 使用候选地块的种群数据
            survivors = candidate_population
            resource_pressure = result.resource_pressure
            
            # 条件1：计算该物种的动态分化门槛
            base_threshold = self._calculate_speciation_threshold(species)
            min_population = int(base_threshold * 1.6)
            
            # 【改进】使用候选地块的种群，而非全局种群
            if candidate_population < min_population:
                continue
            
            # 条件2：演化潜力（放宽门槛 + 累积压力补偿）
            evo_potential = species.hidden_traits.get("evolution_potential", 0.5)
            speciation_pressure = species.morphology_stats.get("speciation_pressure", 0.0) or 0.0
            
            # 【新增】分化冷却期检查
            cooldown = _settings.speciation_cooldown_turns
            last_speciation_turn = species.morphology_stats.get("last_speciation_turn", -999)
            turns_since_speciation = turn_index - last_speciation_turn
            if turns_since_speciation < cooldown:
                logger.debug(
                    f"[分化冷却] {species.common_name} 仍在冷却期 "
                    f"({turns_since_speciation}/{cooldown}回合)"
                )
                continue
            
            # 放宽条件：演化潜力≥0.5，或累积分化压力≥0.3
            if evo_potential < 0.5 and speciation_pressure < 0.3:
                continue
            
            # 条件3：压力或资源饱和
            # 【改进】地理隔离本身就是强分化条件
            has_pressure = (
                (1.5 <= average_pressure <= 15.0) or 
                (resource_pressure > 0.8) or
                is_isolated  # 地理/生态隔离直接满足条件
            )
            
            # 自然辐射演化（繁荣物种分化）
            if not has_pressure:
                pop_factor = min(1.0, survivors / (min_population * 3))
                radiation_chance = 0.03 + (pop_factor * 0.05) + (speciation_pressure * 0.2)
                
                if survivors > min_population * 1.5 and random.random() < radiation_chance:
                    has_pressure = True
                    speciation_type = "辐射演化"
                    logger.info(f"[辐射演化] {species.common_name} 触发辐射演化 (候选种群:{survivors:,}, 概率:{radiation_chance:.1%})")
                else:
                    continue
            
            # 条件4：死亡率检查（已在候选地块筛选时过滤）
            # 对于使用预筛选数据的情况，跳过此检查
            if not candidate_data and (death_rate < 0.03 or death_rate > 0.70):
                continue
            
            # 条件5：随机性 (应用密度制约)
            # 【优化】世代时间影响分化概率，但采用更温和的曲线
            generation_time = species.morphology_stats.get("generation_time_days", 365)
            # 50万年 = 1.825亿天
            total_days = 500_000 * 365
            generations = total_days / max(1.0, generation_time)
            
            # 【调整】世代加成大幅降低，每多一个数量级只增加0.02（原0.08）
            # 这样微生物和大型动物的分化概率差距不会太大
            # 大型动物 (30年=1万代) -> log10(10000)=4 -> bonus=0.08
            # 微生物 (1天=1.8亿代) -> log10(1.8e8)=8.2 -> bonus=0.16
            generation_bonus = math.log10(max(10, generations)) * 0.02
            
            # 【调整】基础分化率从配置读取，默认0.15
            # 50万年虽长，但分化需要严格的生态隔离条件
            # 公式：(基础率 + 演化潜力加成) × 0.8 + 世代加成，再乘以密度阻尼
            base_rate = _settings.base_speciation_rate
            base_chance = ((base_rate + (evo_potential * 0.25)) * 0.8 + generation_bonus) * density_damping
            
            speciation_bonus = 0.0
            speciation_type = "生态隔离"
            
            # 检测地理隔离机会
            # 【核心改进】优先使用候选数据中的隔离信息
            if candidate_data and is_isolated:
                speciation_bonus += 0.25  # 地理隔离是分化的强触发条件
                speciation_type = "地理隔离"
                logger.info(
                    f"[地块级隔离检测] {species.common_name}: "
                    f"检测到{len(clusters)}个隔离区域, "
                    f"死亡率梯度={mortality_gradient:.1%}, "
                    f"候选地块={len(candidate_tiles)}"
                )
            elif not candidate_data:
                # 回退到旧的检测方法
                geo_isolation_data = self._detect_geographic_isolation(lineage_code)
                if geo_isolation_data["is_isolated"]:
                    speciation_bonus += 0.25
                    speciation_type = "地理隔离"
                    clusters = geo_isolation_data["clusters"]
                    logger.info(
                        f"[地理隔离检测] {species.common_name}: "
                        f"检测到{geo_isolation_data['num_clusters']}个隔离区域, "
                        f"死亡率差异={geo_isolation_data['mortality_gradient']:.1%}"
                    )
            
            if map_changes:
                for change in (map_changes or []):
                    change_type = change.get("change_type", "") if isinstance(change, dict) else getattr(change, "change_type", "")
                    if change_type in ["uplift", "volcanic", "glaciation"]:
                        speciation_bonus += 0.15
                        speciation_type = "地理隔离"
                        break
            
            # 检测极端环境特化
            if major_events:
                for event in (major_events or []):
                    severity = event.get("severity", "") if isinstance(event, dict) else getattr(event, "severity", "")
                    if severity in ["extreme", "catastrophic"]:
                        speciation_bonus += 0.10
                        speciation_type = "极端环境特化"
                        break
            
            # 检测协同演化
            if result.niche_overlap > 0.4:
                speciation_bonus += 0.08
                speciation_type = "协同演化"
            
            # 【修复】将累积分化压力加入概率计算
            # 每回合满足条件但未分化的物种，下回合分化概率+10%
            speciation_chance = base_chance + speciation_bonus + speciation_pressure
            
            if random.random() > speciation_chance:
                # 【调整】分化失败时累积压力，增速降低（0.05），上限降低（0.3）
                # 这样需要6回合才能达到上限，且上限较低不会强制分化
                new_pressure = min(0.3, speciation_pressure + 0.05)
                species.morphology_stats["speciation_pressure"] = new_pressure
                species_repository.upsert(species)
                logger.debug(
                    f"[分化累积] {species.common_name} 分化失败, "
                    f"累积压力: {speciation_pressure:.1%} → {new_pressure:.1%}"
                )
                continue
            
            # 分化成功，重置累积压力，并记录分化时间（用于冷却期计算）
            species.morphology_stats["speciation_pressure"] = 0.0
            species.morphology_stats["last_speciation_turn"] = turn_index
            
            # ========== 【基于地块的分化】==========
            # 使用候选地块上的种群进行分化，而非全局种群
            
            # 计算全局种群（用于后续更新父系）
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
            
            if _settings.enable_dynamic_speciation:
                sibling_count = sum(
                    1 for r in mortality_results 
                    if r.species.lineage_code.startswith(species.lineage_code[:2])
                    and r.species.lineage_code != species.lineage_code
                )
                
                # 【改进】基于地块级压力决定子代数量
                if candidate_data and clusters:
                    # 基础计算
                    calculated_offspring = self._calculate_dynamic_offspring_count(
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
                    num_offspring = self._calculate_dynamic_offspring_count(
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
                num_offspring = random.choice([2, 2, 3])
                logger.info(f"[分化] {species.common_name} 将分化出 {num_offspring} 个子种")
            
            # 种群分配（仅从候选地块的种群中分配）
            retention_ratio = random.uniform(0.60, 0.80)
            proposed_parent_from_candidates = max(50, int(speciation_pool * retention_ratio))
            max_parent_allowed = speciation_pool - num_offspring
            if max_parent_allowed <= 0:
                logger.warning(
                    f"[分化终止] {species.common_name} 候选种群不足以生成子种 "
                    f"(speciation_pool={speciation_pool}, offspring={num_offspring})"
                )
                continue
            
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
                    continue
                borrowed = min(needed, transferable)
                parent_from_candidates -= borrowed
                child_pool = speciation_pool - parent_from_candidates
            
            if child_pool < num_offspring:
                logger.warning(
                    f"[分化终止] {species.common_name} 子代可用个体仍不足 "
                    f"(child_pool={child_pool}, offspring={num_offspring})"
                )
                continue
            
            pop_splits = self._allocate_offspring_population(child_pool, num_offspring)
            
            # 生成编码
            new_codes = self._generate_multiple_lineage_codes(
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
            species_repository.upsert(species)
            
            logger.debug(
                f"[种群分配] {species.common_name}: "
                f"全局{global_population:,} → 父系{parent_remaining:,} + 子代{child_pool:,} "
                f"(非候选地块保留{non_candidate_population:,})"
            )
            
            # 【核心改进】基于候选数据为子代分配地块
            if candidate_data and clusters:
                # 使用候选数据中的隔离区域分配地块
                offspring_tiles = self._allocate_tiles_from_clusters(
                    clusters, candidate_tiles, num_offspring
                )
            else:
                # 回退到旧方法
                offspring_tiles = self._allocate_tiles_to_offspring(
                    species.lineage_code, num_offspring
                )
            
            # 为每个子种创建任务
            for idx, (new_code, population) in enumerate(zip(new_codes, pop_splits)):
                # 限制 history_highlights 长度，防止 Context Explosion
                # 只取最后2个事件，且截断长度
                safe_history = []
                if species.history_highlights:
                    for event in species.history_highlights[-2:]:
                        safe_history.append(event[:80] + "..." if len(event) > 80 else event)
                
                # 推断生物类群
                biological_domain = self._infer_biological_domain(species)
                
                # 【核心改进】获取该子代对应区域的压力信息
                assigned_tiles = offspring_tiles[idx] if idx < len(offspring_tiles) else set()
                
                # 获取该子代区域的压力数据
                if cluster_pressure_data and idx < len(cluster_pressure_data):
                    region_data = cluster_pressure_data[idx]
                    region_mortality = region_data["avg_mortality"]
                    region_pressure_level = region_data["pressure_level"]
                    region_population = region_data["population"]
                else:
                    # 计算分配地块的平均死亡率
                    if assigned_tiles and tile_mortality:
                        region_mortality = sum(
                            tile_mortality.get(t, 0.5) for t in assigned_tiles
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
                
                # 生成地块级环境摘要
                tile_context = self._generate_tile_context(
                    assigned_tiles, tile_populations, tile_mortality, 
                    mortality_gradient, is_isolated
                )
                
                # 【新增】规则引擎预处理：计算约束条件
                environment_pressure_dict = {
                    "temperature": 0,  # 从 pressure_summary 解析或使用默认值
                    "humidity": 0,
                    "salinity": 0,
                }
                # 尝试从 pressures 中提取实际压力值（如果可用）
                if hasattr(self, '_current_pressures') and self._current_pressures:
                    for p in self._current_pressures:
                        if hasattr(p, 'modifiers'):
                            environment_pressure_dict.update(p.modifiers)
                
                rule_constraints = self.rules.preprocess(
                    parent_species=species,
                    offspring_index=idx + 1,
                    total_offspring=num_offspring,
                    environment_pressure=environment_pressure_dict,
                    pressure_context=pressure_summary,
                )
                
                ai_payload = {
                    "parent_lineage": species.lineage_code,
                    "latin_name": species.latin_name,
                    "common_name": species.common_name,
                    "habitat_type": species.habitat_type,
                    "biological_domain": biological_domain,
                    "current_organs_summary": self._summarize_organs(species),
                    "environment_pressure": average_pressure,
                    "pressure_summary": pressure_summary,
                    "evolutionary_generations": int(generations),
                    "traits": species.description,
                    "history_highlights": "; ".join(safe_history) if safe_history else "无",
                    "survivors": population,
                    "speciation_type": speciation_type,
                    "map_changes_summary": self._summarize_map_changes(map_changes) if map_changes else "",
                    "major_events_summary": self._summarize_major_events(major_events) if major_events else "",
                    "parent_trophic_level": species.trophic_level,
                    "offspring_index": idx + 1,
                    "total_offspring": num_offspring,
                    "food_chain_status": self._food_chain_summary,
                    # 【新增】地块级分化信息
                    "tile_context": tile_context,
                    "region_mortality": region_mortality,
                    "region_pressure_level": region_pressure_level,
                    "mortality_gradient": mortality_gradient,
                    "num_isolation_regions": len(clusters) if clusters else 1,
                    "is_geographic_isolation": is_isolated and len(clusters) >= 2 if clusters else False,
                    # 【新增】规则引擎约束（供简化版Prompt使用）
                    "trait_budget_summary": rule_constraints["trait_budget_summary"],
                    "organ_constraints_summary": rule_constraints["organ_constraints_summary"],
                    "evolution_direction": rule_constraints["evolution_direction"],
                    "direction_description": rule_constraints["direction_description"],
                    "suggested_increases": ", ".join(rule_constraints["suggested_increases"]),
                    "suggested_decreases": ", ".join(rule_constraints["suggested_decreases"]),
                    "habitat_options": ", ".join(rule_constraints["habitat_options"]),
                    "trophic_range": rule_constraints["trophic_range"],
                    # 【新增】捕食关系信息
                    "diet_type": species.diet_type or "omnivore",
                    "prey_species_summary": self._summarize_prey_species(species),
                }
                
                entries.append({
                    "ctx": {
                        "parent": species,
                        "new_code": new_code,
                        "population": population,
                        "ai_payload_input": ai_payload,  # 原始输入，用于fallback
                        "speciation_type": speciation_type,
                        "assigned_tiles": assigned_tiles,  # 【新增】该子代的栖息地块
                    },
                    "payload": ai_payload,
                })
        
        if not entries and not self._deferred_requests:
            return []

        # 合并上回合遗留请求，并限制本回合最大任务数
        pending = self._deferred_requests + entries
        if len(pending) > self.max_deferred_requests:
            pending = pending[:self.max_deferred_requests]
        active_batch = pending[: self.max_speciation_per_turn]
        self._deferred_requests = pending[self.max_speciation_per_turn :]

        if not active_batch:
            logger.info("[分化] 没有可执行的AI任务，本回合跳过")
            return []

        logger.info(f"[分化] 开始批量处理 {len(active_batch)} 个分化任务 (剩余排队 {len(self._deferred_requests)})")
        
        # 【优化】使用批量请求 + 间隔并行，提高效率
        # 每批最多处理 10 个物种
        batch_size = 10
        
        # 分割成多个批次
        batches = []
        for batch_start in range(0, len(active_batch), batch_size):
            batch_entries = active_batch[batch_start:batch_start + batch_size]
            batches.append(batch_entries)
        
        logger.info(f"[分化] 共 {len(batches)} 个批次，开始间隔并行执行")
        
        async def process_batch(batch_entries: list) -> list:
            """处理单个批次"""
            batch_payload = self._build_batch_payload(
                batch_entries, average_pressure, pressure_summary, 
                map_changes, major_events
            )
            batch_results = await self._call_batch_ai(batch_payload, stream_callback)
            return self._parse_batch_results(batch_results, batch_entries)
        
        # 【优化】间隔并行执行批次，每3秒启动一个，最多同时2个
        coroutines = [process_batch(batch) for batch in batches]
        batch_results_list = await staggered_gather(
            coroutines,
            interval=3.0,  # 每3秒启动一个批次
            max_concurrent=2,  # 最多同时2个批次（每批10个物种）
            task_name="分化批次"
        )
        
        # 合并所有批次的结果
        results = []
        for batch_idx, batch_result in enumerate(batch_results_list):
            if isinstance(batch_result, Exception):
                logger.error(f"[分化] 批次 {batch_idx + 1} 失败: {batch_result}")
                results.extend([batch_result] * len(batches[batch_idx]))
            else:
                success_count = len([r for r in batch_result if not isinstance(r, Exception)])
                logger.info(f"[分化] 批次 {batch_idx + 1} 完成，成功解析 {success_count} 个结果")
                results.extend(batch_result)

        # 3. 结果处理与写入
        logger.info(f"[分化] 开始处理 {len(results)} 个AI结果")
        new_species_events: list[BranchingEvent] = []
        for res, entry in zip(results, active_batch):
            ctx = entry["ctx"]  # 从entry中提取ctx
            
            if isinstance(res, Exception):
                logger.error(f"[分化AI异常] {res}")
                self._queue_deferred_request(entry)
                continue

            ai_content = res
            if not isinstance(ai_content, dict):
                logger.warning(f"[分化警告] AI返回的content不是dict类型: {type(ai_content)}, 内容: {ai_content}")
                self._queue_deferred_request(entry)
                continue

            required_fields = ["latin_name", "common_name", "description"]
            if any(not ai_content.get(field) for field in required_fields):
                logger.warning(
                    "[分化警告] AI返回缺少必要字段: %s",
                    {field: ai_content.get(field) for field in required_fields},
                )
                self._queue_deferred_request(entry)
                continue

            logger.info(
                "[分化AI返回] latin_name: %s, common_name: %s, description长度: %s",
                ai_content.get("latin_name"),
                ai_content.get("common_name"),
                len(str(ai_content.get("description", ""))),
            )
            
            # 【新增】规则引擎后验证：验证并修正AI输出
            ai_content = self.rules.validate_and_fix(
                ai_content, 
                ctx["parent"],
                preprocess_result=None  # 如果需要可以传入预处理结果
            )

            new_species = self._create_species(
                parent=ctx["parent"],
                new_code=ctx["new_code"],
                survivors=ctx["population"],
                turn_index=turn_index,
                ai_payload=ai_content,
                average_pressure=average_pressure,
            )
            logger.info(f"[分化] 新物种 {new_species.common_name} created_turn={new_species.created_turn} (传入的turn_index={turn_index})")
            new_species = species_repository.upsert(new_species)
            logger.info(f"[分化] upsert后 {new_species.common_name} created_turn={new_species.created_turn}")
            
            # ⚠️ 关键修复：子代只继承分配给它的地块（基于地理隔离分化）
            # 如果没有分配地块，则继承全部（回退到旧行为）
            assigned_tiles = ctx.get("assigned_tiles", set())
            self._inherit_habitat_distribution(
                parent=ctx["parent"], 
                child=new_species, 
                turn_index=turn_index,
                assigned_tiles=assigned_tiles  # 【新增】只继承这些地块
            )
            
            self._update_genetic_distances(new_species, ctx["parent"], turn_index)
            
            if ai_content.get("genetic_discoveries") and new_species.genus_code:
                self.gene_library_service.record_discovery(
                    genus_code=new_species.genus_code,
                    discoveries=ai_content["genetic_discoveries"],
                    discoverer_code=new_species.lineage_code,
                    turn=turn_index
                )
            
            if new_species.genus_code:
                genus = genus_repository.get_by_code(new_species.genus_code)
                if genus:
                    self.gene_library_service.inherit_dormant_genes(ctx["parent"], new_species, genus)
                    species_repository.upsert(new_species)
            
            species_repository.log_event(
                LineageEvent(
                    lineage_code=ctx["new_code"],
                    event_type="speciation",
                    payload={"parent": ctx["parent"].lineage_code, "turn": turn_index},
                )
            )
            
            event_desc = ai_content.get("event_description") if ai_content else None
            if not event_desc:
                event_desc = f"{ctx['parent'].common_name}在压力{average_pressure:.1f}条件下分化出{ctx['new_code']}"
            
            reason_text = ai_content.get("reason") or ai_content.get("speciation_reason")
            if not reason_text:
                if ctx["speciation_type"] == "地理隔离":
                    reason_text = f"{ctx['parent'].common_name}因地形剧变导致种群地理隔离，各隔离群体独立演化产生生殖隔离"
                elif ctx["speciation_type"] == "极端环境特化":
                    reason_text = f"{ctx['parent'].common_name}在极端环境压力下，部分种群演化出特化适应能力，与原种群形成生态分离"
                elif ctx["speciation_type"] == "协同演化":
                    reason_text = f"{ctx['parent'].common_name}与竞争物种的生态位重叠导致竞争排斥，促使种群分化到不同资源梯度"
                else:
                    reason_text = f"{ctx['parent'].common_name}种群在演化压力下发生生态位分化"
            
            new_species_events.append(
                BranchingEvent(
                    parent_lineage=ctx["parent"].lineage_code,
                    new_lineage=ctx["new_code"],
                    description=event_desc,
                    timestamp=datetime.utcnow(),
                    reason=reason_text,
                )
            )
            
        return new_species_events

    def _build_batch_payload(
        self,
        entries: list[dict],
        average_pressure: float,
        pressure_summary: str,
        map_changes: list,
        major_events: list
    ) -> dict:
        """构建批量分化请求的 payload"""
        # 构建物种列表文本
        species_list_parts = []
        for idx, entry in enumerate(entries):
            payload = entry["payload"]
            ctx = entry["ctx"]
            
            # 获取生物类群和器官摘要（可能在单独调用时已添加）
            biological_domain = payload.get('biological_domain', 'protist')
            organs_summary = payload.get('current_organs_summary', '无已记录的器官系统')
            
            # 【关键】获取规则引擎约束信息
            organ_constraints = payload.get('organ_constraints_summary', '无器官约束')
            trait_budget = payload.get('trait_budget_summary', '增加上限: +3.0, 减少下限: -1.5')
            trophic_range = payload.get('trophic_range', '1.5-2.5')
            parent_trophic = payload.get('parent_trophic_level', 2.0)
            
            # 【新增】获取地块级信息
            tile_context = payload.get('tile_context', '未知区域')
            region_mortality = payload.get('region_mortality', 0.5)
            region_pressure_level = payload.get('region_pressure_level', '中压')
            mortality_gradient = payload.get('mortality_gradient', 0.0)
            num_isolation_regions = payload.get('num_isolation_regions', 1)
            is_geographic_isolation = payload.get('is_geographic_isolation', False)
            
            species_info = f"""
【物种 {idx + 1}】
- request_id: {idx}
- 父系编码: {payload.get('parent_lineage')}
- 学名: {payload.get('latin_name')}
- 俗名: {payload.get('common_name')}
- 新编码: {ctx['new_code']}
- 栖息地: {payload.get('habitat_type')}
- 生物类群: {biological_domain}
- 营养级: T{parent_trophic:.1f}（允许范围：{trophic_range}）
- 描述: {payload.get('traits', '')[:200]}
- 现有器官: {organs_summary}
- 幸存者: {payload.get('survivors', 0):,}
- 分化类型: {payload.get('speciation_type')}
- 子代编号: 第{payload.get('offspring_index', 1)}个（共{payload.get('total_offspring', 1)}个）
- 【属性预算】: {trait_budget}
- 【器官约束⚠️必须遵守current_stage】:
{organ_constraints}
- 【地块背景】: {tile_context[:150]}
- 区域死亡率: {region_mortality:.1%}（{region_pressure_level}）
- 死亡率梯度: {mortality_gradient:.1%}
- 隔离区域数: {num_isolation_regions}
- 地理隔离: {'是' if is_geographic_isolation else '否'}"""
            species_list_parts.append(species_info)
        
        species_list = "\n".join(species_list_parts)
        
        return {
            "average_pressure": average_pressure,
            "pressure_summary": pressure_summary,
            "map_changes_summary": self._summarize_map_changes(map_changes) if map_changes else "无显著地形变化",
            "major_events_summary": self._summarize_major_events(major_events) if major_events else "无重大事件",
            "species_list": species_list,
            "batch_size": len(entries),
        }
    
    async def _call_batch_ai(
        self, 
        payload: dict, 
        stream_callback: Callable[[str], Awaitable[None] | None] | None
    ) -> dict:
        """调用批量分化 AI 接口（非流式，更稳定）"""
        # 【优化】使用非流式调用，避免流式传输卡住
        # 【修复】添加硬超时保护，防止无限等待
        import asyncio
        try:
            response = await asyncio.wait_for(
                self.router.ainvoke("speciation_batch", payload),
                timeout=120  # 批量请求给更长的超时（120秒）
            )
        except asyncio.TimeoutError:
            logger.error("[分化批量] 请求超时（120秒），跳过本批次")
            return {}
        except Exception as e:
            logger.error(f"[分化批量] 请求异常: {e}")
            return {}
        return response.get("content") if isinstance(response, dict) else {}
    
    def _parse_batch_results(
        self, 
        batch_response: dict, 
        entries: list[dict]
    ) -> list[dict | Exception]:
        """解析批量响应，返回与 entries 对应的结果列表"""
        results = []
        
        if not isinstance(batch_response, dict):
            logger.warning(f"[分化批量] 响应不是字典类型: {type(batch_response)}")
            return [ValueError("Invalid batch response")] * len(entries)
        
        # 尝试从响应中提取 results 数组
        ai_results = batch_response.get("results", [])
        if not isinstance(ai_results, list):
            # 可能响应本身就是结果数组
            if isinstance(batch_response, list):
                ai_results = batch_response
            else:
                logger.warning(f"[分化批量] 响应中没有 results 数组")
                return [ValueError("No results in response")] * len(entries)
        
        # 建立 request_id 到结果的映射
        result_map = {}
        for item in ai_results:
            if isinstance(item, dict):
                req_id = item.get("request_id")
                if req_id is not None:
                    try:
                        result_map[int(req_id)] = item
                    except (ValueError, TypeError):
                        result_map[str(req_id)] = item
        
        # 按顺序匹配结果
        for idx, entry in enumerate(entries):
            # 尝试多种方式匹配
            matched_result = result_map.get(idx) or result_map.get(str(idx))
            
            if matched_result is None and idx < len(ai_results):
                # 如果没有 request_id，按顺序匹配
                matched_result = ai_results[idx] if isinstance(ai_results[idx], dict) else None
            
            if matched_result:
                # 验证必要字段
                required_fields = ["latin_name", "common_name", "description"]
                if all(matched_result.get(f) for f in required_fields):
                    results.append(matched_result)
                    logger.debug(f"[分化批量] 成功匹配结果 {idx}: {matched_result.get('common_name')}")
                else:
                    logger.warning(f"[分化批量] 结果 {idx} 缺少必要字段")
                    results.append(ValueError(f"Missing required fields for entry {idx}"))
            else:
                logger.warning(f"[分化批量] 无法匹配结果 {idx}")
                results.append(ValueError(f"No matching result for entry {idx}"))
        
        return results

    async def _call_ai_wrapper(self, payload: dict, stream_callback: Callable[[str], Awaitable[None] | None] | None) -> dict:
        """AI调用包装器（非流式，更稳定）"""
        # 【优化】使用非流式调用，避免流式传输卡住
        # 【修复】添加硬超时保护
        import asyncio
        try:
            response = await asyncio.wait_for(
                self.router.ainvoke("speciation", payload),
                timeout=90  # 硬超时90秒
            )
        except asyncio.TimeoutError:
            logger.error("[分化] 单个请求超时（90秒）")
            return {}
        except Exception as e:
            logger.error(f"[分化] 请求异常: {e}")
            return {}
        return response.get("content") if isinstance(response, dict) else {}

    # 保留 process 方法以兼容旧调用，直到全部迁移
    def process(self, *args, **kwargs):
        logger.warning("Deprecated: calling synchronous process(). Use process_async() instead.")
        # 临时实现：抛出错误提示修改，或者用 asyncio.run (不推荐在已有循环中)
        # 由于我们是一次性重构，可以假设不会再调用同步版，或者如果调用了说明漏改了
        raise NotImplementedError("Use process_async instead")

    def _queue_deferred_request(self, entry: dict[str, Any]) -> None:
        """将失败的AI请求放回队列，供下一回合重试。"""
        if len(self._deferred_requests) >= self.max_deferred_requests:
            return
        self._deferred_requests.append(entry)

    def _next_lineage_code(self, parent_code: str, existing_codes: set[str]) -> str:
        """生成单个子代编码（保留用于向后兼容）"""
        base = f"{parent_code}a"
        idx = 1
        new_code = f"{base}{idx}"
        while new_code in existing_codes:
            idx += 1
            new_code = f"{base}{idx}"
        return new_code
    
    def _generate_multiple_lineage_codes(
        self, parent_code: str, existing_codes: set[str], num_offspring: int
    ) -> list[str]:
        """生成多个子代编码，使用字母后缀 (A1→A1a, A1b, A1c)
        
        Args:
            parent_code: 父代编码 (如 "A1")
            existing_codes: 已存在的编码集合
            num_offspring: 需要生成的子代数量
            
        Returns:
            子代编码列表 (如 ["A1a", "A1b", "A1c"])
        """
        letters = "abcdefghijklmnopqrstuvwxyz"
        codes = []
        
        for i in range(num_offspring):
            letter = letters[i]
            new_code = f"{parent_code}{letter}"
            
            # 如果编码已存在，添加数字后缀
            if new_code in existing_codes:
                idx = 1
                while f"{new_code}{idx}" in existing_codes:
                    idx += 1
                new_code = f"{new_code}{idx}"
            
            codes.append(new_code)
        
        return codes
    
    def _allocate_offspring_population(self, total_population: int, num_offspring: int) -> list[int]:
        """随机划分子代种群，并确保每个子种至少拥有1个体。"""
        import random
        
        if num_offspring <= 0:
            return []
        if total_population <= 0:
            return [0] * num_offspring
        
        splits: list[int] = []
        remaining = total_population
        
        for idx in range(num_offspring):
            slots_left = num_offspring - idx
            if slots_left == 1:
                allocation = remaining
            else:
                min_allow = 1
                max_allow = remaining - (slots_left - 1)
                avg_share = remaining / slots_left
                lower_bound = max(min_allow, int(avg_share * 0.6))
                upper_bound = min(max_allow, max(lower_bound, int(avg_share * 1.4)))
                if upper_bound < lower_bound:
                    upper_bound = lower_bound
                allocation = random.randint(lower_bound, upper_bound)
            splits.append(allocation)
            remaining -= allocation
        
        return splits

    def _create_species(
        self,
        parent: Species,
        new_code: str,
        survivors: int,
        turn_index: int,
        ai_payload,
        average_pressure: float,
    ) -> Species:
        """创建新的分化物种。
        
        新物种从父代继承大部分属性，但有一些变化：
        - 基因多样性略微增加
        - 描述可能由 AI 修改以反映新特征
        
        种群分配逻辑：
        - 新物种从原物种中分离出20-40%的个体
        - 原物种保留60-80%
        - 总数略减（模拟分化过程的损耗）
        """
        # 种群分配逻辑已在上层处理，这里只负责对象创建
        
        morphology = dict(parent.morphology_stats)
        morphology["population"] = survivors
        
        hidden = dict(parent.hidden_traits)
        hidden["gene_diversity"] = min(1.0, hidden.get("gene_diversity", 0.5) + 0.05)
        
        # 继承父代的 abstract_traits，并应用 AI 建议的变化
        abstract = TraitConfig.merge_traits(parent.abstract_traits, {})
        trait_changes = ai_payload.get("trait_changes") or {}
        
        # 【关键修复】强制差异化和权衡机制
        # 1. 先应用AI建议的变化
        applied_changes = {}
        if isinstance(trait_changes, dict):
            for trait_name, change in trait_changes.items():
                try:
                    if isinstance(change, str):
                        change_value = float(change.replace("+", ""))
                    else:
                        change_value = float(change)
                    applied_changes[trait_name] = change_value
                except (ValueError, TypeError):
                    pass
        
        # 2. 强制权衡：如果只增不减，必须添加减少项
        applied_changes = self._enforce_trait_tradeoffs(abstract, applied_changes, new_code)
        
        # 3. 强制差异化：基于谱系编码添加随机偏移
        applied_changes = self._add_differentiation_noise(applied_changes, new_code)
        
        # 4. 应用最终变化
        for trait_name, change_value in applied_changes.items():
            current_value = abstract.get(trait_name, 5.0)
            new_val = current_value + change_value
            abstract[trait_name] = TraitConfig.clamp_trait(round(new_val, 2))
        
        # 应用形态学变化
        morphology_changes = ai_payload.get("morphology_changes") or {}
        if isinstance(morphology_changes, dict):
            for morph_name, change_factor in morphology_changes.items():
                if morph_name in morphology:
                    try:
                        # change_factor 是倍数，如 1.2 表示增大20%
                        factor = float(change_factor)
                        morphology[morph_name] = morphology[morph_name] * factor
                    except (ValueError, TypeError):
                        pass
        
        # 从AI响应中提取名称和描述
        latin = ai_payload.get("latin_name")
        common = ai_payload.get("common_name")
        description = ai_payload.get("description")
        
        # 如果AI未返回名称或描述，使用回退逻辑
        if not latin or not common or not description or len(str(description).strip()) < 80:
            logger.warning(f"[分化警告] AI返回不完整，使用回退命名: latin={latin}, common={common}")
            # 回退到规则命名
            if not latin:
                latin = self._fallback_latin_name(parent.latin_name, ai_payload)
            if not common:
                common = self._fallback_common_name(parent.common_name, ai_payload)
            if not description or len(str(description).strip()) < 80:
                key_innovations = ai_payload.get("key_innovations", [])
                innovations_text = "，演化出" + "、".join(key_innovations) if key_innovations else ""
                description = f"{parent.description}在环境压力{average_pressure:.1f}下发生适应性变化{innovations_text}。"
                if len(description) < 120:
                    description = parent.description
        
        # 【防重名】检查并处理重名情况
        latin = self._ensure_unique_latin_name(latin, new_code)
        common = self._ensure_unique_common_name(common, new_code)
        
        # 计算新物种的营养级
        # 优先级：AI判定 > 继承父代 > 关键词估算
        ai_trophic = ai_payload.get("trophic_level")
        if ai_trophic is not None:
            try:
                new_trophic = float(ai_trophic)
                # 范围钳制 (1.0-6.0)
                new_trophic = max(1.0, min(6.0, new_trophic))
                logger.info(f"[分化] 使用AI判定的营养级: T{new_trophic:.1f}")
            except (ValueError, TypeError):
                logger.warning(f"[分化] AI返回的营养级格式错误: {ai_trophic}")
                new_trophic = None
        else:
            logger.warning(f"[分化] AI未返回营养级")
            new_trophic = None

        if new_trophic is None:
            # 回退方案1：继承父代营养级（最合理的默认值）
            # 大多数分化事件不会改变营养级（生态位保守性）
            new_trophic = parent.trophic_level
            logger.info(f"[分化] 继承父代营养级: T{new_trophic:.1f}")
            
            # 如果父代营养级也无效，才使用关键词估算（应急回退）
            if new_trophic is None or new_trophic <= 0:
                all_species = species_repository.list_species()
                new_trophic = self.trophic_calculator.calculate_trophic_level(
                    Species(
                        lineage_code=new_code,
                        latin_name=latin,
                        common_name=common,
                        description=description,
                        morphology_stats=morphology,
                        abstract_traits=abstract,
                        hidden_traits=hidden,
                        ecological_vector=None,
                        trophic_level=2.0  # 默认为初级消费者
                    ),
                    all_species
                )
                logger.warning(f"[分化] 使用关键词估算营养级: T{new_trophic:.1f}")
        
        # 【克莱伯定律修正】基于体重和营养级重算代谢率
        # SMR ∝ Mass^-0.25
        mass_g = morphology.get("body_weight_g", 1.0)
        morphology["metabolic_rate"] = self.trophic_calculator.estimate_kleiber_metabolic_rate(
            mass_g, new_trophic
        )
        
        # 验证属性变化是否符合营养级规则
        validation_ok, validation_msg = self._validate_trait_changes(
            parent.abstract_traits, abstract, new_trophic
        )
        if not validation_ok:
            logger.warning(f"[分化警告] 属性验证失败: {validation_msg}，将自动钳制数值")
            # 智能钳制：根据营养级限制缩放属性，而不是直接回退
            abstract = self._clamp_traits_to_limit(abstract, parent.abstract_traits, new_trophic)

        
        # 继承并更新器官系统
        organs = self._inherit_and_update_organs(
            parent=parent,
            ai_payload=ai_payload,
            turn_index=turn_index
        )
        
        # 更新能力标签
        capabilities = self._update_capabilities(parent, organs)
        
        # 继承或更新栖息地类型
        new_habitat_type = ai_payload.get("habitat_type", parent.habitat_type)
        # 确保栖息地类型有效
        valid_habitats = ["marine", "deep_sea", "coastal", "freshwater", "amphibious", "terrestrial", "aerial"]
        if new_habitat_type not in valid_habitats:
            new_habitat_type = parent.habitat_type
        
        # ========== 继承或更新捕食关系 ==========
        # 优先使用AI返回的捕食关系，否则继承父代
        new_diet_type = ai_payload.get("diet_type", parent.diet_type)
        # 确保食性类型有效
        valid_diet_types = ["autotroph", "herbivore", "carnivore", "omnivore", "detritivore"]
        if new_diet_type not in valid_diet_types:
            new_diet_type = parent.diet_type
        
        # 继承或更新猎物列表
        ai_prey_species = ai_payload.get("prey_species")
        if ai_prey_species is not None and isinstance(ai_prey_species, list):
            new_prey_species = ai_prey_species
            logger.info(f"[分化] {new_code} 使用AI指定的猎物: {new_prey_species}")
        else:
            # 继承父代猎物
            new_prey_species = list(parent.prey_species) if parent.prey_species else []
            logger.info(f"[分化] {new_code} 继承父代猎物: {new_prey_species}")
        
        # 继承或更新猎物偏好
        ai_prey_preferences = ai_payload.get("prey_preferences")
        if ai_prey_preferences is not None and isinstance(ai_prey_preferences, dict):
            new_prey_preferences = ai_prey_preferences
        else:
            # 继承父代偏好
            new_prey_preferences = dict(parent.prey_preferences) if parent.prey_preferences else {}
        
        # 验证捕食关系与营养级的一致性
        if new_trophic < 2.0 and new_prey_species:
            # 生产者不应该有猎物
            logger.warning(f"[分化警告] {new_code} 营养级<2.0但有猎物，清空猎物列表")
            new_prey_species = []
            new_prey_preferences = {}
            new_diet_type = "autotroph"
        
        # 不再继承 ecological_vector，让系统基于 description 自动计算 embedding
        return Species(
            lineage_code=new_code,
            latin_name=latin,
            common_name=common,
            description=description,
            habitat_type=new_habitat_type,
            morphology_stats=morphology,
            abstract_traits=abstract,
            hidden_traits=hidden,
            ecological_vector=None,  # 不继承，让系统自动计算
            parent_code=parent.lineage_code,
            status="alive",
            created_turn=turn_index,
            trophic_level=new_trophic,
            organs=organs,
            capabilities=capabilities,
            genus_code=parent.genus_code,
            taxonomic_rank="subspecies",
            # 捕食关系
            diet_type=new_diet_type,
            prey_species=new_prey_species,
            prey_preferences=new_prey_preferences,
        )
    
    def _inherit_habitat_distribution(
        self, 
        parent: Species, 
        child: Species, 
        turn_index: int,
        assigned_tiles: set[int] | None = None
    ) -> None:
        """子代继承父代的栖息地分布
        
        【核心改进】现在支持基于地块的分化：
        - 如果指定了 assigned_tiles，子代只继承这些地块
        - 如果未指定，则继承父代全部地块（旧行为）
        
        Args:
            parent: 父代物种
            child: 子代物种
            turn_index: 当前回合
            assigned_tiles: 分配给该子代的地块集合（可选）
        """
        from ...repositories.environment_repository import environment_repository
        from ...models.environment import HabitatPopulation
        
        # 获取父代的栖息地分布
        all_habitats = environment_repository.latest_habitats()
        parent_habitats = [h for h in all_habitats if h.species_id == parent.id]
        
        if not parent_habitats:
            logger.warning(f"[栖息地继承] 父代 {parent.common_name} 没有栖息地数据，立即为子代计算初始栖息地")
            # 【风险修复】立即计算子代的初始栖息地，而不是等待下次快照
            self._calculate_initial_habitat_for_child(child, parent, turn_index, assigned_tiles)
            return
            
        if child.id is None:
            logger.error(f"[栖息地继承] 严重错误：子代 {child.common_name} 没有 ID，无法继承栖息地")
            return
        
        # 【核心改进】根据 assigned_tiles 过滤要继承的地块
        child_habitats = []
        inherited_count = 0
        
        for parent_hab in parent_habitats:
            # 如果指定了分配地块，只继承在分配范围内的地块
            if assigned_tiles and parent_hab.tile_id not in assigned_tiles:
                continue
            
            child_habitats.append(
                HabitatPopulation(
                    tile_id=parent_hab.tile_id,
                    species_id=child.id,
                    population=0,  # 初始为0，会在回合结束时根据species.population更新
                    suitability=parent_hab.suitability,  # 继承父代的适宜度
                    turn_index=turn_index,
                )
            )
            inherited_count += 1
        
        # 如果分配了地块但一个都没继承到（可能父代不在这些地块），使用分配的地块
        if assigned_tiles and not child_habitats:
            logger.warning(
                f"[栖息地继承] {child.common_name} 分配的地块与父代不重叠，"
                f"将使用分配的地块: {assigned_tiles}"
            )
            for tile_id in assigned_tiles:
                child_habitats.append(
                    HabitatPopulation(
                        tile_id=tile_id,
                        species_id=child.id,
                        population=0,
                        suitability=0.5,  # 默认适宜度
                        turn_index=turn_index,
                    )
                )
        
        if child_habitats:
            environment_repository.write_habitats(child_habitats)
            if assigned_tiles:
                logger.info(
                    f"[基于地块分化] {child.common_name} 继承了 {len(child_habitats)}/{len(parent_habitats)} 个地块 "
                    f"(地理隔离分化)"
                )
            else:
                logger.info(f"[栖息地继承] {child.common_name} 继承了 {len(child_habitats)} 个栖息地")
    
    def _calculate_initial_habitat_for_child(
        self, 
        child: Species, 
        parent: Species, 
        turn_index: int,
        assigned_tiles: set[int] | None = None
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
        """
        from ...repositories.environment_repository import environment_repository
        from ...models.environment import HabitatPopulation
        
        logger.info(f"[栖息地计算] 为 {child.common_name} 计算初始栖息地")
        
        # 1. 获取所有地块
        all_tiles = environment_repository.list_tiles()
        if not all_tiles:
            logger.error(f"[栖息地计算] 没有可用地块，无法为 {child.common_name} 计算栖息地")
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
        habitat_type = getattr(child, 'habitat_type', 'terrestrial')
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
            elif habitat_type == "freshwater" and getattr(tile, 'is_lake', False):
                is_suitable = True
            elif habitat_type == "terrestrial" and "海" not in biome:
                is_suitable = True
            elif habitat_type == "amphibious" and ("海岸" in biome or ("平原" in biome and tile.humidity > 0.4)):
                is_suitable = True
            elif habitat_type == "aerial" and "海" not in biome and "山" not in biome:
                is_suitable = True
            
            if is_suitable:
                suitable_tiles.append(tile)
        
        if not suitable_tiles:
            logger.warning(f"[栖息地计算] {child.common_name} ({habitat_type}) 没有合适的地块")
            # 回退：使用分配的地块或前10个地块
            suitable_tiles = all_tiles[:10] if all_tiles else []
        
        # 3. 计算适宜度
        tile_suitability = []
        for tile in suitable_tiles:
            suitability = self._calculate_suitability_for_species(child, tile)
            if suitability > 0.1:  # 只保留适宜度>0.1的地块
                tile_suitability.append((tile, suitability))
        
        if not tile_suitability:
            logger.warning(f"[栖息地计算] {child.common_name} 没有适宜度>0.1的地块，使用前10个")
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
                logger.info(f"[栖息地计算] {child.common_name} 计算得到 {len(child_habitats)} 个栖息地")
    
    def _calculate_suitability_for_species(self, species: Species, tile) -> float:
        """计算物种对地块的适宜度（简化版）"""
        # 温度适应性
        temp_pref = species.abstract_traits.get("耐热性", 5)
        cold_pref = species.abstract_traits.get("耐寒性", 5)
        
        if tile.temperature > 20:
            temp_score = temp_pref / 10.0
        elif tile.temperature < 5:
            temp_score = cold_pref / 10.0
        else:
            temp_score = 0.8
        
        # 湿度适应性
        drought_pref = species.abstract_traits.get("耐旱性", 5)
        humidity_score = 1.0 - abs(tile.humidity - (1.0 - drought_pref / 10.0))
        
        # 资源可用性
        resource_score = min(1.0, tile.resources / 500.0)
        
        # 综合评分
        return max(0.0, temp_score * 0.4 + humidity_score * 0.3 + resource_score * 0.3)
    
    def _detect_geographic_isolation(self, lineage_code: str) -> dict:
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
        tile_rates = self._tile_mortality_cache.get(lineage_code, {})
        
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
        clusters = self._find_connected_clusters(set(tile_rates.keys()))
        
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
    
    def _find_connected_clusters(self, tile_ids: set[int]) -> list[set[int]]:
        """使用并查集找出连通的地块群
        
        Args:
            tile_ids: 物种占据的地块ID集合
            
        Returns:
            连通地块群列表
        """
        if not tile_ids:
            return []
        
        if not self._tile_adjacency:
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
            neighbors = self._tile_adjacency.get(tile_id, set())
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
    
    def _allocate_tiles_from_clusters(
        self,
        clusters: list[set[int]],
        candidate_tiles: set[int],
        num_offspring: int
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
    
    def _allocate_tiles_to_offspring(
        self, 
        parent_lineage_code: str,
        num_offspring: int
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
        
        geo_data = self._detect_geographic_isolation(parent_lineage_code)
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
            largest_idx = max(range(len(allocations)), key=lambda i: len(allocations[i]))
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
    
    def _calculate_speciation_threshold(self, species: Species) -> int:
        """计算物种的分化门槛 - 基于多维度生态学指标。
        
        综合考虑：
        1. 体型（体长、体重） - 主要因素
        2. 繁殖策略（世代时间、繁殖速度） - r/K策略
        3. 代谢率 - 能量周转速度
        4. 营养级 - 从描述推断
        
        Returns:
            最小种群数量（需要达到此数量才能分化）
        """
        import math
        
        # 1. 基于体型的基础门槛
        body_length_cm = species.morphology_stats.get("body_length_cm", 1.0)
        body_weight_g = species.morphology_stats.get("body_weight_g", 1.0)
        
        # 使用体长作为主要指标（更直观）
        if body_length_cm < 0.01:  # <0.1mm - 细菌级别
            base_threshold = 2_000_000  # 200万
        elif body_length_cm < 0.1:  # 0.1mm-1mm - 原生动物
            base_threshold = 1_000_000  # 100万
        elif body_length_cm < 1.0:  # 1mm-1cm - 小型无脊椎动物
            base_threshold = 100_000   # 10万
        elif body_length_cm < 10.0:  # 1cm-10cm - 昆虫、小鱼
            base_threshold = 10_000    # 1万
        elif body_length_cm < 50.0:  # 10cm-50cm - 中型脊椎动物
            base_threshold = 2_000     # 2千
        elif body_length_cm < 200.0:  # 50cm-2m - 大型哺乳动物
            base_threshold = 500       # 500
        else:  # >2m - 超大型动物（大象、鲸鱼）
            base_threshold = 100       # 100
        
        # 体重修正（提供额外验证）
        # 1g以下：微小生物
        # 1-1000g：小型生物
        # 1kg-100kg：中型生物
        # >100kg：大型生物
        if body_weight_g < 1.0:
            weight_factor = 1.2  # 微小生物需要更大种群
        elif body_weight_g < 1000:
            weight_factor = 1.0
        elif body_weight_g < 100_000:
            weight_factor = 0.8
        else:
            weight_factor = 0.6  # 大型生物门槛更低
        
        # 2. 繁殖策略修正
        generation_time = species.morphology_stats.get("generation_time_days", 365)
        reproduction_speed = species.abstract_traits.get("繁殖速度", 5)
        
        # r策略物种（快繁殖，短世代）需要更大种群
        # K策略物种（慢繁殖，长世代）较小种群即可
        if generation_time < 30 and reproduction_speed >= 7:
            # r策略：微生物、昆虫
            repro_factor = 1.5
        elif generation_time < 365 and reproduction_speed >= 5:
            # 中等：小型哺乳动物、鸟类
            repro_factor = 1.0
        else:
            # K策略：大型哺乳动物
            repro_factor = 0.7
        
        # 3. 代谢率修正
        metabolic_rate = species.morphology_stats.get("metabolic_rate", 3.0)
        # 高代谢率（>5.0）= 需要更多个体维持种群
        # 低代谢率（<2.0）= 少量个体即可
        if metabolic_rate > 5.0:
            metabolic_factor = 1.3
        elif metabolic_rate > 3.0:
            metabolic_factor = 1.0
        else:
            metabolic_factor = 0.8
        
        # 4. 营养级修正（从描述推断）
        desc_lower = species.description.lower()
        if any(kw in desc_lower for kw in ["顶级捕食", "apex", "大型捕食者", "食物链顶端"]):
            trophic_factor = 0.5  # 顶级捕食者种群小
        elif any(kw in desc_lower for kw in ["捕食", "carnivore", "肉食", "掠食"]):
            trophic_factor = 0.7  # 捕食者
        elif any(kw in desc_lower for kw in ["杂食", "omnivore"]):
            trophic_factor = 0.9
        elif any(kw in desc_lower for kw in ["草食", "herbivore", "食草"]):
            trophic_factor = 1.0  # 草食动物种群大
        elif any(kw in desc_lower for kw in ["生产者", "光合", "植物", "藻类", "producer", "photosyn"]):
            trophic_factor = 1.2  # 初级生产者种群最大
        else:
            trophic_factor = 1.0
        
        # 5. 综合计算
        threshold = int(
            base_threshold 
            * weight_factor 
            * repro_factor 
            * metabolic_factor 
            * trophic_factor
        )
        
        # 确保在合理范围内
        # 最小：50（濒危大型动物也需要一定基数）
        # 最大：500万（即使是细菌也不需要无限大）
        threshold = max(50, min(threshold, 5_000_000))
        
        return threshold
    
    def _summarize_food_chain_status(self, trophic_interactions: dict[str, float] | None) -> str:
        """总结食物链状态，供AI做演化决策参考
        
        这是一个关键函数！它告诉AI当前生态系统的营养级状态：
        - 哪些营养级的食物充足/稀缺
        - 是否有级联崩溃的风险
        
        Args:
            trophic_interactions: 营养级互动数据，包含 t2_scarcity, t3_scarcity 等
            
        Returns:
            人类可读的食物链状态描述
        """
        if not trophic_interactions:
            return "食物链状态未知"
        
        status_parts = []
        
        # 检查各级的食物稀缺度
        # scarcity: 0 = 充足, 1 = 紧张, 2 = 严重短缺
        t2_scarcity = trophic_interactions.get("t2_scarcity", 0.0)
        t3_scarcity = trophic_interactions.get("t3_scarcity", 0.0)
        t4_scarcity = trophic_interactions.get("t4_scarcity", 0.0)
        t5_scarcity = trophic_interactions.get("t5_scarcity", 0.0)
        
        def scarcity_level(value: float) -> str:
            if value < 0.3:
                return "充足"
            elif value < 1.0:
                return "紧张"
            elif value < 1.5:
                return "短缺"
            else:
                return "严重短缺"
        
        # T1 是生产者，不依赖其他营养级
        # T2 依赖 T1（生产者）
        if t2_scarcity > 0.5:
            status_parts.append(f"生产者(T1){'紧张' if t2_scarcity < 1.0 else '短缺'}，初级消费者(T2)面临食物压力")
        
        # T3 依赖 T2
        if t3_scarcity > 0.5:
            status_parts.append(f"初级消费者(T2){'紧张' if t3_scarcity < 1.0 else '短缺'}，次级消费者(T3)面临食物压力")
        
        # T4 依赖 T3
        if t4_scarcity > 0.5:
            status_parts.append(f"次级消费者(T3){'紧张' if t4_scarcity < 1.0 else '短缺'}，三级消费者(T4)面临食物压力")
        
        # T5 依赖 T4
        if t5_scarcity > 0.5:
            status_parts.append(f"三级消费者(T4){'紧张' if t5_scarcity < 1.0 else '短缺'}，顶级捕食者(T5)面临食物压力")
        
        # 检测级联崩溃风险
        if t2_scarcity > 1.5 and t3_scarcity > 1.0:
            status_parts.append("⚠️ 食物链底层崩溃，可能引发级联灭绝")
        
        if not status_parts:
            return "食物链稳定，各营养级食物充足"
        
        return "；".join(status_parts)
    
    def _summarize_map_changes(self, map_changes: list) -> str:
        """总结地图变化用于分化原因描述。"""
        if not map_changes:
            return ""
        
        change_types = []
        for change in map_changes[:3]:  # 最多取3个
            if isinstance(change, dict):
                ctype = change.get("change_type", "")
            else:
                ctype = getattr(change, "change_type", "")
            
            if ctype == "uplift":
                change_types.append("地壳抬升")
            elif ctype == "volcanic":
                change_types.append("火山活动")
            elif ctype == "glaciation":
                change_types.append("冰川推进")
            elif ctype == "subsidence":
                change_types.append("地壳下沉")
        
        return "、".join(change_types) if change_types else "地形变化"
    
    def _summarize_major_events(self, major_events: list) -> str:
        """总结重大事件用于分化原因描述。"""
        if not major_events:
            return ""
        
        for event in major_events[:1]:  # 取第一个
            if isinstance(event, dict):
                desc = event.get("description", "")
                severity = event.get("severity", "")
            else:
                desc = getattr(event, "description", "")
                severity = getattr(event, "severity", "")
            
            if desc:
                return f"{severity}级{desc}"
        
        return "重大环境事件"
    
    def _generate_tile_context(
        self,
        assigned_tiles: set[int],
        tile_populations: dict[int, float],
        tile_mortality: dict[int, float],
        mortality_gradient: float,
        is_isolated: bool,
    ) -> str:
        """生成地块级环境上下文描述
        
        用于传递给 AI，帮助其理解分化发生的地理背景
        
        Args:
            assigned_tiles: 该子代分配的地块
            tile_populations: 各地块种群分布
            tile_mortality: 各地块死亡率
            mortality_gradient: 死亡率梯度
            is_isolated: 是否地理隔离
            
        Returns:
            地块环境描述文本
        """
        if not assigned_tiles:
            return "未知区域（全局分化）"
        
        num_tiles = len(assigned_tiles)
        
        # 计算区域统计
        region_pop = sum(tile_populations.get(t, 0) for t in assigned_tiles)
        region_rates = [tile_mortality.get(t, 0.5) for t in assigned_tiles if t in tile_mortality]
        
        if region_rates:
            avg_rate = sum(region_rates) / len(region_rates)
            max_rate = max(region_rates)
            min_rate = min(region_rates)
        else:
            avg_rate, max_rate, min_rate = 0.5, 0.5, 0.5
        
        # 生成描述
        parts = []
        
        # 区域规模
        parts.append(f"分化发生于{num_tiles}个地块区域")
        
        # 种群信息
        parts.append(f"区域种群{int(region_pop):,}")
        
        # 环境压力描述
        if avg_rate > 0.5:
            pressure_desc = "高环境压力"
        elif avg_rate > 0.3:
            pressure_desc = "中等环境压力"
        else:
            pressure_desc = "低环境压力"
        parts.append(f"{pressure_desc}（平均死亡率{avg_rate:.1%}）")
        
        # 隔离状态
        if is_isolated:
            parts.append("与其他种群存在地理隔离")
        
        # 压力梯度
        if mortality_gradient > 0.3:
            parts.append(f"区域间存在显著的环境梯度（压力差异{mortality_gradient:.1%}）")
        elif mortality_gradient > 0.15:
            parts.append(f"区域间存在一定的环境差异")
        
        # 局部异质性
        if len(region_rates) >= 2:
            local_gradient = max_rate - min_rate
            if local_gradient > 0.2:
                parts.append("区域内部环境条件不均匀")
        
        return "。".join(parts)
    
    def _fallback_latin_name(self, parent_latin: str, ai_content: dict) -> str:
        """回退拉丁命名逻辑"""
        import hashlib
        # 提取父系属名
        genus = parent_latin.split()[0] if ' ' in parent_latin else "Species"
        # 基于key_innovations生成种加词
        innovations = ai_content.get("key_innovations", [])
        if innovations:
            # 从第一个创新中提取关键词
            innovation = innovations[0].lower()
            if "鞭毛" in innovation or "游" in innovation:
                epithet = "natans"
            elif "深" in innovation or "底" in innovation:
                epithet = "profundus"
            elif "快" in innovation or "速" in innovation:
                epithet = "velox"
            elif "慢" in innovation or "缓" in innovation:
                epithet = "lentus"
            elif "大" in innovation or "巨" in innovation:
                epithet = "magnus"
            elif "小" in innovation or "微" in innovation:
                epithet = "minutus"
            elif "透明" in innovation:
                epithet = "hyalinus"
            elif "耐盐" in innovation or "盐" in innovation:
                epithet = "salinus"
            elif "耐热" in innovation or "热" in innovation:
                epithet = "thermophilus"
            elif "耐寒" in innovation or "冷" in innovation:
                epithet = "cryophilus"
            else:
                # 使用hash确保唯一性
                hash_suffix = hashlib.md5(str(innovations).encode()).hexdigest()[:6]
                epithet = f"sp{hash_suffix}"
        else:
            # 完全随机
            hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:6]
            epithet = f"sp{hash_suffix}"
        return f"{genus} {epithet}"
    
    def _fallback_common_name(self, parent_common: str, ai_content: dict) -> str:
        """回退中文命名逻辑"""
        import hashlib
        # 提取类群名（通常是最后2-3个字）
        if len(parent_common) >= 2:
            taxon = parent_common[-2:] if parent_common[-1] in "虫藻菌类贝鱼" else parent_common[-3:]
        else:
            taxon = "生物"
        
        # 从key_innovations提取特征词
        innovations = ai_content.get("key_innovations", [])
        if innovations:
            innovation = innovations[0]
            # 提取前2个字作为特征词
            if "鞭毛" in innovation:
                if "多" in innovation or "4" in innovation or "增" in innovation:
                    feature = "多鞭"
                elif "长" in innovation:
                    feature = "长鞭"
                else:
                    feature = "异鞭"
            elif "游" in innovation or "速" in innovation:
                if "快" in innovation or "提升" in innovation:
                    feature = "快游"
                else:
                    feature = "慢游"
            elif "深" in innovation or "底" in innovation:
                feature = "深水"
            elif "浅" in innovation or "表" in innovation:
                feature = "浅水"
            elif "耐盐" in innovation or "盐" in innovation:
                feature = "耐盐"
            elif "透明" in innovation:
                feature = "透明"
            elif "大" in innovation or "巨" in innovation:
                feature = "巨型"
            elif "小" in innovation or "微" in innovation:
                feature = "微型"
            elif "滤食" in innovation:
                feature = "滤食"
            elif "夜" in innovation:
                feature = "夜行"
            else:
                # 提取前两个字
                words = [c for c in innovation if '\u4e00' <= c <= '\u9fff']
                feature = ''.join(words[:2]) if len(words) >= 2 else "变异"
        else:
            # 使用hash生成唯一标识
            hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:2]
            feature = f"型{hash_suffix}"
        
        return f"{feature}{taxon}"
    
    def _ensure_unique_latin_name(self, latin_name: str, lineage_code: str) -> str:
        """确保拉丁学名唯一，使用罗马数字后缀处理重名
        
        策略：
        1. 如果名称唯一，直接返回
        2. 如果重名，尝试添加罗马数字 II, III, IV, V
        3. 如果罗马数字超过V，使用谱系编码作为亚种名
        
        Args:
            latin_name: AI生成的拉丁学名
            lineage_code: 谱系编码
            
        Returns:
            唯一的拉丁学名
        """
        all_species = species_repository.list_species()
        existing_names = {sp.latin_name.lower() for sp in all_species}
        
        # 如果名称唯一，直接返回
        if latin_name.lower() not in existing_names:
            return latin_name
        
        logger.info(f"[防重名] 检测到拉丁学名重复: {latin_name}")
        
        # 尝试添加罗马数字后缀 II-V
        roman_numerals = ["II", "III", "IV", "V"]
        for numeral in roman_numerals:
            variant = f"{latin_name} {numeral}"
            if variant.lower() not in existing_names:
                logger.info(f"[防重名] 使用罗马数字: {variant}")
                return variant
        
        # 如果罗马数字超过V，使用谱系编码作为亚种标识
        logger.info(f"[防重名] 罗马数字已超过V，使用谱系编码标识")
        parts = latin_name.split()
        if len(parts) >= 2:
            genus, species_name = parts[0], parts[1]
            subspecies_suffix = lineage_code.lower().replace("_", "")
            
            # 使用 subsp. 格式
            variant = f"{genus} {species_name} subsp. {subspecies_suffix}"
            if variant.lower() not in existing_names:
                logger.info(f"[防重名] 使用亚种标识: {variant}")
                return variant
        
        # 最终兜底：直接加谱系编码
        return f"{latin_name} [{lineage_code}]"
    
    def _ensure_unique_common_name(self, common_name: str, lineage_code: str) -> str:
        """确保中文俗名唯一，使用罗马数字后缀处理重名
        
        策略：
        1. 如果名称唯一，直接返回
        2. 如果重名，尝试添加罗马数字 II, III, IV, V
        3. 如果罗马数字超过V，使用世代标记
        
        Args:
            common_name: AI生成的中文俗名
            lineage_code: 谱系编码
            
        Returns:
            唯一的中文俗名
        """
        all_species = species_repository.list_species()
        existing_names = {sp.common_name for sp in all_species}
        
        # 如果名称唯一，直接返回
        if common_name not in existing_names:
            return common_name
        
        logger.info(f"[防重名] 检测到中文俗名重复: {common_name}")
        
        # 尝试添加罗马数字后缀 II-V
        roman_numerals = ["II", "III", "IV", "V"]
        for numeral in roman_numerals:
            variant = f"{common_name}{numeral}"
            if variant not in existing_names:
                logger.info(f"[防重名] 添加罗马数字: {variant}")
                return variant
        
        # 如果罗马数字超过V，使用世代标记
        logger.info(f"[防重名] 罗马数字已超过V，使用世代标记")
        for i in range(6, 50):
            variant = f"{common_name}-{i}代"
            if variant not in existing_names:
                logger.info(f"[防重名] 使用世代标记: {variant}")
                return variant
        
        # 最终兜底：添加谱系编码
        return f"{common_name}({lineage_code})"
    
    def _validate_trait_changes(
        self, old_traits: dict, new_traits: dict, trophic_level: float
    ) -> tuple[bool, str]:
        """验证属性变化是否符合营养级规则
        
        Returns:
            (验证是否通过, 错误信息)
        """
        # 获取营养级对应的属性上限
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        # 1. 检查总和变化
        old_sum = sum(old_traits.values())
        new_sum = sum(new_traits.values())
        sum_diff = new_sum - old_sum
        
        if sum_diff > 8:
            return False, f"属性总和增加{sum_diff}，超过上限8"
        
        # 2. 检查总和是否超过营养级上限
        if new_sum > limits["total"]:
            return False, f"属性总和{new_sum}超过营养级{trophic_level:.1f}的上限{limits['total']}"
        
        # 3. 检查单个属性是否超过特化上限
        above_specialized = [
            (k, v) for k, v in new_traits.items() if v > limits["specialized"]
        ]
        if above_specialized:
            return False, f"属性{above_specialized[0][0]}={above_specialized[0][1]}超过特化上限{limits['specialized']}"
        
        # 4. 检查超过基础上限的属性数量
        above_base_count = sum(1 for v in new_traits.values() if v > limits["base"])
        if above_base_count > 2:
            return False, f"{above_base_count}个属性超过基础上限{limits['base']}，最多允许2个"
        
        # 5. 检查权衡（有增必有减，除非是营养级提升）
        increases = sum(1 for k, v in new_traits.items() if v > old_traits.get(k, 0))
        decreases = sum(1 for k, v in new_traits.items() if v < old_traits.get(k, 0))
        
        if increases > 0 and decreases == 0 and sum_diff > 3:
            return False, "有属性提升但无权衡代价"
        
        return True, "验证通过"
    
    def _inherit_and_update_organs(
        self, parent: Species, ai_payload: dict, turn_index: int
    ) -> dict:
        """继承父代器官并应用渐进式器官进化
        
        支持两种格式（优先使用新格式）：
        - organ_evolution: 新的渐进式进化格式（推荐）
        - structural_innovations: 旧格式（向后兼容）
        
        Args:
            parent: 父系物种
            ai_payload: AI返回的数据
            turn_index: 当前回合
            
        Returns:
            更新后的器官字典
        """
        # 1. 继承父代所有器官（深拷贝）
        organs = {}
        for category, organ_data in parent.organs.items():
            organs[category] = dict(organ_data)
            # 确保有进化阶段字段
            if "evolution_stage" not in organs[category]:
                organs[category]["evolution_stage"] = 4  # 旧数据默认完善
            if "evolution_progress" not in organs[category]:
                organs[category]["evolution_progress"] = 1.0
        
        # 2. 优先使用新的 organ_evolution 格式
        organ_evolution = ai_payload.get("organ_evolution", [])
        if organ_evolution and isinstance(organ_evolution, list):
            # 推断生物类群进行验证
            biological_domain = self._infer_biological_domain(parent)
            
            # 验证渐进式进化规则
            _, valid_evolutions = self._validate_gradual_evolution(
                organ_evolution, parent.organs, biological_domain
            )
            
            for evo in valid_evolutions:
                category = evo.get("category", "unknown")
                action = evo.get("action", "enhance")
                target_stage = evo.get("target_stage", 1)
                structure_name = evo.get("structure_name", "未知结构")
                description = evo.get("description", "")
                
                if action == "initiate":
                    # 开始发展新器官（从原基开始）
                    organs[category] = {
                        "type": structure_name,
                        "parameters": {},
                        "evolution_stage": target_stage,
                        "evolution_progress": target_stage / 4.0,  # 阶段对应进度
                        "acquired_turn": turn_index,
                        "is_active": target_stage >= 2,  # 阶段2+才有基础功能
                        "evolution_history": [
                            {
                                "turn": turn_index,
                                "from_stage": 0,
                                "to_stage": target_stage,
                                "description": description
                            }
                        ]
                    }
                    logger.info(
                        f"[渐进式演化] 开始发展{category}: {structure_name} (阶段0→{target_stage})"
                    )
                
                elif action == "enhance" and category in organs:
                    # 增强现有器官
                    current_stage = organs[category].get("evolution_stage", 4)
                    
                    organs[category]["type"] = structure_name
                    organs[category]["evolution_stage"] = target_stage
                    organs[category]["evolution_progress"] = target_stage / 4.0
                    organs[category]["modified_turn"] = turn_index
                    organs[category]["is_active"] = target_stage >= 2
                    
                    # 记录演化历史
                    if "evolution_history" not in organs[category]:
                        organs[category]["evolution_history"] = []
                    organs[category]["evolution_history"].append({
                        "turn": turn_index,
                        "from_stage": current_stage,
                        "to_stage": target_stage,
                        "description": description
                    })
                    
                    logger.info(
                        f"[渐进式演化] 增强{category}: {structure_name} "
                        f"(阶段{current_stage}→{target_stage})"
                    )
            
            return organs
        
        # 3. 兼容旧的 structural_innovations 格式（转换为渐进式）
        innovations = ai_payload.get("structural_innovations", [])
        if not isinstance(innovations, list):
            return organs
        
        for innovation in innovations:
            if not isinstance(innovation, dict):
                continue
            
            category = innovation.get("category", "unknown")
            organ_type = innovation.get("type", "unknown")
            parameters = innovation.get("parameters", {})
            
            if category in organs:
                # 器官改进：最多提升1个阶段
                current_stage = organs[category].get("evolution_stage", 4)
                new_stage = min(current_stage + 1, 4)
                
                organs[category]["type"] = organ_type
                organs[category]["parameters"] = parameters
                organs[category]["evolution_stage"] = new_stage
                organs[category]["evolution_progress"] = new_stage / 4.0
                organs[category]["modified_turn"] = turn_index
                organs[category]["is_active"] = True
                logger.info(
                    f"[器官演化-兼容] 改进器官: {category} → {organ_type} "
                    f"(阶段{current_stage}→{new_stage})"
                )
            else:
                # 新器官：从阶段1（原基）开始，而不是直接完善
                organs[category] = {
                    "type": organ_type,
                    "parameters": parameters,
                    "evolution_stage": 1,  # 从原基开始
                    "evolution_progress": 0.25,
                    "acquired_turn": turn_index,
                    "is_active": False,  # 阶段1还没有功能
                    "evolution_history": [{
                        "turn": turn_index,
                        "from_stage": 0,
                        "to_stage": 1,
                        "description": f"开始发展{organ_type}原基"
                    }]
                }
                logger.info(
                    f"[器官演化-兼容] 新器官原基: {category} → {organ_type} (阶段1)"
                )
        
        return organs
    
    def _update_capabilities(self, parent: Species, organs: dict) -> list[str]:
        """根据器官更新能力标签
        
        Args:
            parent: 父系物种
            organs: 当前器官字典
            
        Returns:
            能力标签列表（中文）
        """
        # 能力映射表：旧英文标签 -> 中文标签
        legacy_map = {
            "photosynthesis": "光合作用",
            "autotrophy": "自养",
            "flagellar_motion": "鞭毛运动",
            "chemical_detection": "化学感知",
            "heterotrophy": "异养",
            "chemosynthesis": "化能合成",
            "extremophile": "嗜极生物",
            "ciliary_motion": "纤毛运动",
            "limb_locomotion": "附肢运动",
            "swimming": "游泳",
            "light_detection": "感光",
            "vision": "视觉",
            "touch_sensation": "触觉",
            "aerobic_respiration": "有氧呼吸",
            "digestion": "消化",
            "armor": "盔甲",
            "spines": "棘刺",
            "venom": "毒素"
        }

        capabilities = set()
        
        # 继承并转换父代能力
        for cap in parent.capabilities:
            if cap in legacy_map:
                capabilities.add(legacy_map[cap])
            else:
                # 如果已经是中文或其他未映射的，直接保留
                capabilities.add(cap)
        
        # 根据活跃器官添加能力标签
        for category, organ_data in organs.items():
            if not organ_data.get("is_active", True):
                continue  # 跳过已退化的器官
            
            organ_type = organ_data.get("type", "").lower()
            
            # 运动能力
            if category == "locomotion":
                if "flagella" in organ_type or "flagellum" in organ_type or "鞭毛" in organ_type:
                    capabilities.add("鞭毛运动")
                elif "cilia" in organ_type or "纤毛" in organ_type:
                    capabilities.add("纤毛运动")
                elif "leg" in organ_type or "limb" in organ_type or "足" in organ_type or "肢" in organ_type:
                    capabilities.add("附肢运动")
                elif "fin" in organ_type or "鳍" in organ_type:
                    capabilities.add("游泳")
            
            # 感觉能力
            elif category == "sensory":
                if "eye" in organ_type or "ocellus" in organ_type or "眼" in organ_type:
                    capabilities.add("感光")
                    capabilities.add("视觉")
                elif "photoreceptor" in organ_type or "eyespot" in organ_type or "光感受" in organ_type or "眼点" in organ_type:
                    capabilities.add("感光")
                elif "mechanoreceptor" in organ_type or "机械感受" in organ_type:
                    capabilities.add("触觉")
                elif "chemoreceptor" in organ_type or "化学感受" in organ_type:
                    capabilities.add("化学感知")
            
            # 代谢能力
            elif category == "metabolic":
                if "chloroplast" in organ_type or "photosynthetic" in organ_type or "叶绿体" in organ_type or "光合" in organ_type:
                    capabilities.add("光合作用")
                elif "mitochondria" in organ_type or "线粒体" in organ_type:
                    capabilities.add("有氧呼吸")
            
            # 消化能力
            elif category == "digestive":
                if organ_data.get("is_active", True):
                    capabilities.add("消化")
            
            # 防御能力
            elif category == "defense":
                if "shell" in organ_type or "carapace" in organ_type or "壳" in organ_type or "甲" in organ_type:
                    capabilities.add("盔甲")
                elif "spine" in organ_type or "thorn" in organ_type or "刺" in organ_type or "棘" in organ_type:
                    capabilities.add("棘刺")
                elif "toxin" in organ_type or "毒" in organ_type:
                    capabilities.add("毒素")
        
        return list(capabilities)
    
    def _update_genetic_distances(self, offspring: Species, parent: Species, turn_index: int):
        """更新遗传距离矩阵"""
        if not parent.genus_code:
            return
        
        genus = genus_repository.get_by_code(parent.genus_code)
        if not genus:
            return
        
        all_species = species_repository.list_species()
        genus_species = [sp for sp in all_species if sp.genus_code == parent.genus_code and sp.status == "alive"]
        
        new_distances = {}
        for sibling in genus_species:
            if sibling.lineage_code == offspring.lineage_code:
                continue
            
            distance = self.genetic_calculator.calculate_distance(offspring, sibling)
            key = self._make_distance_key(offspring.lineage_code, sibling.lineage_code)
            new_distances[key] = distance
        
        genus_repository.update_distances(parent.genus_code, new_distances, turn_index)
    
    def _make_distance_key(self, code1: str, code2: str) -> str:
        """生成距离键"""
        if code1 < code2:
            return f"{code1}-{code2}"
        return f"{code2}-{code1}"
    
    def _clamp_traits_to_limit(self, traits: dict, parent_traits: dict, trophic_level: float) -> dict:
        """智能钳制属性到营养级限制范围内
        
        策略：
        1. 单个属性不超过特化上限
        2. 属性总和不超过营养级上限和父代+5.0
        3. 最多2个属性超过基础上限
        """
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        clamped = dict(traits)
        
        # 1. 钳制单个属性到特化上限
        for k, v in clamped.items():
            if v > limits["specialized"]:
                clamped[k] = limits["specialized"]
        
        # 2. 检查并钳制总和
        current_sum = sum(clamped.values())
        parent_sum = sum(parent_traits.values())
        
        # 总和最多增加5.0（保守的演化步长，比原本允许的8更严格）
        max_increase = 5.0
        target_max_sum = min(limits["total"], parent_sum + max_increase)
        
        if current_sum > target_max_sum:
            # 计算需要缩减的量
            excess = current_sum - target_max_sum
            # 只缩减增加的属性（保持权衡原则）
            increased_traits = {k: v for k, v in clamped.items() if v > parent_traits.get(k, 0)}
            
            if increased_traits:
                # 按增加量比例分配缩减（增加多的缩减多）
                total_increase = sum(v - parent_traits.get(k, 0) for k, v in increased_traits.items())
                if total_increase > 0:
                    for k, v in increased_traits.items():
                        increase = v - parent_traits.get(k, 0)
                        reduction = excess * (increase / total_increase)
                        clamped[k] = max(parent_traits.get(k, 0), v - reduction)
            
            # 如果还是超了（说明没有增加的属性或不足以缩减），全局缩放
            current_sum = sum(clamped.values())
            if current_sum > target_max_sum:
                scale = target_max_sum / current_sum
                for k in clamped:
                    clamped[k] *= scale
        
        # 3. 确保最多2个属性超过基础上限
        base_limit = limits["base"]
        specialized_traits = [(k, v) for k, v in clamped.items() if v > base_limit]
        if len(specialized_traits) > 2:
            # 保留最高的2个，其余降到基础上限
            specialized_traits.sort(key=lambda x: x[1], reverse=True)
            keep_specialized = {k for k, _ in specialized_traits[:2]}
            
            for k, v in clamped.items():
                if v > base_limit and k not in keep_specialized:
                    clamped[k] = base_limit
        
        return {k: round(v, 2) for k, v in clamped.items()}
    
    def _calculate_dynamic_offspring_count(
        self,
        num_generations: float,
        population: int,
        evo_potential: float,
        current_species_count: int = 0,
        sibling_count: int = 0
    ) -> int:
        """【优化版】根据生态条件动态计算分化子种数量
        
        核心改进：
        - 世代多≠更多子种（世代只影响分化概率，不影响子种数量）
        - 子种数量主要由「隔离机会」决定（种群规模、地理分布）
        - 引入物种密度阻尼（防止爆炸性增长）
        
        参数说明：
        - num_generations: 经历的世代数（仅用于日志，不影响计算）
        - population: 当前存活种群数
        - evo_potential: 演化潜力（0-1）
        - current_species_count: 当前物种总数（用于密度阻尼）
        - sibling_count: 同谱系物种数量（用于属内阻尼）
        
        返回值：
        - 子种数量（1-3个，极端情况最多4个）
        """
        import math
        import random
        
        # 基础分化数（固定2个，模拟典型的二歧分化）
        base_offspring = 2
        
        # 1. 【移除】世代数加成 - 世代多只意味着突变多，不意味着隔离多
        # 现实中，细菌虽然繁殖快，但分化出的稳定物种数量并不比大型动物多
        generation_bonus = 0
        
        # 2. 种群规模加成（非常大的种群才可能形成3个隔离亚群）
        # 提高门槛：需要10亿以上才考虑+1
        population_bonus = 0
        if population > 1_000_000_000:  # 10亿
            population_bonus = 1
        
        # 3. 演化潜力加成（只有极高潜力才+1）
        evo_bonus = 1 if evo_potential > 0.90 else 0
        
        # 4. 【关键】物种密度阻尼
        # 当物种数量过多时，强制降低子种数量
        density_penalty = 0
        if current_species_count > 50:
            density_penalty = 1  # 超过50种：-1
        if current_species_count > 100:
            density_penalty = 2  # 超过100种：-2（基本只能分化1个）
        
        # 5. 【新增】同属饱和阻尼
        # 当同一谱系下已有多个物种时，限制继续分化
        sibling_penalty = 0
        if sibling_count >= 3:
            sibling_penalty = 1  # 同属已有3+物种：-1
        if sibling_count >= 5:
            sibling_penalty = 2  # 同属已有5+物种：几乎不能分化
        
        # 6. 汇总（最少1个，最多4个）
        total_offspring = base_offspring + generation_bonus + population_bonus + evo_bonus
        total_offspring -= density_penalty + sibling_penalty
        
        # 边界约束（上限从配置读取，默认4）
        max_offspring = _settings.max_offspring_count
        total_offspring = max(1, min(max_offspring, total_offspring))
        
        # 随机扰动（避免所有物种都分化相同数量）
        if random.random() < 0.3 and total_offspring > 1:
            total_offspring -= 1
        
        return total_offspring
    
    def _enforce_trait_tradeoffs(
        self, 
        current_traits: dict[str, float], 
        proposed_changes: dict[str, float],
        lineage_code: str
    ) -> dict[str, float]:
        """【强制权衡机制】确保属性变化有增必有减
        
        原理：50万年的演化不应该是纯粹的"升级"，而是适应性权衡
        - 如果提议的变化只增不减，自动添加减少项
        - 确保属性总和不会无限增长
        
        Args:
            current_traits: 当前属性字典
            proposed_changes: AI提议的变化 {"耐寒性": 2.0, "运动能力": 1.0}
            lineage_code: 谱系编码（用于确定哪些属性减少）
            
        Returns:
            调整后的变化字典
        """
        import random
        import hashlib
        
        if not proposed_changes:
            return proposed_changes
        
        # 计算总变化
        increases = {k: v for k, v in proposed_changes.items() if v > 0}
        decreases = {k: v for k, v in proposed_changes.items() if v < 0}
        
        total_increase = sum(increases.values())
        total_decrease = abs(sum(decreases.values()))
        
        # 如果已经有足够的减少，直接返回
        if total_decrease >= total_increase * 0.3:
            return proposed_changes
        
        # 需要添加的减少量（至少抵消30%的增加）
        needed_decrease = total_increase * 0.4 - total_decrease
        if needed_decrease <= 0:
            return proposed_changes
        
        # 基于谱系编码生成确定性随机种子（确保同一物种每次结果一致）
        seed = int(hashlib.md5(lineage_code.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        
        # 选择要减少的属性（优先选择当前值较高且未被增加的）
        adjusted = dict(proposed_changes)
        candidate_traits = [
            (name, value) 
            for name, value in current_traits.items() 
            if name not in increases and value > 3.0  # 只减少中高值属性
        ]
        
        if not candidate_traits:
            # 如果没有合适的候选，从增加项中随机选一个减少幅度
            for trait_name in list(increases.keys()):
                if needed_decrease <= 0:
                    break
                reduction = min(needed_decrease, increases[trait_name] * 0.5)
                adjusted[trait_name] = increases[trait_name] - reduction
                needed_decrease -= reduction
            return adjusted
        
        # 随机选择1-3个属性进行减少
        rng.shuffle(candidate_traits)
        num_to_reduce = min(len(candidate_traits), rng.randint(1, 3))
        
        for trait_name, current_value in candidate_traits[:num_to_reduce]:
            if needed_decrease <= 0:
                break
            # 减少幅度与当前值成比例（高值属性减更多）
            max_reduction = min(needed_decrease, current_value * 0.2, 3.0)
            reduction = rng.uniform(max_reduction * 0.5, max_reduction)
            adjusted[trait_name] = -round(reduction, 2)
            needed_decrease -= reduction
            logger.debug(f"[权衡] {lineage_code}: {trait_name} -{reduction:.2f} (权衡代价)")
        
        return adjusted
    
    def _add_differentiation_noise(
        self, 
        trait_changes: dict[str, float],
        lineage_code: str
    ) -> dict[str, float]:
        """【差异化机制】为不同子代添加随机偏移
        
        原理：同一次分化的多个子代应该有不同的演化方向
        - 基于谱系编码的最后字符（a, b, c...）确定偏移模式
        - 确保兄弟物种之间有明显差异
        
        Args:
            trait_changes: 当前变化字典
            lineage_code: 谱系编码（如 "A1a", "A1b", "A1c"）
            
        Returns:
            添加差异化后的变化字典
        """
        import random
        import hashlib
        
        if not trait_changes:
            return trait_changes
        
        # 基于完整谱系编码生成唯一随机种子
        seed = int(hashlib.md5(lineage_code.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        
        # 提取最后一个字符来确定子代编号
        last_char = lineage_code[-1] if lineage_code else 'a'
        offspring_index = ord(last_char.lower()) - ord('a')  # a=0, b=1, c=2...
        
        # 定义演化方向偏好（不同子代偏向不同方向）
        # 偏好模式：每个子代有2-3个属性获得额外加成，另外2-3个属性减少
        direction_patterns = [
            {"favor": ["耐寒性", "耐热性"], "disfavor": ["运动能力", "繁殖速度"]},  # 温度适应型
            {"favor": ["运动能力", "攻击性"], "disfavor": ["耐寒性", "社会性"]},     # 活动型
            {"favor": ["繁殖速度", "社会性"], "disfavor": ["攻击性", "运动能力"]},   # 繁殖型
            {"favor": ["防御性", "耐旱性"], "disfavor": ["繁殖速度", "攻击性"]},      # 防御型
            {"favor": ["耐盐性", "耐旱性"], "disfavor": ["社会性", "防御性"]},        # 环境适应型
        ]
        
        pattern = direction_patterns[offspring_index % len(direction_patterns)]
        
        adjusted = dict(trait_changes)
        
        # 对偏好属性添加额外加成（±0.3到±1.0）
        for trait in pattern["favor"]:
            if trait in adjusted:
                bonus = rng.uniform(0.2, 0.8)
                adjusted[trait] = round(adjusted[trait] + bonus, 2)
            else:
                # 即使AI没提议，也添加小幅增加
                adjusted[trait] = round(rng.uniform(0.3, 0.8), 2)
        
        # 对不偏好属性添加额外减少
        for trait in pattern["disfavor"]:
            if trait in adjusted:
                penalty = rng.uniform(0.2, 0.6)
                adjusted[trait] = round(adjusted[trait] - penalty, 2)
            else:
                # 添加小幅减少
                adjusted[trait] = round(-rng.uniform(0.2, 0.5), 2)
        
        # 添加额外的随机噪声（确保即使相同模式也有差异）
        for trait_name in list(adjusted.keys()):
            noise = rng.uniform(-0.3, 0.3)
            adjusted[trait_name] = round(adjusted[trait_name] + noise, 2)
        
        logger.debug(
            f"[差异化] {lineage_code}: 偏好{pattern['favor']}, "
            f"变化总和={sum(adjusted.values()):.2f}"
        )
        
        return adjusted
    
    # ================ 渐进式器官进化相关方法 ================
    
    # 生物复杂度等级参考描述（用于embedding相似度比较）
    _COMPLEXITY_REFERENCES = {
        0: "原核生物，如细菌和古菌，没有细胞核，只有核糖体，通过二分裂繁殖，体型微小，单细胞",
        1: "简单真核生物，如变形虫、鞭毛虫、纤毛虫，有细胞核和细胞器，单细胞真核生物",
        2: "殖民型或简单多细胞生物，如团藻、海绵、水母，细胞开始分化但无真正组织",
        3: "组织级生物，如扁形虫、环节动物，有真正的组织分化，简单器官系统",
        4: "器官级生物，如软体动物、节肢动物、鱼类，有复杂器官系统，体节或体腔",
        5: "高等器官系统级生物，如两栖类、爬行类、鸟类、哺乳类，高度分化的器官系统和神经系统",
    }
    
    # 缓存embedding向量
    _complexity_embeddings: dict[int, list[float]] | None = None
    
    def _infer_biological_domain(self, species: Species) -> str:
        """根据物种特征推断其生物复杂度等级
        
        采用多层判断策略：
        1. 优先使用embedding相似度（如果服务可用）
        2. 结构化特征检测（器官数量、体型等）
        3. 关键词匹配作为补充
        
        返回值：复杂度等级字符串，格式为 "complexity_N"
        - complexity_0: 原核生物（细菌、古菌）
        - complexity_1: 简单真核（单细胞真核生物）
        - complexity_2: 殖民/简单多细胞（团藻、海绵等）
        - complexity_3: 组织级（扁形虫、环节动物等）
        - complexity_4: 器官级（节肢动物、鱼类等）
        - complexity_5: 高等器官系统（脊椎动物高等类群）
        """
        # 尝试使用embedding进行智能分类
        complexity_level = self._infer_complexity_by_embedding(species)
        
        if complexity_level is None:
            # 降级到基于规则的推断
            complexity_level = self._infer_complexity_by_rules(species)
        
        return f"complexity_{complexity_level}"
    
    def _infer_complexity_by_embedding(self, species: Species) -> int | None:
        """使用embedding相似度推断复杂度等级"""
        # 检查是否有可用的embedding服务
        if not hasattr(self, '_embedding_service') or self._embedding_service is None:
            # 尝试从router获取
            if hasattr(self.router, 'embedding_service'):
                self._embedding_service = self.router.embedding_service
            else:
                return None
        
        if self._embedding_service is None:
            return None
        
        try:
            # 懒加载参考描述的embedding
            if SpeciationService._complexity_embeddings is None:
                ref_descriptions = list(self._COMPLEXITY_REFERENCES.values())
                ref_vectors = self._embedding_service.embed(ref_descriptions, require_real=False)
                SpeciationService._complexity_embeddings = {
                    level: vec for level, vec in enumerate(ref_vectors)
                }
            
            # 获取物种描述的embedding
            species_vec = self._embedding_service.embed([species.description], require_real=False)[0]
            
            # 计算与各等级参考的余弦相似度
            import numpy as np
            species_arr = np.array(species_vec)
            species_norm = np.linalg.norm(species_arr)
            if species_norm == 0:
                return None
            species_arr = species_arr / species_norm
            
            best_level = 1  # 默认简单真核
            best_similarity = -1
            
            for level, ref_vec in self._complexity_embeddings.items():
                ref_arr = np.array(ref_vec)
                ref_norm = np.linalg.norm(ref_arr)
                if ref_norm == 0:
                    continue
                ref_arr = ref_arr / ref_norm
                
                similarity = float(np.dot(species_arr, ref_arr))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_level = level
            
            logger.debug(
                f"[复杂度推断-embedding] {species.common_name}: "
                f"等级{best_level} (相似度{best_similarity:.3f})"
            )
            return best_level
            
        except Exception as e:
            logger.warning(f"[复杂度推断] Embedding推断失败: {e}")
            return None
    
    def _infer_complexity_by_rules(self, species: Species) -> int:
        """基于规则推断复杂度等级（降级方案）"""
        description = (species.description or "").lower()
        common_name = (species.common_name or "").lower()
        organs = species.organs or {}
        body_length = species.morphology_stats.get("body_length_cm", 0.01)
        
        # 关键词映射
        level_keywords = {
            0: ["细菌", "杆菌", "球菌", "古菌", "原核", "bacteria", "archaea", "芽孢"],
            1: ["原生", "单细胞", "鞭毛虫", "纤毛虫", "变形虫", "眼虫", "草履虫", "protist", "amoeba"],
            2: ["团藻", "海绵", "水母", "珊瑚", "群体", "殖民", "简单多细胞", "colony"],
            3: ["扁形虫", "涡虫", "线虫", "环节", "蚯蚓", "水蛭", "组织分化"],
            4: ["节肢", "软体", "昆虫", "甲壳", "蜘蛛", "鱼", "章鱼", "蜗牛", "器官系统"],
            5: ["两栖", "爬行", "鸟", "哺乳", "脊椎", "蛙", "蜥蜴", "蛇", "恐龙", "鲸", "猫", "狗", "人"]
        }
        
        # 关键词匹配
        for level in range(5, -1, -1):  # 从高到低匹配
            if any(kw in description or kw in common_name for kw in level_keywords[level]):
                # 原核生物额外验证：不能有真核特征
                if level == 0:
                    eukaryote_features = ["叶绿体", "线粒体", "细胞核", "内质网", "高尔基体"]
                    if any(kw in description for kw in eukaryote_features):
                        continue
                return level
        
        # 基于器官复杂度推断
        organ_count = len([o for o in organs.values() if o.get("is_active", True)])
        if organ_count >= 5:
            return 4  # 器官级
        elif organ_count >= 3:
            return 3  # 组织级
        elif organ_count >= 1:
            return 2 if body_length > 0.1 else 1
        
        # 基于体型推断
        if body_length < 0.001:  # < 10微米
            return 0  # 原核生物
        elif body_length < 0.1:  # < 1毫米
            return 1  # 简单真核
        elif body_length < 1.0:  # < 1厘米
            return 2  # 简单多细胞
        elif body_length < 10.0:  # < 10厘米
            return 3  # 组织级
        else:
            return 4  # 器官级或更高
    
    def _get_complexity_constraints(self, complexity_level: str) -> dict:
        """获取复杂度等级的基础约束
        
        设计理念：允许自由演化，只限制"跳跃式"发展
        - 不限制能发展什么结构（让环境压力自然筛选）
        - 只限制原核/真核的基本分界（这是生物学硬约束）
        - 通过阶段系统保证渐进式发展
        """
        level = int(complexity_level.split("_")[1]) if "_" in complexity_level else 1
        
        # 极简约束：只区分原核/真核的根本差异
        if level == 0:  # 原核生物
            return {
                # 原核生物的唯一硬约束：不能有真核细胞器
                # （因为这需要内共生事件，不是渐进演化能达到的）
                "origin_type": "prokaryote",
                "hard_forbidden": ["真核鞭毛", "纤毛", "线粒体", "叶绿体", "细胞核", "内质网", "高尔基体"],
                "max_organ_stage": 4,
            }
        else:  # 真核生物（等级1-5）
            return {
                "origin_type": "eukaryote", 
                "hard_forbidden": [],  # 真核生物可以自由发展任何结构
                "max_organ_stage": 4,
            }
    
    def _summarize_organs(self, species: Species) -> str:
        """生成器官系统的文本摘要，包含进化阶段信息"""
        organs = species.organs or {}
        
        if not organs:
            return "无已记录的器官系统"
        
        summaries = []
        for category, organ_data in organs.items():
            if not organ_data.get("is_active", True):
                continue
            
            organ_type = organ_data.get("type", "未知")
            stage = organ_data.get("evolution_stage", 4)  # 默认已完善
            progress = organ_data.get("evolution_progress", 1.0)
            
            # 阶段描述
            stage_names = {0: "无", 1: "原基", 2: "初级", 3: "功能化", 4: "完善"}
            stage_name = stage_names.get(stage, "完善")
            
            # 构建摘要
            category_names = {
                "locomotion": "运动系统",
                "sensory": "感觉系统", 
                "metabolic": "代谢系统",
                "digestive": "消化系统",
                "defense": "防御系统",
                "reproductive": "生殖系统"
            }
            cat_name = category_names.get(category, category)
            
            if stage < 4:
                summaries.append(f"- {cat_name}: {organ_type}（阶段{stage}/{stage_name}，进度{progress*100:.0f}%）")
            else:
                summaries.append(f"- {cat_name}: {organ_type}（完善）")
        
        return "\n".join(summaries) if summaries else "无已记录的器官系统"
    
    def _summarize_prey_species(self, species: Species) -> str:
        """生成捕食关系的文本摘要，用于AI提示词
        
        返回格式：
        - 自养生物（无猎物）：返回"自养生物（无需猎物）"
        - 有猎物：返回猎物列表和偏好
        """
        diet_type = species.diet_type or "omnivore"
        prey_species = species.prey_species or []
        prey_preferences = species.prey_preferences or {}
        
        if diet_type == "autotroph" or not prey_species:
            diet_labels = {
                "autotroph": "自养生物（无需猎物）",
                "herbivore": "草食动物（猎物未指定）",
                "carnivore": "肉食动物（猎物未指定）",
                "omnivore": "杂食动物（猎物未指定）",
                "detritivore": "腐食动物（以有机碎屑为食）",
            }
            return diet_labels.get(diet_type, "食性未知")
        
        # 构建猎物摘要
        prey_summary = []
        all_species = species_repository.list_species()
        species_map = {sp.lineage_code: sp for sp in all_species}
        
        for prey_code in prey_species:
            pref = prey_preferences.get(prey_code, 1.0 / max(1, len(prey_species)))
            prey_sp = species_map.get(prey_code)
            if prey_sp:
                prey_summary.append(f"{prey_code}({prey_sp.common_name}, {pref*100:.0f}%)")
            else:
                prey_summary.append(f"{prey_code}({pref*100:.0f}%)")
        
        diet_labels = {
            "herbivore": "草食动物",
            "carnivore": "肉食动物",
            "omnivore": "杂食动物",
            "detritivore": "腐食动物",
        }
        diet_label = diet_labels.get(diet_type, diet_type)
        
        return f"{diet_label}，猎物: " + ", ".join(prey_summary)
    
    def _validate_gradual_evolution(
        self, 
        organ_evolution: list, 
        parent_organs: dict,
        biological_domain: str
    ) -> tuple[bool, list]:
        """验证器官进化是否符合渐进式原则
        
        设计理念：最小限制，最大自由
        - 只验证"渐进式"（不能跳跃）
        - 只验证"原核/真核分界"（硬性生物学约束）
        - 其他一切都允许，让环境压力自然筛选
        
        返回：(是否有效, 过滤后的有效进化列表)
        """
        if not organ_evolution:
            return True, []
        
        valid_evolutions = []
        
        # 获取基础约束
        constraints = self._get_complexity_constraints(biological_domain)
        hard_forbidden = constraints.get("hard_forbidden", [])
        max_stage = constraints.get("max_organ_stage", 4)
        origin_type = constraints.get("origin_type", "eukaryote")
        
        for evo in organ_evolution:
            if not isinstance(evo, dict):
                continue
            
            category = evo.get("category", "")
            action = evo.get("action", "")
            current_stage = evo.get("current_stage", 0)
            target_stage = evo.get("target_stage", 0)
            structure_name = evo.get("structure_name", "")
            
            # === 核心验证1：阶段跳跃限制（渐进式核心） ===
            stage_jump = target_stage - current_stage
            if stage_jump > 2:
                logger.info(f"[渐进式] 修正跳跃: {structure_name} {current_stage}→{target_stage} 改为 →{min(current_stage + 2, max_stage)}")
                target_stage = min(current_stage + 2, max_stage)
                evo["target_stage"] = target_stage
            
            # === 核心验证2：新器官从原基开始 ===
            if action == "initiate" and target_stage > 1:
                logger.info(f"[渐进式] 新器官从原基开始: {structure_name}")
                evo["target_stage"] = 1
            
            # === 核心验证3：原核/真核硬性分界 ===
            # 这是唯一的"禁止"规则，因为这需要内共生事件
            if origin_type == "prokaryote" and hard_forbidden:
                if any(f in structure_name for f in hard_forbidden):
                    logger.warning(
                        f"[生物学约束] 原核生物不能发展真核结构: {structure_name} "
                        f"(需要内共生事件，非渐进演化)"
                    )
                    continue
            
            # === 验证4：enhance操作需要父代有该器官 ===
            if action == "enhance":
                if category not in parent_organs:
                    # 自动转为initiate，允许发展新器官
                    logger.debug(f"[器官] {category}不存在，转为新发展")
                    evo["action"] = "initiate"
                    evo["current_stage"] = 0
                    evo["target_stage"] = 1
                else:
                    # 使用父代实际阶段
                    actual_stage = parent_organs[category].get("evolution_stage", 4)
                    if current_stage != actual_stage:
                        evo["current_stage"] = actual_stage
                        if target_stage - actual_stage > 2:
                            evo["target_stage"] = min(actual_stage + 2, max_stage)
            
            valid_evolutions.append(evo)
        
        # 限制每次分化最多3个器官变化（放宽限制）
        if len(valid_evolutions) > 3:
            logger.info(f"[器官验证] 单次分化器官变化限制为3个")
            valid_evolutions = valid_evolutions[:3]
        
        return True, valid_evolutions


