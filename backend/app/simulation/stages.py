"""
Simulation Stages - 流水线阶段定义

该模块定义了模拟回合中的各个阶段。每个阶段实现 Stage 协议，
可以被流水线执行器按顺序调用。

设计原则：
1. 每个阶段只负责一个相对独立的功能
2. 阶段之间通过 SimulationContext 交换数据
3. 阶段可以依赖 SimulationEngine 中的服务和仓储
4. 阶段执行可能是同步或异步的
5. 每个阶段声明自己的依赖和输出，便于验证执行顺序
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable, Set, List

if TYPE_CHECKING:
    from .context import SimulationContext
    from .engine import SimulationEngine

# 导入服务（用于替代 engine 方法调用）
from ..services.species.trophic_interaction import get_trophic_service
from ..services.species.intervention import InterventionService
from ..services.species.extinction_checker import ExtinctionChecker
from ..services.species.reemergence import ReemergenceService
from ..services.analytics.turn_report import TurnReportService
from ..services.analytics.population_snapshot import PopulationSnapshotService

logger = logging.getLogger(__name__)


# ============================================================================
# Stage 依赖声明
# ============================================================================

@dataclass
class StageDependency:
    """阶段依赖声明
    
    Attributes:
        requires_stages: 必须先执行的阶段名称集合
        requires_fields: 必须已填充的 Context 字段集合
        writes_fields: 本阶段会写入的 Context 字段集合
        optional_stages: 可选的前置阶段（如果存在则依赖）
    """
    requires_stages: Set[str] = field(default_factory=set)
    requires_fields: Set[str] = field(default_factory=set)
    writes_fields: Set[str] = field(default_factory=set)
    optional_stages: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        # 转换为 set 以防传入 list
        self.requires_stages = set(self.requires_stages)
        self.requires_fields = set(self.requires_fields)
        self.writes_fields = set(self.writes_fields)
        self.optional_stages = set(self.optional_stages)


class DependencyError(Exception):
    """依赖验证错误"""
    pass


@dataclass
class DependencyValidationResult:
    """依赖验证结果"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dependency_graph: str = ""  # 文本形式的依赖图


class StageDependencyValidator:
    """阶段依赖验证器"""
    
    # 引导字段：SimulationContext 创建时就已经存在的字段
    # 这些字段不需要由任何 Stage 提供
    BOOTSTRAP_FIELDS: Set[str] = {
        # 回合基础信息（构造时传入）
        "turn_index",
        "command",
        "event_callback",
        # 初始化为空列表/字典/默认值的字段
        "pressures",
        "modifiers",
        "major_events",
        "pressure_context",
        "map_changes",
        "temp_delta",
        "sea_delta",
        "all_species",
        "species_batch",
        "extinct_codes",
        "all_habitats",
        "all_tiles",
        "niche_metrics",
        "trophic_interactions",
        "preliminary_mortality",
        "critical_results",
        "focus_results",
        "background_results",
        "combined_results",
        "migration_events",
        "migration_count",
        "new_populations",
        "reproduction_results",
        "ai_status_evals",
        "activation_events",
        "gene_flow_count",
        "drift_count",
        "auto_hybrids",
        "adaptation_events",
        "branching_events",
        "background_summary",
        "mass_extinction",
        "reemergence_events",
        "species_snapshots",
        "embedding_turn_data",
    }
    
    def __init__(self, stages: List["Stage"]):
        self.stages = stages
        self.stage_map = {s.name: s for s in stages}
        self.order_map = {s.name: s.order for s in stages}
    
    def validate(self) -> DependencyValidationResult:
        """验证所有阶段的依赖关系"""
        errors = []
        warnings = []
        executed_stages: Set[str] = set()
        # 从引导字段开始，这些字段由 SimulationContext 初始化提供
        available_fields: Set[str] = set(self.BOOTSTRAP_FIELDS)
        
        # 按顺序检查每个阶段
        for stage in sorted(self.stages, key=lambda s: s.order):
            dep = stage.get_dependency()
            
            # 检查阶段依赖
            for req_stage in dep.requires_stages:
                if req_stage not in executed_stages:
                    if req_stage in self.stage_map:
                        errors.append(
                            f"❌ [{stage.name}] 依赖 [{req_stage}] 但它尚未执行 "
                            f"(order: {stage.order} vs {self.order_map.get(req_stage, '?')})"
                        )
                    else:
                        errors.append(
                            f"❌ [{stage.name}] 依赖未注册的阶段 [{req_stage}]"
                        )
            
            # 检查可选依赖（只在存在时检查顺序）
            for opt_stage in dep.optional_stages:
                if opt_stage in self.stage_map and opt_stage not in executed_stages:
                    if self.order_map.get(opt_stage, 0) > stage.order:
                        warnings.append(
                            f"⚠️ [{stage.name}] 可选依赖 [{opt_stage}] 的顺序在其之后"
                        )
            
            # 检查字段依赖
            for req_field in dep.requires_fields:
                if req_field not in available_fields:
                    # 检查是否由之前的阶段提供
                    provider = self._find_field_provider(req_field, executed_stages)
                    if provider:
                        available_fields.add(req_field)
                    else:
                        errors.append(
                            f"❌ [{stage.name}] 需要字段 [{req_field}] 但没有前置阶段提供它"
                        )
            
            # 记录本阶段的输出
            available_fields.update(dep.writes_fields)
            executed_stages.add(stage.name)
        
        # 生成依赖图
        dependency_graph = self._generate_dependency_graph()
        
        return DependencyValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            dependency_graph=dependency_graph,
        )
    
    def _find_field_provider(self, field_name: str, executed_stages: Set[str]) -> str | None:
        """查找提供指定字段的阶段"""
        for stage_name in executed_stages:
            stage = self.stage_map.get(stage_name)
            if stage:
                dep = stage.get_dependency()
                if field_name in dep.writes_fields:
                    return stage_name
        return None
    
    def _generate_dependency_graph(self) -> str:
        """生成文本形式的依赖图"""
        lines = ["Stage 依赖关系图:", "=" * 50]
        
        for stage in sorted(self.stages, key=lambda s: s.order):
            dep = stage.get_dependency()
            lines.append(f"\n[{stage.order:3d}] {stage.name}")
            
            if dep.requires_stages:
                lines.append(f"      ← 依赖阶段: {', '.join(sorted(dep.requires_stages))}")
            if dep.requires_fields:
                lines.append(f"      ← 需要字段: {', '.join(sorted(dep.requires_fields))}")
            if dep.writes_fields:
                lines.append(f"      → 输出字段: {', '.join(sorted(dep.writes_fields))}")
        
        lines.append("\n" + "=" * 50)
        return "\n".join(lines)


class StageOrder(Enum):
    """阶段执行顺序枚举"""
    INIT = 0
    PARSE_PRESSURES = 10
    MAP_EVOLUTION = 20
    TECTONIC_MOVEMENT = 25
    FETCH_SPECIES = 30
    FOOD_WEB = 35
    TIERING_AND_NICHE = 40
    PRELIMINARY_MORTALITY = 50
    PREY_DISTRIBUTION = 55
    MIGRATION = 60
    DISPERSAL = 65
    HUNGER_MIGRATION = 66
    POST_MIGRATION_NICHE = 70
    FINAL_MORTALITY = 80
    AI_STATUS_EVAL = 85
    SPECIATION_DATA_TRANSFER = 86
    POPULATION_UPDATE = 90
    GENE_ACTIVATION = 95
    GENE_FLOW = 100
    GENETIC_DRIFT = 105
    AUTO_HYBRIDIZATION = 110
    SUBSPECIES_PROMOTION = 115
    AI_PARALLEL_TASKS = 120
    BACKGROUND_MANAGEMENT = 130
    BUILD_REPORT = 140
    SAVE_MAP_SNAPSHOT = 150
    VEGETATION_COVER = 155
    SAVE_POPULATION_SNAPSHOT = 160
    EMBEDDING_HOOKS = 165
    SAVE_HISTORY = 170
    EXPORT_DATA = 175
    FINALIZE = 180


