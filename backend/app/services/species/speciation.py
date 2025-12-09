from __future__ import annotations

import asyncio
import logging
import random
import warnings
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence, Callable, Awaitable, Any, TYPE_CHECKING

from ...models.species import LineageEvent, Species
from ...models.config import SpeciationConfig
from ...ai.model_router import staggered_gather
from ...ai.prompts.species import SPECIES_PROMPTS

logger = logging.getLogger(__name__)
from ...repositories.genus_repository import genus_repository
from ...repositories.species_repository import species_repository
from ...repositories.environment_repository import environment_repository
from ...schemas.responses import BranchingEvent
from .genetic_distance import GeneticDistanceCalculator
from .trait_config import TraitConfig, PlantTraitConfig
from .trophic import TrophicLevelCalculator
from .speciation_rules import SpeciationRules, speciation_rules  # 【新增】规则引擎
from .plant_evolution import plant_evolution_service, PLANT_MILESTONES  # 【植物演化】
from .plant_competition import plant_competition_calculator  # 【植物竞争】
from .description_enhancer import DescriptionEnhancerService  # 【描述增强】
from .gene_diversity import GeneDiversityService
from .naming_hints import NamingHintGenerator
from .organ_evolution_service import OrganEvolutionService, get_organ_evolution_service
from ...tensor.tradeoff import TradeoffCalculator
from ...core.config import get_settings
from ...simulation.constants import get_time_config

if TYPE_CHECKING:
    from .gene_library import GeneLibraryService

# 获取配置
_settings = get_settings()




