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
from ...repositories.species_repository import species_repository
from ...repositories.environment_repository import environment_repository
from ...schemas.responses import BranchingEvent
from .genetic_distance import GeneticDistanceCalculator
from .speciation_context import (
    summarize_food_chain_status,
    summarize_major_events,
    summarize_map_changes,
    summarize_organs,
)
from .speciation_ai import (
    build_batch_payload,
    call_batch_ai,
    call_ai_wrapper,
    generate_rule_based_fallback,
    normalize_ai_content,
    parse_batch_results,
)
from .speciation_naming import fallback_common_name, fallback_latin_name
from .speciation_lineage import (
    generate_multiple_lineage_codes,
    next_lineage_code,
)
from .speciation_process import (
    collect_candidate_entries,
    enhance_rule_fallback_descriptions,
    execute_active_ai_batches,
    generate_background_results,
    materialize_active_results,
    materialize_background_results,
    partition_speciation_entries,
)
from .speciation_habitat import (
    allocate_tiles_from_clusters,
    allocate_tiles_to_offspring,
    calculate_initial_habitat_for_child,
    calculate_suitability_for_species,
    detect_geographic_isolation,
    find_connected_clusters,
    inherit_habitat_distribution,
)
from .speciation_organs import (
    get_complexity_constraints,
    inherit_and_update_organs,
    infer_biological_domain,
    infer_complexity_by_embedding,
    infer_complexity_by_rules,
    normalize_organ_evolution,
    process_plant_organ_changes,
    update_capabilities,
    validate_gradual_evolution,
)
from .speciation_traits import (
    add_differentiation_noise,
    apply_tradeoff_penalties,
    clamp_traits_to_limit,
    enforce_trait_tradeoffs,
    validate_trait_changes,
)
from .speciation_dormant_genes import (
    process_ai_activated_genes,
    process_ai_new_dormant_genes,
    summarize_dormant_genes,
)
from .trait_config import TraitConfig, PlantTraitConfig
from .trophic import TrophicLevelCalculator
from .speciation_rules import SpeciationRules, speciation_rules  # 【新增】规则引擎
from .plant_evolution import (  # 【植物演化】
    PLANT_MILESTONES,
    PLANT_ORGANS,
    PLANT_ORGAN_CATEGORIES,
    plant_evolution_service,
)
from .plant_competition import plant_competition_calculator  # 【植物竞争】
from .description_enhancer import DescriptionEnhancerService  # 【描述增强】
from .gene_diversity import GeneDiversityService
from .naming_hints import NamingHintGenerator
from .organ_evolution_service import OrganEvolutionService, get_organ_evolution_service
from ...tensor.tradeoff import TradeoffCalculator
from ...core.config import get_settings