@runtime_checkable
class Stage(Protocol):
    """阶段协议 - 所有阶段必须实现此接口"""
    
    @property
    def name(self) -> str:
        """阶段名称（用于日志和调试）"""
        ...
    
    @property
    def order(self) -> int:
        """阶段顺序（数值越小越先执行）"""
        ...
    
    @property
    def is_async(self) -> bool:
        """是否为异步阶段"""
        ...
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        """执行阶段逻辑
        
        Args:
            ctx: 回合上下文
            engine: 模拟引擎（用于访问服务和仓储）
        """
        ...


@dataclass
class StageResult:
    """阶段执行结果"""
    stage_name: str
    success: bool
    error: Exception | None = None
    duration_ms: float = 0.0


class BaseStage(ABC):
    """阶段基类，提供通用功能
    
    子类应该重写 `get_dependency()` 方法来声明依赖关系。
    """
    
    def __init__(self, order: int, name: str, is_async: bool = False):
        self._order = order
        self._name = name
        self._is_async = is_async
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def order(self) -> int:
        return self._order
    
    @property
    def is_async(self) -> bool:
        return self._is_async
    
    def get_dependency(self) -> StageDependency:
        """获取本阶段的依赖声明
        
        子类应重写此方法来声明依赖关系。
        """
        return StageDependency()
    
    @abstractmethod
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        """子类必须实现此方法"""
        pass


# ============================================================================
# 具体阶段实现
# ============================================================================

class InitStage(BaseStage):
    """回合初始化阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.INIT.value, "回合初始化")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages=set(),  # 无前置依赖
            requires_fields={"turn_index", "command"},  # 需要基本信息
            writes_fields=set(),  # 只做清理，不写入字段
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        """清理各服务缓存"""
        engine.speciation.clear_tile_cache()
        engine.migration_advisor.clear_tile_mortality_cache()
        engine.tile_mortality.clear_accumulated_data()


class ParsePressuresStage(BaseStage):
    """解析环境压力阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.PARSE_PRESSURES.value, "解析环境压力")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"回合初始化"},
            requires_fields={"command", "turn_index"},
            writes_fields={"pressures", "modifiers", "major_events"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        logger.info("解析压力...")
        ctx.emit_event("stage", "🌡️ 解析环境压力", "环境")
        
        ctx.pressures = engine.environment.parse_pressures(ctx.command.pressures)
        ctx.modifiers = engine.environment.apply_pressures(ctx.pressures)
        ctx.major_events = engine.escalation_service.register(
            ctx.command.pressures, ctx.turn_index
        )


class MapEvolutionStage(BaseStage):
    """地图演化阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.MAP_EVOLUTION.value, "地图演化")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"解析环境压力"},
            requires_fields={"modifiers", "major_events", "turn_index"},
            writes_fields={"current_map_state", "map_changes", "temp_delta", "sea_delta"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        logger.info("地图演化...")
        ctx.emit_event("stage", "🗺️ 地图演化与海平面变化", "地质")
        
        ctx.current_map_state = environment_repository.get_state()
        if not ctx.current_map_state:
            logger.info("初始化地图状态...")
            ctx.emit_event("info", "初始化地图状态", "地质")
            ctx.current_map_state = environment_repository.save_state(
                {"stage_name": "稳定期", "stage_progress": 0, "stage_duration": 0}
            )
        
        ctx.map_changes = engine.map_evolution.advance(
            ctx.major_events, ctx.turn_index, ctx.modifiers, ctx.current_map_state
        ) or []
        
        # 计算温度和海平面变化
        if ctx.modifiers:
            temp_change, sea_level_change = engine.map_evolution.calculate_climate_changes(
                ctx.modifiers, ctx.current_map_state
            )
            ctx.temp_delta = temp_change
            ctx.sea_delta = sea_level_change
            
            if abs(temp_change) > 0.01 or abs(sea_level_change) > 0.01:
                new_temp = ctx.current_map_state.global_avg_temperature + temp_change
                new_sea_level = ctx.current_map_state.sea_level + sea_level_change
                
                logger.info(f"温度: {ctx.current_map_state.global_avg_temperature:.1f}°C → {new_temp:.1f}°C")
                logger.info(f"海平面: {ctx.current_map_state.sea_level:.1f}m → {new_sea_level:.1f}m")
                
                ctx.current_map_state.global_avg_temperature = new_temp
                ctx.current_map_state.sea_level = new_sea_level
                ctx.current_map_state.turn_index = ctx.turn_index
                environment_repository.save_state(ctx.current_map_state)
                
                if abs(sea_level_change) > 0.5:
                    engine.map_manager.reclassify_terrain_by_sea_level(new_sea_level)
        
        if not engine._use_tectonic_system:
            logger.info("[地形演化] 板块系统未启用，仅使用 MapEvolution 结果")
            ctx.emit_event("info", "⏭️ 板块系统未启用，采用 MapEvolution 结果", "地质")


class TectonicMovementStage(BaseStage):
    """板块构造运动阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.TECTONIC_MOVEMENT.value, "板块构造运动")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"地图演化"},
            requires_fields={"modifiers", "current_map_state"},
            writes_fields={"tectonic_result"},
            optional_stages=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not engine._use_tectonic_system or not engine.tectonic:
            return
        
        from ..repositories.environment_repository import environment_repository
        from ..repositories.species_repository import species_repository
        from ..services.species.habitat_manager import habitat_manager
        from ..services.species.dispersal_engine import dispersal_engine
        
        try:
            ctx.emit_event("stage", "🌍 板块构造运动", "地质")
            
            # 获取物种和栖息地数据
            all_species_for_tectonic = species_repository.list_species()
            alive_species = [sp for sp in all_species_for_tectonic if sp.status == "alive"]
            
            # 获取栖息地数据
            habitat_data = []
            for sp in alive_species:
                for h in getattr(sp, "habitats", []):
                    habitat_data.append({
                        "tile_id": getattr(h, "tile_id", 0),
                        "species_id": sp.id,
                        "population": getattr(h, "population", 0),
                    })
            
            map_tiles = environment_repository.list_tiles()
            
            ctx.tectonic_result = engine.tectonic.step(
                species_list=alive_species,
                habitat_data=habitat_data,
                map_tiles=map_tiles,
                pressure_modifiers=ctx.modifiers,
            )
            
            wilson = ctx.tectonic_result.wilson_phase
            logger.info(f"[板块系统] 威尔逊周期: {wilson['phase']} ({wilson['progress']:.0%})")
            
            for summary in ctx.tectonic_result.get_major_events_summary():
                ctx.emit_event("info", f"🌋 {summary}", "地质")
            
            # 应用地形变化
            if ctx.tectonic_result.terrain_changes and map_tiles:
                coord_map = {(t.x, t.y): t for t in map_tiles}
                updated_tiles = []
                
                for change in ctx.tectonic_result.terrain_changes:
                    tile = coord_map.get((change["x"], change["y"]))
                    if tile:
                        tile.elevation = change["new_elevation"]
                        if hasattr(tile, "temperature") and "new_temperature" in change:
                            tile.temperature = change["new_temperature"]
                        updated_tiles.append(tile)
                
                if updated_tiles:
                    environment_repository.upsert_tiles(updated_tiles)
                    avg_change = sum(abs(c["delta"]) for c in ctx.tectonic_result.terrain_changes) / len(ctx.tectonic_result.terrain_changes)
                    logger.info(f"[板块系统] 应用了 {len(updated_tiles)} 处地形变化 (平均 {avg_change:.2f}m)")
                    
                    engine.map_manager.reclassify_terrain_by_sea_level(ctx.current_map_state.sea_level)
                    logger.info("[板块系统] 水体重新分类完成（湖泊检测）")
                    
                    relocation_result = habitat_manager.handle_terrain_type_changes(
                        alive_species, updated_tiles, ctx.turn_index,
                        dispersal_engine=dispersal_engine
                    )
                    if relocation_result["forced_relocations"] > 0:
                        ctx.emit_event(
                            "migration",
                            f"🌊 海陆变化导致 {relocation_result['forced_relocations']} 次物种迁徙",
                            "生态"
                        )
                    if relocation_result.get("hunger_migrations", 0) > 0:
                        ctx.emit_event(
                            "migration",
                            f"🍖 {relocation_result['hunger_migrations']} 个消费者追踪猎物迁徙",
                            "生态"
                        )
            
            # 合并压力反馈
            for key, value in ctx.tectonic_result.pressure_feedback.items():
                ctx.modifiers[key] = ctx.modifiers.get(key, 0) + value
        
        except Exception as e:
            logger.warning(f"[板块系统] 运行失败: {e}")
            import traceback
            traceback.print_exc()


