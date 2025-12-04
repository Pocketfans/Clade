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
        # 插件数据共享
        "plugin_data",
        "embedding_turn_data",
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
    RESOURCE_CALC = 32  # 资源计算（NPP/承载力）
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
    EMBEDDING_PLUGINS = 166
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
        self._plugin_manager = None
        self._plugin_init_attempted = False
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages=set(),  # 无前置依赖
            requires_fields={"turn_index", "command"},  # 需要基本信息
            writes_fields=set(),  # 只做清理，不写入字段
        )
    
    def _get_plugin_manager(self, engine: 'SimulationEngine'):
        """延迟获取插件管理器"""
        if self._plugin_init_attempted:
            return self._plugin_manager
        
        self._plugin_init_attempted = True
        
        embedding_service = getattr(engine, 'embedding_service', None)
        if not embedding_service:
            return None
        
        try:
            from ..services.embedding_plugins import (
                EmbeddingPluginManager,
                load_all_plugins
            )
            
            load_all_plugins()
            self._plugin_manager = EmbeddingPluginManager(embedding_service)
            self._plugin_manager.load_plugins()
            return self._plugin_manager
        except Exception as e:
            logger.debug(f"[InitStage] 无法加载 embedding 插件: {e}")
            return None
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        """清理各服务缓存"""
        engine.speciation.clear_tile_cache()
        engine.migration_advisor.clear_tile_mortality_cache()
        engine.tile_mortality.clear_accumulated_data()
        
        # 触发插件 on_turn_start
        if engine._use_embedding_integration:
            manager = self._get_plugin_manager(engine)
            if manager:
                try:
                    manager.on_turn_start(ctx)
                    logger.debug(f"[InitStage] 插件 on_turn_start 已触发")
                except Exception as e:
                    logger.warning(f"[InitStage] 插件 on_turn_start 失败: {e}")


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
                # 注意：turn_index 会在 FinalizeStage 中统一更新为下一个回合数
                # 这里暂时保存当前回合数，仅用于中间状态
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
            
            # 【新增】触发资源系统事件脉冲
            self._apply_resource_event_pulses(ctx, ctx.tectonic_result, map_tiles)
        
        except Exception as e:
            logger.warning(f"[板块系统] 运行失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _apply_resource_event_pulses(
        self,
        ctx: "SimulationContext",
        tectonic_result,
        map_tiles: list,
    ):
        """将板块/地质事件转换为资源脉冲"""
        try:
            # 使用 engine 注入的 resource_manager，避免全局单例
            resource_mgr = engine.resource_manager if engine else None
            if resource_mgr is None:
                logger.warning("[地质阶段] 资源管理器未注入，跳过资源脉冲")
                return
            
            # 初始化地块资源状态（如果尚未初始化）
            if map_tiles:
                resource_mgr.initialize_tiles(map_tiles)
            
            # 处理火山事件
            if hasattr(tectonic_result, 'volcanic_events'):
                for event in tectonic_result.volcanic_events:
                    affected_tiles = event.get('affected_tiles', [])
                    for tile_id in affected_tiles:
                        resource_mgr.apply_event_pulse(tile_id, "volcanic_ash", duration_turns=5)
                    
                    if affected_tiles:
                        ctx.emit_event(
                            "info",
                            f"🌋 火山灰影响 {len(affected_tiles)} 个地块的资源",
                            "生态"
                        )
            
            # 处理洪水事件（从 modifiers 检测）
            flood_intensity = ctx.modifiers.get("flood", 0)
            if flood_intensity > 0.3:
                # 影响低海拔地块
                for tile in map_tiles or []:
                    if hasattr(tile, 'elevation') and tile.elevation < 50:
                        resource_mgr.apply_event_pulse(tile.id, "flood", duration_turns=3)
            
            # 处理干旱事件
            drought_intensity = ctx.modifiers.get("drought", 0)
            if drought_intensity > 0.3:
                # 影响干旱敏感地块
                for tile in map_tiles or []:
                    if hasattr(tile, 'humidity') and tile.humidity < 0.3:
                        resource_mgr.apply_event_pulse(tile.id, "drought", duration_turns=4)
            
            # 更新资源动态（计算消耗）
            # 消耗数据将在后续阶段计算后更新
            
        except Exception as e:
            logger.warning(f"[资源事件脉冲] 处理失败: {e}")


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