if TYPE_CHECKING:
    from ...repositories.genus_repository import GenusRepository
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

    def __init__(
        self,
        router,
        config: SpeciationConfig | None = None,
        genus_repository: GenusRepository | None = None,
    ) -> None:
        if genus_repository is None:
            from ...repositories.genus_repository import GenusRepository

            genus_repository = GenusRepository()
        self._genus_repository = genus_repository
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
        
        entries = collect_candidate_entries(
            self,
            mortality_results,
            existing_codes,
            direct_offspring_map=direct_offspring_map,
            turn_offspring_counts=turn_offspring_counts,
            spec_config=spec_config,
            current_species_count=current_species_count,
            turn_index=turn_index,
            is_early_game=is_early_game,
            average_pressure=average_pressure,
            pressure_summary=pressure_summary,
            density_damping=density_damping,
            map_changes=map_changes,
            major_events=major_events,
            settings=_settings,
            species_repository=species_repository,
            plant_evolution_service=plant_evolution_service,
            random_source=random,
            is_plant=PlantTraitConfig.is_plant,
        )

        if not entries and not self._deferred_requests:
            return []

        # 【优化】分离背景物种和非背景物种的 entries
        # 背景物种直接走规则生成，不调用 AI，节省 Token 和时间
        (
            background_entries,
            active_batch,
            self._deferred_requests,
        ) = partition_speciation_entries(
            entries,
            self._deferred_requests,
            max_deferred_requests=self.max_deferred_requests,
            max_speciation_per_turn=self.max_speciation_per_turn,
        )
        
        if background_entries:
            logger.info(
                f"[分化优化] 检测到 {len(background_entries)} 个背景物种分化，"
                f"跳过 AI 直接使用规则生成"
            )

        if not active_batch and not background_entries:
            logger.info("[分化] 没有可执行的分化任务，本回合跳过")
            return []

        logger.info(f"[分化] 开始批量处理 {len(active_batch)} 个AI分化任务 + {len(background_entries)} 个规则分化任务 (剩余排队 {len(self._deferred_requests)})")
        
        # ========== 【优化】先处理背景物种的规则分化 ==========
        # 背景物种完全跳过 AI，直接使用规则引擎生成，节省 Token 和时间
        # 【改进】现在使用完整的规则引擎约束系统，生成高质量的物种数据
        background_results = generate_background_results(
            background_entries,
            pressures,
            average_pressure=average_pressure,
            turn_index=turn_index,
            generate_rule_based_fallback=self._generate_rule_based_fallback,
        )
        
        # ========== AI 分化（仅针对非背景物种）==========
        results = await execute_active_ai_batches(
            active_batch,
            average_pressure=average_pressure,
            pressure_summary=pressure_summary,
            map_changes=map_changes,
            major_events=major_events,
            turn_index=turn_index,
            stream_callback=stream_callback,
            build_batch_payload=self._build_batch_payload,
            call_batch_ai=self._call_batch_ai,
            parse_batch_results=self._parse_batch_results,
            staggered_gather=staggered_gather,
        )

        # 3. 结果处理与写入
        logger.info(f"[分化] 开始处理 {len(results)} 个AI结果 + {len(background_results)} 个规则结果")
        new_species_events: list[BranchingEvent] = []
        materialize_active_results(
            results,
            active_batch,
            result_events=new_species_events,
            preparation_kwargs={
                "turn_index": turn_index,
                "average_pressure": average_pressure,
                "environment_pressure": env_pressure_dict,
                "queue_deferred_request": self._queue_deferred_request,
                "normalize_ai_content": self._normalize_ai_content,
                "generate_rule_based_fallback": (
                    self._generate_rule_based_fallback
                ),
            },
            materialization_kwargs={
                "turn_index": turn_index,
                "average_pressure": average_pressure,
                "validate_and_fix": self.rules.validate_and_fix,
                "create_species": self._create_species,
                "turn_offspring_counts": turn_offspring_counts,
                "rule_fallback_species": self._rule_fallback_species,
                "random_uniform": (
                    lambda low, high: random.uniform(low, high)
                ),
                "inherit_habitat_distribution": (
                    self._inherit_habitat_distribution
                ),
                "update_genetic_distances": (
                    self._update_genetic_distances
                ),
                "gene_library_service_owner": self,
                "genus_repository": self._genus_repository,
                "process_ai_activated_genes": (
                    self._process_ai_activated_genes
                ),
                "process_ai_new_dormant_genes": (
                    self._process_ai_new_dormant_genes
                ),
                "try_speciation_breakthrough": (
                    self._try_speciation_breakthrough
                ),
                "check_and_trigger_plant_milestones": (
                    self._check_and_trigger_plant_milestones
                ),
                "evaluate_new_species_viability": (
                    self.evaluate_new_species_viability
                ),
                "upsert_species": species_repository.upsert,
                "log_lineage_event": species_repository.log_event,
                "lineage_event_factory": LineageEvent,
                "branching_event_factory": BranchingEvent,
                "utcnow": lambda: datetime.utcnow(),
            },
        )
        
        # ========== 【优化】处理背景物种的规则分化结果 ==========
        materialize_background_results(
            background_results,
            result_events=new_species_events,
            turn_index=turn_index,
            average_pressure=average_pressure,
            validate_and_fix=self.rules.validate_and_fix,
            create_species=self._create_species,
            rule_fallback_species=self._rule_fallback_species,
            random_uniform=lambda low, high: random.uniform(low, high),
            inherit_habitat_distribution=(
                self._inherit_habitat_distribution
            ),
            gene_library_service_owner=self,
            genus_repository=self._genus_repository,
            try_speciation_breakthrough=(
                self._try_speciation_breakthrough
            ),
            upsert_species=species_repository.upsert,
            log_lineage_event=species_repository.log_event,
            lineage_event_factory=LineageEvent,
            branching_event_factory=BranchingEvent,
            utcnow=lambda: datetime.utcnow(),
        )
        
        # 【描述增强】处理规则fallback物种的描述增强
        await enhance_rule_fallback_descriptions(
            self._rule_fallback_species,
            description_enhancer=self.description_enhancer,
            upsert_species=species_repository.upsert,
        )
            
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
        return build_batch_payload(
            entries=entries,
            average_pressure=average_pressure,
            pressure_summary=pressure_summary,
            map_changes=map_changes,
            major_events=major_events,
            turn_index=turn_index,
            is_plant=PlantTraitConfig.is_plant,
            get_stage_name=PlantTraitConfig.get_stage_name,
            get_milestone_hints=plant_evolution_service.get_milestone_hints,
            format_competition_context=(
                plant_competition_calculator.format_competition_context
            ),
            get_evolution_hint=self.get_evolution_hint,
            naming_hint_generator=self.naming_hint_generator,
            summarize_map_changes=self._summarize_map_changes,
            summarize_major_events=self._summarize_major_events,
            get_tradeoff_ratio=lambda: getattr(
                self.tradeoff_calculator,
                "tradeoff_ratio",
                getattr(self, "tradeoff_ratio", 0.7),
            ),
        )
    
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
        return await call_batch_ai(
            self.router,
            payload,
            stream_callback,
            entries,
            attempt_endosymbiosis_async=self._attempt_endosymbiosis_async,
            is_plant=PlantTraitConfig.is_plant,
            get_organ_category_info_for_prompt=(
                plant_evolution_service.get_organ_category_info_for_prompt
            ),
        )
    
    def _parse_batch_results(
        self, 
        batch_response: dict, 
        entries: list[dict]
    ) -> list[dict | Exception]:
        """解析批量响应，返回与 entries 对应的结果列表
        
        【内共生支持】优先使用 _endo_overrides 中的结果
        【重要修复】如果响应包含 _use_fallback 标记，立即为所有entry生成规则fallback结果
        """
        return parse_batch_results(
            batch_response,
            entries,
            generate_rule_based_fallback=self._generate_rule_based_fallback,
        )

    async def _call_ai_wrapper(self, payload: dict, stream_callback: Callable[[str], Awaitable[None] | None] | Callable[[str, str, str], None] | None) -> dict:
        """AI调用包装器（带心跳检测）"""
        return await call_ai_wrapper(self.router, payload, stream_callback)

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
        return normalize_ai_content(ai_content)
    
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
        return generate_rule_based_fallback(
            parent=parent,
            new_code=new_code,
            survivors=survivors,
            speciation_type=speciation_type,
            average_pressure=average_pressure,
            environment_pressure=environment_pressure,
            turn_index=turn_index,
            preprocess_rules=self.rules.preprocess,
            generate_background_species_name=(
                self._generate_background_species_name
            ),
        )
    
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
        return next_lineage_code(parent_code, existing_codes)
    
    def _generate_multiple_lineage_codes(
        self, parent_code: str, existing_codes: set[str], num_offspring: int
    ) -> list[str]:
        return generate_multiple_lineage_codes(
            parent_code, existing_codes, num_offspring
        )
    
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
        
        # 【v3.1】父子强竞争标记
        # 新分化的物种与父代有极高的生态位重叠，竞争激烈
        # 这个因子会在扩散到同一区域时放大竞争效应
        morphology["parent_competition_factor"] = 0.85  # 85% 生态位重叠（高竞争）
        morphology["competition_parent_code"] = parent.lineage_code
        
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
    
    def evaluate_new_species_viability(
        self,
        species: Species,
        tensor_state,
        species_map: dict[str, int],
        turn_index: int,
    ) -> dict:
        """评估新物种的生存可行性
        
        【v3.0 新增】分化后的"生存筛选"机制：
        - 使用 TensorEcology 的适宜度/死亡率快速估算
        - 若平均适宜度 < 0.12 或净增长为负且分布 < 3 格，标记为高风险
        - 给新种设置惩罚系数（高死亡/低出生）
        
        Args:
            species: 新分化的物种
            tensor_state: 张量状态对象
            species_map: {lineage_code: tensor_index}
            turn_index: 当前回合
        
        Returns:
            dict: {
                "viable": bool,  # 是否可行
                "avg_suitability": float,  # 平均适宜度
                "tile_count": int,  # 分布地块数
                "mortality_penalty": float,  # 死亡率惩罚系数
                "birth_penalty": float,  # 出生率惩罚系数
                "recommendation": str,  # 建议（"pass", "penalize", "extinct"）
            }
        """
        result = {
            "viable": True,
            "avg_suitability": 0.5,
            "tile_count": 0,
            "mortality_penalty": 1.0,
            "birth_penalty": 1.0,
            "recommendation": "pass",
        }
        
        if tensor_state is None:
            logger.debug(f"[新种评估] {species.lineage_code}: 无张量状态，跳过评估")
            return result
        
        lineage = species.lineage_code
        idx = species_map.get(lineage)
        if idx is None:
            logger.debug(f"[新种评估] {species.lineage_code}: 不在张量映射中，跳过评估")
            return result
        
        try:
            import numpy as np
            
            # 获取该物种的种群和适宜度
            pop = tensor_state.pop[idx]  # (H, W)
            
            # 计算分布地块数
            tile_count = int((pop > 0).sum())
            result["tile_count"] = tile_count
            
            if tile_count == 0:
                logger.warning(f"[新种评估] {species.lineage_code}: 无分布地块，标记为高风险")
                result["viable"] = False
                result["recommendation"] = "extinct"
                return result
            
            # 尝试计算适宜度
            from ...tensor.ecology import extract_species_traits
            
            # 构造单物种的特质矩阵
            traits = extract_species_traits([species], {lineage: 0})
            
            # 使用已有的适宜度数据（如果可用）
            if hasattr(tensor_state, 'suitability') and tensor_state.suitability is not None:
                suit = tensor_state.suitability[idx]
            else:
                # 简化适宜度估算：使用环境匹配
                env = tensor_state.env
                # 温度匹配
                temp_trait = traits[0, 0] if traits.shape[1] > 0 else 5.0
                temp_pref = (temp_trait - 5.0) / 5.0  # 归一化到 [-1, 1]
                temp = env[0] if env.shape[0] > 0 else np.zeros((pop.shape[0], pop.shape[1]))
                temp_match = np.maximum(0.0, 1.0 - np.abs(temp - temp_pref) * 2.0)
                
                # 栖息地匹配
                land_pref = traits[0, 8] if traits.shape[1] > 8 else 0.5
                ocean_pref = traits[0, 9] if traits.shape[1] > 9 else 0.5
                if env.shape[0] >= 6:
                    habitat_match = env[4] * land_pref + env[5] * ocean_pref
                else:
                    habitat_match = np.ones_like(temp_match) * 0.5
                
                suit = temp_match * 0.5 + habitat_match * 0.5
            
            # 只考虑有种群的地块
            valid_mask = pop > 0
            if valid_mask.any():
                avg_suit = float(suit[valid_mask].mean())
            else:
                avg_suit = 0.0
            result["avg_suitability"] = avg_suit
            
            # 评估逻辑
            CRITICAL_SUITABILITY = 0.12
            LOW_SUITABILITY = 0.20
            MIN_TILES = 3
            
            if avg_suit < CRITICAL_SUITABILITY:
                # 极低适宜度：标记为快速灭绝候选
                result["viable"] = False
                result["recommendation"] = "extinct"
                result["mortality_penalty"] = 1.5
                result["birth_penalty"] = 0.5
                logger.warning(
                    f"[新种评估] {species.common_name}: 极低适宜度={avg_suit:.3f}<{CRITICAL_SUITABILITY}，"
                    f"标记为快速灭绝候选"
                )
            elif avg_suit < LOW_SUITABILITY or tile_count < MIN_TILES:
                # 低适宜度或分布过窄：应用惩罚系数
                result["viable"] = True
                result["recommendation"] = "penalize"
                # 惩罚系数：适宜度越低惩罚越重
                penalty_factor = 1.0 - (avg_suit - CRITICAL_SUITABILITY) / (LOW_SUITABILITY - CRITICAL_SUITABILITY)
                result["mortality_penalty"] = 1.0 + penalty_factor * 0.25  # 最高 1.25
                result["birth_penalty"] = 1.0 - penalty_factor * 0.20  # 最低 0.80
                logger.info(
                    f"[新种评估] {species.common_name}: 低适宜度={avg_suit:.3f}或分布窄={tile_count}格，"
                    f"应用惩罚(死亡x{result['mortality_penalty']:.2f}, 出生x{result['birth_penalty']:.2f})"
                )
            else:
                # 正常通过
                result["viable"] = True
                result["recommendation"] = "pass"
                logger.debug(
                    f"[新种评估] {species.common_name}: 适宜度={avg_suit:.3f}, 分布={tile_count}格, 通过"
                )
            
            # 将惩罚系数保存到物种的 morphology_stats
            if result["recommendation"] in ("penalize", "extinct"):
                if species.morphology_stats is None:
                    species.morphology_stats = {}
                species.morphology_stats["new_species_mortality_penalty"] = result["mortality_penalty"]
                species.morphology_stats["new_species_birth_penalty"] = result["birth_penalty"]
                species.morphology_stats["new_species_penalty_turns"] = 2  # 惩罚持续2回合
                species.morphology_stats["new_species_penalty_start"] = turn_index
            
            return result
            
        except Exception as e:
            logger.warning(f"[新种评估] {species.lineage_code}: 评估异常: {e}")
            return result
    
    def _inherit_habitat_distribution(
        self, 
        parent: Species, 
        child: Species, 
        turn_index: int,
        assigned_tiles: set[int] | None = None,
        reproduction_bonus: float = 0.0
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
        """
        return inherit_habitat_distribution(
            parent,
            child,
            turn_index,
            assigned_tiles,
            reproduction_bonus,
            self._calculate_initial_habitat_for_child,
        )
    
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
        return calculate_initial_habitat_for_child(
            child,
            parent,
            turn_index,
            assigned_tiles,
            self._calculate_suitability_for_species,
        )
    
    def _calculate_suitability_for_species(self, species: Species, tile) -> float:
        """计算物种对地块的适宜度 (v2.0 收紧版)
        
        【v2.0 改进】
        - 温度范围：5-10°C（极窄）
        - 温度惩罚：0.4/度
        - 湿度惩罚：4.0系数
        - 资源门槛：900
        """
        return calculate_suitability_for_species(species, tile)
    
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
        return detect_geographic_isolation(
            lineage_code,
            self._tile_mortality_cache,
            self._find_connected_clusters,
        )
    
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
        return find_connected_clusters(tile_ids, self._tile_adjacency)
    
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
        return allocate_tiles_from_clusters(
            clusters,
            candidate_tiles,
            num_offspring,
        )
    
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
        return allocate_tiles_to_offspring(
            parent_lineage_code,
            num_offspring,
            self._detect_geographic_isolation,
        )
    
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
        return summarize_food_chain_status(trophic_interactions)
    
    def _summarize_map_changes(self, map_changes: list) -> str:
        return summarize_map_changes(map_changes)
    
    def _summarize_major_events(self, major_events: list) -> str:
        return summarize_major_events(major_events)
    
    def _process_ai_activated_genes(
        self,
        species: Species,
        activated_genes: list[str],
        turn_index: int,
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
        return process_ai_activated_genes(
            species, activated_genes, turn_index
        )

    def _summarize_dormant_genes(
        self,
        species: Species,
        pressure_types: list[str] | None = None,
        pressure_strength: float = 5.0,
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
        return summarize_dormant_genes(
            species, pressure_types, pressure_strength
        )

    def _process_ai_new_dormant_genes(
        self,
        species: Species,
        new_genes_data: dict,
        turn_index: int,
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
        return process_ai_new_dormant_genes(
            species, new_genes_data, turn_index
        )

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
        return fallback_latin_name(parent_latin, ai_content)
    
    def _fallback_common_name(self, parent_common: str, ai_content: dict) -> str:
        return fallback_common_name(parent_common, ai_content)
    
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
        return validate_trait_changes(
            old_traits,
            new_traits,
            trophic_level,
            self.trophic_calculator.get_attribute_limits,
        )
    
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
        return inherit_and_update_organs(
            parent,
            ai_payload,
            turn_index,
            PlantTraitConfig.is_plant,
            self._process_plant_organ_changes,
            self._infer_biological_domain,
            self._validate_gradual_evolution,
            self._normalize_organ_evolution,
        )
    
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
        return process_plant_organ_changes(
            organs,
            organ_changes,
            parent,
            turn_index,
            plant_evolution_service,
            PLANT_ORGANS,
            PLANT_ORGAN_CATEGORIES,
        )
    
    def _update_capabilities(self, parent: Species, organs: dict) -> list[str]:
        """根据器官更新能力标签
        
        Args:
            parent: 父系物种
            organs: 当前器官字典
            
        Returns:
            能力标签列表（中文）
        """
        return update_capabilities(parent, organs)
    
    def _update_genetic_distances(self, offspring: Species, parent: Species, turn_index: int):
        """更新遗传距离矩阵"""
        if not parent.genus_code:
            return
        
        genus = self._genus_repository.get_by_code(parent.genus_code)
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
        
        self._genus_repository.update_distances(parent.genus_code, new_distances, turn_index)
    
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
        return clamp_traits_to_limit(
            traits,
            parent_traits,
            trophic_level,
            self.trophic_calculator.get_attribute_limits,
        )
    
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
        return apply_tradeoff_penalties(
            proposed_changes,
            current_traits,
            self.tradeoff_calculator,
        )
    
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
        return enforce_trait_tradeoffs(
            current_traits,
            proposed_changes,
            lineage_code,
        )
    
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
        return add_differentiation_noise(trait_changes, lineage_code)
    
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
        return infer_biological_domain(
            species,
            self._infer_complexity_by_embedding,
            self._infer_complexity_by_rules,
        )
    
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

        return infer_complexity_by_embedding(
            species,
            self._embedding_service,
            self._COMPLEXITY_REFERENCES,
            lambda: SpeciationService._complexity_embeddings,
            lambda embeddings: setattr(
                SpeciationService, "_complexity_embeddings", embeddings
            ),
            lambda: self._complexity_embeddings,
        )
    
    def _infer_complexity_by_rules(self, species: Species) -> int:
        """基于规则推断复杂度等级（降级方案）"""
        return infer_complexity_by_rules(species)
    
    def _get_complexity_constraints(self, complexity_level: str) -> dict:
        """获取复杂度等级的基础约束
        
        设计理念：允许自由演化，只限制"跳跃式"发展
        - 不限制能发展什么结构（让环境压力自然筛选）
        - 只限制原核/真核的基本分界（这是生物学硬约束）
        - 通过阶段系统保证渐进式发展
        """
        return get_complexity_constraints(complexity_level)
    
    def _summarize_organs(self, species: Species) -> str:
        return summarize_organs(species.organs)
    
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
        return validate_gradual_evolution(
            organ_evolution,
            parent_organs,
            biological_domain,
            self._get_complexity_constraints,
        )

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
        return normalize_organ_evolution(
            organ_evolution,
            parent,
            turn_index,
            gene_diversity_radius,
            self._organ_catalog,
        )


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
        from ...ai.streaming_helper import acall_with_heartbeat
        
        prompt = SPECIES_PROMPTS["endosymbiosis"].format(
            host_name=f"{host.latin_name} ({host.common_name})",
            symbiont_name=f"{symbiont.latin_name} ({symbiont.common_name})",
            pressure_context=pressure_context
        )
        
        try:
            response_text = await acall_with_heartbeat(
                router=self.router,
                capability="speciation",  # 复用 capability
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"内共生[{host.common_name}+{symbiont.common_name}]",
            )
            
            # 【修复】正确解析响应
            if isinstance(response_text, dict):
                content = response_text.get("content", {})
            else:
                content = response_text
            
            # 如果 content 是字符串，尝试解析 JSON
            if isinstance(content, str):
                try:
                    import json
                    content = json.loads(content)
                except json.JSONDecodeError:
                    logger.warning(f"[内共生] AI 返回非 JSON 格式: {content[:100]}")
                    return None
            
            if not isinstance(content, dict):
                logger.warning(f"[内共生] AI 返回格式错误: {type(content)}")
                return None
            
            # 验证必要字段
            required_fields = ["latin_name", "common_name", "description"]
            if not all(content.get(f) for f in required_fields):
                logger.warning(f"[内共生] AI 返回缺少必要字段")
                return None
                
            # 标记为内共生类型，以便后续处理
            content["speciation_type"] = "内共生突变"
            content["is_endosymbiosis"] = True
            
            # 记录共生来源，供后续逻辑使用
            content["symbiont_code"] = symbiont.lineage_code
            content["symbiont_name"] = symbiont.common_name
            
            logger.info(f"[内共生成功] 生成了基于 {symbiont.common_name} 的新器官")
            
            return content

        except asyncio.TimeoutError:
            logger.warning(f"[内共生超时] {host.common_name} + {symbiont.common_name}")
            return None    
        except Exception as e:
            logger.error(f"[内共生失败] AI调用出错: {e}")
            return None