class FetchSpeciesStage(BaseStage):
    """获取物种列表阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.FETCH_SPECIES.value, "获取物种列表")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("获取物种列表...")
        ctx.emit_event("stage", "🧬 获取物种列表", "物种")
        
        ctx.all_species = species_repository.list_species()
        ctx.species_batch = [sp for sp in ctx.all_species if sp.status == "alive"]
        ctx.extinct_codes = {sp.lineage_code for sp in ctx.all_species if sp.status == "extinct"}
        
        logger.info(f"当前物种数量: {len(ctx.species_batch)} (总共{len(ctx.all_species)}个，其中{len(ctx.extinct_codes)}个已灭绝)")
        ctx.emit_event("info", f"当前存活物种: {len(ctx.species_batch)} 个", "物种")
        
        # Embedding 集成
        if engine._use_embedding_integration and ctx.species_batch:
            try:
                engine.embedding_integration.on_turn_start(ctx.turn_index, ctx.species_batch)
                engine.embedding_integration.on_pressure_applied(
                    ctx.turn_index, ctx.command.pressures, ctx.modifiers
                )
            except Exception as e:
                logger.warning(f"[Embedding集成] 回合开始钩子失败: {e}")
        
        # 气候调整
        if ctx.species_batch and (abs(ctx.temp_delta) > 0.1 or abs(ctx.sea_delta) > 0.5):
            habitat_manager.adjust_habitats_for_climate(
                ctx.species_batch,
                ctx.temp_delta,
                ctx.sea_delta,
                ctx.turn_index,
            )
        
        # 更新干预状态（使用 InterventionService）
        from ..repositories.species_repository import species_repository
        intervention_service = InterventionService(
            species_repository=species_repository,
            event_callback=ctx.emit_event,
        )
        intervention_service.update_intervention_status(ctx.species_batch)


class FoodWebStage(BaseStage):
    """食物网维护阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.FOOD_WEB.value, "食物网维护")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.info("维护食物网...")
        ctx.emit_event("stage", "🕸️ 维护食物网", "生态")
        
        try:
            ctx.food_web_analysis = engine.food_web_manager.maintain_food_web(
                ctx.all_species, species_repository, ctx.turn_index
            )
            food_web_changes = engine.food_web_manager.get_changes()
            
            if food_web_changes:
                ctx.emit_event(
                    "info",
                    f"🍽️ 更新了 {len(food_web_changes)} 个物种的食物关系",
                    "生态"
                )
                ctx.all_species = species_repository.list_species()
                ctx.species_batch = [sp for sp in ctx.all_species if sp.status == "alive"]
            
            if ctx.food_web_analysis.bottleneck_warnings:
                for warning in ctx.food_web_analysis.bottleneck_warnings[:3]:
                    ctx.emit_event("warning", warning, "生态")
            
            logger.info(
                f"[食物网] 健康度: {ctx.food_web_analysis.health_score:.0%}, "
                f"链接数: {ctx.food_web_analysis.total_links}, "
                f"孤立消费者: {len(ctx.food_web_analysis.orphaned_consumers)}"
            )
        except Exception as e:
            logger.warning(f"[食物网维护] 失败: {e}")


class TieringAndNicheStage(BaseStage):
    """物种分层与生态位分析阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.TIERING_AND_NICHE.value, "物种分层与生态位")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        logger.info("物种分层...")
        ctx.emit_event("stage", "📊 物种分层与生态位分析", "生态")
        
        ctx.tiered = engine.tiering.classify(ctx.species_batch, engine.watchlist)
        logger.info(f"Critical: {len(ctx.tiered.critical)}, Focus: {len(ctx.tiered.focus)}, Background: {len(ctx.tiered.background)}")
        ctx.emit_event("info", f"Critical: {len(ctx.tiered.critical)}, Focus: {len(ctx.tiered.focus)}, Background: {len(ctx.tiered.background)}", "生态")
        
        logger.info("生态位分析（迁徙前）...")
        ctx.all_habitats = environment_repository.latest_habitats()
        ctx.all_tiles = environment_repository.list_tiles()
        ctx.niche_metrics = engine.niche_analyzer.analyze(ctx.species_batch, habitat_data=ctx.all_habitats)


class PreliminaryMortalityStage(BaseStage):
    """初步死亡率评估阶段（迁徙前）"""
    
    def __init__(self):
        super().__init__(StageOrder.PRELIMINARY_MORTALITY.value, "初步死亡率评估")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        logger.info("【阶段1】计算营养级互动...")
        ctx.emit_event("stage", "⚔️ 【阶段1】计算营养级互动与死亡率", "生态")
        
        # 使用 TrophicInteractionService 计算营养级互动
        trophic_service = get_trophic_service()
        ctx.trophic_interactions = trophic_service.calculate(ctx.species_batch)
        
        logger.info("【阶段1】计算初步死亡率（迁徙前）...")
        
        if engine._use_tile_based_mortality and ctx.all_tiles:
            logger.info("[地块死亡率] 构建地块-物种矩阵...")
            ctx.emit_event("info", "🗺️ 使用按地块计算死亡率", "生态")
            
            engine.tile_mortality.build_matrices(ctx.species_batch, ctx.all_tiles, ctx.all_habitats)
            
            preliminary_critical = engine.tile_mortality.evaluate(
                ctx.tiered.critical, ctx.modifiers, ctx.niche_metrics, tier="critical",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            preliminary_focus = engine.tile_mortality.evaluate(
                ctx.tiered.focus, ctx.modifiers, ctx.niche_metrics, tier="focus",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            preliminary_background = engine.tile_mortality.evaluate(
                ctx.tiered.background, ctx.modifiers, ctx.niche_metrics, tier="background",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
        else:
            preliminary_critical = engine.mortality.evaluate(
                ctx.tiered.critical, ctx.modifiers, ctx.niche_metrics, tier="critical",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            preliminary_focus = engine.mortality.evaluate(
                ctx.tiered.focus, ctx.modifiers, ctx.niche_metrics, tier="focus",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            preliminary_background = engine.mortality.evaluate(
                ctx.tiered.background, ctx.modifiers, ctx.niche_metrics, tier="background",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
        
        ctx.preliminary_mortality = preliminary_critical + preliminary_focus + preliminary_background
        logger.info("【阶段1】初步死亡率计算完成，用于迁徙决策")
        
        # 传递地块死亡率数据给迁徙服务
        if engine._use_tile_based_mortality and ctx.all_tiles:
            engine.migration_advisor.clear_tile_mortality_cache()
            tile_mortality_data = engine.tile_mortality.get_all_species_tile_mortality()
            for lineage_code, tile_rates in tile_mortality_data.items():
                engine.migration_advisor.set_tile_mortality_data(lineage_code, tile_rates)
            logger.debug(f"[数据传递] 向迁徙服务传递了 {len(tile_mortality_data)} 个物种的地块死亡率数据")


class MigrationStage(BaseStage):
    """迁徙执行阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.MIGRATION.value, "迁徙执行")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("【阶段2】迁徙建议与执行...")
        ctx.emit_event("stage", "🦅 【阶段2】迁徙建议与执行", "生态")
        
        # 更新猎物分布缓存
        ctx.all_habitats = environment_repository.latest_habitats()
        habitat_manager.update_prey_distribution_cache(ctx.species_batch, ctx.all_habitats)
        
        # 为消费者设置猎物密度数据
        for sp in ctx.species_batch:
            if sp.status != "alive" or not sp.id:
                continue
            trophic_level = getattr(sp, 'trophic_level', 1.0)
            if trophic_level >= 2.0:
                prey_tiles = habitat_manager.get_prey_tiles_for_consumer(trophic_level)
                species_habitats = [h for h in ctx.all_habitats if h.species_id == sp.id]
                current_prey_density = 0.0
                if species_habitats and prey_tiles:
                    for hab in species_habitats:
                        tile_prey = prey_tiles.get(hab.tile_id, 0.0)
                        current_prey_density += tile_prey * hab.suitability
                    total_suitability = sum(h.suitability for h in species_habitats)
                    if total_suitability > 0:
                        current_prey_density /= total_suitability
                engine.migration_advisor.set_prey_density_data(sp.lineage_code, current_prey_density)
        
        logger.debug("[猎物追踪] 已更新消费者猎物密度数据")
        
        # 获取冷却期物种
        ctx.cooldown_species = {
            sp.lineage_code for sp in ctx.species_batch
            if sp.status == "alive" and habitat_manager.is_migration_on_cooldown(
                sp.lineage_code, ctx.turn_index, cooldown_turns=2
            )
        }
        if ctx.cooldown_species:
            logger.debug(f"[迁徙冷却] {len(ctx.cooldown_species)} 个物种处于冷却期，跳过")
        
        # 规划迁徙
        ctx.migration_events = engine.migration_advisor.plan(
            ctx.preliminary_mortality,
            ctx.modifiers, ctx.major_events, ctx.map_changes,
            current_turn=ctx.turn_index,
            cooldown_species=ctx.cooldown_species
        )
        
        # 执行迁徙
        if ctx.migration_events and engine.migration_advisor.enable_actual_migration:
            logger.info(f"[迁徙] 执行 {len(ctx.migration_events)} 个迁徙事件...")
            tiles = environment_repository.list_tiles()
            
            for event in ctx.migration_events:
                migrating_species = next(
                    (sp for sp in ctx.species_batch if sp.lineage_code == event.lineage_code),
                    None
                )
                if migrating_species:
                    success = habitat_manager.execute_migration(
                        migrating_species, event, tiles, ctx.turn_index
                    )
                    if success:
                        ctx.migration_count += 1
                        logger.info(f"[迁徙成功] {migrating_species.common_name}: {event.origin} → {event.destination}")
                        ctx.emit_event("migration", f"🗺️ 迁徙: {migrating_species.common_name} 从 {event.origin} 迁往 {event.destination}", "迁徙")
                        
                        # 处理共生物种追随
                        followers = habitat_manager.get_symbiotic_followers(migrating_species, ctx.species_batch)
                        if followers:
                            new_habitats = environment_repository.latest_habitats()
                            new_tile_ids = [
                                h.tile_id for h in new_habitats
                                if h.species_id == migrating_species.id
                            ]
                            for follower in followers:
                                follow_success = habitat_manager.execute_symbiotic_following(
                                    migrating_species, follower, new_tile_ids, tiles, ctx.turn_index
                                )
                                if follow_success:
                                    ctx.symbiotic_follow_count += 1
            
            log_msg = f"【阶段2】迁徙执行完成: {ctx.migration_count}/{len(ctx.migration_events)} 个物种成功迁徙"
            if ctx.symbiotic_follow_count > 0:
                log_msg += f", {ctx.symbiotic_follow_count} 个共生物种追随"
            logger.info(log_msg)
            ctx.emit_event("info", f"{ctx.migration_count} 个物种完成迁徙", "生态")
        else:
            logger.debug(f"[迁徙] 生成了 {len(ctx.migration_events)} 个迁徙建议（未执行或无迁徙）")