class ResourceCalcStage(BaseStage):
    """资源计算阶段
    
    使用 ResourceManager 计算各地块的 NPP 和承载力，
    生成 resource_snapshot 供后续阶段（死亡率、繁殖、迁徙）使用。
    """
    
    def __init__(self):
        super().__init__(StageOrder.RESOURCE_CALC.value, "资源计算")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"获取物种列表"},  # 需要物种列表和地块信息
            requires_fields={"species_batch", "all_tiles", "turn_index"},
            writes_fields={"resource_snapshot"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        """执行资源计算
        
        1. 从引擎获取 ResourceManager（通过容器注入）
        2. 计算各地块的消耗量（基于物种分布）
        3. 更新资源动态
        4. 生成资源快照供后续阶段使用
        """
        logger.info("计算资源分布...")
        ctx.emit_event("stage", "🌿 计算资源分布", "生态")
        
        try:
            # 从引擎获取 ResourceManager（不再使用全局容器）
            resource_manager = engine.resource_manager
            if resource_manager is None:
                logger.warning("ResourceManager 不可用，跳过资源阶段")
                return
            
            # 【新增v12】注入生态拟真数据（用于动态同化效率）
            eco_realism_data = ctx.plugin_data.get("ecological_realism", {})
            if eco_realism_data:
                resource_manager._ecological_realism_data = eco_realism_data
                logger.debug("[资源计算] 已注入生态拟真数据（动态同化效率）")
            
            # 计算各地块的物种消耗
            consumption_by_tile = self._calculate_consumption(ctx)
            
            # 更新资源动态
            if ctx.all_tiles:
                resource_manager.update_resource_dynamics(
                    ctx.all_tiles,
                    consumption_by_tile,
                    ctx.turn_index,
                )
            
            # 生成并存储资源快照
            ctx.resource_snapshot = resource_manager.get_snapshot(ctx.turn_index)
            
            # 输出汇总信息
            if ctx.resource_snapshot:
                overgrazing = ctx.resource_snapshot.overgrazing_tiles
                total_npp = ctx.resource_snapshot.total_npp
                ctx.emit_event(
                    "info",
                    f"🌱 总NPP: {total_npp:.0f} kg | 过采地块: {overgrazing}",
                    "生态"
                )
                logger.info(
                    f"资源计算完成: total_npp={total_npp:.0f}, "
                    f"avg_npp={ctx.resource_snapshot.avg_npp:.2f}, "
                    f"overgrazing_tiles={overgrazing}"
                )
        except Exception as e:
            logger.warning(f"资源计算阶段出错: {e}")
            ctx.emit_event("warning", f"资源计算出错: {e}", "生态")
    
    def _calculate_consumption(self, ctx: SimulationContext) -> dict[int, float]:
        """计算各地块的资源消耗量
        
        基于物种分布和代谢需求估算消耗。
        """
        consumption: dict[int, float] = {}
        
        # 遍历存活物种
        for species in ctx.species_batch:
            if species.status != "alive":
                continue
            
            # 获取体重（用于代谢计算）
            body_weight = getattr(species, 'body_weight_kg', 1.0)
            if body_weight is None:
                body_weight = 1.0
            
            # 获取栖息地分布
            habitats = getattr(species, 'habitats', []) or []
            
            if not habitats:
                continue
            
            # 估算代谢需求（异速生长：需求 ∝ 体重^0.75）
            individual_demand = 0.01 * (body_weight ** 0.75)  # 简化的代谢模型
            
            # 按栖息地分配消耗
            population = species.population or 0
            tiles_count = len(habitats)
            pop_per_tile = population / tiles_count if tiles_count > 0 else 0
            
            for hab in habitats:
                tile_id = getattr(hab, 'tile_id', None)
                if tile_id is not None:
                    tile_consumption = individual_demand * pop_per_tile
                    consumption[tile_id] = consumption.get(tile_id, 0.0) + tile_consumption
        
        return consumption


class FoodWebStage(BaseStage):
    """食物网维护阶段
    
    【v2增强】
    1. 猎物多样性阈值检查和自动补充
    2. 新物种（T1/T2）自动集成
    3. 区域权重感知（饥饿区域、孤立区域）
    4. 生成 trophic_interactions 反馈信号
    """
    
    def __init__(self):
        super().__init__(StageOrder.FOOD_WEB.value, "食物网维护")
        self._previous_species_codes: set[str] | None = None
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        
        logger.info("维护食物网...")
        ctx.emit_event("stage", "🕸️ 维护食物网", "生态")
        
        try:
            # 构建地块-物种映射（用于区域权重）
            tile_species_map, species_tiles = self._build_tile_species_map(ctx.all_species)
            
            # 获取上回合的物种代码（用于检测新物种）
            current_codes = {s.lineage_code for s in ctx.all_species if s.status == "alive"}
            previous_codes = self._previous_species_codes
            self._previous_species_codes = current_codes.copy()
            
            # 执行食物网维护（v2增强版）
            ctx.food_web_analysis = engine.food_web_manager.maintain_food_web(
                ctx.all_species, species_repository, ctx.turn_index,
                tile_species_map=tile_species_map,
                species_tiles=species_tiles,
                previous_species_codes=previous_codes,
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
            
            # 【新增】生成 trophic_interactions 反馈信号
            trophic_signals = engine.food_web_manager.generate_trophic_signals(
                ctx.food_web_analysis, ctx.all_species
            )
            
            # 合并到 trophic_interactions（供后续阶段使用）
            if not hasattr(ctx, 'trophic_interactions') or ctx.trophic_interactions is None:
                ctx.trophic_interactions = {}
            ctx.trophic_interactions.update(trophic_signals)
            
            # 报告新生产者
            if ctx.food_web_analysis.new_producers:
                ctx.emit_event(
                    "info",
                    f"🌱 发现 {len(ctx.food_web_analysis.new_producers)} 个新 T1/T2 物种",
                    "生态"
                )
            
            # 报告猎物不足的物种
            if ctx.food_web_analysis.prey_shortage_species:
                ctx.emit_event(
                    "warning",
                    f"⚠️ {len(ctx.food_web_analysis.prey_shortage_species)} 个物种猎物多样性不足",
                    "生态"
                )
            
            if ctx.food_web_analysis.bottleneck_warnings:
                for warning in ctx.food_web_analysis.bottleneck_warnings[:3]:
                    ctx.emit_event("warning", warning, "生态")
            
            logger.info(
                f"[食物网] 健康度: {ctx.food_web_analysis.health_score:.0%}, "
                f"链接数: {ctx.food_web_analysis.total_links}, "
                f"孤立消费者: {len(ctx.food_web_analysis.orphaned_consumers)}, "
                f"trophic_signals: {len(trophic_signals)}"
            )
        except Exception as e:
            logger.warning(f"[食物网维护] 失败: {e}")
    
    def _build_tile_species_map(
        self, 
        all_species: list
    ) -> tuple[dict[int, set[str]], dict[str, set[int]]]:
        """构建地块-物种双向映射"""
        tile_species_map: dict[int, set[str]] = {}
        species_tiles: dict[str, set[int]] = {}
        
        for sp in all_species:
            if sp.status != "alive":
                continue
            tiles = set(sp.morphology_stats.get("tile_ids", []))
            if tiles:
                species_tiles[sp.lineage_code] = tiles
                for tid in tiles:
                    if tid not in tile_species_map:
                        tile_species_map[tid] = set()
                    tile_species_map[tid].add(sp.lineage_code)
        
        return tile_species_map, species_tiles


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
        
        # 【新增】注入生态拟真数据到 trophic_interactions
        # 这样死亡率计算可以访问语义驱动的生态学修正
        eco_realism_data = ctx.plugin_data.get("ecological_realism", {})
        if eco_realism_data:
            ctx.trophic_interactions["_ecological_realism_data"] = eco_realism_data
            logger.debug("[死亡率] 已注入生态拟真数据")
        
        logger.info("【阶段1】计算初步死亡率（迁徙前）...")
        
        if engine._use_tile_based_mortality and ctx.all_tiles:
            logger.info("[地块死亡率] 构建地块-物种矩阵...")
            ctx.emit_event("info", "🗺️ 使用按地块计算死亡率", "生态")
            
            # 【新增v12】注入生态拟真数据到死亡率引擎
            # 用于空间捕食效率、垂直生态位竞争等修正
            engine.tile_mortality._ecological_realism_data = eco_realism_data if eco_realism_data else None
            
            engine.tile_mortality.build_matrices(ctx.species_batch, ctx.all_tiles, ctx.all_habitats)
            
            preliminary_critical = engine.tile_mortality.evaluate(
                ctx.tiered.critical, ctx.modifiers, ctx.niche_metrics, tier="critical",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes,
                turn_index=ctx.turn_index
            )
            preliminary_focus = engine.tile_mortality.evaluate(
                ctx.tiered.focus, ctx.modifiers, ctx.niche_metrics, tier="focus",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes,
                turn_index=ctx.turn_index
            )
            preliminary_background = engine.tile_mortality.evaluate(
                ctx.tiered.background, ctx.modifiers, ctx.niche_metrics, tier="background",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes,
                turn_index=ctx.turn_index
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
    """迁徙执行阶段
    
    使用 ModifierApplicator 应用迁徙偏向修正：
    - migration_bias > 0: 增加迁徙倾向
    - migration_bias < 0: 减少迁徙倾向
    """
    
    def __init__(self):
        super().__init__(StageOrder.MIGRATION.value, "迁徙执行")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"初步死亡率评估"},
            optional_stages={"生态智能体评估"},  # 使用 ModifierApplicator
            requires_fields={"preliminary_mortality", "species_batch"},
            writes_fields={"migration_events", "migration_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("【阶段2】迁徙建议与执行...")
        ctx.emit_event("stage", "🦅 【阶段2】迁徙建议与执行", "生态")
        
        # 获取 ModifierApplicator（如果可用）
        modifier = getattr(ctx, 'modifier_applicator', None)
        use_modifier = modifier is not None and len(modifier._assessments) > 0
        
        if use_modifier:
            logger.debug("[迁徙] 使用 ModifierApplicator 应用迁徙偏向修正")
        
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
        
        # 【关键】应用迁徙偏向修正
        # 如果 ModifierApplicator 可用，调整每个物种的迁徙阈值
        migration_bias_overrides = {}
        if use_modifier:
            for sp in ctx.species_batch:
                code = sp.lineage_code
                # 基础迁徙概率阈值
                base_threshold = 0.3
                # 通过 ModifierApplicator 调整
                adjusted_threshold = modifier.apply(code, base_threshold, "migration")
                if abs(adjusted_threshold - base_threshold) > 0.01:
                    migration_bias_overrides[code] = adjusted_threshold
                    logger.debug(f"[迁徙偏向] {sp.common_name}: 阈值 {base_threshold:.2f} → {adjusted_threshold:.2f}")
        
        # 规划迁徙
        ctx.migration_events = engine.migration_advisor.plan(
            ctx.preliminary_mortality,
            ctx.modifiers, ctx.major_events, ctx.map_changes,
            current_turn=ctx.turn_index,
            cooldown_species=ctx.cooldown_species,
            migration_bias_overrides=migration_bias_overrides if migration_bias_overrides else None,
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
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes,
                turn_index=ctx.turn_index
            )
            ctx.focus_results = engine.tile_mortality.evaluate(
                ctx.tiered.focus, ctx.modifiers, ctx.niche_metrics, tier="focus",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes,
                turn_index=ctx.turn_index
            )
            ctx.background_results = engine.tile_mortality.evaluate(
                ctx.tiered.background, ctx.modifiers, ctx.niche_metrics, tier="background",
                trophic_interactions=ctx.trophic_interactions, extinct_codes=ctx.extinct_codes,
                turn_index=ctx.turn_index
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
    """种群更新阶段
    
    使用 ModifierApplicator 统一应用 AI 修正：
    - mortality: 死亡率修正
    - reproduction_r: 繁殖率修正 (r)
    - carrying_capacity: 承载力修正 (K)
    """
    
    def __init__(self):
        super().__init__(StageOrder.POPULATION_UPDATE.value, "种群更新")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"最终死亡率评估"},
            optional_stages={"生态智能体评估"},  # 使用 ModifierApplicator
            requires_fields={"combined_results", "species_batch"},
            writes_fields={"new_populations", "reproduction_results"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.species_repository import species_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("计算种群变化（死亡+繁殖并行）...")
        ctx.emit_event("stage", "💀🐣 计算种群变化", "物种")
        
        # 获取 ModifierApplicator（如果可用）
        modifier = getattr(ctx, 'modifier_applicator', None)
        use_modifier = modifier is not None and len(modifier._assessments) > 0
        
        if use_modifier:
            logger.info("[种群更新] 使用 ModifierApplicator 应用 AI 修正 (mortality/r/K)")
            stats = modifier.get_stats()
            logger.debug(f"[种群更新] ModifierApplicator 统计: {stats}")
        
        # 更新环境动态修正系数
        temp_change = ctx.modifiers.get("temperature", 0.0) if ctx.modifiers else 0.0
        sea_level_change = 0.0
        if ctx.current_map_state:
            prev_sea = getattr(ctx.current_map_state, '_prev_sea_level', ctx.current_map_state.sea_level)
            sea_level_change = ctx.current_map_state.sea_level - prev_sea
            ctx.current_map_state._prev_sea_level = ctx.current_map_state.sea_level
        engine.reproduction_service.update_environmental_modifier(temp_change, sea_level_change)
        
        # 【v8新增】更新资源繁荣加成（正面压力提高繁殖率）
        if ctx.modifiers:
            engine.reproduction_service.update_resource_boost(ctx.modifiers)
        
        # 【新增v12】注入生态拟真数据到繁殖服务
        # 用于应用 Allee 效应、环境波动、共生等语义驱动的繁殖率修正
        eco_realism_data = ctx.plugin_data.get("ecological_realism", {})
        if eco_realism_data:
            engine.reproduction_service._ecological_realism_data = eco_realism_data
            logger.debug("[种群更新] 已注入生态拟真数据到繁殖服务")
        else:
            engine.reproduction_service._ecological_realism_data = None
        
        # 【修复】先计算所有物种的调整后死亡率，用于构建真实存活率
        # 这样繁殖模块才能正确反应压力造成的高死亡率
        adjusted_death_rates = {}
        for item in ctx.combined_results:
            code = item.species.lineage_code
            base_death_rate = item.death_rate
            
            # 通过 ModifierApplicator 应用 AI 死亡率修正
            if use_modifier:
                adjusted = modifier.apply(code, base_death_rate, "mortality")
            else:
                adjusted = base_death_rate
            
            # 确保死亡率在有效范围内
            adjusted_death_rates[code] = max(0.0, min(1.0, adjusted))
        
        # 【关键修复】使用真实存活率（1 - adjusted_death_rate）
        # 原来硬编码为 1.0，导致繁殖模块忽略了压力/LLM/规则系统计算的死亡率
        survival_rates = {
            code: max(0.01, 1.0 - death_rate)  # 保证最低 1% 存活率避免除零
            for code, death_rate in adjusted_death_rates.items()
        }
        
        # 记录高死亡率物种的存活率（便于调试）
        high_mortality_species = [(code, sr) for code, sr in survival_rates.items() if sr < 0.5]
        if high_mortality_species:
            logger.info(f"[种群更新] 高死亡率物种存活率: {high_mortality_species[:5]}...")
        
        niche_data = {
            code: (metrics.overlap, metrics.saturation)
            for code, metrics in ctx.niche_metrics.items()
        }
        
        # 临时设置种群为初始值
        for item in ctx.combined_results:
            item.species.morphology_stats["population"] = item.initial_population
        
        ctx.reproduction_results = engine.reproduction_service.apply_reproduction(
            ctx.species_batch, niche_data, survival_rates,
            habitat_manager=habitat_manager,
            turn_index=ctx.turn_index
        )
        
        # 计算最终种群
        for item in ctx.combined_results:
            code = item.species.lineage_code
            initial = item.initial_population
            
            # 【复用】使用之前计算的调整后死亡率（保持一致性）
            death_rate = adjusted_death_rates.get(code, item.death_rate)
            
            repro_pop = ctx.reproduction_results.get(code, initial)
            repro_gain = max(0, repro_pop - initial)
            
            # 【关键】通过 ModifierApplicator 应用繁殖率 r 修正
            if use_modifier:
                r_factor = modifier.apply(code, 1.0, "reproduction_r")
                repro_gain = int(repro_gain * r_factor)
            
            survivors = int(initial * (1.0 - death_rate))
            survivor_ratio = survivors / initial if initial > 0 else 0
            
            offspring_survival = 0.8 + 0.2 * (1.0 - death_rate)
            effective_gain = int(repro_gain * survivor_ratio * offspring_survival)
            
            # 【关键】通过 ModifierApplicator 应用承载力 K 修正
            # 承载力限制最终种群上限
            # 【修复】动态计算承载力，不再使用硬编码默认值
            from ..services.species.population_calculator import PopulationCalculator
            stored_k = item.species.morphology_stats.get("carrying_capacity")
            if stored_k and stored_k > 0:
                base_carrying_capacity = stored_k
            else:
                # 基于体型动态计算承载力
                body_length = item.species.morphology_stats.get("body_length_cm", 1.0)
                body_weight = item.species.morphology_stats.get("body_weight_g")
                _, base_carrying_capacity = PopulationCalculator.calculate_reasonable_population(
                    body_length, body_weight
                )
            if use_modifier:
                adjusted_k = modifier.apply(code, base_carrying_capacity, "carrying_capacity")
            else:
                adjusted_k = base_carrying_capacity
            
            final_pop = survivors + effective_gain
            
            # 应用 K 限制：如果超过承载力，多余个体死亡
            if final_pop > adjusted_k:
                excess = final_pop - adjusted_k
                final_pop = int(adjusted_k)
                if excess > 100:
                    logger.debug(f"[承载力限制] {item.species.common_name}: 超出 K={adjusted_k:,.0f}，减少 {excess:,}")
            
            ctx.new_populations[code] = max(0, final_pop)
            
            item.births = effective_gain
            item.final_population = final_pop
            item.survivors = survivors
            # 记录 AI 修正后的实际死亡率
            item.adjusted_death_rate = death_rate
            item.adjusted_k = adjusted_k
            
            if abs(final_pop - initial) > initial * 0.3:
                mod_info = ""
                if use_modifier:
                    parts = []
                    if abs(base_death_rate - death_rate) > 0.01:
                        parts.append(f"mort:{base_death_rate:.0%}→{death_rate:.0%}")
                    if abs(adjusted_k - base_carrying_capacity) > 100:
                        parts.append(f"K:{base_carrying_capacity:,.0f}→{adjusted_k:,.0f}")
                    if parts:
                        mod_info = f" [AI: {', '.join(parts)}]"
                logger.debug(
                    f"[种群变化] {item.species.common_name}: "
                    f"{initial:,} → {final_pop:,} "
                    f"(死亡{death_rate:.1%}, 存活{survivors:,}, 繁殖+{effective_gain:,}){mod_info}"
                )
        
        # 应用最终种群
        for species in ctx.species_batch:
            if species.lineage_code in ctx.new_populations:
                species.morphology_stats["population"] = ctx.new_populations[species.lineage_code]
                species_repository.upsert(species)
        
        # 更新灭绝状态（使用 ExtinctionChecker，传入配置）
        spec_config = getattr(engine.speciation, '_config', None)
        extinction_checker = ExtinctionChecker(
            species_repository=species_repository,
            turn_counter=ctx.turn_index,
            event_callback=ctx.emit_event,
            config=spec_config,  # 传入配置以使用灭绝阈值
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
        
        # 【新增】更新资源系统动态
        self._update_resource_dynamics(ctx, engine)
    
    def _update_resource_dynamics(self, ctx: "SimulationContext", engine: "SimulationEngine"):
        """更新资源系统动态（计算消耗并触发再生）"""
        try:
            from ..repositories.environment_repository import environment_repository
            
            # 使用 engine 注入的 resource_manager，避免全局单例
            resource_mgr = engine.resource_manager if engine else None
            if resource_mgr is None:
                logger.warning("[资源动态] 资源管理器未注入，跳过资源更新")
                return
            
            # 获取所有地块
            all_tiles = environment_repository.list_tiles()
            if not all_tiles:
                return
            
            # 计算各地块的资源消耗
            consumption_by_tile: dict[int, float] = {}
            
            for result in ctx.combined_results:
                sp = result.species
                if sp.trophic_level >= 2.0:
                    continue  # 只计算生产者的消耗（由消费者施加）
                
                # 获取物种分布
                habitats = getattr(sp, 'habitats', [])
                body_weight_kg = sp.morphology_stats.get("body_weight_g", 1.0) / 1000.0
                
                for hab in habitats:
                    tile_id = getattr(hab, 'tile_id', 0)
                    pop = getattr(hab, 'population', 0)
                    
                    if tile_id > 0 and pop > 0:
                        # 简单估算消耗（生产者的生物量 = 消费者的食物）
                        consumption = pop * body_weight_kg * 0.1  # 每回合消耗 10%
                        consumption_by_tile[tile_id] = consumption_by_tile.get(tile_id, 0) + consumption
            
            # 添加消费者的猎物消耗
            for result in ctx.combined_results:
                sp = result.species
                if sp.trophic_level < 2.0:
                    continue
                
                habitats = getattr(sp, 'habitats', [])
                body_weight_kg = sp.morphology_stats.get("body_weight_g", 1.0) / 1000.0
                metabolic_rate = sp.morphology_stats.get("metabolic_rate", 3.0)
                
                for hab in habitats:
                    tile_id = getattr(hab, 'tile_id', 0)
                    pop = getattr(hab, 'population', 0)
                    
                    if tile_id > 0 and pop > 0:
                        # 消费者的能量需求
                        consumption = pop * body_weight_kg * (metabolic_rate / 10.0)
                        consumption_by_tile[tile_id] = consumption_by_tile.get(tile_id, 0) + consumption
            
            # 更新资源动态
            resource_mgr.update_resource_dynamics(all_tiles, consumption_by_tile, ctx.turn_index)
            
            # 记录统计
            stats = resource_mgr.get_stats()
            if stats.get("overgrazing_tiles", 0) > 0:
                logger.info(
                    f"[资源动态] 过采地块: {stats['overgrazing_tiles']}, "
                    f"平均NPP: {stats['avg_npp']:.0f} kg"
                )
        
        except Exception as e:
            logger.warning(f"[资源动态] 更新失败: {e}")


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
            # 【关键修复】使用 TileBasedMortalityEngine 获取完整的地块级分化候选数据
            # 原代码只传递了 death_rate 和 population，但 speciation.py 期望完整的地块级数据
            if engine._use_tile_based_mortality and hasattr(engine, 'tile_mortality'):
                # 调用正确的方法获取完整的候选数据（包含 candidate_tiles, tile_populations, 
                # tile_mortality, is_isolated, clusters, mortality_gradient 等字段）
                candidates = engine.tile_mortality.get_speciation_candidates()
                logger.info(f"[分化数据传递] 从 TileBasedMortalityEngine 获取 {len(candidates)} 个候选物种")
            else:
                # 回退到简单数据（兼容旧逻辑，但分化效果会大打折扣）
                candidates = {}
                for result in ctx.combined_results:
                    candidates[result.species.lineage_code] = {
                        "death_rate": result.death_rate,
                        "population": result.species.morphology_stats.get("population", 0),
                    }
                logger.warning("[分化数据传递] 未使用地块级死亡率引擎，分化数据不完整")
            
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
    """自动杂交阶段
    
    【实现】检测同域、近缘物种，触发自动杂交。
    
    杂交条件：
    - 两个物种分布在相同地块（同域）
    - 遗传距离在杂交阈值内（近缘）
    - 种群规模足够大
    - 随机概率检查（基础概率）
    - 杂交成功率骰点（通过基础检查后还需骰点成功）
    """
    
    # 【参数配置】从 settings 读取，此处仅定义备用默认值
    MIN_POPULATION_FOR_HYBRIDIZATION = 500  # 最小种群才能参与杂交
    SYMPATRIC_BONUS = 0.08  # 完全同域时的概率加成
    
    def __init__(self):
        super().__init__(StageOrder.AUTO_HYBRIDIZATION.value, "自动杂交")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"遗传漂变"},
            requires_fields={"species_batch", "all_habitats"},
            writes_fields={"auto_hybrids"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        import random
        from ..repositories.species_repository import species_repository
        from ..services.species.hybridization import HybridizationService
        from ..services.species.genetic_distance import GeneticDistanceCalculator
        
        logger.info("自动杂交检查...")
        ctx.emit_event("stage", "🧬 自动杂交检查", "进化")
        
        ctx.auto_hybrids = []
        
        # 从 SpeciationConfig 读取杂交参数（与分化配置统一管理）
        spec_config = engine.speciation._config
        base_chance = spec_config.auto_hybridization_chance  # 基础杂交概率
        success_rate = spec_config.hybridization_success_rate  # 杂交成功率
        max_hybrids = spec_config.max_hybrids_per_turn  # 每回合最多杂交数
        min_pop_for_hybrid = spec_config.min_population_for_hybridization  # 杂交所需最小种群
        
        # 获取所有存活物种
        alive_species = [sp for sp in ctx.species_batch if sp.status == "alive"]
        if len(alive_species) < 2:
            logger.debug("[自动杂交] 物种数量不足，跳过")
            return
        
        # 筛选种群足够大的物种（使用配置中的门槛）
        candidate_species = [
            sp for sp in alive_species
            if (sp.morphology_stats.get("population", 0) or 0) >= min_pop_for_hybrid
        ]
        
        if len(candidate_species) < 2:
            logger.debug("[自动杂交] 候选物种不足，跳过")
            return
        
        # 初始化杂交服务
        genetic_calculator = GeneticDistanceCalculator()
        hybridization_service = HybridizationService(genetic_calculator, engine.router)
        
        # 构建 species_id -> lineage_code 映射
        id_to_code: dict[int, str] = {}
        for sp in ctx.species_batch:
            if sp.id is not None:
                id_to_code[sp.id] = sp.lineage_code
        
        # 构建物种的栖息地映射 {lineage_code: set(tile_ids)}
        species_tiles: dict[str, set[int]] = {}
        if ctx.all_habitats:
            for hab in ctx.all_habitats:
                # HabitatPopulation 只有 species_id，需要通过映射获取 lineage_code
                code = id_to_code.get(hab.species_id)
                if not code:
                    continue
                if code not in species_tiles:
                    species_tiles[code] = set()
                species_tiles[code].add(hab.tile_id)
        
        existing_codes = {sp.lineage_code for sp in ctx.species_batch}
        hybrids_created = 0
        checked_pairs = set()
        
        # 遍历所有物种对
        for i, sp1 in enumerate(candidate_species):
            if hybrids_created >= max_hybrids:
                break
                
            for sp2 in candidate_species[i+1:]:
                if hybrids_created >= max_hybrids:
                    break
                
                # 避免重复检查
                pair_key = tuple(sorted([sp1.lineage_code, sp2.lineage_code]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                # 检查是否同域（至少有一个共同地块）
                tiles1 = species_tiles.get(sp1.lineage_code, set())
                tiles2 = species_tiles.get(sp2.lineage_code, set())
                shared_tiles = tiles1 & tiles2
                
                if not shared_tiles:
                    continue  # 无共同分布区域，跳过
                
                # 计算遗传距离，判断是否可杂交
                can_hybrid, fertility = hybridization_service.can_hybridize(sp1, sp2)
                if not can_hybrid:
                    continue
                
                # 【步骤1】计算杂交检测概率
                # 基础概率 + 同域程度加成 + 可育性加成
                sympatry_ratio = len(shared_tiles) / max(1, min(len(tiles1), len(tiles2)))
                hybrid_chance = (
                    base_chance 
                    + self.SYMPATRIC_BONUS * sympatry_ratio
                    + 0.03 * fertility  # 可育性越高，概率越高
                )
                
                # 检测概率骰点
                if random.random() > hybrid_chance:
                    continue
                
                # 【步骤2】杂交成功率骰点（类似分化的成功率机制）
                if random.random() > success_rate:
                    logger.debug(
                        f"[自动杂交] 骰点失败: {sp1.common_name} × {sp2.common_name} "
                        f"(成功率={success_rate:.0%})"
                    )
                    continue
                
                # 创建杂交种
                logger.info(
                    f"[自动杂交] 尝试杂交: {sp1.common_name} × {sp2.common_name} "
                    f"(可育性={fertility:.1%}, 共享地块={len(shared_tiles)})"
                )
                
                hybrid = hybridization_service.create_hybrid(
                    sp1, sp2, ctx.turn_index, 
                    existing_codes=existing_codes
                )
                
                if hybrid:
                    # 设置初始种群（从两个亲本中分出一部分）
                    pop1 = sp1.morphology_stats.get("population", 0) or 0
                    pop2 = sp2.morphology_stats.get("population", 0) or 0
                    
                    # 杂交种初始种群 = 两亲本各贡献 10% × 可育性
                    # 亲本各损失 10% × 可育性（零和游戏，不再凭空创造种群）
                    contribution_rate = 0.10  # 每个亲本贡献10%
                    
                    pop1_contribution = int(pop1 * contribution_rate * fertility)
                    pop2_contribution = int(pop2 * contribution_rate * fertility)
                    hybrid_pop = pop1_contribution + pop2_contribution
                    
                    # 【修复】使用配置中的最小种群门槛，避免产生微型物种
                    min_hybrid_pop = spec_config.min_offspring_population
                    if hybrid_pop < min_hybrid_pop:
                        # 种群不足，放弃杂交
                        logger.debug(
                            f"[自动杂交] 种群不足放弃: {sp1.common_name} × {sp2.common_name} "
                            f"(计算种群={hybrid_pop:,} < 门槛={min_hybrid_pop:,})"
                        )
                        continue
                    
                    hybrid.morphology_stats["population"] = hybrid_pop
                    
                    # 从亲本中减少种群（与贡献相等，零和）
                    sp1.morphology_stats["population"] = max(100, pop1 - pop1_contribution)
                    sp2.morphology_stats["population"] = max(100, pop2 - pop2_contribution)
                    
                    # 保存杂交种
                    species_repository.upsert(hybrid)
                    species_repository.upsert(sp1)
                    species_repository.upsert(sp2)
                    
                    ctx.auto_hybrids.append(hybrid)
                    existing_codes.add(hybrid.lineage_code)
                    hybrids_created += 1
                    
                    logger.info(
                        f"[自动杂交] 成功: {hybrid.common_name} "
                        f"(种群={hybrid_pop:,}, 可育性={fertility:.1%})"
                    )
                    ctx.emit_event(
                        "speciation", 
                        f"🧬 杂交诞生: {hybrid.common_name}", 
                        "进化"
                    )
        
        if ctx.auto_hybrids:
            logger.info(f"[自动杂交] 本回合产生了 {len(ctx.auto_hybrids)} 个杂交种")
            # 将杂交种加入物种列表
            ctx.species_batch.extend(ctx.auto_hybrids)
            
            # 【描述增强】为杂交种进行LLM描述增强
            try:
                from ..services.species.description_enhancer import DescriptionEnhancerService
                
                enhancer = DescriptionEnhancerService(engine.router)
                
                for hybrid in ctx.auto_hybrids:
                    # 获取杂交亲本信息
                    hybrid_parents = getattr(hybrid, 'hybrid_parent_codes', [])
                    parent1 = None
                    parent2 = None
                    if hybrid_parents and len(hybrid_parents) >= 2:
                        for sp in ctx.species_batch:
                            if sp.lineage_code == hybrid_parents[0]:
                                parent1 = sp
                            elif sp.lineage_code == hybrid_parents[1]:
                                parent2 = sp
                    
                    enhancer.queue_for_enhancement(
                        species=hybrid,
                        parent=parent1,
                        parent2=parent2,
                        is_hybrid=True,
                        fertility=getattr(hybrid, 'hybrid_fertility', 1.0),
                    )
                
                # 批量处理增强
                enhanced_list = await enhancer.process_queue_async(
                    max_items=10,  # 每回合最多处理10个杂交种描述
                    timeout_per_item=25.0,
                )
                
                if enhanced_list:
                    for enhanced_sp in enhanced_list:
                        species_repository.upsert(enhanced_sp)
                    logger.info(f"[杂交描述增强] 完成 {len(enhanced_list)}/{len(ctx.auto_hybrids)} 个杂交种描述增强")
            except Exception as e:
                logger.warning(f"[杂交描述增强] 处理失败（不影响杂交结果）: {e}")


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
            
            # 【新增】设置事件回调，确保并行任务能发送心跳
            engine.ai_pressure_service.set_event_callback(ctx.emit_event)
            
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
                    mortality_results=ctx.combined_results,
                    event_callback=ctx.emit_event,  # 【新增】传递事件回调
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
    
    使用 ModifierApplicator 应用分化信号修正：
    - speciation_signal > 0.7: 高概率触发分化
    - speciation_signal < 0.3: 低概率分化
    """
    
    def __init__(self):
        super().__init__(StageOrder.AI_PARALLEL_TASKS.value + 2, "物种分化", is_async=True)
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"种群更新"},  # 【修复】改为依赖种群更新，而非适应性演化（后者可能被禁用）
            optional_stages={"生态智能体评估", "适应性演化"},  # 适应性演化改为可选
            requires_fields={"species_batch", "combined_results", "critical_results", "focus_results", "modifiers"},
            writes_fields={"branching_events"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        logger.info("开始物种分化...")
        ctx.emit_event("stage", "🌱 物种分化", "分化")
        
        # 获取 ModifierApplicator（如果可用）
        modifier = getattr(ctx, 'modifier_applicator', None)
        use_modifier = modifier is not None and len(modifier._assessments) > 0
        
        try:
            # 【关键】通过 ModifierApplicator 识别高分化信号物种
            speciation_candidates = set()
            evolution_directions = {}
            
            if use_modifier:
                for result in ctx.critical_results + ctx.focus_results:
                    code = result.species.lineage_code
                    # 检查分化信号（阈值从0.6降到0.5，更容易触发分化）
                    if modifier.should_speciate(code, threshold=0.5):
                        speciation_candidates.add(code)
                        # 获取演化方向
                        directions = modifier.get_evolution_direction(code)
                        if directions:
                            evolution_directions[code] = directions
                        logger.info(
                            f"[分化候选] {result.species.common_name}: "
                            f"信号={modifier.get_speciation_signal(code):.2f}, "
                            f"方向={directions[:2] if directions else '无'}"
                        )
                
                if speciation_candidates:
                    logger.info(f"[分化] AI 识别 {len(speciation_candidates)} 个高分化信号物种")
                    ctx.emit_event(
                        "info",
                        f"🧬 AI 识别 {len(speciation_candidates)} 个分化候选",
                        "分化"
                    )
            
            # Embedding 集成：获取演化提示
            if engine._use_embedding_integration and hasattr(engine, 'embedding_integration'):
                try:
                    evolution_hints = {}
                    pressure_vectors = engine.embedding_integration.map_pressures_to_vectors(ctx.modifiers)
                    
                    for result in ctx.critical_results + ctx.focus_results:
                        sp = result.species
                        pop = sp.morphology_stats.get("population", 0)
                        # 对高分化信号物种降低种群要求
                        min_pop = 3000 if sp.lineage_code in speciation_candidates else 5000
                        if pop > min_pop and 0.05 < result.death_rate < 0.5:
                            hint = engine.embedding_integration.get_evolution_hints(sp, pressure_vectors)
                            if hint:
                                evolution_hints[sp.lineage_code] = hint
                    
                    # 合并 AI 演化方向
                    for code, directions in evolution_directions.items():
                        if code not in evolution_hints:
                            evolution_hints[code] = {}
                        evolution_hints[code]["ai_directions"] = directions
                    
                    if evolution_hints:
                        engine.speciation.set_evolution_hints(evolution_hints)
                        logger.info(f"[Embedding] 为 {len(evolution_hints)} 个物种提供演化提示")
                except Exception as e:
                    logger.warning(f"[Embedding] 获取演化提示失败: {e}")
            
            # 【关键修复】执行分化时使用 combined_results 而不是只用 critical + focus
            # 原代码只处理 critical_results + focus_results，导致大量 background 物种无法分化
            # 物种分化不需要 AI 做筛选决策，只需要 AI 生成新物种描述，所以处理全部物种是安全的
            
            # 【心跳回调】将 ctx.emit_event 包装为 stream_callback，用于 AI 调用心跳
            # 【修复】接收 event_type 和 category，正确传递事件类型
            def speciation_stream_callback(event_type: str, message: str, category: str = "AI"):
                ctx.emit_event(event_type, message, category)
            
            ctx.branching_events = await asyncio.wait_for(
                engine.speciation.process_async(
                    mortality_results=ctx.combined_results,  # 【修复】使用所有物种
                    existing_codes={s.lineage_code for s in ctx.species_batch},
                    average_pressure=sum(ctx.modifiers.values()) / (len(ctx.modifiers) or 1),
                    turn_index=ctx.turn_index,
                    map_changes=ctx.map_changes,
                    major_events=ctx.major_events,
                    pressures=ctx.pressures,
                    trophic_interactions=ctx.trophic_interactions,
                    stream_callback=speciation_stream_callback,  # 【新增】传递心跳回调
                    speciation_candidates=speciation_candidates if speciation_candidates else None,
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
                
                # 【新增】分化后触发局部食物网更新
                # 将新生产者/初级消费者立即集成到食物网，不等下一回合全量扫描
                if new_species:
                    self._integrate_new_species_to_food_web(
                        new_species, ctx, engine, species_repository
                    )
        
        except asyncio.TimeoutError:
            logger.warning("[物种分化] 超时")
            ctx.branching_events = []
        except Exception as e:
            logger.error(f"[物种分化] 失败: {e}")
            ctx.branching_events = []
    
    def _integrate_new_species_to_food_web(
        self,
        new_species: list,
        ctx: "SimulationContext",
        engine: "SimulationEngine",
        species_repository,
    ) -> None:
        """将新物种立即集成到食物网
        
        【触发条件】
        - 新物种是 T1/T2（生产者或初级消费者）
        - 或新物种是消费者但没有分配猎物
        """
        from ..services.species.food_web_manager import FoodWebChange
        
        try:
            all_species = species_repository.list_species()
            alive_species = [s for s in all_species if s.status == "alive"]
            
            # 构建地块-物种映射
            species_tiles = {}
            tile_species_map = {}
            for sp in alive_species:
                tiles = set(sp.morphology_stats.get("tile_ids", []))
                if tiles:
                    species_tiles[sp.lineage_code] = tiles
                    for tid in tiles:
                        if tid not in tile_species_map:
                            tile_species_map[tid] = set()
                        tile_species_map[tid].add(sp.lineage_code)
            
            changes = []
            
            for sp in new_species:
                # 为新消费者分配猎物
                if sp.trophic_level >= 2.0 and not sp.prey_species:
                    prey_changes = engine.food_web_manager.integrate_new_species(
                        sp, alive_species, species_repository
                    )
                    changes.extend(prey_changes)
                
                # 将新 T1/T2 物种添加到现有消费者的猎物列表
                if sp.trophic_level < 3.0:
                    # 找到猎物不足的消费者
                    for consumer in alive_species:
                        if consumer.lineage_code == sp.lineage_code:
                            continue
                        if consumer.trophic_level < 2.0:
                            continue
                        
                        # 检查营养级匹配
                        trophic_diff = consumer.trophic_level - sp.trophic_level
                        if not (0.5 <= trophic_diff <= 1.5):
                            continue
                        
                        current_prey = consumer.prey_species or []
                        alive_codes = {s.lineage_code for s in alive_species}
                        valid_prey = [c for c in current_prey if c in alive_codes]
                        
                        # 只对猎物不足的消费者添加
                        if len(valid_prey) <= 3 and sp.lineage_code not in current_prey:
                            # 检查栖息地/瓦片重叠
                            consumer_tiles = species_tiles.get(consumer.lineage_code, set())
                            sp_tiles = species_tiles.get(sp.lineage_code, set())
                            
                            if consumer_tiles and sp_tiles and not (consumer_tiles & sp_tiles):
                                continue  # 无重叠，跳过
                            
                            # 添加为新猎物
                            new_prey_list = valid_prey + [sp.lineage_code]
                            consumer.prey_species = new_prey_list
                            species_repository.upsert(consumer)
                            
                            changes.append(FoodWebChange(
                                species_code=consumer.lineage_code,
                                species_name=consumer.common_name,
                                change_type="prey_added",
                                details=f"分化后添加新猎物 {sp.common_name}",
                                old_prey=current_prey,
                                new_prey=new_prey_list,
                            ))
            
            if changes:
                logger.info(f"[分化-食物网] 更新了 {len(changes)} 条食物关系")
                ctx.emit_event("info", f"🕸️ 分化后更新 {len(changes)} 条食物链", "生态")
        
        except Exception as e:
            logger.warning(f"[分化-食物网] 集成失败: {e}")


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
            
            # 合并 species_batch（存活）和已灭绝物种，构成完整的物种列表
            # ctx.species_batch 在 SpeciationStage 后已包含新分化的物种
            all_species_for_report = list(ctx.species_batch) if ctx.species_batch else []
            # 添加灭绝物种（从 all_species 中筛选）
            if ctx.all_species:
                extinct_species = [sp for sp in ctx.all_species if sp.status == "extinct"]
                all_species_for_report.extend(extinct_species)
            
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
                    all_species=all_species_for_report,
                    ecological_realism_data=ctx.plugin_data.get("ecological_realism"),  # 【新增】
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


class EmbeddingPluginsStage(BaseStage):
    """Embedding 扩展插件阶段
    
    加载并执行所有启用的 Embedding 扩展插件：
    - behavior_strategy: 行为策略向量
    - food_web: 生态网络向量
    - tile_biome: 区域地块向量
    - prompt_optimizer: Prompt 优化
    - evolution_space: 演化空间
    - ancestry: 血统压缩
    
    每个插件在回合结束时更新其向量索引。
    配置从 stage_config.yaml 加载。
    """
    
    def __init__(self):
        super().__init__(StageOrder.EMBEDDING_PLUGINS.value, "Embedding扩展插件")
        self._manager = None
        self._initialized = False
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"Embedding集成"},  # 在 Embedding 集成之后
            optional_stages=set(),
            requires_fields={"all_species"},  # 所有插件都需要物种列表
            writes_fields=set(),  # 插件数据存储在各自的索引中
        )
    
    def _ensure_manager(self, engine: 'SimulationEngine') -> bool:
        """确保插件管理器已初始化"""
        if self._initialized:
            return self._manager is not None
        
        self._initialized = True
        
        # 检查是否有 embedding_service
        embedding_service = getattr(engine, 'embedding_service', None)
        if not embedding_service:
            logger.debug("[EmbeddingPlugins] EmbeddingService 不可用，跳过")
            return False
        
        try:
            from ..services.embedding_plugins import (
                EmbeddingPluginManager,
                load_all_plugins
            )
            from pathlib import Path
            
            # 加载所有内置插件
            loaded = load_all_plugins()
            if loaded:
                logger.info(f"[EmbeddingPlugins] 已注册插件: {loaded}")
            
            # 获取当前模式（优先使用 _pipeline_mode）
            mode = getattr(engine, '_pipeline_mode', None) or \
                   getattr(engine, '_stage_mode', None) or 'full'
            
            # 获取配置文件路径
            config_path = Path(__file__).parent / "stage_config.yaml"
            
            # 创建管理器并加载启用的插件
            self._manager = EmbeddingPluginManager(
                embedding_service, 
                mode=mode,
                config_path=config_path
            )
            count = self._manager.load_plugins()
            
            if count > 0:
                logger.info(f"[EmbeddingPlugins] 已加载 {count} 个插件 (模式: {mode})")
                return True
            else:
                logger.debug(f"[EmbeddingPlugins] 模式 {mode} 没有启用的插件")
                return False
                
        except Exception as e:
            logger.warning(f"[EmbeddingPlugins] 初始化失败: {e}")
            return False
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not self._ensure_manager(engine):
            return
        
        logger.debug("[EmbeddingPlugins] 执行插件回合结束钩子...")
        ctx.emit_event("stage", "🔌 Embedding 扩展插件", "AI")
        
        try:
            # 调用所有插件的 on_turn_end
            self._manager.on_turn_end(ctx)
            
            # 获取统计信息
            stats = self._manager.get_all_stats()
            plugin_count = stats.get("manager", {}).get("plugin_count", 0)
            
            if plugin_count > 0:
                logger.info(f"[EmbeddingPlugins] {plugin_count} 个插件已更新")
                
        except Exception as e:
            logger.warning(f"[EmbeddingPlugins] 执行失败: {e}")


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
        
        # 更新 MapState.turn_index - 保存下一个回合的索引，这样引擎恢复时可以直接使用
        # 【关键修复】保存 ctx.turn_index + 1，避免 hot reload 后回合数重复
        map_state = environment_repository.get_state()
        if map_state:
            map_state.turn_index = ctx.turn_index + 1  # 保存下一个回合数
            environment_repository.save_state(map_state)
            logger.debug(f"[FinalizeStage] 已保存下一回合索引: {map_state.turn_index}")
        
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
        ResourceCalcStage(),  # 资源计算（NPP/承载力）
        FoodWebStage(),
        TieringAndNicheStage(),
        PreliminaryMortalityStage(),
        MigrationStage(),
        FinalMortalityStage(),
        PopulationUpdateStage(),
        AIStatusEvalStage(),
        SpeciationDataTransferStage(),  # 【关键修复】分化数据传递阶段
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