class SpeciationService:
    """根据存活数据和演化潜力，生成新的谱系并记录事件。
    
    【核心改进】现在支持基于地块的分化：
    - 分化发生在特定区域（地块集群），而非全局
    - 子代物种只在分化起源区域出现
    - 不同子代可以分配到不同地块（模拟地理隔离）
    
    【依赖注入】
    配置必须通过构造函数注入，内部方法不再调用 _load_speciation_config。
    如需刷新配置，使用 reload_config() 显式更新。
    """

    def __init__(self, router, config: SpeciationConfig | None = None) -> None:
        self.router = router
        self.trophic_calculator = TrophicLevelCalculator()
        self.genetic_calculator = GeneticDistanceCalculator()
        # [DEPRECATED] GeneLibraryService 惰性初始化，仅用于旧存档兼容
        self._gene_library_service: "GeneLibraryService | None" = None
        self.gene_diversity_service = GeneDiversityService()
        self.naming_hint_generator = NamingHintGenerator()  # 【命名提示】
        # 【器官演化】自由器官演化系统 - embedding 服务将在首次使用时从 router 获取
        self._organ_evolution_service: OrganEvolutionService | None = None
        self.rules = speciation_rules  # 【新增】规则引擎实例
        self.description_enhancer = DescriptionEnhancerService(router)  # 【描述增强】LLM增强规则生成的描述
        self.max_speciation_per_turn = 20
        self.max_deferred_requests = 60
        self._deferred_requests: list[dict[str, Any]] = []
        self._rule_fallback_species: list[tuple[Species, Species, str]] = []  # [(species, parent, speciation_type)]
        self._tensor_state = None
        # 器官枚举（闭集 organ_key）
        self._organ_catalog = [
            {"organ_key": "vision_simple_eye", "category": "sensory", "default_name": "眼点"},
            {"organ_key": "vision_complex_eye", "category": "sensory", "default_name": "成像眼"},
            {"organ_key": "locomotion_fins", "category": "locomotion", "default_name": "鳍状运动"},
            {"organ_key": "locomotion_limbs", "category": "locomotion", "default_name": "肢体运动"},
            {"organ_key": "respiration_gills", "category": "respiratory", "default_name": "鳃呼吸"},
            {"organ_key": "respiration_lung", "category": "respiratory", "default_name": "肺/气囊呼吸"},
            {"organ_key": "defense_scales", "category": "defense", "default_name": "鳞片防御"},
            {"organ_key": "defense_spikes", "category": "defense", "default_name": "棘刺防御"},
            {"organ_key": "sense_lateral_line", "category": "sensory", "default_name": "侧线感知"},
            {"organ_key": "sense_auditory", "category": "sensory", "default_name": "听觉感知"},
        ]
        
        # 配置注入 - 如未提供则使用默认值并警告
        if config is None:
            logger.warning("[分化服务] config 未注入，使用默认值")
            config = SpeciationConfig()
        self._config = config
        self._use_auto_tradeoff = getattr(config, "use_auto_tradeoff", getattr(_settings, "use_auto_tradeoff", False))
        tradeoff_ratio = getattr(config, "tradeoff_ratio", getattr(_settings, "tradeoff_ratio", 0.7))
        self.tradeoff_calculator = TradeoffCalculator(tradeoff_ratio=tradeoff_ratio)
        
        # 【新增】地块级数据缓存
        self._tile_mortality_cache: dict[str, dict[int, float]] = {}  # {lineage_code: {tile_id: death_rate}}
        self._tile_population_cache: dict[str, dict[int, float]] = {}  # {lineage_code: {tile_id: population}}
        self._tile_adjacency: dict[int, set[int]] = {}  # {tile_id: {adjacent_tile_ids}}
        self._speciation_candidates: dict[str, dict] = {}  # 预筛选的分化候选数据
        
        # 【Embedding集成】演化提示缓存
        self._evolution_hints: dict[str, dict] = {}  # {lineage_code: {reference_species, predicted_traits, ...}}
    
    @property
    def gene_library_service(self) -> "GeneLibraryService":
        """[DEPRECATED] 惰性加载 GeneLibraryService，仅用于旧存档兼容"""
        if self._gene_library_service is None:
            warnings.warn(
                "GeneLibraryService 已废弃，请迁移到 GeneDiversityService",
                DeprecationWarning,
                stacklevel=2
            )
            from .gene_library import GeneLibraryService
            self._gene_library_service = GeneLibraryService()
        return self._gene_library_service
    
    @property
    def organ_evolution_service(self) -> OrganEvolutionService:
        """惰性加载器官演化服务，自动注入 embedding 服务"""
        if self._organ_evolution_service is None:
            # 尝试从 router 获取 embedding 服务
            embedding_service = None
            if hasattr(self.router, 'embedding_service'):
                embedding_service = self.router.embedding_service
            self._organ_evolution_service = OrganEvolutionService(embedding_service)
        return self._organ_evolution_service
    
    def reload_config(self, config: SpeciationConfig | None = None) -> None:
        """热更新配置
        
        Args:
            config: 分化配置（必须由调用方提供）
            
        注意: 配置应由 SimulationEngine.reload_configs() 统一从容器获取后传入。
        """
        if config is not None:
            self._config = config
            logger.info("[分化服务] 配置已重新加载")
    
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

    def set_tensor_state(self, tensor_state) -> None:
        """设置张量状态影子数据（可选）。"""
        self._tensor_state = tensor_state
    
    def set_tile_adjacency(self, adjacency: dict[int, set[int]]) -> None:
        """设置地块邻接关系"""
        self._tile_adjacency = adjacency
    
    def clear_tile_cache(self) -> None:
        """清空地块缓存（每回合开始时调用）"""
        self._tile_mortality_cache.clear()
        self._tile_population_cache.clear()
        self._speciation_candidates.clear()
        self._evolution_hints.clear()
    
    def clear_all_caches(self) -> None:
        """清空所有缓存（存档切换时调用）
        
        【重要】切换存档时必须调用此方法，否则旧存档的
        延迟分化请求可能会影响新存档。
        """
        self.clear_tile_cache()
        self._deferred_requests.clear()
        self._tile_adjacency.clear()
    
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
        pressures: Sequence = None,  # ParsedPressure 列表
        trophic_interactions: dict[str, float] = None,  # 营养级互动信息
        stream_callback: Callable[[str, str, str], None] | None = None,  # (event_type, message, category)
        speciation_candidates: set[str] | None = None,  # AI 识别的高分化信号物种
    ) -> list[BranchingEvent]:
        """处理物种分化 (异步并发版)
        
        Args:
            speciation_candidates: AI 通过 ModifierApplicator 识别的高分化信号物种代码集合
                                   这些物种会获得分化概率加成
        """
        import random
        import math
        
        # 保存营养级互动信息，供后续使用
        self._current_trophic_interactions = trophic_interactions or {}
        
        # 保存 AI 分化候选
        self._ai_speciation_candidates = speciation_candidates or set()
        
        # 提取压力描述摘要和压力类型列表
        pressure_summary = "无显著环境压力"
        self._current_pressure_types: list[str] = ["adaptive"]  # 默认
        if pressures:
            # 使用 set 去重描述，避免重复
            narratives = sorted(list(set(p.narrative for p in pressures)))
            pressure_summary = "; ".join(narratives)
            # 提取压力类型用于基因筛选
            self._current_pressure_types = list(set(p.kind for p in pressures if p.kind))
            if not self._current_pressure_types:
                self._current_pressure_types = ["adaptive"]
        elif major_events:
            pressure_summary = "重大地质/气候变迁"
            self._current_pressure_types = ["environment", "catastrophe"]
        elif average_pressure > 5.0:
            pressure_summary = f"高环境压力 ({average_pressure:.1f}/10)"
            self._current_pressure_types = ["environment", "stress"]
        
        # 生成食物链状态描述（用于AI）
        self._food_chain_summary = self._summarize_food_chain_status(trophic_interactions)
        
        # ========== 加载分化配置 ==========
        spec_config = self._config
        is_early_game = turn_index < spec_config.early_game_turns
        
        # 动态分化限制 (Dynamic Speciation Limiting)
        # 【优化】收紧限制，依赖淘汰机制来控制物种数量
        current_species_count = len(mortality_results)
        soft_cap = spec_config.species_soft_cap
        
        # 【早期分化优化】早期不做密度衰减，鼓励多分化
        if is_early_game:
            density_damping = 1.0
            logger.debug(f"[早期分化] turn={turn_index} < {spec_config.early_game_turns}，跳过密度衰减")
        else:
            density_damping = 1.0 / (1.0 + max(0, current_species_count - soft_cap) / float(soft_cap))
        
        # 1. 准备阶段：筛选候选并生成任务
        entries: list[dict[str, Any]] = []
        
        # 【新增】构建物种后代索引，用于直接后代数量检查
        all_species = species_repository.list_species()
        direct_offspring_map: dict[str, list[Species]] = {}  # {parent_code: [child_species]}
        for sp in all_species:
            parent = sp.parent_code
            if parent:
                if parent not in direct_offspring_map:
                    direct_offspring_map[parent] = []
                direct_offspring_map[parent].append(sp)
        
        # 【新增】本回合亲本子代计数（共享杂交/分化）
        from collections import Counter
        turn_offspring_counts: Counter[str] = Counter()
        for sp in all_species:
            parent = sp.parent_code
            if parent and getattr(sp, "created_turn", -1) == turn_index:
                turn_offspring_counts[parent] += 1
        # 共享给后续阶段（如自动杂交）
        try:
            ctx.turn_offspring_counts = turn_offspring_counts  # type: ignore[attr-defined]
        except Exception:
            pass
        
        for result in mortality_results:
            species = result.species
            lineage_code = species.lineage_code
            
            # ========== 【直接后代数量限制检查】==========
            # 检查该物种是否已达到最大直接后代数量
            max_direct_offspring = spec_config.max_direct_offspring
            count_only_alive = spec_config.count_only_alive_offspring
            max_offspring_per_parent_per_turn = spec_config.max_hybrids_per_parent_per_turn
            
            direct_children = direct_offspring_map.get(lineage_code, [])
            if count_only_alive:
                # 只计算存活的直接后代
                alive_children_count = sum(1 for c in direct_children if c.status == "alive")
            else:
                # 计算所有历史直接后代
                alive_children_count = len(direct_children)
            
            if alive_children_count >= max_direct_offspring:
                logger.debug(
                    f"[分化限制] {species.common_name}: "
                    f"直接后代数量({alive_children_count})已达上限({max_direct_offspring})，跳过分化"
                )
                continue
            
            # 【新增】按回合限制：杂交/分化共享计数
            if max_offspring_per_parent_per_turn and max_offspring_per_parent_per_turn > 0:
                turn_children = turn_offspring_counts.get(lineage_code, 0)
                if turn_children >= max_offspring_per_parent_per_turn:
                    logger.debug(
                        f"[分化限制-本回合] {species.common_name}: "
                        f"本回合子代数({turn_children})已达上限({max_offspring_per_parent_per_turn})，跳过分化"
                    )
                    continue
            
            # ========== 【种群数量门槛检查】==========
            # 整体种群低于最小门槛的物种不允许分化
            global_population = int(species.morphology_stats.get("population", 0) or 0)
            min_pop_for_speciation = spec_config.min_population_for_speciation
            if global_population < min_pop_for_speciation:
                logger.debug(
                    f"[分化跳过-种群门槛] {species.common_name}: "
                    f"全局种群{global_population:,} < 门槛{min_pop_for_speciation:,}"
                )
                continue
            
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
                tile_total_population = int(sum(tile_populations.values()))
                # 与全局种群同步：以地块总和为准，修正全局人口
                if tile_total_population > 0 and abs(tile_total_population - global_population) > 0:
                    logger.warning(
                        f"[种群同步] {species.common_name}: 地块总人口({tile_total_population:,}) "
                        f"≠ 全局人口({global_population:,})，以地块总和为准"
                    )
                    global_population = tile_total_population
                    species.morphology_stats["population"] = tile_total_population
                # 候选人口不得超过全局人口
                if candidate_population > global_population:
                    candidate_population = global_population
                
                # 计算候选地块的加权平均死亡率
                total_pop = sum(tile_populations.get(t, 0) for t in candidate_tiles)
                if total_pop > 0:
                    death_rate = sum(
                        tile_mortality.get(t, 0) * tile_populations.get(t, 0) 
                        for t in candidate_tiles
                    ) / total_pop
                else:
                    death_rate = result.death_rate
                
                # 【一揽子修改】候选簇人口检查
                # 要求候选簇内人口 >= 基础门槛的 60%，避免极度分散的小簇触发
                # 【早期分化优化】传入 turn_index 用于早期折减
                base_threshold_for_cluster = self._calculate_speciation_threshold(species, turn_index)
                min_cluster_pop = int(base_threshold_for_cluster * 0.6)
                
                # 检查每个簇的人口
                valid_clusters = []
                for cluster in clusters:
                    cluster_pop = sum(tile_populations.get(t, 0) for t in cluster)
                    if cluster_pop >= min_cluster_pop:
                        valid_clusters.append(cluster)
                
                # 如果没有有效簇，降级隔离状态
                if not valid_clusters and clusters:
                    is_isolated = False
                    logger.debug(
                        f"[簇人口不足] {species.common_name}: "
                        f"所有{len(clusters)}个簇人口 < 门槛60%({min_cluster_pop:,})"
                    )
                elif valid_clusters:
                    clusters = valid_clusters
                
                logger.debug(
                    f"[地块分化检查] {species.common_name}: "
                    f"候选地块={len(candidate_tiles)}, 候选种群={candidate_population:,}, "
                    f"加权死亡率={death_rate:.1%}, 隔离={is_isolated}, "
                    f"有效簇={len(valid_clusters) if valid_clusters else 0}/{len(clusters) if clusters else 0}"
                )
            else:
                # 回退到全局数据（兼容旧逻辑）
                candidate_tiles = set()
                tile_populations = self._tile_population_cache.get(lineage_code, {})
                tile_mortality = self._tile_mortality_cache.get(lineage_code, {})
                candidate_population = int(species.morphology_stats.get("population", 0) or 0)
                tile_total_population = int(sum(tile_populations.values())) if tile_populations else candidate_population
                if tile_total_population > 0 and abs(tile_total_population - candidate_population) > 0:
                    logger.warning(
                        f"[种群同步] {species.common_name}: 地块总人口({tile_total_population:,}) "
                        f"≠ 全局人口({candidate_population:,})，以地块总和为准"
                    )
                    candidate_population = tile_total_population
                    species.morphology_stats["population"] = tile_total_population
                    global_population = tile_total_population
                death_rate = result.death_rate
                is_isolated = False
                mortality_gradient = 0.0
                clusters = []
                
                # 如果有地块数据，尝试筛选候选地块
                # 使用配置中的筛选条件
                if tile_populations and tile_mortality:
                    for tile_id, pop in tile_populations.items():
                        rate = tile_mortality.get(tile_id, 0.5)
                        if (pop >= spec_config.candidate_tile_min_pop and 
                            spec_config.candidate_tile_death_rate_min <= rate <= spec_config.candidate_tile_death_rate_max):
                            candidate_tiles.add(tile_id)
                    if candidate_tiles:
                        candidate_population = int(sum(tile_populations.get(t, 0) for t in candidate_tiles))
            
            # 使用候选地块的种群数据
            survivors = candidate_population
            resource_pressure = result.resource_pressure
            
            # 获取生态位信息（用于后续门槛调整）
            niche_overlap_for_threshold = result.niche_overlap
            niche_saturation_for_threshold = getattr(result, 'niche_saturation', 0.0)
            
            # 条件1：计算该物种的动态分化门槛
            # 【一揽子修改】根据隔离状态和生态条件动态调整门槛
            # 【早期分化优化】传入 turn_index 用于早期折减
            base_threshold = self._calculate_speciation_threshold(species, turn_index)
            
            # 基础门槛修正
            threshold_multiplier = 1.0
            
            # 【大浪淘沙v3】隔离/不隔离的门槛修正
            if is_isolated:
                # 已隔离时，门槛降低（奖励隔离分化）
                threshold_multiplier *= 0.7  # 【新增】隔离奖励
            else:
                # 未隔离时，小幅提高门槛
                threshold_multiplier *= 1.1  # 原1.2 -> 1.1（进一步降低惩罚）
            
            # 【大浪淘沙v3】高种群时门槛额外降低（巨无霸格奖励）
            if candidate_population > base_threshold * 3:
                threshold_multiplier *= 0.8  # 种群是门槛3倍时，门槛再降20%
            elif candidate_population > base_threshold * 2:
                threshold_multiplier *= 0.9  # 种群是门槛2倍时，门槛再降10%
            
            # 高生态位重叠（overlap > 0.7）时，门槛小幅提高（原0.6）
            if niche_overlap_for_threshold > 0.7:
                threshold_multiplier *= 1.1  # 原1.2 -> 1.1
            
            # 资源饱和很高（saturation > 0.85）且无隔离时，门槛小幅提高
            if niche_saturation_for_threshold > 0.85 and not is_isolated:
                threshold_multiplier *= 1.1  # 原1.2 -> 1.1
            
            min_population = int(base_threshold * threshold_multiplier)
            
            # 【改进】使用候选地块的种群，而非全局种群
            if candidate_population < min_population:
                logger.debug(
                    f"[分化跳过-种群不足] {species.common_name}: "
                    f"种群{candidate_population:,} < 门槛{min_population:,}"
                )
                continue
            
            # 条件2：演化潜力（放宽门槛 + 累积压力补偿）
            evo_potential = species.hidden_traits.get("evolution_potential", 0.5)
            speciation_pressure = species.morphology_stats.get("speciation_pressure", 0.0) or 0.0
            
            # 【新增】分化冷却期检查
            # 早期跳过冷却期，鼓励早期多分化
            cooldown = spec_config.cooldown_turns
            last_speciation_turn = species.morphology_stats.get("last_speciation_turn", -999)
            turns_since_speciation = turn_index - last_speciation_turn
            
            if turn_index >= spec_config.early_skip_cooldown_turns and turns_since_speciation < cooldown:
                logger.debug(
                    f"[分化冷却] {species.common_name} 仍在冷却期 "
                    f"({turns_since_speciation}/{cooldown}回合)"
                )
                continue
            elif turn_index < spec_config.early_skip_cooldown_turns and turns_since_speciation < cooldown:
                logger.debug(f"[早期分化] turn={turn_index} < {spec_config.early_skip_cooldown_turns}，跳过冷却期检查")
            
            # 【平衡优化v4】几乎所有物种都有分化潜力
            # 演化潜力≥0.15 或 累积分化压力≥0.10
            # 生物学依据：50万年尺度下，几乎任何物种都会产生遗传分化
            if evo_potential < 0.15 and speciation_pressure < 0.10:
                logger.debug(
                    f"[分化跳过-潜力不足] {species.common_name}: "
                    f"演化潜力{evo_potential:.2f} < 0.15, 累积压力{speciation_pressure:.2f} < 0.10"
                )
                continue
            
            # 记录通过初步检查的物种
            # 【早期分化优化】添加详细日志，便于验证早期分化效果
            logger.info(
                f"[分化候选] {species.common_name}: "
                f"turn={turn_index}, 种群={candidate_population:,}, 门槛={min_population:,} "
                f"(base={base_threshold:,}, multiplier={threshold_multiplier:.2f}), "
                f"演化潜力={evo_potential:.2f}, 累积压力={speciation_pressure:.2f}, "
                f"avg_pressure={average_pressure:.2f}, resource_pressure={resource_pressure:.2f}, "
                f"is_isolated={is_isolated}, early_game={turn_index < 10}"
            )
            
            # 条件3：压力或资源饱和
            # 【一揽子修改】收紧压力阈值，地理隔离为主通道
            # 无隔离时需满足更严格条件
            
            # 获取生态位信息（用于生态隔离判断）
            niche_overlap = result.niche_overlap
            niche_saturation = getattr(result, 'niche_saturation', 0.0)
            
            # 根据回合阶段使用不同的阈值（从配置读取）
            if is_early_game:
                pressure_threshold = spec_config.pressure_threshold_early
                resource_threshold = spec_config.resource_threshold_early
                evo_threshold = spec_config.evo_potential_threshold_early
            else:
                pressure_threshold = spec_config.pressure_threshold_late
                resource_threshold = spec_config.resource_threshold_late
                evo_threshold = spec_config.evo_potential_threshold_late
            
            # 【大浪淘沙v3】大幅放宽分化触发条件
            
            # 地理隔离时条件最宽松
            if is_isolated:
                has_pressure = True
            # 【新增】高种群直接触发（巨无霸格强制分化）
            elif candidate_population >= base_threshold * 2.5:
                has_pressure = True
                logger.debug(
                    f"[巨无霸分化] {species.common_name}: "
                    f"种群{candidate_population:,} >= 门槛×2.5({int(base_threshold*2.5):,})，强制触发分化"
                )
            # 累积分化压力足够高时触发
            elif speciation_pressure >= 0.05:  # 原0.08 -> 0.05
                has_pressure = True
            # 无隔离时需压力或资源条件
            elif (average_pressure >= pressure_threshold or resource_pressure >= resource_threshold):
                # 早期：任一条件满足即可
                if is_early_game:
                    has_pressure = True
                else:
                    # 后期条件放宽：资源压力0.35或饱和度0.4即可
                    if resource_pressure >= 0.35 or niche_saturation > 0.4:
                        has_pressure = True
                    else:
                        has_pressure = False
            elif evo_potential >= evo_threshold:  # 高演化潜力可单独触发
                has_pressure = True
            # 【新增】累积分化压力兜底
            elif speciation_pressure >= 0.03 and candidate_population >= min_population * 1.5:
                has_pressure = True
                logger.debug(f"[累积压力分化] {species.common_name}: speciation_pressure={speciation_pressure:.2f}>=0.03")
            else:
                has_pressure = False
            
            # 【新增】植物专用分化条件
            is_plant = PlantTraitConfig.is_plant(species)
            plant_milestone_ready = False
            if is_plant:
                # 检查植物是否接近里程碑
                milestone_progress = species.morphology_stats.get("milestone_progress", 0.0)
                next_milestone = plant_evolution_service.get_next_milestone(species)
                
                if next_milestone:
                    is_met, readiness, _ = plant_evolution_service.check_milestone_requirements(
                        species, next_milestone.id
                    )
                    
                    # 如果里程碑条件满足，强制触发分化（阶段升级）
                    if is_met:
                        has_pressure = True
                        plant_milestone_ready = True
                        speciation_type = f"里程碑演化：{next_milestone.name}"
                        logger.info(
                            f"[植物里程碑] {species.common_name} 触发里程碑分化：{next_milestone.name}"
                        )
                    # 如果接近里程碑（readiness > 80%），增加分化概率
                    elif readiness > 0.8:
                        speciation_pressure += 0.1 * readiness
                        logger.debug(
                            f"[植物里程碑进度] {species.common_name} 接近里程碑 {next_milestone.name} "
                            f"(准备度 {readiness:.0%})"
                        )
            
            # 自然辐射演化（繁荣物种分化）
            # 【大浪淘沙v3】大幅提高辐射演化概率，降低门槛
            if not has_pressure:
                pop_ratio = survivors / min_population if min_population > 0 else 0
                
                # 【大浪淘沙v3】基础概率提高
                radiation_base = spec_config.radiation_base_chance  # 现在是0.15
                
                # 早期额外加成（从配置）
                early_bonus = 0.0
                min_pop_ratio_for_bonus = spec_config.radiation_pop_ratio_early if is_early_game else spec_config.radiation_pop_ratio_late
                if is_early_game and pop_ratio >= min_pop_ratio_for_bonus:
                    early_bonus = spec_config.radiation_early_bonus  # 现在是0.25
                
                # 【大浪淘沙v3】种群因子：降低门槛，提高加成
                if pop_ratio >= 1.5:  # 原2.0 -> 1.5
                    pop_factor = min(0.20, (pop_ratio - 1.5) * 0.05)  # 最多+0.20（原0.10）
                elif is_early_game and pop_ratio >= min_pop_ratio_for_bonus:
                    pop_factor = min(0.15, (pop_ratio - 0.5) * 0.10)  # 早期更宽松
                else:
                    pop_factor = 0.0
                
                # 【大浪淘沙v3】资源饱和加成：降低门槛
                saturation_factor = 0.0
                if niche_saturation > 0.5:  # 原0.7 -> 0.5
                    saturation_factor = (niche_saturation - 0.5) * 0.25  # 最多+0.125
                
                # 累积压力加成（提高权重）
                pressure_factor = speciation_pressure * 0.40  # 原0.20 -> 0.40
                
                radiation_chance = radiation_base + early_bonus + pop_factor + saturation_factor + pressure_factor
                
                # 植物加成提高
                if is_plant:
                    radiation_chance += 0.05  # 原0.03 -> 0.05
                
                # 【大浪淘沙v3】硬性上限提高
                max_radiation = spec_config.radiation_max_chance_early if is_early_game else spec_config.radiation_max_chance_late
                radiation_chance = min(max_radiation, radiation_chance)  # 早期60%，后期40%
                
                # 【大浪淘沙v3】无隔离惩罚减轻
                no_isolation_penalty = spec_config.no_isolation_penalty_early if is_early_game else spec_config.no_isolation_penalty_late
                if not is_isolated:
                    radiation_chance *= no_isolation_penalty  # 早期95%，后期70%
                
                # 【大浪淘沙v3】种群门槛降低
                min_pop_ratio = spec_config.radiation_pop_ratio_early if is_early_game else spec_config.radiation_pop_ratio_late
                if survivors >= min_population * min_pop_ratio and random.random() < radiation_chance:
                    has_pressure = True
                    speciation_type = "辐射演化"
                    logger.info(
                        f"[辐射演化] {species.common_name} 触发辐射演化 "
                        f"(种群:{survivors:,}/{min_population:,}={pop_ratio:.1f}x, "
                        f"饱和度:{niche_saturation:.1%}, 概率:{radiation_chance:.1%}, "
                        f"早期={is_early_game})"
                    )
                else:
                    # 【大浪淘沙v4】移除硬性跳过！
                    # 即使辐射演化随机检查没通过，分化候选也应该进入后续概率计算
                    # 只是把 has_pressure 标记为 False，后续会有更低的基础概率
                    has_pressure = False
                    speciation_type = "自然分化"
                    logger.debug(
                        f"[自然分化候选] {species.common_name}: "
                        f"辐射演化检查未通过，但作为候选进入概率计算 "
                        f"(radiation_chance={radiation_chance:.1%})"
                    )
            
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

            # 【早期兜底】防止早期(前100回合)连续多年无分化
            # - 若满足隔离或超大种群，则设定至少 45% 触发概率
            # - 其他早期候选至少 20%
            if turn_index < spec_config.early_game_turns:
                if is_isolated or candidate_population >= base_threshold * 2.0:
                    base_chance = max(base_chance, 0.45)
                else:
                    base_chance = max(base_chance, 0.20)
            
            speciation_bonus = 0.0
            speciation_type = "生态隔离"
            
            # 【一揽子修改】地理隔离为主通道
            # ========== 死亡率区间检查 ==========
            # 优选 5%~40%，>40% 线性衰减到 60%，>60% 拒绝
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
                continue
            
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
                geo_isolation_data = self._detect_geographic_isolation(lineage_code)
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
            coevolution_result = self._detect_coevolution(species, mortality_results)
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
                    continue
            
            speciation_chance *= migration_penalty
            
            # 【新增】AI 分化信号加成
            # 如果物种被 ModifierApplicator 识别为高分化信号候选，增加概率
            ai_boost = 0.0
            if lineage_code in self._ai_speciation_candidates:
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
            
            roll = random.random()
            if roll > speciation_chance:
                # 【平衡优化v3】分化失败时累积压力提升更快（0.08），上限提高（0.4）
                new_pressure = min(0.4, speciation_pressure + 0.08)
                species.morphology_stats["speciation_pressure"] = new_pressure
                species_repository.upsert(species)
                logger.info(
                    f"[分化失败] {species.common_name}: 掷骰{roll:.2f} > 概率{speciation_chance:.1%}, "
                    f"累积压力: {speciation_pressure:.1%} → {new_pressure:.1%}"
                )
                continue
            
            # 分化成功！
            logger.info(
                f"[分化成功!] {species.common_name}: 掷骰{roll:.2f} <= 概率{speciation_chance:.1%}"
            )
            
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
                # 【新增】获取该子代所属隔离簇的环境详情
                cluster_environment = None
                tile_environment = candidate_data.get("tile_environment") if candidate_data else None
                cluster_environments = candidate_data.get("cluster_environments", []) if candidate_data else []
                if cluster_environments and idx < len(cluster_environments):
                    cluster_environment = cluster_environments[idx]
                
                tile_context = self._generate_tile_context(
                    assigned_tiles, tile_populations, tile_mortality, 
                    mortality_gradient, is_isolated,
                    tile_environment=tile_environment,
                    cluster_environment=cluster_environment
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
                
                # 【命名提示】生成随机命名参考
                naming_seed = abs(hash(f"{new_code}-{species.lineage_code}-{idx}")) % 1_000_000_007
                self.naming_hint_generator.set_seed(naming_seed)
                naming_hints = self.naming_hint_generator.generate_compact_hint()
                
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
                    # 【新增】生态位探索策略（指导子代往不同生态位方向演化）
                    "niche_exploration_strategy": rule_constraints.get("niche_exploration_strategy", "保守继承型"),
                    "niche_exploration_description": rule_constraints.get("niche_exploration_description", ""),
                    "niche_exploration_full": rule_constraints.get("niche_exploration_full", ""),
                    "target_diet_focus": rule_constraints.get("target_diet_focus", "与父代相同"),
                    "target_body_size_trend": rule_constraints.get("target_body_size_trend", "similar"),
                    "target_ecological_role": rule_constraints.get("target_ecological_role", ""),
                    "competition_with_parent": rule_constraints.get("competition_with_parent", "direct"),
                    # 【新增】时代信息
                    "era_summary": rule_constraints.get("era_summary", ""),
                    "era_single_cap": rule_constraints.get("era_single_cap", 15),
                    "era_total_cap": rule_constraints.get("era_total_cap", 100),
                    # 【新增】增强预算上下文（边际递减、突破机会、栖息地加成）
                    "diminishing_returns_context": rule_constraints.get("diminishing_returns_context", ""),
                    "breakthrough_opportunities": rule_constraints.get("breakthrough_opportunities", ""),
                    "habitat_specialization_bonus": rule_constraints.get("habitat_specialization_bonus", ""),
                    "strategy_recommendation": rule_constraints.get("strategy_recommendation", ""),
                    "budget_usage_percent": rule_constraints.get("budget_usage_percent", 0.5),
                    "remaining_budget": rule_constraints.get("remaining_budget", 50),
                    # 【新增】捕食关系信息
                    "diet_type": species.diet_type or "omnivore",
                    "prey_species_summary": self._summarize_prey_species(species),
                    # 【新增】基因多样性状态
                    "gene_diversity_radius": getattr(species, "gene_diversity_radius", 0.35) or 0.35,
                    "gene_stability": getattr(species, "gene_stability", 0.5) or 0.5,
                    "explored_directions": len(getattr(species, "explored_directions", []) or []),
                    # 【新增】休眠基因信息，智能筛选后指导AI分化方向
                    "dormant_genes_summary": self._summarize_dormant_genes(
                        species, 
                        pressure_types=self._current_pressure_types,
                        pressure_strength=average_pressure
                    ),
                    # 【新增】器官枚举提示（闭集 organ_key）
                    "organ_key_catalog": "\n".join(
                        [f"- {c['organ_key']} ({c['category']})：{c['default_name']}" for c in self._organ_catalog]
                    ),
                    # 【新增】成熟器官上下文（自由器官演化系统）
                    "mature_organs_context": self.organ_evolution_service.build_mature_organs_context(species),
                    # 【命名提示】随机命名参考
                    "naming_hints": naming_hints,
                }
                
                entries.append({
                    "ctx": {
                        "parent": species,
                        "new_code": new_code,
                        "population": population,
                        "ai_payload_input": ai_payload,  # 原始输入，用于fallback
                        "speciation_type": speciation_type,
                        "assigned_tiles": assigned_tiles,  # 【新增】该子代的栖息地块
                        "average_pressure": average_pressure,  # 【修复】添加压力信息用于fallback
                    },
                    "payload": ai_payload,
                })
        
        if not entries and not self._deferred_requests:
            return []

        # 【优化】分离背景物种和非背景物种的 entries
        # 背景物种直接走规则生成，不调用 AI，节省 Token 和时间
        background_entries: list[dict] = []
        ai_entries: list[dict] = []
        
        for entry in entries:
            parent = entry["ctx"]["parent"]
            if getattr(parent, 'is_background', False):
                background_entries.append(entry)
            else:
                ai_entries.append(entry)
        
        if background_entries:
            logger.info(
                f"[分化优化] 检测到 {len(background_entries)} 个背景物种分化，"
                f"跳过 AI 直接使用规则生成"
            )

        # 合并上回合遗留请求，并限制本回合最大任务数（只针对非背景物种）
        pending = self._deferred_requests + ai_entries
        if len(pending) > self.max_deferred_requests:
            pending = pending[:self.max_deferred_requests]
        active_batch = pending[: self.max_speciation_per_turn]
        self._deferred_requests = pending[self.max_speciation_per_turn :]

        if not active_batch and not background_entries:
            logger.info("[分化] 没有可执行的分化任务，本回合跳过")
            return []

        logger.info(f"[分化] 开始批量处理 {len(active_batch)} 个AI分化任务 + {len(background_entries)} 个规则分化任务 (剩余排队 {len(self._deferred_requests)})")
        
        # ========== 【优化】先处理背景物种的规则分化 ==========
        # 背景物种完全跳过 AI，直接使用规则引擎生成，节省 Token 和时间
        # 【改进】现在使用完整的规则引擎约束系统，生成高质量的物种数据
        background_results: list[tuple[dict, dict]] = []  # [(entry, ai_content)]
        
        # 构建环境压力字典（用于规则引擎）
        env_pressure_dict = {}
        if pressures:
            for p in pressures:
                if hasattr(p, 'category') and hasattr(p, 'intensity'):
                    env_pressure_dict[p.category] = p.intensity
        
        for entry in background_entries:
            ctx = entry["ctx"]
            ai_content = self._generate_rule_based_fallback(
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
            logger.info(f"[规则分化] 完成 {len(background_results)} 个背景物种的规则生成")
        
        # ========== AI 分化（仅针对非背景物种）==========
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
            
            logger.info(f"[分化] 共 {len(batches)} 个AI批次（每批≤{batch_size}个），开始高并发执行")
            
            async def process_batch(batch_entries: list) -> list:
                """处理单个批次"""
                batch_payload = self._build_batch_payload(
                    batch_entries,
                    average_pressure,
                    pressure_summary,
                    map_changes,
                    major_events,
                    turn_index,
                )
                # 【混合模式】传入entries用于判断是否为植物批次
                batch_results = await self._call_batch_ai(batch_payload, stream_callback, batch_entries)
                return self._parse_batch_results(batch_results, batch_entries)
            
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
                    logger.error(f"[分化] 批次 {batch_idx + 1} 失败: {batch_result}")
                    results.extend([batch_result] * len(batches[batch_idx]))
                else:
                    success_count = len([r for r in batch_result if not isinstance(r, Exception)])
                    logger.info(f"[分化] 批次 {batch_idx + 1} 完成，成功解析 {success_count} 个结果")
                    results.extend(batch_result)

        # 3. 结果处理与写入
        logger.info(f"[分化] 开始处理 {len(results)} 个AI结果 + {len(background_results)} 个规则结果")
        new_species_events: list[BranchingEvent] = []
        for res, entry in zip(results, active_batch):
            ctx = entry["ctx"]  # 从entry中提取ctx
            
            # 【优化】检查是否需要使用规则fallback
            retry_count = entry.get("_retry_count", 0)
            use_fallback = False
            
            if isinstance(res, Exception):
                logger.error(f"[分化AI异常] {res}")
                if retry_count >= 2:
                    use_fallback = True
                    logger.info(f"[分化] 重试{retry_count}次后AI仍失败，使用规则fallback")
                else:
                    self._queue_deferred_request(entry)
                    continue

            ai_content = res
            if not use_fallback and not isinstance(ai_content, dict):
                logger.warning(f"[分化警告] AI返回的content不是dict类型: {type(ai_content)}, 内容: {ai_content}")
                if retry_count >= 2:
                    use_fallback = True
                else:
                    self._queue_deferred_request(entry)
                    continue
            if not use_fallback:
                ai_content = self._normalize_ai_content(ai_content)

            required_fields = ["latin_name", "common_name", "description"]
            if not use_fallback and any(not ai_content.get(field) for field in required_fields):
                logger.warning(
                    "[分化警告] AI返回缺少必要字段: %s",
                    {field: ai_content.get(field) for field in required_fields},
                )
                if retry_count >= 2:
                    use_fallback = True
                else:
                    self._queue_deferred_request(entry)
                    continue
            
            # 【新增】使用规则fallback生成内容
            if use_fallback:
                ai_content = self._generate_rule_based_fallback(
                    parent=ctx["parent"],
                    new_code=ctx["new_code"],
                    survivors=ctx["population"],
                    speciation_type=ctx["speciation_type"],
                    average_pressure=average_pressure,
                    environment_pressure=env_pressure_dict,
                    turn_index=turn_index,
                )
                ai_content = self._normalize_ai_content(ai_content)

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
                speciation_type=ctx["speciation_type"],  # 【一揽子修改】传递分化类型
            )
            logger.info(f"[分化] 新物种 {new_species.common_name} created_turn={new_species.created_turn} (传入的turn_index={turn_index})")
            new_species = species_repository.upsert(new_species)
            # 记录本回合亲本子代计数（与杂交共享上限）
            parent_code = ctx["parent"].lineage_code
            try:
                turn_offspring_counts[parent_code] += 1
                ctx.turn_offspring_counts = turn_offspring_counts  # type: ignore[attr-defined]
            except Exception:
                pass
            logger.info(f"[分化] upsert后 {new_species.common_name} created_turn={new_species.created_turn}")
            # 记录本回合亲本子代计数（与杂交共享上限）
            parent_code = ctx["parent"].lineage_code
            try:
                turn_offspring_counts[parent_code] += 1
                ctx.turn_offspring_counts = turn_offspring_counts  # type: ignore[attr-defined]
            except Exception:
                pass
            
            # 【描述增强】如果使用了规则fallback，将物种加入增强队列
            if ai_content.get("_is_rule_fallback"):
                self._rule_fallback_species.append((new_species, ctx["parent"], ctx["speciation_type"]))
            
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
            
            # 【修复】即使没有 genus 也调用继承方法（处理新突变和额外基因）
            genus = genus_repository.get_by_code(new_species.genus_code) if new_species.genus_code else None
            self.gene_library_service.inherit_dormant_genes(ctx["parent"], new_species, genus)
            species_repository.upsert(new_species)
            
            # 【AI指定基因激活】处理 AI 返回的 activated_genes
            ai_activated_genes = ai_content.get("activated_genes", []) if ai_content else []
            if ai_activated_genes:
                activated_count = self._process_ai_activated_genes(new_species, ai_activated_genes, turn_index)
                if activated_count > 0:
                    species_repository.upsert(new_species)
                    logger.info(f"[AI基因激活] {new_species.common_name} 激活了 {activated_count} 个AI指定的基因")
            
            # 【LLM新基因】处理 AI 返回的 new_dormant_genes（分化时生成的新休眠基因）
            ai_new_genes = ai_content.get("new_dormant_genes") if ai_content else None
            if ai_new_genes:
                added_count = self._process_ai_new_dormant_genes(new_species, ai_new_genes, turn_index)
                if added_count > 0:
                    species_repository.upsert(new_species)
                    logger.info(f"[LLM新基因] {new_species.common_name} 获得了 {added_count} 个LLM生成的新休眠基因")
            
            # 【分化突破】仅激活已有休眠基因（不再本地生成新基因）
            breakthrough_result = self._try_speciation_breakthrough(new_species, turn_index)
            if breakthrough_result:
                species_repository.upsert(new_species)
                logger.info(
                    f"[分化突破] {new_species.common_name} 在分化中激活休眠基因: "
                    f"{breakthrough_result}"
                )
            
            # 【植物演化】主动检查并触发里程碑
            milestone_result = self._check_and_trigger_plant_milestones(new_species, turn_index)
            if milestone_result:
                # 里程碑触发后需要重新保存物种
                species_repository.upsert(new_species)
                logger.info(
                    f"[植物里程碑] {new_species.common_name} 触发里程碑: "
                    f"{milestone_result.get('milestone_name', 'unknown')}"
                )
            
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
        
        # ========== 【优化】处理背景物种的规则分化结果 ==========
        for entry, ai_content in background_results:
            ctx = entry["ctx"]
            
            logger.info(
                f"[规则分化结果] 背景物种: {ai_content.get('common_name')}, description长度: {len(str(ai_content.get('description', '')))}"
            )
            
            # 【新增】规则引擎后验证：验证并修正输出
            ai_content = self.rules.validate_and_fix(
                ai_content, 
                ctx["parent"],
                preprocess_result=None
            )

            new_species = self._create_species(
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
            
            logger.info(f"[规则分化] 新背景物种 {new_species.common_name} created_turn={new_species.created_turn}")
            new_species = species_repository.upsert(new_species)
            
            # 将背景物种加入增强队列（用于模板描述和向量遗传）
            self._rule_fallback_species.append((new_species, ctx["parent"], ctx["speciation_type"]))
            
            # 处理分配地块
            assigned_tiles = ctx.get("assigned_tiles", set())
            self._inherit_habitat_distribution(
                parent=ctx["parent"],
                child=new_species,
                turn_index=turn_index,
                assigned_tiles=assigned_tiles
            )
            
            # 【修复】即使没有 genus 也调用继承方法（处理新突变和额外基因）
            if hasattr(self, 'gene_library_service') and self.gene_library_service:
                genus = genus_repository.get_by_code(new_species.genus_code) if new_species.genus_code else None
                self.gene_library_service.inherit_dormant_genes(ctx["parent"], new_species, genus)
                species_repository.upsert(new_species)
            
            # 【分化突破】背景物种仅激活已有休眠基因（不生成新基因）
            breakthrough_result = self._try_speciation_breakthrough(new_species, turn_index)
            if breakthrough_result:
                species_repository.upsert(new_species)
                logger.info(
                    f"[分化突破-背景] {new_species.common_name} 在分化中激活休眠基因: "
                    f"{breakthrough_result}"
                )
            
            species_repository.log_event(
                LineageEvent(
                    lineage_code=ctx["new_code"],
                    event_type="speciation",
                    payload={"parent": ctx["parent"].lineage_code, "turn": turn_index},
                )
            )
            
            event_desc = f"{ctx['parent'].common_name}在压力{average_pressure:.1f}条件下分化出{ctx['new_code']}（背景物种）"
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
        
        # 【描述增强】处理规则fallback物种的描述增强
        if self._rule_fallback_species:
            logger.info(f"[描述增强] 开始处理 {len(self._rule_fallback_species)} 个规则生成物种的描述增强")
            try:
                # 将物种加入增强队列
                for species, parent, speciation_type in self._rule_fallback_species:
                    self.description_enhancer.queue_for_enhancement(
                        species=species,
                        parent=parent,
                        speciation_type=speciation_type,
                        is_hybrid=False,
                    )
                
                # 批量处理增强队列
                enhanced_list = await self.description_enhancer.process_queue_async(
                    max_items=20,  # 每回合最多处理20个
                    timeout_per_item=25.0,
                )
                
                # 保存增强后的物种描述
                for enhanced_species in enhanced_list:
                    species_repository.upsert(enhanced_species)
                
                logger.info(f"[描述增强] 完成 {len(enhanced_list)}/{len(self._rule_fallback_species)} 个物种描述增强")
            except Exception as e:
                logger.error(f"[描述增强] 处理失败: {e}")
            finally:
                self._rule_fallback_species.clear()
            
        return new_species_events

    def _build_batch_payload(
        self,
        entries: list[dict],
        average_pressure: float,
        pressure_summary: str,
        map_changes: list,
        major_events: list,
        turn_index: int,
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
            
            # 【植物演化】为植物物种添加专有上下文
            parent_species = ctx['parent']
            is_plant = PlantTraitConfig.is_plant(parent_species)
            plant_context = ""
            
            if is_plant:
                # 获取植物演化阶段信息
                life_form_stage = getattr(parent_species, 'life_form_stage', 0)
                growth_form = getattr(parent_species, 'growth_form', 'aquatic')
                stage_name = PlantTraitConfig.get_stage_name(life_form_stage)
                
                # 获取里程碑提示
                milestone_hints = plant_evolution_service.get_milestone_hints(parent_species)
                
                # 获取植物特质摘要
                traits = parent_species.abstract_traits or {}
                plant_trait_summary = ", ".join([
                    f"{k}={v:.1f}" for k, v in traits.items()
                    if k in ["光合效率", "根系发达度", "保水能力", "木质化程度", "种子化程度", "多细胞程度"]
                ])
                
                # 【新增】获取竞争上下文
                # 从entries中收集所有父代物种作为species_list
                all_parent_species = [e["ctx"]["parent"] for e in entries]
                competition_context = plant_competition_calculator.format_competition_context(
                    parent_species, all_parent_species
                )
                
                plant_context = f"""
- 【🌱植物演化信息】:
  - 当前阶段: {life_form_stage} ({stage_name})
  - 生长形式: {growth_form}
  - 植物特质: {plant_trait_summary or '无'}
  - 里程碑提示:
{milestone_hints}
- {competition_context}
- 【植物阶段约束⚠️】:
  - 阶段只能升级1级（{life_form_stage} → {life_form_stage + 1}）
  - 登陆条件(阶段2→3): 保水能力>=5.0, 耐旱性>=4.0
  - 成为树木条件: 木质化程度>=7.0, 阶段>=5"""
            
            # 【新增】获取 AI 演化提示（来自生态智能体）
            parent_code = payload.get('parent_lineage')
            evolution_hint = self.get_evolution_hint(parent_code)
            ai_evolution_context = ""
            if evolution_hint:
                ai_directions = evolution_hint.get("ai_directions", [])
                if ai_directions:
                    ai_evolution_context = f"""
- 【🧠AI演化建议】（来自生态智能体评估）:
  - 建议方向: {', '.join(ai_directions[:5])}
  - 请参考这些方向设计子代的特质变化！"""
                    logger.debug(f"[分化] {parent_code} 使用AI演化提示: {ai_directions}")
            
            species_info = f"""
【物种 {idx + 1}】{'🌱植物' if is_plant else '🦎动物'}
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
{organ_constraints}{plant_context}{ai_evolution_context}
- 【地块背景】: {tile_context[:150]}
- 区域死亡率: {region_mortality:.1%}（{region_pressure_level}）
- 死亡率梯度: {mortality_gradient:.1%}
- 隔离区域数: {num_isolation_regions}
- 地理隔离: {'是' if is_geographic_isolation else '否'}"""
            species_list_parts.append(species_info)
        
        species_list = "\n".join(species_list_parts)
        
        # 【修复】不再转义 species_list 中的花括号
        # prompt format(**payload) 不会递归解析 value 中的花括号
        species_list_escaped = species_list
        
        time_config = get_time_config(max(turn_index, 0))
        time_context = (
            "\n=== ⏳ 时间尺度上下文 (Chronos Flow) ===\n"
            f"当前地质年代：{time_config['era_name']}\n"
            f"时间流逝速度：{time_config['years_per_turn']:,} 年/回合\n"
            f"演化指导原则：{time_config.get('evolution_guide', 'Standard')}\n"
        )

        # 【命名提示】为批量分化生成随机命名参考
        batch_naming_seed = abs(hash(f"batch-{turn_index}-{len(entries)}")) % 1_000_000_007
        self.naming_hint_generator.set_seed(batch_naming_seed)
        naming_hints = self.naming_hint_generator.generate_naming_prompt(samples_per_category=2)
        
        payload_data = {
            "average_pressure": average_pressure,
            "pressure_summary": pressure_summary,
            "map_changes_summary": self._summarize_map_changes(map_changes) if map_changes else "无显著地形变化",
            "major_events_summary": self._summarize_major_events(major_events) if major_events else "无重大事件",
            # 【修复】同时提供 major_events 字段
            "major_events": self._summarize_major_events(major_events) if major_events else "无重大事件",
            "species_list": species_list_escaped,
            "batch_size": len(entries),
            "time_context": time_context,
            "naming_hints": naming_hints,
        }
        first_payload = entries[0]["payload"] if entries else {}
        payload_data.update(
            {
                # 张量系统预先计算的预算约束，LLM 只需输出增益
                "max_increase": 3.0,
                "single_max": 2.0,
                "era_caps": first_payload.get("trait_budget_summary", "依时代上限"),
                "tradeoff_ratio": getattr(self.tradeoff_calculator, "tradeoff_ratio", getattr(self, "tradeoff_ratio", 0.7)),
                # 为精简版prompt提供摘要
                "parent_summary": species_list_escaped,
                "trigger_context": pressure_summary,
            }
        )
        logger.debug(f"[分化批量] Payload keys: {list(payload_data.keys())}")
        return payload_data
    
    async def _call_batch_ai(
        self, 
        payload: dict, 
        stream_callback: Callable[[str], Awaitable[None] | None] | None,
        entries: list[dict] | None = None
    ) -> dict:
        """调用批量分化 AI 接口（带心跳检测）
        
        【混合模式】
        - 如果批次全是植物，使用 plant_speciation prompt
        - 否则使用通用 speciation_batch prompt
        
        【内共生检测】
        - 并发尝试触发内共生事件（极低概率）
        
        Args:
            payload: 请求参数
            stream_callback: 流式回调（用于心跳）
            entries: 原始entries列表，用于判断是否为植物批次
        """
        from ...ai.streaming_helper import stream_invoke_with_heartbeat
        import asyncio
        
        # === 【新增】内共生并发检测 ===
        endosymbiosis_tasks = []
        endosymbiosis_indices = []  # 记录对应的 entries 索引
        
        if entries:
            pressure = payload.get("average_pressure", 0.0)
            pressure_context = payload.get("pressure_summary", "")
            
            for i, entry in enumerate(entries):
                parent = entry["ctx"]["parent"]
                turn_index = entry["ctx"].get("turn_index", 0)
                
                # 并发启动内共生尝试（不阻塞主流程）
                task = asyncio.create_task(
                    self._attempt_endosymbiosis_async(
                        parent, pressure, pressure_context, turn_index
                    )
                )
                endosymbiosis_tasks.append(task)
                endosymbiosis_indices.append(i)

        # 【植物混合模式】检测是否为纯植物批次
        prompt_name = "speciation_batch"  # 默认
        batch_type = "动物"
        if entries:
            is_all_plants = all(
                PlantTraitConfig.is_plant(e["ctx"]["parent"]) for e in entries
            )
            if is_all_plants:
                prompt_name = "plant_speciation_batch"
                batch_type = "植物"
                # 为植物批次添加器官类别信息
                if entries:
                    first_parent = entries[0]["ctx"]["parent"]
                    current_stage = getattr(first_parent, 'life_form_stage', 0)
                    payload["organ_categories_info"] = plant_evolution_service.get_organ_category_info_for_prompt(current_stage)
                logger.debug(f"[分化批量] 使用植物专用Prompt，批次大小: {len(entries)}")
        
        # 【优化】使用流式调用 + 智能空闲超时（只要AI在输出就不会超时）
        # 【修复】正确传递 event_type 和 category，不再丢失事件类型
        def heartbeat_callback(event_type: str, message: str, category: str):
            if stream_callback:
                try:
                    result = stream_callback(event_type, message, category)
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
                except Exception:
                    pass
        
        batch_size = len(entries) if entries else 0
        
        # 启动 Batch AI Task
        batch_ai_task = asyncio.create_task(
            stream_invoke_with_heartbeat(
                router=self.router,
                capability=prompt_name,
                payload=payload,
                task_name=f"分化[{batch_type}×{batch_size}]",
                idle_timeout=90,  # 智能空闲超时：90秒无输出才超时
                heartbeat_interval=2.0,
                event_callback=heartbeat_callback if stream_callback else None,
            )
        )
        
        # 等待所有任务 (Batch + Endosymbiosis)
        # 注意：我们允许内共生失败（返回None），也允许Batch失败（异常）
        all_tasks = [batch_ai_task] + endosymbiosis_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        batch_result = results[0]
        endo_results = results[1:]
        
        # 处理 Batch 结果
        final_content = {}
        if isinstance(batch_result, dict):
            # 正常的 invoke_with_heartbeat 返回包含 content 的 dict
            final_content = batch_result.get("content", {}) if "content" in batch_result else batch_result
        elif isinstance(batch_result, Exception):
            # Batch 失败处理
            if isinstance(batch_result, asyncio.TimeoutError):
                logger.warning("[分化批量] AI请求空闲超时（90秒无输出），将使用规则fallback")
                final_content = {"_timeout": True, "_use_fallback": True}
            else:
                logger.error(f"[分化批量] 请求异常: {batch_result}，将使用规则fallback")
                final_content = {"_error": str(batch_result), "_use_fallback": True}
        
        if not isinstance(final_content, dict):
            final_content = {}

        # === 注入内共生结果 ===
        # 将成功的内共生结果暂存到 _endo_overrides 字段
        # 后续 _parse_batch_results 会优先使用这些结果
        
        valid_endo_overrides = {}
        for idx, res in zip(endosymbiosis_indices, endo_results):
            if isinstance(res, dict) and res.get("is_endosymbiosis"):
                res["request_id"] = idx # 确保 ID 匹配
                valid_endo_overrides[idx] = res
        
        if valid_endo_overrides:
             final_content["_endo_overrides"] = valid_endo_overrides
             logger.info(f"[内共生] 成功捕获 {len(valid_endo_overrides)} 个内共生事件，准备注入")

        return final_content
    
    def _parse_batch_results(
        self, 
        batch_response: dict, 
        entries: list[dict]
    ) -> list[dict | Exception]:
        """解析批量响应，返回与 entries 对应的结果列表
        
        【内共生支持】优先使用 _endo_overrides 中的结果
        【重要修复】如果响应包含 _use_fallback 标记，立即为所有entry生成规则fallback结果
        """
        results = []
        
        # 【新增】提取内共生覆盖结果
        endo_overrides = {}
        if isinstance(batch_response, dict):
             endo_overrides = batch_response.pop("_endo_overrides", {})
        
        # 【修复】检测是否需要使用fallback（AI超时或错误）
        if isinstance(batch_response, dict) and batch_response.get("_use_fallback"):
            logger.info(f"[分化批量] 检测到fallback标记，为 {len(entries)} 个物种生成规则fallback")
            for idx, entry in enumerate(entries):
                # 【新增】即使是 fallback，如果内共生成功了，也优先使用内共生
                if idx in endo_overrides:
                    results.append(endo_overrides[idx])
                    continue
                    
                ctx = entry["ctx"]
                fallback_result = self._generate_rule_based_fallback(
                    parent=ctx["parent"],
                    new_code=ctx["new_code"],
                    survivors=ctx["population"],
                    speciation_type=ctx["speciation_type"],
                    average_pressure=ctx.get("average_pressure", 3.0),
                )
                # 标记为fallback结果
                fallback_result["_is_fallback"] = True
                results.append(fallback_result)
            return results
        
        if not isinstance(batch_response, dict):
            logger.warning(f"[分化批量] 响应不是字典类型: {type(batch_response)}")
            # 【修复】改为生成fallback而不是返回异常
            for idx, entry in enumerate(entries):
                if idx in endo_overrides:
                    results.append(endo_overrides[idx])
                    continue
                    
                ctx = entry["ctx"]
                fallback_result = self._generate_rule_based_fallback(
                    parent=ctx["parent"],
                    new_code=ctx["new_code"],
                    survivors=ctx["population"],
                    speciation_type=ctx["speciation_type"],
                    average_pressure=ctx.get("average_pressure", 3.0),
                )
                fallback_result["_is_fallback"] = True
                results.append(fallback_result)
            return results
        
        # 尝试从响应中提取 results 数组
        ai_results = batch_response.get("results", [])
        if not isinstance(ai_results, list):
            # 可能响应本身就是结果数组
            if isinstance(batch_response, list):
                ai_results = batch_response
            else:
                logger.warning(f"[分化批量] 响应中没有 results 数组，使用规则fallback")
                # 【修复】使用fallback而不是返回异常
                for entry in entries:
                    ctx = entry["ctx"]
                    fallback_result = self._generate_rule_based_fallback(
                        parent=ctx["parent"],
                        new_code=ctx["new_code"],
                        survivors=ctx["population"],
                        speciation_type=ctx["speciation_type"],
                        average_pressure=ctx.get("average_pressure", 3.0),
                    )
                    fallback_result["_is_fallback"] = True
                    results.append(fallback_result)
                return results
        
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
            # 【新增】检查是否有内共生覆盖（优先使用）
            if idx in endo_overrides:
                results.append(endo_overrides[idx])
                continue

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
                    logger.warning(f"[分化批量] 结果 {idx} 缺少必要字段，使用规则fallback")
                    # 【修复】使用fallback而不是返回异常
                    ctx = entry["ctx"]
                    fallback_result = self._generate_rule_based_fallback(
                        parent=ctx["parent"],
                        new_code=ctx["new_code"],
                        survivors=ctx["population"],
                        speciation_type=ctx["speciation_type"],
                        average_pressure=ctx.get("average_pressure", 3.0),
                    )
                    fallback_result["_is_fallback"] = True
                    results.append(fallback_result)
            else:
                logger.warning(f"[分化批量] 无法匹配结果 {idx}，使用规则fallback")
                # 【修复】使用fallback而不是返回异常
                ctx = entry["ctx"]
                fallback_result = self._generate_rule_based_fallback(
                    parent=ctx["parent"],
                    new_code=ctx["new_code"],
                    survivors=ctx["population"],
                    speciation_type=ctx["speciation_type"],
                    average_pressure=ctx.get("average_pressure", 3.0),
                )
                fallback_result["_is_fallback"] = True
                results.append(fallback_result)
        
        return results

    async def _call_ai_wrapper(self, payload: dict, stream_callback: Callable[[str], Awaitable[None] | None] | Callable[[str, str, str], None] | None) -> dict:
        """AI调用包装器（带心跳检测）"""
        from ...ai.streaming_helper import invoke_with_heartbeat
        import asyncio
        
        def heartbeat_callback(event_type: str, message: str, category: str):
            if stream_callback:
                try:
                    # 尝试以3参数方式调用 (event_type, message, category)
                    # 这是为了兼容 SpeciationStage 传入的完整事件回调
                    try:
                        result = stream_callback(event_type, message, category)
                    except TypeError:
                        # 如果失败，回退到1参数方式 (message only)
                        # 用于兼容旧的仅接收消息的回调
                        result = stream_callback(message)
                    
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
                except Exception as e:
                    # 避免回调错误中断主流程，但记录日志
                    logger.warning(f"[Speciation] 心跳回调失败: {e}")
        
        try:
            response = await invoke_with_heartbeat(
                router=self.router,
                capability="speciation",
                payload=payload,
                task_name="单物种分化",
                timeout=90,
                heartbeat_interval=2.0,
                event_callback=heartbeat_callback if stream_callback else None,
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
        """将失败的AI请求放回队列，供下一回合重试。
        
        【优化】添加重试计数，超过阈值时使用规则fallback
        """
        if len(self._deferred_requests) >= self.max_deferred_requests:
            return
        
        # 增加重试计数
        retry_count = entry.get("_retry_count", 0) + 1
        entry["_retry_count"] = retry_count
        
        # 如果重试超过3次，不再排队（会在处理时使用fallback）
        if retry_count > 3:
            logger.warning(f"[分化] 请求重试超过3次，将使用规则fallback: {entry.get('ctx', {}).get('new_code', 'unknown')}")
            return
        
        self._deferred_requests.append(entry)

    def _normalize_ai_content(self, ai_content: Any) -> Any:
        """将新格式的AI输出规范化为内部通用字段。
        
        - 如果提供了 innovations/gains，则汇总为 trait_changes
        - 缺少 key_innovations 时从 innovations 中提取
        """
        if not isinstance(ai_content, dict):
            return ai_content
        
        if not ai_content.get("trait_changes"):
            aggregated: dict[str, float] = {}
            key_innovations = list(ai_content.get("key_innovations") or [])
            innovations = ai_content.get("innovations") or []
            
            if isinstance(innovations, list):
                for inv in innovations:
                    if not isinstance(inv, dict):
                        continue
                    name = inv.get("name")
                    if name and name not in key_innovations:
                        key_innovations.append(name)
                    
                    gains = inv.get("gains") or {}
                    if isinstance(gains, dict):
                        for trait, delta in gains.items():
                            try:
                                val = float(str(delta).replace("+", ""))
                            except (ValueError, TypeError):
                                continue
                            aggregated[trait] = aggregated.get(trait, 0.0) + val
            
            if aggregated:
                ai_content["trait_changes"] = aggregated
            if key_innovations and not ai_content.get("key_innovations"):
                ai_content["key_innovations"] = key_innovations
        
        return ai_content
    
    def _generate_rule_based_fallback(
        self,
        parent: 'Species',
        new_code: str,
        survivors: int,
        speciation_type: str,
        average_pressure: float,
        environment_pressure: dict[str, float] | None = None,
        turn_index: int = 0,
    ) -> dict:
        """【优化】当AI持续失败时，使用规则引擎生成新物种内容
        
        这确保即使AI完全不可用，物种分化仍能进行。
        现在使用完整的规则引擎约束系统，生成高质量的物种数据。
        
        Args:
            parent: 父系物种
            new_code: 新物种编码
            survivors: 存活数
            speciation_type: 分化类型
            average_pressure: 平均压力
            environment_pressure: 环境压力字典（可选）
            turn_index: 当前回合（用于时代约束）
            
        Returns:
            可直接用于 _create_species 的内容字典
        """
        import random
        import hashlib
        
        # 使用 new_code 作为随机种子，确保相同物种生成一致的内容
        seed = int(hashlib.md5(new_code.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        
        # ========== 0. 使用规则引擎获取约束 ==========
        env_pressure = environment_pressure or {"temperature": 0, "humidity": 0}
        constraints = self.rules.preprocess(
            parent_species=parent,
            offspring_index=1,
            total_offspring=1,
            environment_pressure=env_pressure,
            pressure_context=speciation_type,
            turn_index=turn_index,
        )
        
        # ========== 1. 生成名称（优化：避免累加截断）==========
        parent_latin = parent.latin_name or "Species unknown"
        latin_parts = parent_latin.split()
        genus = latin_parts[0] if latin_parts else "Genus"
        
        # 根据分化类型和演化方向选择后缀
        evolution_direction = constraints.get("evolution_direction", "自然分化")
        
        suffix_map = {
            "环境适应型": ["robustus", "tolerans", "resistens", "durans", "fortis"],
            "活动强化型": ["velox", "agilis", "cursor", "celer", "mobilis"],
            "繁殖策略型": ["fecundus", "prolifer", "fertilis", "abundans", "vivax"],
            "防御特化型": ["armatus", "spinosus", "coriaceus", "tectus", "protectus"],
            "极端特化型": ["extremus", "ultimus", "maximus", "supremus", "insignis"],
        }
        suffixes = suffix_map.get(evolution_direction, ["novus", "adaptus", "evolutus", "mutatus", "diversus"])
        
        # 添加编码后缀避免重名
        code_suffix = new_code.replace(".", "").lower()[-3:]
        new_species_name = f"{genus} {rng.choice(suffixes)}_{code_suffix}"
        
        # 中文俗名：【优化】使用独立的名字系统，避免累加截断
        new_common_name = self._generate_background_species_name(
            parent=parent,
            evolution_direction=evolution_direction,
            habitat_type=parent.habitat_type,
            trophic_level=parent.trophic_level,
            rng=rng,
        )
        
        # ========== 2. 使用规则引擎生成特质变化 ==========
        trait_changes = {}
        
        # 从规则引擎获取建议的增强/减弱属性
        suggested_increases = constraints.get("suggested_increases", [])
        suggested_decreases = constraints.get("suggested_decreases", [])
        
        # 增强属性（使用规则引擎的预算）
        trait_budget = constraints.get("_trait_budget")
        if trait_budget:
            max_increase = trait_budget.total_increase_allowed
            max_decrease = trait_budget.total_decrease_required
            single_max = trait_budget.single_trait_max
        else:
            max_increase, max_decrease, single_max = 3.0, 1.5, 2.0
        
        # 分配增强点数
        total_increase = 0
        for trait in suggested_increases[:2]:  # 最多增强2个属性
            if trait and "随机" not in trait:
                change = rng.uniform(0.5, min(single_max, max_increase - total_increase))
                trait_changes[trait] = f"+{change:.1f}"
                total_increase += change
                if total_increase >= max_increase:
                    break
        
        # 分配减弱点数（权衡）
        total_decrease = 0
        for trait in suggested_decreases[:2]:  # 最多减弱2个属性
            if trait:
                change = rng.uniform(0.3, min(single_max * 0.5, max_decrease - total_decrease))
                trait_changes[trait] = f"-{change:.1f}"
                total_decrease += change
                if total_decrease >= max_decrease:
                    break
        
        # ========== 3. 生成器官演化（使用约束）==========
        organ_evolution = []
        organ_constraints = constraints.get("_organ_constraints", [])
        
        # 随机选择一个器官进行演化
        evolvable_organs = [
            oc for oc in organ_constraints 
            if oc.max_target_stage > oc.current_stage
        ]
        
        if evolvable_organs and rng.random() > 0.3:  # 70% 概率进行器官演化
            chosen = rng.choice(evolvable_organs)
            new_stage = min(chosen.max_target_stage, chosen.current_stage + 1)
            
            organ_names = {
                "locomotion": "运动器官",
                "sensory": "感觉器官",
                "metabolic": "代谢系统",
                "digestive": "消化系统",
                "defense": "防御结构",
                "reproduction": "繁殖系统",
            }
            stage_names = {
                1: "原基形成",
                2: "初级结构",
                3: "功能完善",
                4: "高度特化",
            }
            
            organ_evolution.append({
                "category": chosen.category,
                "current_stage": chosen.current_stage,
                "target_stage": new_stage,
                "description": f"{organ_names.get(chosen.category, chosen.category)}发展至{stage_names.get(new_stage, '新阶段')}"
            })
        
        # ========== 4. 生成形态变化 ==========
        parent_morph = parent.morphology_stats or {}
        morphology_changes = {}
        
        # 体长变化（±20%）
        base_length = parent_morph.get("body_length_cm", 10.0)
        length_ratio = rng.uniform(0.85, 1.15)
        morphology_changes["body_length_cm"] = length_ratio
        
        # 体重变化（与体长相关，但有独立变异）
        base_weight = parent_morph.get("body_weight_g", 100.0)
        weight_ratio = length_ratio ** 2.5 * rng.uniform(0.9, 1.1)  # 体重与体长的立方近似
        morphology_changes["body_weight_g"] = weight_ratio
        
        # ========== 5. 生成描述（更详细）==========
        habitat_map = {
            "marine": "海洋", "freshwater": "淡水", "terrestrial": "陆地",
            "amphibious": "两栖", "aerial": "空中", "deep_sea": "深海", "coastal": "沿岸"
        }
        diet_map = {
            "herbivore": "植食性", "carnivore": "肉食性", "omnivore": "杂食性",
            "detritivore": "腐食性", "autotroph": "自养型"
        }
        
        habitat_str = habitat_map.get(parent.habitat_type, parent.habitat_type or "未知")
        diet_str = diet_map.get(parent.diet_type, parent.diet_type or "杂食性")
        direction_desc = constraints.get("direction_description", "自然选择")
        
        # 构建详细描述
        description_parts = [
            f"{new_common_name}是从{parent.common_name}分化而来的{habitat_str}{diet_str}物种。",
            f"在{speciation_type}的选择压力下，该物种发展出{direction_desc}的演化策略。",
        ]
        
        # 添加关键特质描述
        if trait_changes:
            changes_desc = []
            for trait, change in trait_changes.items():
                if change.startswith("+"):
                    changes_desc.append(f"{trait}增强")
                else:
                    changes_desc.append(f"{trait}降低")
            description_parts.append(f"主要适应性变化包括{'、'.join(changes_desc)}。")
        
        # 添加器官演化描述
        if organ_evolution:
            organ_desc = organ_evolution[0].get("description", "器官结构优化")
            description_parts.append(f"形态上，{organ_desc}。")
        
        description = "".join(description_parts)
        
        # ========== 6. 生成关键创新 ==========
        key_innovations = [f"{speciation_type}适应"]
        if organ_evolution:
            key_innovations.append(organ_evolution[0].get("description", "器官演化"))
        if suggested_increases:
            key_innovations.append(f"{suggested_increases[0]}强化")
        
        # ========== 7. 返回完整内容 ==========
        logger.info(
            f"[规则Fallback] 为 {new_code} 生成规则物种: "
            f"{new_common_name} ({evolution_direction})"
        )
        
        return {
            "latin_name": new_species_name,
            "common_name": new_common_name,
            "description": description,
            "habitat_type": parent.habitat_type,
            "trophic_level": parent.trophic_level,
            "diet_type": parent.diet_type,
            "prey_species": list(parent.prey_species) if parent.prey_species else [],
            "prey_preferences": dict(parent.prey_preferences) if parent.prey_preferences else {},
            "key_innovations": key_innovations,
            "trait_changes": trait_changes,
            "morphology_changes": morphology_changes,
            "event_description": f"因{speciation_type}从{parent.common_name}分化，采用{evolution_direction}策略",
            "speciation_type": speciation_type,
            "reason": f"在{speciation_type}条件下，通过{direction_desc}实现自然选择",
            "organ_evolution": organ_evolution,
            "_is_rule_fallback": True,  # 标记为规则生成
            "_evolution_direction": evolution_direction,  # 记录演化方向供后续使用
        }
    
    def _generate_background_species_name(
        self,
        parent: 'Species',
        evolution_direction: str,
        habitat_type: str,
        trophic_level: float,
        rng,  # random.Random instance
    ) -> str:
        """为背景物种生成独立的中文名称
        
        【设计原则】
        - 不依赖父系名称，避免累加截断问题
        - 使用栖息地+营养级+特征的组合命名
        - 名称长度控制在2-5个字
        - 背景物种使用更朴素的名字，暗示其"配角"地位
        
        Args:
            parent: 父系物种
            evolution_direction: 演化方向
            habitat_type: 栖息地类型
            trophic_level: 营养级
            rng: 随机数生成器
            
        Returns:
            中文物种名称
        """
        # 栖息地前缀词库（1-2字）
        habitat_prefixes = {
            "marine": ["海", "洋", "咸水", "远洋"],
            "deep_sea": ["深海", "渊", "幽暗"],
            "coastal": ["岸", "滨", "潮间"],
            "freshwater": ["溪", "河", "淡水", "泽"],
            "amphibious": ["两栖", "沼", "泥"],
            "terrestrial": ["陆", "原", "野"],
            "aerial": ["翔", "天", "空"],
        }
        
        # 营养级相关词库
        trophic_words = {
            # T1: 生产者
            (0.0, 2.0): ["藻", "菌", "苔", "萍", "蕨", "草"],
            # T2: 初级消费者
            (2.0, 3.0): ["虫", "螺", "蚌", "介", "甲"],
            # T3: 次级消费者
            (3.0, 4.0): ["游", "爬", "蠕", "钳"],
            # T4+: 高级捕食者
            (4.0, 6.0): ["齿", "爪", "猎", "噬"],
        }
        
        # 演化方向后缀（1-2字）
        direction_suffixes = {
            "环境适应型": ["甲", "壳", "韧", "坚"],
            "活动强化型": ["捷", "敏", "游", "行"],
            "繁殖策略型": ["繁", "群", "众", "盛"],
            "防御特化型": ["刺", "盾", "甲", "棘"],
            "极端特化型": ["奇", "异", "怪", "特"],
        }
        
        # 通用后缀（当其他条件不满足时）
        generic_suffixes = ["类", "属", "种", "形", "型"]
        
        # 1. 选择栖息地前缀
        habitat_key = habitat_type or "terrestrial"
        prefixes = habitat_prefixes.get(habitat_key, habitat_prefixes["terrestrial"])
        prefix = rng.choice(prefixes)
        
        # 2. 选择营养级相关词
        trophic_word = ""
        for (low, high), words in trophic_words.items():
            if low <= trophic_level < high:
                trophic_word = rng.choice(words)
                break
        if not trophic_word:
            trophic_word = rng.choice(["生", "物", "灵"])
        
        # 3. 选择演化方向后缀（50%概率添加）
        suffix = ""
        if rng.random() > 0.5:
            suffixes = direction_suffixes.get(evolution_direction, generic_suffixes)
            suffix = rng.choice(suffixes)
        
        # 4. 组合名称（控制长度）
        base_name = f"{prefix}{trophic_word}"
        if suffix and len(base_name) < 8:
            base_name += suffix
        
        # 5. 如果名称太短，添加一个通用后缀
        if len(base_name) < 2:
            base_name += rng.choice(generic_suffixes)
        
        return base_name

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
        """随机划分子代种群，并确保每个子种至少拥有最小种群门槛。
        
        【优化】使用配置中的 min_offspring_population 作为每个子种的最小种群，
        避免分化出过小的种群（只有几百个体的"微型物种"）。
        """
        import random
        
        if num_offspring <= 0:
            return []
        if total_population <= 0:
            return [0] * num_offspring
        
        # 获取配置中的最小子代种群
        min_offspring_pop = self._config.min_offspring_population
        
        # 检查总种群是否足够分配
        required_minimum = min_offspring_pop * num_offspring
        if total_population < required_minimum:
            # 种群不足以满足最小门槛，尝试减少子代数量
            feasible_offspring = total_population // min_offspring_pop
            if feasible_offspring <= 0:
                # 完全不够，返回空列表（由调用方处理）
                logger.warning(
                    f"[种群分配] 总种群{total_population:,} 不足以产生任何子种 "
                    f"(最小门槛={min_offspring_pop:,})"
                )
                return []
            # 使用可行的子代数量
            num_offspring = feasible_offspring
            logger.info(
                f"[种群分配] 总种群{total_population:,} 不足以产生{num_offspring}个子种，"
                f"调整为{feasible_offspring}个 (最小门槛={min_offspring_pop:,})"
            )
        
        splits: list[int] = []
        remaining = total_population
        
        for idx in range(num_offspring):
            slots_left = num_offspring - idx
            if slots_left == 1:
                allocation = remaining
            else:
                # 确保每个子种至少获得 min_offspring_pop 的种群
                # 同时确保留给后续子种的种群也够分配
                min_allow = min_offspring_pop
                reserved_for_others = min_offspring_pop * (slots_left - 1)
                max_allow = remaining - reserved_for_others
                
                if max_allow < min_allow:
                    # 安全检查：如果计算出错，使用最小值
                    allocation = min_allow
                else:
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
        speciation_type: str = "生态隔离",  # 【一揽子修改】分化类型参数
    ) -> Species:
        """创建新的分化物种。
        
        新物种从父代继承大部分属性，但有一些变化：
        - 基因多样性略微增加
        - 描述可能由 AI 修改以反映新特征
        
        种群分配逻辑：
        - 新物种从原物种中分离出20-40%的个体
        - 原物种保留60-80%
        - 总数略减（模拟分化过程的损耗）
        
        Args:
            speciation_type: 分化类型标记（地理隔离/生态隔离/辐射演化等）
        """
        # 种群分配逻辑已在上层处理，这里只负责对象创建
        
        morphology = dict(parent.morphology_stats)
        morphology["population"] = survivors
        
        # 【一揽子修改】保存分化类型标记，便于日志和后处理
        morphology["speciation_type"] = speciation_type
        morphology["speciation_turn"] = turn_index
        
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
        
        # 1.1 使用自动代价计算器，为增益添加权衡代价
        if self._use_auto_tradeoff and self.tradeoff_calculator:
            applied_changes = self._apply_tradeoff_penalties(applied_changes, abstract)
        
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
        
        # 【修复】放宽description长度要求：30字即可接受（很多有效描述在50-80字）
        # 只有完全缺失或极短时才触发回退
        min_desc_length = 30
        
        # 分别检查和回退每个字段
        needs_fallback_name = not latin or not common
        needs_fallback_desc = not description or len(str(description).strip()) < min_desc_length
        
        if needs_fallback_name or needs_fallback_desc:
            if needs_fallback_name:
                logger.info(f"[分化] 名称不完整，使用回退命名: latin={latin}, common={common}")
            if needs_fallback_desc:
                logger.debug(f"[分化] 描述过短({len(str(description or '').strip())}字 < {min_desc_length}字)，补充描述")
            
            # 回退到规则命名
            if not latin:
                latin = self._fallback_latin_name(parent.latin_name, ai_payload)
            if not common:
                common = self._fallback_common_name(parent.common_name, ai_payload)
            
            # 【优化】描述补充逻辑：保留AI返回的内容并追加
            if needs_fallback_desc:
                key_innovations = ai_payload.get("key_innovations", [])
                innovations_text = "，演化出" + "、".join(key_innovations) if key_innovations else ""
                base_desc = str(description or "").strip()
                
                if len(base_desc) > 10:
                    # AI返回了部分描述，追加补充
                    description = f"{base_desc}。作为{parent.common_name}的后代{innovations_text}。"
                else:
                    # 完全没有描述，使用父系描述
                    description = f"{parent.description}在环境压力{average_pressure:.1f}下发生适应性变化{innovations_text}。"
                
                # 确保描述不会过短
                if len(description) < 50:
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
        
        # 基因多样性继承
        try:
            self.gene_diversity_service.ensure_initialized(parent, turn_index)
            base_radius = getattr(parent, "gene_diversity_radius", 0.35) or 0.35
            child_radius = self.gene_diversity_service.inherit_radius(base_radius, turn_index)
        except Exception:
            child_radius = max(0.35, getattr(parent, "gene_diversity_radius", 0.35) or 0.35)
        child_gene_stability = getattr(parent, "gene_stability", 0.5) or 0.5
        child_explored = list(getattr(parent, "explored_directions", []) or [])
        hidden["gene_diversity"] = child_radius

        # 验证捕食关系与营养级的一致性
        if new_trophic < 2.0 and new_prey_species:
            # 生产者不应该有猎物
            logger.warning(f"[分化警告] {new_code} 营养级<2.0但有猎物，清空猎物列表")
            new_prey_species = []
            new_prey_preferences = {}
            new_diet_type = "autotroph"
        
        # 【新增】处理植物演化系统字段
        new_life_form_stage = getattr(parent, 'life_form_stage', 0)
        new_growth_form = getattr(parent, 'growth_form', 'aquatic')
        new_achieved_milestones = list(getattr(parent, 'achieved_milestones', []) or [])
        
        if new_trophic < 2.0:
            # 植物物种，检查AI是否返回了植物字段
            parent_stage = getattr(parent, 'life_form_stage', 0)
            ai_life_form_stage = ai_payload.get("life_form_stage")
            
            if ai_life_form_stage is not None:
                try:
                    proposed_stage = int(ai_life_form_stage)
                    # 范围钳制 (0-6)
                    proposed_stage = max(0, min(6, proposed_stage))
                    
                    # 【植物演化】阶段验证：不允许跳级，最多升级1级
                    if proposed_stage > parent_stage + 1:
                        logger.warning(
                            f"[植物演化修正] {new_code}: AI返回阶段{proposed_stage}跳级过大"
                            f"(父代阶段{parent_stage})，修正为{parent_stage + 1}"
                        )
                        new_life_form_stage = parent_stage + 1
                    elif proposed_stage < parent_stage:
                        # 不允许退化阶段
                        logger.warning(
                            f"[植物演化修正] {new_code}: AI返回阶段{proposed_stage}低于父代"
                            f"(父代阶段{parent_stage})，保持父代阶段"
                        )
                        new_life_form_stage = parent_stage
                    else:
                        new_life_form_stage = proposed_stage
                        
                except (ValueError, TypeError):
                    pass
            
            ai_growth_form = ai_payload.get("growth_form")
            if ai_growth_form in ["aquatic", "moss", "herb", "shrub", "tree"]:
                # 【植物演化】验证生长形式与阶段是否匹配
                if PlantTraitConfig.validate_growth_form(ai_growth_form, new_life_form_stage):
                    new_growth_form = ai_growth_form
                else:
                    valid_forms = PlantTraitConfig.get_valid_growth_forms(new_life_form_stage)
                    if valid_forms:
                        new_growth_form = valid_forms[0]
                        logger.warning(
                            f"[植物演化修正] {new_code}: 生长形式{ai_growth_form}与阶段{new_life_form_stage}不匹配，"
                            f"修正为{new_growth_form}"
                        )
            
            # 检查是否触发了新里程碑
            ai_milestone = ai_payload.get("milestone_triggered")
            if ai_milestone and ai_milestone not in new_achieved_milestones:
                # 验证里程碑是否真的可以触发
                if ai_milestone in PLANT_MILESTONES:
                    milestone = PLANT_MILESTONES[ai_milestone]
                    if milestone.from_stage is not None and milestone.from_stage != parent_stage:
                        logger.warning(
                            f"[植物里程碑修正] {new_code}: 里程碑{ai_milestone}需要阶段{milestone.from_stage}，"
                            f"当前父代阶段{parent_stage}，忽略此里程碑"
                        )
                    else:
                        new_achieved_milestones.append(ai_milestone)
                        logger.info(f"[植物分化] {new_code} 触发里程碑: {ai_milestone}")
        
        # 不再继承 ecological_vector，让系统基于 description 自动计算 embedding
        
        # 【改进】基于环境压力的基因继承机制
        # 高压力环境下，不适应的基因更容易丢失（自然选择）
        # 低压力环境下，基因保留率更高（遗传漂变较弱）
        import copy
        inherited_dormant_genes = {"traits": {}, "organs": {}}
        
        if parent.dormant_genes:
            # 获取基因多样性配置参数
            gene_cfg = self.gene_diversity_service.config if hasattr(self, 'gene_diversity_service') else None
            pressure_threshold = gene_cfg.gene_loss_pressure_threshold if gene_cfg else 2.0
            loss_rate_per_pressure = gene_cfg.gene_loss_rate_per_pressure if gene_cfg else 0.02
            max_loss_rate = gene_cfg.max_gene_loss_rate if gene_cfg else 0.15
            pressure_match_bonus = gene_cfg.pressure_match_retain_bonus if gene_cfg else 0.10
            dominant_harmful_factor = gene_cfg.dominant_harmful_retain_factor if gene_cfg else 0.70
            mildly_harmful_factor = gene_cfg.mildly_harmful_retain_factor if gene_cfg else 0.90
            organ_stability = gene_cfg.organ_gene_stability_factor if gene_cfg else 0.50
            
            # 获取当前环境压力类型（用于判断基因是否匹配当前选择压力）
            current_pressure_types = getattr(self, '_current_pressure_types', ['adaptive']) or ['adaptive']
            
            # 计算基于压力的基础丢失率
            # average_pressure 范围 0-10，转换为丢失率 0-max_loss_rate
            # 低压力(< threshold): 丢失率 0，高压力时按 loss_rate_per_pressure 递增
            base_loss_rate = min(max_loss_rate, max(0.0, (average_pressure - pressure_threshold) * loss_rate_per_pressure))
            
            # 继承特质
            parent_traits = parent.dormant_genes.get("traits", {})
            lost_traits = []
            for trait_name, gene_data in parent_traits.items():
                if not isinstance(gene_data, dict):
                    continue
                
                # 计算该基因的保留概率
                retain_prob = 1.0 - base_loss_rate
                
                # 【压力匹配加成】如果基因与当前环境压力相关，保留概率更高
                gene_pressure_types = gene_data.get("pressure_types", [])
                pressure_match = any(pt in current_pressure_types for pt in gene_pressure_types)
                if pressure_match:
                    retain_prob = min(1.0, retain_prob + pressure_match_bonus)
                
                # 【有害突变更容易丢失】显性有害突变在高压力下更容易被选择掉
                mutation_effect = gene_data.get("mutation_effect", "beneficial")
                if mutation_effect in ("harmful", "lethal"):
                    dominance = gene_data.get("dominance", "codominant")
                    if dominance != "recessive":  # 显性有害突变更容易丢失
                        retain_prob *= dominant_harmful_factor
                elif mutation_effect == "mildly_harmful":
                    retain_prob *= mildly_harmful_factor
                
                # 随机决定是否保留
                if random.random() < retain_prob:
                    new_gene = copy.deepcopy(gene_data)
                    new_gene["exposure_count"] = 0
                    new_gene["inherited_from"] = parent.lineage_code
                    inherited_dormant_genes["traits"][trait_name] = new_gene
                else:
                    lost_traits.append(trait_name)
            
            # 继承器官
            parent_organs = parent.dormant_genes.get("organs", {})
            lost_organs = []
            for organ_name, gene_data in parent_organs.items():
                if not isinstance(gene_data, dict):
                    continue
                
                # 器官基因通常更稳定，丢失率按配置倍数降低
                retain_prob = 1.0 - (base_loss_rate * organ_stability)
                
                # 压力匹配加成（器官加成减半）
                gene_pressure_types = gene_data.get("pressure_types", [])
                pressure_match = any(pt in current_pressure_types for pt in gene_pressure_types)
                if pressure_match:
                    retain_prob = min(1.0, retain_prob + pressure_match_bonus * 0.5)
                
                if random.random() < retain_prob:
                    new_gene = copy.deepcopy(gene_data)
                    new_gene["exposure_count"] = 0
                    new_gene["inherited_from"] = parent.lineage_code
                    inherited_dormant_genes["organs"][organ_name] = new_gene
                else:
                    lost_organs.append(organ_name)
            
            # 记录丢失情况（仅在有丢失时记录）
            if lost_traits or lost_organs:
                logger.debug(
                    f"[基因丢失] {new_code} 在压力{average_pressure:.1f}下丢失: "
                    f"特质{len(lost_traits)}个, 器官{len(lost_organs)}个 "
                    f"(保留率: {1.0-base_loss_rate:.0%})"
                )
        
        # ========== 继承器官胚芽池和已成熟器官 ==========
        import copy
        inherited_organ_rudiments = copy.deepcopy(parent.organ_rudiments or {})
        inherited_evolved_organs = copy.deepcopy(parent.evolved_organs or {})
        
        # 创建新物种
        new_species = Species(
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
            # 基因多样性字段
            gene_diversity_radius=child_radius,
            gene_stability=child_gene_stability,
            explored_directions=child_explored,
            # 植物演化系统字段
            life_form_stage=new_life_form_stage,
            growth_form=new_growth_form,
            achieved_milestones=new_achieved_milestones,
            # 【修复】直接继承父代的休眠基因
            dormant_genes=inherited_dormant_genes,
            # 【新增】自由器官演化系统
            organ_rudiments=inherited_organ_rudiments,
            evolved_organs=inherited_evolved_organs,
        )
        
        # ========== 处理器官演化（更新胚芽池）==========
        organ_evolution = ai_payload.get("organ_evolution", [])
        if organ_evolution and isinstance(organ_evolution, list):
            try:
                # 获取当前压力类型
                current_pressures = getattr(self, '_current_pressure_types', ['competition']) or ['competition']
                
                # 调用器官演化服务处理
                organ_result = self.organ_evolution_service.process_organ_evolution(
                    species=new_species,
                    llm_organs=organ_evolution,
                    turn=turn_index,
                    current_pressures=current_pressures
                )
                
                if organ_result.get("upgraded"):
                    logger.info(
                        f"[器官演化] {new_code} 升级器官: {organ_result['upgraded']}"
                    )
                if organ_result.get("matured"):
                    logger.info(
                        f"[器官演化] {new_code} 器官胚芽成熟: {organ_result['matured']}"
                    )
                if organ_result.get("created"):
                    logger.debug(
                        f"[器官演化] {new_code} 新建器官胚芽: {organ_result['created']}"
                    )
            except Exception as e:
                logger.warning(f"[器官演化] 处理失败: {e}")
        
        return new_species
    
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
            diff = min(abs(tile.temperature - min_temp), abs(tile.temperature - max_temp))
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
        return max(0.0, temp_score * 0.35 + humidity_score * 0.25 + resource_score * 0.40)
    
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
    
    def _detect_coevolution(
        self,
        species: 'Species',
        mortality_results: list,
    ) -> dict:
        """【新增】检测动植物协同演化关系
        
        识别以下协同演化模式：
        1. 食草压力驱动的防御演化（植物）
        2. 植物防御驱动的捕食者特化（动物）
        3. 传粉/散布互惠关系的雏形
        
        Args:
            species: 当前物种
            mortality_results: 死亡率结果列表
            
        Returns:
            {has_coevolution, bonus, type, partner_codes}
        """
        result = {
            "has_coevolution": False,
            "bonus": 0.0,
            "type": "无协同演化",
            "partner_codes": [],
        }
        
        is_plant = PlantTraitConfig.is_plant(species)
        
        # 收集所有物种
        all_species = [r.species for r in mortality_results]
        plants = [s for s in all_species if PlantTraitConfig.is_plant(s)]
        animals = [s for s in all_species if not PlantTraitConfig.is_plant(s)]
        
        if is_plant:
            # ===== 植物的协同演化检测 =====
            
            # 检测食草压力驱动的防御演化
            herbivores = [
                a for a in animals 
                if 2.0 <= a.trophic_level < 2.5 and 
                   getattr(a, 'diet_type', '') in ['herbivore', 'omnivore']
            ]
            
            # 检查是否被食草动物捕食
            predator_codes = []
            for herbivore in herbivores:
                prey_list = getattr(herbivore, 'prey_species', []) or []
                if species.lineage_code in prey_list:
                    predator_codes.append(herbivore.lineage_code)
            
            if predator_codes:
                # 被食草动物捕食 → 驱动防御演化
                defense_traits = species.abstract_traits
                has_defense = (
                    defense_traits.get("化学防御", 0) > 5.0 or 
                    defense_traits.get("物理防御", 0) > 5.0
                )
                
                if has_defense:
                    result["has_coevolution"] = True
                    result["bonus"] = 0.12
                    result["type"] = "食草-防御军备竞赛"
                    result["partner_codes"] = predator_codes
                else:
                    # 有压力但尚未发展防御 → 小幅促进分化
                    result["has_coevolution"] = True
                    result["bonus"] = 0.06
                    result["type"] = "食草压力适应"
                    result["partner_codes"] = predator_codes
            
            # 检测潜在的传粉关系（高阶段植物 + 小型动物）
            if getattr(species, 'life_form_stage', 0) >= 5:  # 裸子植物及以上
                potential_pollinators = [
                    a for a in animals
                    if a.morphology_stats.get("body_length_cm", 100) < 10 and
                       a.trophic_level >= 2.0
                ]
                if potential_pollinators:
                    result["has_coevolution"] = True
                    result["bonus"] = max(result["bonus"], 0.08)
                    if result["type"] == "无协同演化":
                        result["type"] = "潜在传粉互惠"
                    result["partner_codes"].extend([p.lineage_code for p in potential_pollinators[:2]])
        
        else:
            # ===== 动物的协同演化检测 =====
            
            # 检测食草动物对植物防御的适应
            if 2.0 <= species.trophic_level < 2.5:
                prey_list = getattr(species, 'prey_species', []) or []
                defended_plants = []
                
                for plant in plants:
                    if plant.lineage_code in prey_list:
                        defense = max(
                            plant.abstract_traits.get("化学防御", 0),
                            plant.abstract_traits.get("物理防御", 0)
                        )
                        if defense > 5.0:
                            defended_plants.append(plant.lineage_code)
                
                if defended_plants:
                    result["has_coevolution"] = True
                    result["bonus"] = 0.10
                    result["type"] = "突破植物防御特化"
                    result["partner_codes"] = defended_plants
            
            # 检测捕食者对猎物的协同演化
            if species.trophic_level >= 2.5:
                prey_list = getattr(species, 'prey_species', []) or []
                fast_prey = []
                
                for other in all_species:
                    if other.lineage_code in prey_list:
                        speed = other.abstract_traits.get("运动能力", 0)
                        if speed > 7.0:
                            fast_prey.append(other.lineage_code)
                
                if fast_prey:
                    result["has_coevolution"] = True
                    result["bonus"] = 0.08
                    result["type"] = "捕食者-猎物军备竞赛"
                    result["partner_codes"] = fast_prey
        
        return result
    
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
    
    def _calculate_speciation_threshold(self, species: Species, turn_index: int = 0) -> int:
        """计算物种的分化门槛 - 基于多维度生态学指标。
        
        综合考虑：
        1. 体型（体长、体重） - 主要因素
        2. 繁殖策略（世代时间、繁殖速度） - r/K策略
        3. 代谢率 - 能量周转速度
        4. 营养级 - 从描述推断
        5. 【新增】早期折减 - 前10回合门槛降低，鼓励早期分化
        
        Args:
            species: 物种对象
            turn_index: 当前回合索引（用于早期折减计算）
        
        Returns:
            最小种群数量（需要达到此数量才能分化）
        """
        import math
        
        # 1. 基于体型的基础门槛
        # 【早期分化优化】整体下调 5-10 倍，让早期更容易分化
        body_length_cm = species.morphology_stats.get("body_length_cm", 1.0)
        body_weight_g = species.morphology_stats.get("body_weight_g", 1.0)
        
        # 使用体长作为主要指标（更直观）
        # 【大浪淘沙v1】大幅降低分化门槛，让物种更容易分化
        if body_length_cm < 0.01:  # <0.1mm - 细菌级别
            base_threshold = 5_000     # 原20万 -> 5千（降低40倍）
        elif body_length_cm < 0.1:  # 0.1mm-1mm - 原生动物
            base_threshold = 3_000     # 原10万 -> 3千（降低33倍）
        elif body_length_cm < 1.0:  # 1mm-1cm - 小型无脊椎动物
            base_threshold = 1_000     # 原2万 -> 1千（降低20倍）
        elif body_length_cm < 10.0:  # 1cm-10cm - 昆虫、小鱼
            base_threshold = 300       # 原2千 -> 300（降低7倍）
        elif body_length_cm < 50.0:  # 10cm-50cm - 中型脊椎动物
            base_threshold = 100       # 原600 -> 100（降低6倍）
        elif body_length_cm < 200.0:  # 50cm-2m - 大型哺乳动物
            base_threshold = 50        # 原200 -> 50（降低4倍）
        else:  # >2m - 超大型动物（大象、鲸鱼）
            base_threshold = 20        # 原80 -> 20（降低4倍）
        
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
        
        # 早期折减系数（从配置读取）
        # turn < early_game_turns 时门槛明显降低
        # 公式：factor = max(min_factor, 1 - decay_rate * turn_index)
        spec_config = self._config
        early_factor = max(
            spec_config.early_threshold_min_factor, 
            1.0 - spec_config.early_threshold_decay_rate * turn_index
        )
        threshold = int(threshold * early_factor)
        
        # 确保在合理范围内
        # 最小：30（进一步降低，让早期小种群也能分化）
        # 最大：200万（降低上限）
        threshold = max(30, min(threshold, 2_000_000))
        
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
    
    def _process_ai_activated_genes(
        self,
        species: Species,
        activated_genes: list[str],
        turn_index: int
    ) -> int:
        """处理 AI 指定要激活的休眠基因 v2.0
        
        【v2.0 更新】
        - 应用显隐性效果到表达值
        - 阻止 AI 激活有害突变
        - 器官按发育阶段处理
        
        Args:
            species: 新物种对象
            activated_genes: AI 指定的要激活的基因名列表
            turn_index: 当前回合
            
        Returns:
            成功激活的基因数量
        """
        if not activated_genes:
            return 0
        
        if not species.dormant_genes:
            return 0
        
        # 导入显隐性系数
        try:
            from .gene_constants import DOMINANCE_EXPRESSION_FACTOR, DominanceType, OrganStage
        except ImportError:
            DOMINANCE_EXPRESSION_FACTOR = {
                "recessive": 0.25, "codominant": 0.60, 
                "dominant": 1.0, "overdominant": 1.15
            }
            DominanceType = None
            OrganStage = None
        
        activated_count = 0
        
        for gene_name in activated_genes:
            # 尝试在休眠特质中查找
            if "traits" in species.dormant_genes:
                for trait_name, gene_data in species.dormant_genes["traits"].items():
                    # 模糊匹配：基因名包含或被包含
                    if (gene_name in trait_name or trait_name in gene_name) and not gene_data.get("activated", False):
                        
                        # 阻止 AI 激活有害突变
                        mutation_effect = gene_data.get("mutation_effect", "beneficial")
                        if mutation_effect in ("mildly_harmful", "harmful", "lethal"):
                            logger.warning(f"[AI基因激活] 阻止激活有害突变: {trait_name}")
                            continue
                        
                        potential_value = gene_data.get("potential_value", 8.0)
                        dominance = gene_data.get("dominance", "codominant")
                        
                        # 应用显隐性效果
                        if DominanceType:
                            try:
                                dom_type = DominanceType(dominance)
                                expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(dom_type, 0.6)
                            except ValueError:
                                expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(dominance, 0.6)
                        else:
                            expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(dominance, 0.6)
                        
                        expressed_value = potential_value * expression_factor
                        
                        species.abstract_traits[trait_name] = min(15.0, expressed_value)
                        gene_data["activated"] = True
                        gene_data["activation_turn"] = turn_index
                        gene_data["expressed_value"] = expressed_value
                        activated_count += 1
                        
                        dom_label = {"dominant": "显性", "recessive": "隐性", "codominant": "共显性", "overdominant": "超显性"}.get(dominance, "")
                        logger.info(
                            f"[AI基因激活] {species.common_name} 激活特质: {trait_name} = {expressed_value:.1f} "
                            f"(潜力{potential_value:.1f}, {dom_label})"
                        )
                        break
            
            # 尝试在休眠器官中查找
            if "organs" in species.dormant_genes:
                for organ_name, gene_data in species.dormant_genes["organs"].items():
                    # 检查是否正在发育或已成熟
                    dev_stage = gene_data.get("development_stage")
                    is_already_active = gene_data.get("activated", False) and dev_stage == 3
                    
                    if (gene_name in organ_name or organ_name in gene_name) and not is_already_active:
                        organ_data = gene_data.get("organ_data", {})
                        organ_category = organ_data.get("category", "sensory")
                        
                        # AI 激活直接跳到功能原型阶段（60%效率）
                        if dev_stage is None or dev_stage < 2:
                            gene_data["development_stage"] = 2  # 功能原型
                            gene_data["stage_start_turn"] = turn_index
                            efficiency = 0.60
                        else:
                            efficiency = {0: 0.0, 1: 0.25, 2: 0.60, 3: 1.0}.get(dev_stage, 0.6)
                        
                        species.organs[organ_category] = {
                            "type": organ_data.get("type", organ_name),
                            "parameters": {
                                **organ_data.get("parameters", {}),
                                "efficiency_modifier": efficiency
                            },
                            "acquired_turn": turn_index,
                            "is_active": True,
                            "maturity": efficiency,
                            "development_stage": gene_data.get("development_stage", 2)
                        }
                        gene_data["activated"] = True
                        gene_data["activation_turn"] = turn_index
                        activated_count += 1
                        
                        stage_names = {0: "原基", 1: "初级", 2: "功能原型", 3: "成熟"}
                        logger.info(
                            f"[AI基因激活] {species.common_name} 激活器官: {organ_name} "
                            f"({stage_names.get(gene_data.get('development_stage'), '未知')}, 效率{efficiency:.0%})"
                        )
                        break
        
        return activated_count
    
    def _summarize_dormant_genes(
        self, 
        species: Species, 
        pressure_types: list[str] | None = None,
        pressure_strength: float = 5.0
    ) -> str:
        """智能筛选并总结休眠基因信息，供 AI 参考分化方向 v2.0
        
        【v2.0 更新】
        - 包含显隐性信息（影响激活表达效果）
        - 标注有害突变风险
        - 显示器官发育阶段
        - 新增压力类型关键词
        
        筛选策略：
        1. 优先选择与当前压力类型匹配的基因
        2. 排除有害突变（除非高压力下别无选择）
        3. 按潜力值从高到低排序
        4. 最多返回 3个特质 + 1个器官
        
        Args:
            species: 物种对象
            pressure_types: 当前环境压力类型列表
            pressure_strength: 压力强度 (0-10)
            
        Returns:
            精简的休眠基因摘要字符串，供 AI 参考
        """
        if not species.dormant_genes:
            return "无休眠基因"
        
        pressure_types = pressure_types or ["competition"]
        dormant_traits = species.dormant_genes.get("traits", {})
        dormant_organs = species.dormant_genes.get("organs", {})
        
        # 过滤未激活的休眠基因
        available_traits = [
            (name, data) for name, data in dormant_traits.items()
            if not data.get("activated", False)
        ]
        available_organs = [
            (name, data) for name, data in dormant_organs.items()
            if not data.get("activated", False) or data.get("development_stage", 3) < 3
        ]
        
        if not available_traits and not available_organs:
            return "无可激活基因"
        
        # 分离有害突变和有益基因
        harmful_traits = []
        beneficial_traits = []
        for name, data in available_traits:
            mutation_effect = data.get("mutation_effect", "beneficial")
            if mutation_effect in ("mildly_harmful", "harmful", "lethal"):
                harmful_traits.append((name, data))
            else:
                beneficial_traits.append((name, data))
        
        # === 智能筛选特质 ===
        def score_trait(item: tuple) -> float:
            """计算特质的优先级分数"""
            name, data = item
            score = 0.0
            
            # 1. 潜力值权重 (0-15 -> 0-3分)
            potential = data.get("potential_value", 5.0)
            score += potential / 5.0
            
            # 2. 压力匹配加成 (+5分)
            gene_pressures = set(data.get("pressure_types", []))
            if gene_pressures & set(pressure_types):
                score += 5.0
            
            # 3. 暴露次数加成
            exposure = data.get("exposure_count", 0)
            score += min(exposure * 0.5, 2.0)
            
            # 4. 显隐性加成（显性更容易表达）
            dominance = data.get("dominance", "codominant")
            if dominance == "dominant":
                score += 1.0
            elif dominance == "overdominant":
                score += 1.5
            elif dominance == "recessive":
                score -= 0.5
            
            # 5. 高压力时优先选择与压力直接相关的
            if pressure_strength >= 7:
                pressure_keywords = {
                    "cold": ["耐寒", "寒"],
                    "heat": ["耐热", "热"],
                    "drought": ["耐旱", "旱", "保水"],
                    "temperature_fluctuation": ["耐寒", "耐热", "温度", "适应"],
                    "competition": ["竞争", "适应", "运动", "效率"],
                    "predation": ["防御", "速度", "感知", "逃避"],
                    "hunting": ["捕猎", "追踪", "攻击"],
                    "starvation": ["代谢", "储能", "消化", "效率"],
                    "disease": ["免疫", "抗性"],
                    "salinity": ["耐盐", "渗透"],
                    "pressure_deep": ["耐压", "深海"],
                    "light_limitation": ["光合", "弱光"],
                }
                for ptype in pressure_types:
                    for keyword in pressure_keywords.get(ptype, []):
                        if keyword in name:
                            score += 3.0
                            break
            
            return score
        
        # 排序有益特质
        sorted_traits = sorted(beneficial_traits, key=score_trait, reverse=True)
        top_traits = sorted_traits[:3]
        
        # === 智能筛选器官 ===
        def score_organ(item: tuple) -> float:
            """计算器官的优先级分数"""
            name, data = item
            score = 0.0
            
            organ_data = data.get("organ_data", {})
            category = organ_data.get("category", "")
            
            # 压力匹配
            gene_pressures = set(data.get("pressure_types", []))
            if gene_pressures & set(pressure_types):
                score += 3.0
            
            # 高压力时优先防御/感知器官
            if pressure_strength >= 7:
                if category in ["defense", "sensory"]:
                    score += 2.0
            
            # 已有发育进度的器官优先
            dev_stage = data.get("development_stage")
            if dev_stage is not None:
                score += (dev_stage + 1) * 0.5
            
            # 暴露次数
            exposure = data.get("exposure_count", 0)
            score += min(exposure * 0.3, 1.0)
            
            return score
        
        sorted_organs = sorted(available_organs, key=score_organ, reverse=True)
        top_organs = sorted_organs[:1]
        
        # === 生成简洁摘要 ===
        lines = []
        
        if top_traits:
            trait_items = []
            for name, data in top_traits:
                potential = data.get("potential_value", 8.0)
                dominance = data.get("dominance", "codominant")
                
                # 显隐性标记
                dom_mark = ""
                if dominance == "dominant":
                    dom_mark = "[显]"
                elif dominance == "recessive":
                    dom_mark = "[隐]"
                elif dominance == "overdominant":
                    dom_mark = "[超显]"
                
                # 压力匹配标记
                gene_pressures = set(data.get("pressure_types", []))
                is_matched = "⭐" if gene_pressures & set(pressure_types) else ""
                
                trait_items.append(f"{is_matched}{name}{dom_mark}({potential:.0f})")
            lines.append(f"推荐特质: {', '.join(trait_items)}")
        
        if top_organs:
            name, data = top_organs[0]
            organ_data = data.get("organ_data", {})
            category = organ_data.get("category", "")
            
            # 发育阶段标记
            dev_stage = data.get("development_stage")
            stage_mark = ""
            if dev_stage is not None:
                stage_names = {0: "原基", 1: "初级", 2: "功能", 3: "成熟"}
                stage_mark = f"[{stage_names.get(dev_stage, '未知')}]"
            
            lines.append(f"推荐器官: {name}({category}){stage_mark}")
        
        # 有害突变警告（仅在有害突变数量较多时提示）
        if len(harmful_traits) >= 2:
            harm_names = [n for n, _ in harmful_traits[:2]]
            lines.append(f"⚠️ 遗传负荷: {', '.join(harm_names)} (避免激活)")
        
        if not lines:
            return "无推荐基因"
        
        # 极简提示
        lines.append("(⭐=匹配当前压力优先激活; [显]=显性易表达; [隐]=隐性需高压激活)")
        
        return "\n".join(lines)
    
    def _process_ai_new_dormant_genes(
        self,
        species: Species,
        new_genes_data: dict,
        turn_index: int
    ) -> int:
        """【LLM新基因】处理AI返回的新休眠基因，添加到物种基因库
        
        分化时LLM生成的新休眠基因，这些基因将成为子代未来演化的潜力。
        
        Args:
            species: 新分化的物种
            new_genes_data: LLM返回的 new_dormant_genes 字典
            turn_index: 当前回合
            
        Returns:
            成功添加的基因数量
        """
        if not new_genes_data:
            return 0
        
        # 确保 dormant_genes 结构存在
        if not species.dormant_genes:
            species.dormant_genes = {"traits": {}, "organs": {}}
        species.dormant_genes.setdefault("traits", {})
        species.dormant_genes.setdefault("organs", {})
        
        added_count = 0
        
        # 处理特质基因
        traits_list = new_genes_data.get("traits", [])
        if isinstance(traits_list, list):
            for trait_data in traits_list:
                if not isinstance(trait_data, dict):
                    continue
                
                trait_name = trait_data.get("name")
                if not trait_name:
                    continue
                
                # 跳过已存在的基因
                if trait_name in species.dormant_genes["traits"]:
                    continue
                if trait_name in (species.abstract_traits or {}):
                    continue
                
                # 解析基因数据
                potential_value = trait_data.get("potential_value", 6.0)
                try:
                    potential_value = float(potential_value)
                    potential_value = max(0.0, min(15.0, potential_value))
                except (ValueError, TypeError):
                    potential_value = 6.0
                
                pressure_types = trait_data.get("pressure_types", ["competition"])
                if not isinstance(pressure_types, list):
                    pressure_types = ["competition"]
                
                dominance = trait_data.get("dominance", "codominant")
                valid_dominance = ["dominant", "codominant", "recessive", "overdominant"]
                if dominance not in valid_dominance:
                    dominance = "codominant"
                
                mutation_effect = trait_data.get("mutation_effect", "beneficial")
                valid_effects = ["beneficial", "neutral", "mildly_harmful", "harmful", "lethal"]
                if mutation_effect not in valid_effects:
                    mutation_effect = "beneficial"
                
                description = trait_data.get("description", "")
                
                # 构建休眠基因数据
                dormant_gene = {
                    "potential_value": potential_value,
                    "activation_threshold": 0.20,
                    "pressure_types": pressure_types,
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": "llm_speciation",
                    "dominance": dominance,
                    "mutation_effect": mutation_effect,
                    "description": description,
                    "created_turn": turn_index,
                }
                
                # 有害突变的额外处理
                if mutation_effect in ("mildly_harmful", "harmful", "lethal"):
                    # 确保有害突变是隐性的
                    dormant_gene["dominance"] = "recessive"
                    # 提取目标特质（如果描述中提到）
                    target_trait = trait_data.get("target_trait")
                    if target_trait:
                        dormant_gene["target_trait"] = target_trait
                    value_modifier = trait_data.get("value_modifier", -1.0)
                    try:
                        dormant_gene["value_modifier"] = float(value_modifier)
                    except (ValueError, TypeError):
                        dormant_gene["value_modifier"] = -1.0
                
                species.dormant_genes["traits"][trait_name] = dormant_gene
                added_count += 1
                
                effect_label = {"beneficial": "有益", "neutral": "中性", "mildly_harmful": "轻微有害", "harmful": "有害"}.get(mutation_effect, "")
                dom_label = {"dominant": "显", "codominant": "共显", "recessive": "隐", "overdominant": "超显"}.get(dominance, "")
                logger.debug(
                    f"[LLM新基因] {species.common_name} 获得特质基因: {trait_name} "
                    f"(潜力{potential_value:.1f}, {dom_label}, {effect_label})"
                )
        
        # 处理器官原基
        organs_list = new_genes_data.get("organs", [])
        if isinstance(organs_list, list):
            for organ_data in organs_list:
                if not isinstance(organ_data, dict):
                    continue
                
                organ_name = organ_data.get("name")
                if not organ_name:
                    continue
                
                # 跳过已存在的器官
                if organ_name in species.dormant_genes["organs"]:
                    continue
                
                # 解析器官数据
                organ_info = organ_data.get("organ_data", {})
                if not isinstance(organ_info, dict):
                    organ_info = {}
                
                category = organ_info.get("category", "sensory")
                organ_type = organ_info.get("type", organ_name)
                parameters = organ_info.get("parameters", {})
                if not isinstance(parameters, dict):
                    parameters = {}
                
                pressure_types = organ_data.get("pressure_types", ["competition", "predation"])
                if not isinstance(pressure_types, list):
                    pressure_types = ["competition", "predation"]
                
                dominance = organ_data.get("dominance", "codominant")
                valid_dominance = ["dominant", "codominant", "recessive", "overdominant"]
                if dominance not in valid_dominance:
                    dominance = "codominant"
                
                description = organ_data.get("description", "")
                
                # 构建休眠器官数据
                dormant_organ = {
                    "organ_data": {
                        "category": category,
                        "type": organ_type,
                        "parameters": parameters
                    },
                    "activation_threshold": 0.25,
                    "pressure_types": pressure_types,
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": "llm_speciation",
                    "dominance": dominance,
                    "development_stage": None,  # 渐进发育系统
                    "stage_start_turn": None,
                    "description": description,
                    "created_turn": turn_index,
                }
                
                species.dormant_genes["organs"][organ_name] = dormant_organ
                added_count += 1
                
                dom_label = {"dominant": "显", "codominant": "共显", "recessive": "隐", "overdominant": "超显"}.get(dominance, "")
                logger.debug(
                    f"[LLM新基因] {species.common_name} 获得器官原基: {organ_name} "
                    f"({category}, {dom_label})"
                )
        
        if added_count > 0:
            logger.info(
                f"[LLM新基因] {species.common_name} 成功添加 {added_count} 个LLM生成的休眠基因 "
                f"(特质: {len(traits_list) if isinstance(traits_list, list) else 0}, "
                f"器官: {len(organs_list) if isinstance(organs_list, list) else 0})"
            )
        
        return added_count
    
    def _try_speciation_breakthrough(
        self,
        species: Species,
        turn_index: int
    ) -> str | None:
        """【分化突破 v3.0】分化时有概率激活已有休眠基因
        
        【v3.0 更新】
        - 移除本地规则生成新基因的功能
        - 新基因完全由 LLM 在分化时生成（通过 new_dormant_genes 字段）
        - 本方法仅负责激活已有的休眠基因
        
        【v2.0 保留功能】
        - 排除有害突变（避免分化时激活有害基因）
        - 应用显隐性效果到表达值
        - 显性基因更容易被选中
        - 使用新的压力类型系统
        
        50% 概率在分化时直接激活一个已有的休眠基因。
        
        Args:
            species: 新分化的物种
            turn_index: 当前回合
            
        Returns:
            激活的基因名称，如果没有激活则返回 None
        """
        import random
        
        # 导入显隐性系数
        try:
            from .gene_constants import DOMINANCE_EXPRESSION_FACTOR, DominanceType
        except ImportError:
            DOMINANCE_EXPRESSION_FACTOR = {
                "recessive": 0.25, "codominant": 0.60, 
                "dominant": 1.0, "overdominant": 1.15
            }
            DominanceType = None
        
        # 50% 概率触发分化突破
        if random.random() > 0.50:
            return None
        
        # 确保 dormant_genes 存在
        if not species.dormant_genes:
            species.dormant_genes = {"traits": {}, "organs": {}}
        species.dormant_genes.setdefault("traits", {})
        species.dormant_genes.setdefault("organs", {})
        
        # 筛选可激活的休眠基因（排除有害突变）
        dormant_traits = []
        for name, data in species.dormant_genes.get("traits", {}).items():
            if data.get("activated", False):
                continue
            
            # 排除有害突变
            mutation_effect = data.get("mutation_effect", "beneficial")
            if mutation_effect in ("mildly_harmful", "harmful", "lethal"):
                continue
            
            # 计算选择权重（显性基因更容易被选中）
            dominance = data.get("dominance", "codominant")
            weight = 1.0
            if dominance == "dominant":
                weight = 1.5
            elif dominance == "overdominant":
                weight = 1.8
            elif dominance == "recessive":
                weight = 0.5
            
            dormant_traits.append((name, data, weight))
        
        if dormant_traits and random.random() < 0.70:  # 70% 概率激活已有休眠基因
            # 加权随机选择
            total_weight = sum(w for _, _, w in dormant_traits)
            r = random.random() * total_weight
            cumulative = 0
            selected = dormant_traits[0]
            for item in dormant_traits:
                cumulative += item[2]
                if r <= cumulative:
                    selected = item
                    break
            
            trait_name, gene_data, _ = selected
            potential_value = gene_data.get("potential_value", 8.0)
            dominance = gene_data.get("dominance", "codominant")
            
            # 应用显隐性效果
            if DominanceType:
                try:
                    dom_type = DominanceType(dominance)
                    expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(dom_type, 0.6)
                except ValueError:
                    expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(dominance, 0.6)
            else:
                expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(dominance, 0.6)
            
            expressed_value = potential_value * expression_factor
            
            # 直接激活到 abstract_traits
            species.abstract_traits[trait_name] = min(15.0, expressed_value)
            gene_data["activated"] = True
            gene_data["activation_turn"] = turn_index
            gene_data["expressed_value"] = expressed_value
            
            dom_label = {"dominant": "显性", "recessive": "隐性", "codominant": "共显性", "overdominant": "超显性"}.get(dominance, "")
            logger.info(
                f"[分化突破] {species.common_name} 激活休眠特质: {trait_name} = {expressed_value:.1f} "
                f"(潜力{potential_value:.1f}, {dom_label})"
            )
            return f"激活特质: {trait_name} ({dom_label})"
        
        # 【v3.0 移除】不再本地生成新基因
        # 新基因完全由 LLM 在分化时生成（通过 new_dormant_genes 字段）
        # 这样可以更好地利用 LLM 的语义理解能力，生成符合物种特性的基因
        return None
    
    def _check_and_trigger_plant_milestones(
        self,
        species: Species,
        turn_index: int
    ) -> dict | None:
        """【植物演化】主动检查并触发满足条件的里程碑
        
        在物种创建后调用，检查是否满足里程碑条件并自动触发。
        
        Args:
            species: 新创建的物种
            turn_index: 当前回合
            
        Returns:
            触发的里程碑结果，如果没有触发则返回 None
        """
        # 仅处理植物物种
        if not PlantTraitConfig.is_plant(species):
            return None
        
        # 获取下一个可能的里程碑
        next_milestone = plant_evolution_service.get_next_milestone(species)
        if not next_milestone:
            return None
        
        # 检查里程碑条件
        is_met, readiness, unmet = plant_evolution_service.check_milestone_requirements(
            species, next_milestone.id
        )
        
        if not is_met:
            # 条件未满足，记录日志但不触发
            if readiness >= 0.8:
                logger.debug(
                    f"[植物里程碑] {species.common_name} 接近触发 '{next_milestone.name}' "
                    f"(准备度: {readiness:.0%}, 未满足: {unmet})"
                )
            return None
        
        # 条件满足，触发里程碑
        result = plant_evolution_service.trigger_milestone(
            species, next_milestone.id, turn_index
        )
        
        if result.get("success"):
            logger.info(
                f"[植物里程碑] ✅ {species.common_name} 成功触发里程碑 '{next_milestone.name}'"
            )
            
            # 记录里程碑事件
            species_repository.log_event(
                LineageEvent(
                    lineage_code=species.lineage_code,
                    event_type="milestone",
                    payload={
                        "milestone_id": next_milestone.id,
                        "milestone_name": next_milestone.name,
                        "turn": turn_index,
                        "stage_change": result.get("stage_change"),
                        "new_organs": result.get("new_organs"),
                        "achievement": result.get("achievement"),
                    },
                )
            )
            
            return result
        
        return None
    
    def _generate_tile_context(
        self,
        assigned_tiles: set[int],
        tile_populations: dict[int, float],
        tile_mortality: dict[int, float],
        mortality_gradient: float,
        is_isolated: bool,
        tile_environment: dict | None = None,
        cluster_environment: dict | None = None,
    ) -> str:
        """生成地块级环境上下文描述
        
        用于传递给 AI，帮助其理解分化发生的地理背景
        
        Args:
            assigned_tiles: 该子代分配的地块
            tile_populations: 各地块种群分布
            tile_mortality: 各地块死亡率
            mortality_gradient: 死亡率梯度
            is_isolated: 是否地理隔离
            tile_environment: 【新增】地块环境详情（来自张量系统）
            cluster_environment: 【新增】该子代所属隔离簇的环境详情
            
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
        
        # 【优先使用】环境详情中的描述
        env = cluster_environment or tile_environment
        if env and env.get("environment_description"):
            parts.append(f"【环境特征】{env['environment_description']}")
            
            # 补充详细的环境数据
            env_details = []
            if "avg_temperature" in env:
                temp = env["avg_temperature"]
                temp_range = env.get("temp_range", (temp, temp))
                env_details.append(f"温度{temp_range[0]}~{temp_range[1]}°C")
            if "avg_humidity" in env:
                humidity = env["avg_humidity"]
                if humidity < 0.3:
                    env_details.append("干燥")
                elif humidity > 0.7:
                    env_details.append("潮湿")
            if "avg_salinity" in env:
                sal = env["avg_salinity"]
                if sal < 5:
                    env_details.append("淡水")
                elif sal > 40:
                    env_details.append(f"高盐度({sal:.0f}‰)")
            if "avg_elevation" in env:
                elev = env["avg_elevation"]
                if elev < -500:
                    env_details.append("深海")
                elif elev < -100:
                    env_details.append("浅海")
                elif elev > 2000:
                    env_details.append("高山")
            if "dominant_biome" in env and env["dominant_biome"] != "unknown":
                env_details.append(f"主要生境:{env['dominant_biome']}")
            
            if env_details:
                parts.append("(" + "，".join(env_details) + ")")
        
        # 区域规模和种群
        parts.append(f"分化区域{num_tiles}块，种群{int(region_pop):,}")
        
        # 环境压力描述（基于死亡率）
        if avg_rate > 0.5:
            pressure_desc = "高选择压力"
        elif avg_rate > 0.3:
            pressure_desc = "中等选择压力"
        else:
            pressure_desc = "低选择压力"
        parts.append(f"{pressure_desc}（死亡率{avg_rate:.1%}）")
        
        # 隔离状态
        if is_isolated:
            parts.append("存在地理隔离")
        
        # 压力梯度（驱动分化的关键因素）
        if mortality_gradient > 0.3:
            parts.append(f"显著环境梯度({mortality_gradient:.1%})→强分化压力")
        elif mortality_gradient > 0.15:
            parts.append(f"中等环境梯度({mortality_gradient:.1%})")
        
        # 局部异质性
        if len(region_rates) >= 2:
            local_gradient = max_rate - min_rate
            if local_gradient > 0.2:
                parts.append("区域内环境不均匀")
        
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
        
        【修复】与 prompt 中的预算限制保持一致：
        - prompt 告诉 AI: max_increase=3.0
        - 这里的验证应该允许一定容错（考虑权衡后的净增益）
        - 硬限制改为 6.0（允许 AI 略微超出，但不能离谱）
        
        Returns:
            (验证是否通过, 错误信息)
        """
        # 获取营养级对应的属性上限
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        # 1. 检查总和变化（与 prompt 中 max_increase=3.0 对应，但允许容错到 6.0）
        old_sum = sum(old_traits.values())
        new_sum = sum(new_traits.values())
        sum_diff = new_sum - old_sum
        
        # 【修改】净增益上限从 8 改为 6（prompt 要求 3，允许 2x 容错）
        # 超过 6 说明 AI 完全忽略了预算限制
        if sum_diff > 6.0:
            logger.warning(f"[属性验证] 净增益 {sum_diff:.1f} 超过上限 6.0（prompt 要求 ≤3.0）")
            return False, f"属性总和净增加{sum_diff:.1f}，超过上限6.0（建议≤3.0）"
        
        # 2. 检查总和是否超过营养级上限
        if new_sum > limits["total"]:
            return False, f"属性总和{new_sum:.1f}超过营养级T{trophic_level:.1f}的上限{limits['total']}"
        
        # 3. 检查单个属性是否超过特化上限
        above_specialized = [
            (k, v) for k, v in new_traits.items() if v > limits["specialized"]
        ]
        if above_specialized:
            return False, f"属性{above_specialized[0][0]}={above_specialized[0][1]:.1f}超过特化上限{limits['specialized']}"
        
        # 4. 检查超过基础上限的属性数量
        above_base_count = sum(1 for v in new_traits.values() if v > limits["base"])
        if above_base_count > 2:
            return False, f"{above_base_count}个属性超过基础上限{limits['base']}，最多允许2个"
        
        # 5. 检查权衡（有增必有减，除非是小幅提升）
        increases = sum(1 for k, v in new_traits.items() if v > old_traits.get(k, 0))
        decreases = sum(1 for k, v in new_traits.items() if v < old_traits.get(k, 0))
        
        # 【修改】放宽权衡检查：只有净增益 >4 且无任何减少时才拒绝
        if increases > 0 and decreases == 0 and sum_diff > 4.0:
            return False, f"净增益{sum_diff:.1f}但无权衡代价（需要至少一项属性降低）"
        
        return True, "验证通过"
    
    def _inherit_and_update_organs(
        self, parent: Species, ai_payload: dict, turn_index: int
    ) -> dict:
        """继承父代器官并应用渐进式器官进化
        
        支持三种格式（优先级从高到低）：
        - organ_changes: 【新】植物混合模式格式（支持自定义器官）
        - organ_evolution: 渐进式进化格式（动物）
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
        
        # 【植物混合模式】优先处理 organ_changes 格式
        if PlantTraitConfig.is_plant(parent):
            organ_changes = ai_payload.get("organ_changes", [])
            if organ_changes and isinstance(organ_changes, list):
                organs = self._process_plant_organ_changes(
                    organs, organ_changes, parent, turn_index
                )
                return organs  # 植物使用专用处理，跳过动物逻辑
        
        # 2. 优先使用新的 organ_evolution 格式
        organ_evolution = ai_payload.get("organ_evolution", [])
        if organ_evolution and isinstance(organ_evolution, list):
            # 推断生物类群进行验证
            biological_domain = self._infer_biological_domain(parent)

            # 验证渐进式进化规则
            _, valid_evolutions = self._validate_gradual_evolution(
                organ_evolution, parent.organs, biological_domain
            )
            # 归一化/去重/半径限制
            valid_evolutions = self._normalize_organ_evolution(
                valid_evolutions,
                parent,
                turn_index,
                getattr(parent, "gene_diversity_radius", 0.35) or 0.35,
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
    
    def _process_plant_organ_changes(
        self,
        organs: dict,
        organ_changes: list,
        parent: Species,
        turn_index: int
    ) -> dict:
        """【植物混合模式】处理植物的器官变化
        
        支持：
        1. 里程碑必须器官（固定名称）
        2. 参考器官（预定义）
        3. 自定义器官（LLM创意）
        
        Args:
            organs: 继承的器官字典
            organ_changes: AI返回的器官变化列表
            parent: 父代物种
            turn_index: 当前回合
            
        Returns:
            更新后的器官字典（含植物专用结构）
        """
        from .plant_evolution import (
            plant_evolution_service, 
            PLANT_ORGANS, 
            PLANT_ORGAN_CATEGORIES,
            MILESTONE_REQUIRED_ORGANS
        )
        
        current_stage = getattr(parent, 'life_form_stage', 0)
        
        # 初始化或继承植物器官
        plant_organs = getattr(parent, 'plant_organs', None)
        if plant_organs is None:
            plant_organs = {}
        else:
            plant_organs = dict(plant_organs)  # 深拷贝
            for cat, cat_organs in plant_organs.items():
                if isinstance(cat_organs, dict):
                    plant_organs[cat] = dict(cat_organs)
        
        for change in organ_changes:
            if not isinstance(change, dict):
                continue
            
            category = change.get("category", "")
            change_type = change.get("change_type", "new")
            organ_name = change.get("organ_name", "")
            
            # 参数可能是新格式的 parameters 或旧格式的 parameter+delta
            parameters = change.get("parameters", {})
            if not parameters:
                # 兼容旧格式
                param_name = change.get("parameter", "")
                delta = change.get("delta", 0)
                if param_name:
                    parameters = {param_name: delta}
            
            # 验证类别是否有效
            if category not in PLANT_ORGAN_CATEGORIES:
                logger.warning(f"[植物器官] 未知类别 {category}，跳过")
                continue
            
            cat_config = PLANT_ORGAN_CATEGORIES[category]
            min_stage = cat_config.get("min_stage", 0)
            
            # 验证阶段限制
            if current_stage < min_stage:
                logger.warning(
                    f"[植物器官] {organ_name} 需要阶段{min_stage}，当前阶段{current_stage}，跳过"
                )
                continue
            
            # 检查是否是里程碑必须器官
            is_milestone_organ, milestone_id = plant_evolution_service.is_milestone_required_organ(organ_name)
            
            if change_type == "new":
                # 新增器官
                if category not in plant_organs:
                    plant_organs[category] = {}
                
                # 使用验证系统获取修正后的参数
                valid, reason, corrected_params = plant_evolution_service.validate_custom_organ(
                    category, organ_name, parameters, current_stage
                )
                
                if valid:
                    plant_organs[category][organ_name] = {
                        **corrected_params,
                        "acquired_turn": turn_index,
                        "is_custom": organ_name not in PLANT_ORGANS.get(category, {}),
                    }
                    
                    # 里程碑器官特殊标记
                    if is_milestone_organ:
                        plant_organs[category][organ_name]["milestone_required"] = True
                        plant_organs[category][organ_name]["milestone_id"] = milestone_id
                    
                    organ_type = "自定义" if plant_organs[category][organ_name]["is_custom"] else "参考"
                    logger.info(
                        f"[植物器官] 新增{organ_type}器官: {organ_name} ({category})"
                    )
                else:
                    logger.warning(f"[植物器官] 验证失败: {reason}")
            
            elif change_type == "enhance":
                # 增强现有器官
                if category in plant_organs and organ_name in plant_organs[category]:
                    existing = plant_organs[category][organ_name]
                    
                    # 应用参数增强
                    param_ranges = cat_config.get("param_ranges", {})
                    for param, delta in parameters.items():
                        current_val = existing.get(param, 0)
                        new_val = current_val + delta
                        
                        # 范围钳制
                        if param in param_ranges:
                            min_val, max_val = param_ranges[param]
                            new_val = max(min_val, min(max_val, new_val))
                        
                        existing[param] = new_val
                    
                    existing["modified_turn"] = turn_index
                    logger.info(f"[植物器官] 增强器官: {organ_name} ({category})")
                else:
                    logger.warning(
                        f"[植物器官] 增强失败: 器官 {organ_name} 不存在于 {category}"
                    )
            
            elif change_type == "degrade":
                # 退化器官
                if category in plant_organs and organ_name in plant_organs[category]:
                    # 里程碑器官不能退化
                    if is_milestone_organ:
                        logger.warning(
                            f"[植物器官] 里程碑器官 {organ_name} 不能退化"
                        )
                        continue
                    
                    existing = plant_organs[category][organ_name]
                    existing["is_degraded"] = True
                    existing["degraded_turn"] = turn_index
                    logger.info(f"[植物器官] 退化器官: {organ_name} ({category})")
        
        # 将植物器官合并到通用器官字典中
        # 同时保持与动物器官系统的兼容性
        for category, cat_organs in plant_organs.items():
            if category not in organs:
                organs[category] = {}
            
            # 找到该类别中最高效的器官作为主器官
            if cat_organs:
                best_organ = None
                best_value = -1
                
                for name, data in cat_organs.items():
                    if data.get("is_degraded"):
                        continue
                    
                    # 获取主要参数值作为排序依据
                    cat_config = PLANT_ORGAN_CATEGORIES.get(category, {})
                    main_param = (cat_config.get("required_params") or ["efficiency"])[0]
                    value = data.get(main_param, 0)
                    
                    if value > best_value:
                        best_value = value
                        best_organ = name
                
                if best_organ:
                    organs[category]["type"] = best_organ
                    organs[category]["parameters"] = dict(cat_organs[best_organ])
                    organs[category]["evolution_stage"] = 4  # 植物器官默认完善
                    organs[category]["evolution_progress"] = 1.0
                    organs[category]["is_active"] = True
        
        # 保存完整的植物器官到隐藏字段（供后续使用）
        organs["_plant_organs"] = plant_organs
        
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
    
    def _apply_tradeoff_penalties(
        self,
        proposed_changes: dict[str, float],
        current_traits: dict[str, float],
    ) -> dict[str, float]:
        """基于自动代价计算器为增益添加权衡代价。"""
        if not proposed_changes or not self.tradeoff_calculator:
            return proposed_changes
        
        gains = {k: v for k, v in proposed_changes.items() if v > 0}
        if not gains:
            return proposed_changes
        
        try:
            penalties = self.tradeoff_calculator.calculate_penalties(gains, current_traits or {})
        except Exception as e:
            logger.debug(f"[权衡计算] 计算失败，跳过自动代价: {e}")
            return proposed_changes
        
        if not penalties:
            return proposed_changes
        
        merged = dict(proposed_changes)
        for trait, delta in penalties.items():
            merged[trait] = merged.get(trait, 0.0) + delta
        logger.debug(f"[权衡计算] 自动代价: {penalties}")
        return merged
    
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
            
            # 获取物种描述的embedding（使用统一的描述构建方法）
            from ..system.embedding import EmbeddingService
            species_text = EmbeddingService.build_species_text(species, include_traits=True, include_names=False)
            species_vec = self._embedding_service.embed([species_text], require_real=False)[0]
            
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

    # ------------------------------------------------------------------ #
    # 器官归一化与去重（闭集 organ_key + 语义相似度漏斗）
    # ------------------------------------------------------------------ #
    def _normalize_organ_evolution(
        self,
        organ_evolution: list,
        parent: Species,
        turn_index: int,
        gene_diversity_radius: float,
    ) -> list:
        """
        - 强制 organ_key 闭集：未知 key 会尝试根据名称猜测，失败则丢弃。
        - 语义漏斗：与父系/同批次名称相似度高（>0.85）则转为升级，不新增。
        - 半径限制：radius<0.2 禁止新增；radius>=0.4 仅允许新增1个新 organ_key。
        """
        if not organ_evolution:
            return []

        import re
        from difflib import SequenceMatcher

        catalog = {c["organ_key"]: c for c in self._organ_catalog}

        def _normalize_name(name: str) -> str:
            n = (name or "").lower()
            n = re.sub(r"[^\w\u4e00-\u9fff]+", "", n)
            return n

        def _guess_key_by_name(name: str) -> str | None:
            n = _normalize_name(name)
            for key, meta in catalog.items():
                base = _normalize_name(meta["default_name"])
                if base and base in n:
                    return key
            return None

        def _similar(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio()

        # 父系器官名称索引
        parent_index = []
        for cat, data in (parent.organs or {}).items():
            if isinstance(data, dict):
                parent_index.append(
                    {
                        "category": cat,
                        "name_norm": _normalize_name(data.get("type", "")),
                        "raw": data.get("type", ""),
                    }
                )

        new_allowed = gene_diversity_radius >= 0.4
        new_count = 0
        normalized: list = []

        for evo in organ_evolution:
            if not isinstance(evo, dict):
                continue

            raw_name = evo.get("structure_name", "") or evo.get("description", "") or evo.get("organ_key", "")
            organ_key = evo.get("organ_key") or _guess_key_by_name(raw_name)
            if organ_key not in catalog:
                organ_key = _guess_key_by_name(raw_name)
            if organ_key not in catalog:
                # 无法识别的 organ_key 丢弃，避免污染
                continue

            category = catalog[organ_key]["category"]
            evo["organ_key"] = organ_key
            evo["category"] = category
            name_norm = _normalize_name(raw_name)
            action = evo.get("action", "enhance")

            # 与父系同类比对，语义相似则转为升级
            similar_parent = False
            for meta in parent_index:
                if meta["category"] != category:
                    continue
                if _similar(name_norm, meta["name_norm"]) > 0.85:
                    similar_parent = True
                    break

            if similar_parent and action == "initiate":
                evo["action"] = "enhance"

            # 半径限制新增
            is_new = evo.get("action", "enhance") == "initiate"
            if is_new:
                if not new_allowed:
                    if category in (parent.organs or {}):
                        evo["action"] = "enhance"
                    else:
                        continue
                else:
                    if new_count >= 1:
                        continue
                    new_count += 1

            # 同批次 organ_key 去重：取更高 target_stage
            existing = next((x for x in normalized if x.get("organ_key") == organ_key), None)
            if existing:
                existing["target_stage"] = max(existing.get("target_stage", 1), evo.get("target_stage", 1))
                continue

            normalized.append(evo)

        return normalized


    async def _attempt_endosymbiosis_async(
        self,
        host: Species,
        average_pressure: float,
        pressure_context: str,
        turn_index: int
    ) -> dict | None:
        """【内共生】尝试触发罕见的内共生事件
        
        触发条件（必须全部满足）：
        1. 宿主是捕食者 (prey_species 不为空)
        2. 宿主面临高代谢压力 (speciation_pressure > 0.15 或 随机极低概率)
        3. 随机判定通过 (基础概率 2%)
        4. 成功找到合适的共生候选者（猎物）
        """
        import random
        
        # 1. 基础概率检查 (2%)
        # 如果压力极大，概率提升到 5%
        base_chance = 0.02
        if average_pressure > 6.0:
            base_chance = 0.05
            
        if random.random() > base_chance:
            return None
            
        # 2. 检查是否有猎物
        if not host.prey_species:
            return None
            
        # 3. 寻找合适的共生体（从猎物中选）
        # 优先选择有特殊能力的猎物（如光合作用、化能合成）
        candidates = []
        for prey_code in host.prey_species:
            prey = species_repository.get_by_code(prey_code)
            if not prey:
                continue
            
            # 评分：有特殊能力加分，体型小加分
            score = 1.0
            caps = set(prey.capabilities)
            if "photosynthesis" in caps or "光合作用" in caps:
                score += 5.0
            if "chemosynthesis" in caps or "化能合成" in caps:
                score += 5.0
            if "aerobic_respiration" in caps or "有氧呼吸" in caps:
                score += 3.0
                
            # 只有营养级比宿主低的才行
            if prey.trophic_level >= host.trophic_level:
                continue
                
            candidates.append((prey, score))
            
        if not candidates:
            return None
            
        # 按分数加权随机选择
        candidates.sort(key=lambda x: x[1], reverse=True)
        symbiont = candidates[0][0] # 选分最高的
        
        logger.info(f"[内共生尝试] 宿主 {host.common_name} 试图吞噬共生 {symbiont.common_name}")
        
        # 4. 调用 AI 生成内共生结果
        from ...ai.streaming_helper import invoke_with_heartbeat
        
        prompt = SPECIES_PROMPTS["endosymbiosis"].format(
            host_name=f"{host.latin_name} ({host.common_name})",
            symbiont_name=f"{symbiont.latin_name} ({symbiont.common_name})",
            pressure_context=pressure_context
        )
        
        try:
            response = await invoke_with_heartbeat(
                router=self.router,
                capability="speciation", # 复用 capability
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"内共生[{host.common_name}+{symbiont.common_name}]",
                timeout=45
            )
            
            content = self.router._parse_content(response)
            if not content:
                return None
                
            # 标记为内共生类型，以便后续处理
            content["speciation_type"] = "内共生突变"
            content["is_endosymbiosis"] = True
            
            # 记录共生来源，供后续逻辑使用
            content["symbiont_code"] = symbiont.lineage_code
            content["symbiont_name"] = symbiont.common_name
            
            logger.info(f"[内共生成功] 生成了基于 {symbiont.common_name} 的新器官")
            
            return content
            
        except Exception as e:
            logger.error(f"[内共生失败] AI调用出错: {e}")
            return None