class FinalMortalityStage(BaseStage):
    """最终死亡率评估阶段（迁徙后）"""
    
    def __init__(self):
        super().__init__(StageOrder.FINAL_MORTALITY.value, "最终死亡率评估")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        # 重新分析生态位（如有迁徙）
        if ctx.migration_count > 0:
            logger.info("【阶段3】重新分析生态位（迁徙后）...")
            ctx.emit_event("stage", "📊 【阶段3】重新分析生态位", "生态")
            ctx.all_habitats = environment_repository.latest_habitats()
            ctx.niche_metrics = engine.niche_analyzer.analyze(ctx.species_batch, habitat_data=ctx.all_habitats)
            logger.info("【阶段3】生态位重新分析完成")
        
        # 重新计算死亡率
        logger.info("【阶段3】重新计算死亡率（迁徙后）...")
        ctx.emit_event("stage", "💀 【阶段3】重新计算死亡率", "生态")
        
        if engine._use_tile_based_mortality and ctx.all_tiles:
            if ctx.migration_count > 0:
                ctx.all_habitats = environment_repository.latest_habitats()
                engine.tile_mortality.build_matrices(ctx.species_batch, ctx.all_tiles, ctx.all_habitats)
            
            ctx.critical_results = engine.tile_mortality.evaluate(
                ctx.tiered.critical, ctx.modifiers, ctx.niche_metrics, tier="critical",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            ctx.focus_results = engine.tile_mortality.evaluate(
                ctx.tiered.focus, ctx.modifiers, ctx.niche_metrics, tier="focus",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            ctx.background_results = engine.tile_mortality.evaluate(
                ctx.tiered.background, ctx.modifiers, ctx.niche_metrics, tier="background",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
        else:
            ctx.critical_results = engine.mortality.evaluate(
                ctx.tiered.critical, ctx.modifiers, ctx.niche_metrics, tier="critical",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            ctx.focus_results = engine.mortality.evaluate(
                ctx.tiered.focus, ctx.modifiers, ctx.niche_metrics, tier="focus",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
            ctx.background_results = engine.mortality.evaluate(
                ctx.tiered.background, ctx.modifiers, ctx.niche_metrics, tier="background",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes
            )
        
        ctx.combined_results = ctx.critical_results + ctx.focus_results + ctx.background_results
        
        # 日志：对比迁徙前后变化
        if ctx.migration_count > 0:
            for final_result in ctx.combined_results:
                prelim_result = next(
                    (r for r in ctx.preliminary_mortality if r.species.lineage_code == final_result.species.lineage_code),
                    None
                )
                if prelim_result and abs(final_result.death_rate - prelim_result.death_rate) > 0.05:
                    logger.info(
                        f"[死亡率变化] {final_result.species.common_name}: "
                        f"{prelim_result.death_rate:.1%} → {final_result.death_rate:.1%}"
                    )
        
        logger.info("【阶段3】最终死亡率计算完成")


class PopulationUpdateStage(BaseStage):
    """种群更新阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.POPULATION_UPDATE.value, "种群更新")
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("计算种群变化（死亡+繁殖并行）...")
        ctx.emit_event("stage", "💀🐣 计算种群变化", "物种")
        
        # 更新环境动态修正系数
        temp_change = ctx.modifiers.get("temperature", 0.0) if ctx.modifiers else 0.0
        sea_level_change = 0.0
        if ctx.current_map_state:
            prev_sea = getattr(ctx.current_map_state, '_prev_sea_level', ctx.current_map_state.sea_level)
            sea_level_change = ctx.current_map_state.sea_level - prev_sea
            ctx.current_map_state._prev_sea_level = ctx.current_map_state.sea_level
        engine.reproduction_service.update_environmental_modifier(temp_change, sea_level_change)
        
        # 准备繁殖数据
        survival_rates = {
            item.species.lineage_code: 1.0
            for item in ctx.combined_results
        }
        niche_data = {
            code: (metrics.overlap, metrics.saturation)
            for code, metrics in ctx.niche_metrics.items()
        }
        
        # 临时设置种群为初始值
        for item in ctx.combined_results:
            item.species.morphology_stats["population"] = item.initial_population
        
        ctx.reproduction_results = engine.reproduction_service.apply_reproduction(
            ctx.species_batch, niche_data, survival_rates,
            habitat_manager=habitat_manager
        )
        
        # 计算最终种群
        for item in ctx.combined_results:
            code = item.species.lineage_code
            initial = item.initial_population
            death_rate = item.death_rate
            
            repro_pop = ctx.reproduction_results.get(code, initial)
            repro_gain = max(0, repro_pop - initial)
            
            survivors = int(initial * (1.0 - death_rate))
            survivor_ratio = survivors / initial if initial > 0 else 0
            
            offspring_survival = 0.8 + 0.2 * (1.0 - death_rate)
            effective_gain = int(repro_gain * survivor_ratio * offspring_survival)
            
            final_pop = survivors + effective_gain
            ctx.new_populations[code] = max(0, final_pop)
            
            item.births = effective_gain
            item.final_population = final_pop
            item.survivors = survivors
            
            if abs(final_pop - initial) > initial * 0.3:
                logger.debug(
                    f"[种群变化] {item.species.common_name}: "
                    f"{initial:,} → {final_pop:,} "
                    f"(死亡{death_rate:.1%}, 存活{survivors:,}, 繁殖+{effective_gain:,})"
                )
        
        # 应用最终种群
        for species in ctx.species_batch:
            if species.lineage_code in ctx.new_populations:
                species.morphology_stats["population"] = ctx.new_populations[species.lineage_code]
                species_repository.upsert(species)
        
        # 更新灭绝状态（使用 ExtinctionChecker）
        extinction_checker = ExtinctionChecker(
            species_repository=species_repository,
            turn_counter=ctx.turn_index,
            event_callback=ctx.emit_event,
        )
        extinction_checker.check_and_apply(ctx.combined_results, ctx.new_populations)
        
        logger.info("种群变化计算完成")
        ctx.emit_event("info", "种群变化计算完成", "物种")
        
        # 更新慢性衰退追踪
        for result in ctx.combined_results:
            old_pop = result.initial_population
            new_pop = ctx.new_populations.get(result.species.lineage_code, result.survivors)
            growth_rate = new_pop / old_pop if old_pop > 0 else 1.0
            engine.migration_advisor.update_decline_streak(
                result.species.lineage_code,
                result.death_rate,
                growth_rate
            )


# ============================================================================
# 遗传与演化阶段
# ============================================================================

class PreyDistributionStage(BaseStage):
    """猎物分布更新阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.PREY_DISTRIBUTION.value, "猎物分布更新")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"初步死亡率评估"},
            requires_fields={"species_batch", "all_habitats"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.debug("更新猎物分布缓存...")
        ctx.all_habitats = environment_repository.latest_habitats()
        habitat_manager.update_prey_distribution_cache(ctx.species_batch, ctx.all_habitats)


class DispersalStage(BaseStage):
    """被动扩散阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.DISPERSAL.value, "被动扩散")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"迁徙执行"},
            requires_fields={"species_batch", "all_tiles"},
            writes_fields={"dispersal_results"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        from ..services.species.dispersal_engine import process_batch_dispersal
        
        logger.info("执行被动扩散...")
        ctx.emit_event("stage", "🌱 被动扩散", "生态")
        
        try:
            tiles = ctx.all_tiles or environment_repository.list_tiles()
            habitats = ctx.all_habitats or environment_repository.latest_habitats()
            
            # 构建死亡率数据
            mortality_data = {}
            for result in ctx.combined_results:
                mortality_data[result.species.lineage_code] = result.death_rate
            
            if tiles and ctx.species_batch:
                ctx.dispersal_results = process_batch_dispersal(
                    ctx.species_batch,
                    tiles,
                    habitats,
                    mortality_data,
                    ctx.turn_index,
                    engine.embedding_integration if hasattr(engine, 'embedding_integration') else None,
                )
                if ctx.dispersal_results:
                    logger.info(f"[扩散] {len(ctx.dispersal_results)} 个物种发生扩散")
        except Exception as e:
            logger.warning(f"[扩散] 执行失败: {e}")


class HungerMigrationStage(BaseStage):
    """饥饿驱动迁徙阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.HUNGER_MIGRATION.value, "饥饿迁徙")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"被动扩散"},
            requires_fields={"species_batch", "preliminary_mortality"},
            writes_fields={"hunger_migrations_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.debug("检查饥饿驱动迁徙...")
        
        ctx.hunger_migrations_count = 0
        
        # 消费者追踪猎物
        for sp in ctx.species_batch:
            if sp.status != "alive":
                continue
            
            trophic_level = getattr(sp, 'trophic_level', 1.0)
            if trophic_level < 2.0:
                continue
            
            # 检查是否需要追踪猎物
            result = next(
                (r for r in ctx.preliminary_mortality if r.species.lineage_code == sp.lineage_code),
                None
            )
            
            if result and result.death_rate > 0.3:
                # 高死亡率消费者可能需要追踪猎物
                prey_tiles = habitat_manager.get_prey_tiles_for_consumer(trophic_level)
                if prey_tiles:
                    # 实际迁徙逻辑由 habitat_manager 处理
                    ctx.hunger_migrations_count += 1
        
        if ctx.hunger_migrations_count > 0:
            logger.info(f"[饥饿迁徙] {ctx.hunger_migrations_count} 个消费者追踪猎物")


class PostMigrationNicheStage(BaseStage):
    """迁徙后生态位重新分析阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.POST_MIGRATION_NICHE.value, "后迁徙生态位")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"饥饿迁徙"},
            requires_fields={"species_batch", "migration_count"},
            writes_fields={"niche_metrics"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        if ctx.migration_count > 0:
            logger.info("重新分析生态位（迁徙后）...")
            ctx.emit_event("stage", "📊 后迁徙生态位分析", "生态")
            ctx.all_habitats = environment_repository.latest_habitats()
            ctx.niche_metrics = engine.niche_analyzer.analyze(
                ctx.species_batch, habitat_data=ctx.all_habitats
            )


class SpeciationDataTransferStage(BaseStage):
    """物种分化数据传递阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.SPECIATION_DATA_TRANSFER.value, "分化数据传递")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages=set(),  # 无强依赖
            optional_stages={"AI状态评估"},  # AI状态评估可选
            requires_fields={"combined_results", "modifiers"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        # 传递数据给分化服务
        logger.debug("传递数据给分化服务...")
        
        if hasattr(engine, 'speciation') and ctx.combined_results:
            # 构建分化候选数据
            candidates = {}
            for result in ctx.combined_results:
                candidates[result.species.lineage_code] = {
                    "death_rate": result.death_rate,
                    "population": result.species.morphology_stats.get("population", 0),
                }
            engine.speciation.set_speciation_candidates(candidates)


class GeneActivationStage(BaseStage):
    """基因激活阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.GENE_ACTIVATION.value, "基因激活")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"种群更新"},
            requires_fields={"species_batch", "modifiers"},
            writes_fields={"activation_events"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.info("基因激活检查...")
        ctx.emit_event("stage", "🧬 基因激活", "进化")
        
        try:
            # 使用 batch_check 方法检查基因激活
            ctx.activation_events = engine.gene_activation_service.batch_check(
                ctx.species_batch,
                ctx.combined_results,
                ctx.turn_index,
            )
            
            if ctx.activation_events:
                logger.info(f"[基因激活] {len(ctx.activation_events)} 个物种发生基因激活")
                for species in ctx.species_batch:
                    species_repository.upsert(species)
        except Exception as e:
            logger.warning(f"[基因激活] 失败: {e}")
            ctx.activation_events = []


class GeneFlowStage(BaseStage):
    """基因流动阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.GENE_FLOW.value, "基因流动")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"基因激活"},
            requires_fields={"species_batch", "all_habitats"},
            writes_fields={"gene_flow_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        from ..repositories.genus_repository import genus_repository
        
        logger.info("基因流动计算...")
        ctx.emit_event("stage", "🔄 基因流动", "进化")
        
        try:
            # 按属分组物种
            genus_groups: dict[str, list] = {}
            for species in ctx.species_batch:
                if not species.genus_code:
                    continue
                if species.genus_code not in genus_groups:
                    genus_groups[species.genus_code] = []
                genus_groups[species.genus_code].append(species)
            
            total_flow_count = 0
            for genus_code, species_list in genus_groups.items():
                if len(species_list) < 2:
                    continue
                genus = genus_repository.get_by_code(genus_code)
                if not genus:
                    continue
                flow_count = engine.gene_flow_service.apply_gene_flow(genus, species_list)
                total_flow_count += flow_count
            
            ctx.gene_flow_count = total_flow_count
            
            if ctx.gene_flow_count > 0:
                logger.info(f"[基因流动] 发生了 {ctx.gene_flow_count} 对基因交流")
                for species in ctx.species_batch:
                    species_repository.upsert(species)
        except Exception as e:
            logger.warning(f"[基因流动] 失败: {e}")
            ctx.gene_flow_count = 0


class GeneticDriftStage(BaseStage):
    """遗传漂变阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.GENETIC_DRIFT.value, "遗传漂变")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"基因流动"},
            requires_fields={"species_batch"},
            writes_fields={"genetic_drift_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        import random
        from ..repositories.species_repository import species_repository
        
        logger.debug("遗传漂变检查...")
        
        ctx.genetic_drift_count = 0
        
        for sp in ctx.species_batch:
            if sp.status != "alive":
                continue
            
            population = sp.morphology_stats.get("population", 0) or 0
            
            # 小种群更容易发生遗传漂变
            if population < 1000 and random.random() < 0.1:
                # 随机修改一个隐藏特征
                if hasattr(sp, 'hidden_traits') and sp.hidden_traits:
                    trait_key = random.choice(list(sp.hidden_traits.keys()))
                    old_value = sp.hidden_traits[trait_key]
                    if isinstance(old_value, (int, float)):
                        drift = random.gauss(0, 0.1)
                        sp.hidden_traits[trait_key] = old_value * (1 + drift)
                        ctx.genetic_drift_count += 1
        
        if ctx.genetic_drift_count > 0:
            logger.info(f"[遗传漂变] {ctx.genetic_drift_count} 个物种发生漂变")
            for sp in ctx.species_batch:
                species_repository.upsert(sp)


class AutoHybridizationStage(BaseStage):
    """自动杂交阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.AUTO_HYBRIDIZATION.value, "自动杂交")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"遗传漂变"},
            requires_fields={"species_batch", "all_habitats"},
            writes_fields={"auto_hybrids"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.debug("自动杂交检查...")
        
        ctx.auto_hybrids = []
        
        # 检查同域物种是否可以杂交
        # 实际逻辑需要根据物种亲缘关系和地理分布
        # 这里只是占位实现
        
        if ctx.auto_hybrids:
            logger.info(f"[自动杂交] 产生了 {len(ctx.auto_hybrids)} 个杂交种")
            ctx.emit_event("speciation", f"🧬 杂交: {len(ctx.auto_hybrids)} 个新杂交种", "进化")


class SubspeciesPromotionStage(BaseStage):
    """亚种晋升阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.SUBSPECIES_PROMOTION.value, "亚种晋升")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"遗传漂变"},  # 依赖遗传漂变而非自动杂交
            optional_stages={"自动杂交"},  # 自动杂交可选
            requires_fields={"species_batch"},
            writes_fields={"promotion_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.debug("亚种晋升检查...")
        
        ctx.promotion_count = 0
        
        # 检查是否有亚种需要晋升为独立物种
        for sp in ctx.species_batch:
            if sp.status != "alive":
                continue
            
            # 检查亚种隔离时间和遗传分化程度
            subspecies = getattr(sp, 'subspecies', [])
            for sub in subspecies:
                isolation_turns = ctx.turn_index - sub.get('created_turn', 0)
                genetic_distance = sub.get('genetic_distance', 0)
                
                # 长期隔离的亚种可能晋升
                if isolation_turns > 50 and genetic_distance > 0.3:
                    ctx.promotion_count += 1
        
        if ctx.promotion_count > 0:
            logger.info(f"[亚种晋升] {ctx.promotion_count} 个亚种可能晋升")


# ============================================================================
# AI 相关阶段
# ============================================================================

class AIStatusEvalStage(BaseStage):
    """AI 状态评估阶段
    
    使用 AI 评估物种当前状态，为后续决策提供支持。
    """
    
    def __init__(self):
        super().__init__(StageOrder.AI_STATUS_EVAL.value, "AI状态评估", is_async=True)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"最终死亡率"},
            requires_fields={"combined_results", "modifiers"},
            writes_fields={"ai_status_evals", "emergency_responses", "pressure_context"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not engine._use_ai_pressure_response:
            logger.debug("[AI状态评估] AI 压力响应已禁用")
            return
        
        logger.info("开始 AI 状态评估...")
        ctx.emit_event("stage", "🤖 AI 状态评估", "AI")
        
        try:
            # 构建压力上下文
            pressure_parts = []
            for key, value in (ctx.modifiers or {}).items():
                if abs(value) > 0.1:
                    pressure_parts.append(f"{key}: {value:+.1f}")
            ctx.pressure_context = "; ".join(pressure_parts) if pressure_parts else "环境稳定"
            
            # 评估关键物种
            if hasattr(engine, 'ai_status_evaluator') and engine.ai_status_evaluator:
                species_to_eval = []
                for result in ctx.critical_results + ctx.focus_results:
                    if result.death_rate > 0.1:
                        species_to_eval.append({
                            "species": result.species,
                            "death_rate": result.death_rate,
                            "population": result.survivors,
                        })
                
                if species_to_eval:
                    evals = await asyncio.wait_for(
                        engine.ai_status_evaluator.batch_evaluate(
                            species_to_eval, ctx.modifiers, ctx.major_events
                        ),
                        timeout=60
                    )
                    ctx.ai_status_evals = evals or {}
                    
                    # 提取紧急响应
                    for code, eval_result in ctx.ai_status_evals.items():
                        if hasattr(eval_result, 'emergency_actions') and eval_result.emergency_actions:
                            ctx.emergency_responses.extend(eval_result.emergency_actions)
                    
                    logger.info(f"[AI状态评估] 评估了 {len(ctx.ai_status_evals)} 个物种")
        
        except asyncio.TimeoutError:
            logger.warning("[AI状态评估] 超时")
        except Exception as e:
            logger.error(f"[AI状态评估] 失败: {e}")


class AINarrativeStage(BaseStage):
    """AI 叙事生成阶段
    
    为物种生成叙事描述。
    """
    
    def __init__(self):
        super().__init__(StageOrder.AI_PARALLEL_TASKS.value, "AI叙事生成", is_async=True)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages=set(),  # 无强依赖
            optional_stages={"AI状态评估"},  # AI状态评估可选
            requires_fields={"critical_results", "focus_results", "modifiers"},
            writes_fields={"narrative_results"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not engine._use_ai_pressure_response:
            logger.debug("[AI叙事] AI 压力响应已禁用")
            return
        
        logger.info("开始生成物种叙事...")
        ctx.emit_event("stage", "📖 生成物种叙事", "AI")
        
        try:
            if not hasattr(engine, 'ai_pressure_service') or not engine.ai_pressure_service:
                return
            
            # 准备物种数据
            species_data = []
            for result in ctx.critical_results + ctx.focus_results:
                events = []
                if hasattr(result, 'death_causes') and result.death_causes:
                    events.append(f"主要压力: {result.death_causes}")
                species_data.append({
                    "species": result.species,
                    "tier": result.tier,
                    "death_rate": result.death_rate,
                    "status_eval": ctx.ai_status_evals.get(result.species.lineage_code),
                    "events": events,
                })
            
            if not species_data:
                return
            
            # 构建环境描述
            global_env = "; ".join([
                f"{k}: {v:.1f}" for k, v in (ctx.modifiers or {}).items() if abs(v) > 0.1
            ]) or "环境稳定"
            major_events_str = ", ".join([e.kind for e in ctx.major_events]) if ctx.major_events else "无"
            
            # 生成叙事
            ctx.narrative_results = await asyncio.wait_for(
                engine.ai_pressure_service.generate_species_narratives(
                    species_data,
                    ctx.turn_index,
                    global_env,
                    major_events_str,
                ),
                timeout=180
            )
            
            # 应用叙事到结果
            if ctx.narrative_results:
                narrative_map = {nr.lineage_code: nr for nr in ctx.narrative_results}
                for result in ctx.critical_results + ctx.focus_results:
                    code = result.species.lineage_code
                    if code in narrative_map:
                        nr = narrative_map[code]
                        result.ai_narrative = nr.narrative
                        result.ai_headline = getattr(nr, 'headline', '')
                        result.ai_mood = getattr(nr, 'mood', '')
                
                logger.info(f"[AI叙事] 生成了 {len(ctx.narrative_results)} 个叙事")
        
        except asyncio.TimeoutError:
            logger.warning("[AI叙事] 超时")
            ctx.narrative_results = []
        except Exception as e:
            logger.error(f"[AI叙事] 失败: {e}")
            ctx.narrative_results = []


class AdaptationStage(BaseStage):
    """适应性演化阶段
    
    处理物种对环境压力的适应性变化。
    """
    
    def __init__(self):
        super().__init__(StageOrder.AI_PARALLEL_TASKS.value + 1, "适应性演化", is_async=True)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"种群更新"},
            requires_fields={"species_batch", "modifiers", "combined_results"},
            writes_fields={"adaptation_events"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not engine._use_ai_pressure_response:
            logger.debug("[适应性演化] AI 压力响应已禁用")
            return
        
        logger.info("开始适应性演化...")
        ctx.emit_event("stage", "🧬 适应性演化", "进化")
        
        try:
            if not hasattr(engine, 'adaptation_service') or not engine.adaptation_service:
                return
            
            ctx.adaptation_events = await asyncio.wait_for(
                engine.adaptation_service.apply_adaptations_async(
                    ctx.species_batch,
                    ctx.modifiers,
                    ctx.turn_index,
                    ctx.pressures,
                    mortality_results=ctx.combined_results
                ),
                timeout=300
            )
            
            if ctx.adaptation_events:
                logger.info(f"[适应性演化] {len(ctx.adaptation_events)} 个物种发生适应")
                ctx.emit_event("info", f"适应演化: {len(ctx.adaptation_events)} 个物种", "进化")
                
                # 保存更新
                from ..repositories.species_repository import species_repository
                for species in ctx.species_batch:
                    species_repository.upsert(species)
        
        except asyncio.TimeoutError:
            logger.warning("[适应性演化] 超时")
            ctx.adaptation_events = []
        except Exception as e:
            logger.error(f"[适应性演化] 失败: {e}")
            ctx.adaptation_events = []


class SpeciationStage(BaseStage):
    """物种分化阶段
    
    处理物种分化事件，创建新物种。
    """
    
    def __init__(self):
        super().__init__(StageOrder.AI_PARALLEL_TASKS.value + 2, "物种分化", is_async=True)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"适应性演化"},
            requires_fields={"species_batch", "critical_results", "focus_results", "modifiers"},
            writes_fields={"branching_events"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        logger.info("开始物种分化...")
        ctx.emit_event("stage", "🌱 物种分化", "分化")
        
        try:
            # Embedding 集成：获取演化提示
            if engine._use_embedding_integration and hasattr(engine, 'embedding_integration'):
                try:
                    evolution_hints = {}
                    pressure_vectors = engine.embedding_integration.map_pressures_to_vectors(ctx.modifiers)
                    
                    for result in ctx.critical_results + ctx.focus_results:
                        sp = result.species
                        pop = sp.morphology_stats.get("population", 0)
                        if pop > 5000 and 0.05 < result.death_rate < 0.5:
                            hint = engine.embedding_integration.get_evolution_hints(sp, pressure_vectors)
                            if hint:
                                evolution_hints[sp.lineage_code] = hint
                    
                    if evolution_hints:
                        engine.speciation.set_evolution_hints(evolution_hints)
                        logger.info(f"[Embedding] 为 {len(evolution_hints)} 个物种提供演化提示")
                except Exception as e:
                    logger.warning(f"[Embedding] 获取演化提示失败: {e}")
            
            # 执行分化
            ctx.branching_events = await asyncio.wait_for(
                engine.speciation.process_async(
                    mortality_results=ctx.critical_results + ctx.focus_results,
                    existing_codes={s.lineage_code for s in ctx.species_batch},
                    average_pressure=sum(ctx.modifiers.values()) / (len(ctx.modifiers) or 1),
                    turn_index=ctx.turn_index,
                    map_changes=ctx.map_changes,
                    major_events=ctx.major_events,
                    pressures=ctx.pressures,
                    trophic_interactions=ctx.trophic_interactions,
                ),
                timeout=600
            )
            
            if ctx.branching_events:
                logger.info(f"[物种分化] 发生了 {len(ctx.branching_events)} 次分化")
                
                # 将新物种加入列表
                from ..repositories.species_repository import species_repository
                all_species_updated = species_repository.list_species()
                new_species = [
                    sp for sp in all_species_updated
                    if sp.status == "alive" and sp.lineage_code not in {s.lineage_code for s in ctx.species_batch}
                ]
                
                for sp in new_species:
                    ctx.emit_event("speciation", f"🌱 新物种: {sp.common_name}", "分化")
                    
                    # Embedding 记录
                    if engine._use_embedding_integration and hasattr(engine, 'embedding_integration'):
                        try:
                            parent_sp = next(
                                (s for s in ctx.species_batch if s.lineage_code == sp.parent_code),
                                None
                            )
                            if parent_sp:
                                engine.embedding_integration.on_speciation(
                                    ctx.turn_index, parent_sp, [sp], trigger_reason="环境压力分化"
                                )
                        except Exception as e:
                            logger.warning(f"[Embedding] 记录分化事件失败: {e}")
                
                ctx.species_batch.extend(new_species)
                logger.info(f"新物种已加入，总数: {len(ctx.species_batch)}")
        
        except asyncio.TimeoutError:
            logger.warning("[物种分化] 超时")
            ctx.branching_events = []
        except Exception as e:
            logger.error(f"[物种分化] 失败: {e}")
            ctx.branching_events = []


class BackgroundManagementStage(BaseStage):
    """背景物种管理阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.BACKGROUND_MANAGEMENT.value, "背景物种管理")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"亚种晋升"},  # 依赖亚种晋升
            optional_stages={"物种分化"},  # 物种分化可选
            requires_fields={"background_results", "combined_results"},
            writes_fields={"background_summary", "mass_extinction", "reemergence_events"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.info("背景物种管理...")
        ctx.emit_event("stage", "🌾 背景物种管理", "生态")
        
        ctx.background_summary = engine.background_manager.summarize(ctx.background_results)
        ctx.mass_extinction = engine.background_manager.detect_mass_extinction(ctx.combined_results)
        
        if ctx.mass_extinction:
            promoted = engine.background_manager.promote_candidates(ctx.background_results)
            if promoted:
                # 使用 ReemergenceService 评估物种重现
                reemergence_service = ReemergenceService(species_repository)
                ctx.reemergence_events = reemergence_service.evaluate_reemergence(promoted, ctx.modifiers)
                if ctx.reemergence_events:
                    ctx.emit_event("info", f"大灭绝后重现: {len(ctx.reemergence_events)} 个物种", "生态")


class BuildReportStage(BaseStage):
    """构建报告阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.BUILD_REPORT.value, "构建报告", is_async=True)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"背景物种管理"},
            requires_fields={"combined_results", "pressures", "branching_events"},
            writes_fields={"report", "species_snapshots"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        logger.info("构建回合报告...")
        ctx.emit_event("stage", "📝 构建回合报告", "报告")
        
        try:
            # 定义流式回调
            async def on_narrative_chunk(chunk: str):
                ctx.emit_event("narrative_token", chunk, "报告")
            
            # 使用 TurnReportService 构建报告
            turn_report_service = TurnReportService(
                report_builder=engine.report_builder,
                environment_repository=environment_repository,
                trophic_service=engine.trophic_service,
                emit_event_fn=ctx.emit_event,
            )
            
            ctx.report = await asyncio.wait_for(
                turn_report_service.build_report(
                    turn_index=ctx.turn_index,
                    mortality_results=ctx.combined_results,
                    pressures=ctx.pressures,
                    branching_events=ctx.branching_events,
                    background_summary=ctx.background_summary,
                    reemergence_events=ctx.reemergence_events,
                    major_events=ctx.major_events,
                    map_changes=ctx.map_changes,
                    migration_events=ctx.migration_events,
                    stream_callback=on_narrative_chunk,
                ),
                timeout=90
            )
            ctx.emit_event("stage", "✅ 报告生成完成", "报告")
        
        except asyncio.TimeoutError:
            logger.warning("[报告生成] 超时，使用简单模式")
            ctx.emit_event("warning", "⏱️ AI 超时，使用快速模式", "报告")
            
            # 构建简单报告
            from ..schemas.responses import TurnReport
            ctx.report = TurnReport(
                turn_index=ctx.turn_index,
                narrative="本回合报告生成超时。",
                pressures_summary=str(ctx.modifiers),
                species=[],
                branching_events=ctx.branching_events,
                major_events=ctx.major_events,
            )
        except Exception as e:
            logger.error(f"[报告生成] 失败: {e}")


class SaveMapSnapshotStage(BaseStage):
    """保存地图快照阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.SAVE_MAP_SNAPSHOT.value, "保存地图快照")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"构建报告"},
            requires_fields={"species_batch", "all_tiles"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.info("保存地图栖息地快照...")
        ctx.emit_event("stage", "💾 保存地图快照", "系统")
        
        all_species_final = species_repository.list_species()
        
        # 获取地块级存活数据
        tile_survivors = {}
        if engine._use_tile_based_mortality and ctx.all_tiles:
            tile_survivors = engine.tile_mortality.get_all_species_tile_survivors()
        
        reproduction_gains = {}
        
        engine.map_manager.snapshot_habitats(
            all_species_final,
            turn_index=ctx.turn_index,
            tile_survivors=tile_survivors,
            reproduction_gains=reproduction_gains
        )


class VegetationCoverStage(BaseStage):
    """植被覆盖更新阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.VEGETATION_COVER.value, "植被覆盖更新")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"保存地图快照"},
            requires_fields=set(),
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        from ..repositories.species_repository import species_repository
        from ..services.geo.vegetation_cover import vegetation_cover_service
        
        logger.info("更新植被覆盖...")
        ctx.emit_event("stage", "🌿 更新植被覆盖", "环境")
        
        try:
            tiles = environment_repository.list_tiles()
            habitats = environment_repository.latest_habitats()
            all_species = species_repository.list_species()
            species_map = {sp.id: sp for sp in all_species if sp.id}
            
            updated_tiles = vegetation_cover_service.update_vegetation_cover(
                tiles, habitats, species_map
            )
            if updated_tiles:
                environment_repository.upsert_tiles(updated_tiles)
                logger.info(f"[植被覆盖] 更新了 {len(updated_tiles)} 个地块")
        except Exception as e:
            logger.warning(f"[植被覆盖] 更新失败: {e}")


class SavePopulationSnapshotStage(BaseStage):
    """保存种群快照阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.SAVE_POPULATION_SNAPSHOT.value, "保存种群快照")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"植被覆盖更新"},
            requires_fields=set(),
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.info("保存人口快照...")
        ctx.emit_event("stage", "💾 保存种群快照", "系统")
        
        # 使用 PopulationSnapshotService 保存快照
        all_species_final = species_repository.list_species()
        snapshot_service = PopulationSnapshotService(species_repository)
        snapshot_service.save_snapshots(all_species_final, ctx.turn_index)


class EmbeddingStage(BaseStage):
    """Embedding 集成阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.EMBEDDING_HOOKS.value, "Embedding集成")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"保存种群快照"},
            requires_fields={"species_batch", "combined_results"},
            writes_fields={"embedding_turn_data"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not engine._use_embedding_integration:
            logger.debug("[Embedding] Embedding 集成已禁用")
            return
        
        logger.info("Embedding 集成钩子...")
        ctx.emit_event("stage", "🔗 Embedding 集成", "AI")
        
        try:
            # 记录灭绝事件
            for result in ctx.combined_results:
                if result.species.status == "extinct":
                    cause = ""
                    if hasattr(result, 'death_causes') and result.death_causes:
                        cause = result.death_causes
                    elif result.species.morphology_stats.get("extinction_reason"):
                        cause = result.species.morphology_stats["extinction_reason"]
                    else:
                        cause = f"死亡率{result.death_rate:.1%}"
                    
                    engine.embedding_integration.on_extinction(
                        ctx.turn_index, result.species, cause=cause
                    )
            
            # 回合结束钩子
            ctx.embedding_turn_data = engine.embedding_integration.on_turn_end(
                ctx.turn_index, ctx.species_batch
            )
            
            if ctx.embedding_turn_data.get("taxonomy"):
                logger.info("[Embedding] 分类树已更新")
        
        except Exception as e:
            logger.warning(f"[Embedding] 失败: {e}")
            ctx.embedding_turn_data = {}


class SaveHistoryStage(BaseStage):
    """保存历史记录阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.SAVE_HISTORY.value, "保存历史记录")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"保存种群快照"},  # 依赖保存种群快照
            optional_stages={"Embedding集成"},  # Embedding可选
            requires_fields={"report"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.history_repository import history_repository
        from ..models.history import TurnLog
        
        logger.info("保存历史记录...")
        ctx.emit_event("stage", "💾 保存历史记录", "系统")
        
        if not ctx.report:
            logger.warning("[历史记录] 没有报告可保存")
            return
        
        record_data = ctx.report.model_dump(mode="json")
        # 安全获取 embedding_turn_data（可能不存在）
        embedding_turn_data = getattr(ctx, 'embedding_turn_data', None)
        if embedding_turn_data:
            record_data["embedding_integration"] = {
                "has_taxonomy": "taxonomy" in embedding_turn_data,
                "has_narrative": "narrative" in embedding_turn_data,
            }
        
        history_repository.log_turn(
            TurnLog(
                turn_index=ctx.report.turn_index,
                pressures_summary=ctx.report.pressures_summary,
                narrative=ctx.report.narrative,
                record_data=record_data,
            )
        )


class ExportDataStage(BaseStage):
    """导出数据阶段"""
    
    def __init__(self):
        super().__init__(StageOrder.EXPORT_DATA.value, "导出数据")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"保存历史记录"},
            requires_fields={"report", "species_batch"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        logger.info("导出数据...")
        ctx.emit_event("stage", "💾 导出数据", "系统")
        
        if ctx.report:
            engine.exporter.export_turn(ctx.report, ctx.species_batch)


class FinalizeStage(BaseStage):
    """最终化阶段
    
    更新回合计数器，完成回合。
    """
    
    def __init__(self):
        super().__init__(StageOrder.FINALIZE.value, "最终化")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"导出数据"},
            requires_fields={"report"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        logger.info("最终化回合...")
        
        # 更新 MapState.turn_index
        map_state = environment_repository.get_state()
        if map_state:
            map_state.turn_index = ctx.turn_index
            environment_repository.save_state(map_state)
        
        ctx.emit_event("turn_complete", f"✅ 回合 {ctx.turn_index} 完成", "系统")
        logger.info(f"回合 {ctx.turn_index} 完成")


# ============================================================================
# 阶段注册表
# ============================================================================

def get_default_stages() -> list[BaseStage]:
    """获取默认的阶段列表（按顺序排列）"""
    return sorted([
        InitStage(),
        ParsePressuresStage(),
        MapEvolutionStage(),
        TectonicMovementStage(),
        FetchSpeciesStage(),
        FoodWebStage(),
        TieringAndNicheStage(),
        PreliminaryMortalityStage(),
        MigrationStage(),
        FinalMortalityStage(),
        PopulationUpdateStage(),
        AIStatusEvalStage(),
        AINarrativeStage(),
        AdaptationStage(),
        SpeciationStage(),
        BackgroundManagementStage(),
        BuildReportStage(),
        SaveMapSnapshotStage(),
        VegetationCoverStage(),
        SavePopulationSnapshotStage(),
        EmbeddingStage(),
        SaveHistoryStage(),
        ExportDataStage(),
        FinalizeStage(),
    ], key=lambda s: s.order)

