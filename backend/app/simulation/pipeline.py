"""
Pipeline Executor - 流水线执行器

该模块实现了按顺序执行 Stage 的流水线组件。
支持同步和异步阶段的混合执行，以及统一的错误处理。
包含健康监控与时间统计功能。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from .context import SimulationContext
    from .engine import SimulationEngine
    from .stages import Stage, StageResult

logger = logging.getLogger(__name__)


# ============================================================================
# Context 差异辅助函数
# ============================================================================

# 关键字段列表（用于差异追踪）
KEY_CONTEXT_FIELDS = [
    "pressures", "modifiers", "major_events",
    "current_map_state", "map_changes", "temp_delta", "sea_delta",
    "tectonic_result", "all_species", "species_batch", "extinct_codes",
    "all_habitats", "all_tiles", "food_web_analysis", "tiered",
    "niche_metrics", "trophic_interactions", "preliminary_mortality",
    "migration_events", "migration_count", "symbiotic_follow_count",
    "dispersal_results", "hunger_migrations_count",
    "critical_results", "focus_results", "background_results", "combined_results",
    "ai_status_evals", "emergency_responses", "new_populations",
    "reproduction_results", "activation_events", "gene_flow_count",
    "genetic_drift_count", "auto_hybrids", "promotion_count",
    "adaptation_events", "branching_events", "narrative_results",
    "background_summary", "mass_extinction", "reemergence_events",
    "report", "species_snapshots", "ecosystem_metrics",
]


def capture_context_state(ctx: "SimulationContext") -> dict[str, Any]:
    """捕获 Context 关键字段的状态摘要"""
    state = {}
    for field_name in KEY_CONTEXT_FIELDS:
        value = getattr(ctx, field_name, None)
        if value is None:
            state[field_name] = None
        elif isinstance(value, (list, set)):
            state[field_name] = len(value)
        elif isinstance(value, dict):
            state[field_name] = len(value)
        elif isinstance(value, (int, float, str, bool)):
            state[field_name] = value
        else:
            # 对象类型，只记录是否存在
            state[field_name] = "exists"
    return state


def compute_context_diff(
    before: dict[str, Any],
    after: dict[str, Any]
) -> dict[str, str]:
    """计算两个状态之间的差异"""
    changes = {}
    for key in set(before.keys()) | set(after.keys()):
        old_val = before.get(key)
        new_val = after.get(key)
        
        if old_val != new_val:
            # 格式化变化
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                delta = new_val - old_val
                if delta > 0:
                    changes[key] = f"{old_val} → {new_val} (+{delta})"
                else:
                    changes[key] = f"{old_val} → {new_val} ({delta})"
            elif old_val is None and new_val is not None:
                changes[key] = f"None → {new_val}"
            elif old_val is not None and new_val is None:
                changes[key] = f"{old_val} → None"
            else:
                changes[key] = f"{old_val} → {new_val}"
    
    return changes


def format_context_diff(changes: dict[str, str]) -> str:
    """格式化差异为可读字符串"""
    if not changes:
        return "  (无变化)"
    
    lines = []
    for key, change in sorted(changes.items()):
        lines.append(f"  • {key}: {change}")
    return "\n".join(lines)


# ============================================================================
# 监控数据结构
# ============================================================================

@dataclass
class StageMetrics:
    """阶段监控指标"""
    stage_name: str
    duration_ms: float = 0.0
    success: bool = True
    error_message: str = ""
    # 阶段特定统计
    species_count: int = 0
    migration_count: int = 0
    extinction_count: int = 0
    speciation_count: int = 0
    ai_adjustments: int = 0
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    # Context 变化摘要
    context_changes: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "stage": self.stage_name,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error": self.error_message,
            "species_count": self.species_count,
            "migration_count": self.migration_count,
            "extinction_count": self.extinction_count,
            "speciation_count": self.speciation_count,
            "ai_adjustments": self.ai_adjustments,
            "custom": self.custom_metrics,
        }


@dataclass
class PipelineMetrics:
    """流水线监控指标"""
    total_duration_ms: float = 0.0
    stage_metrics: list[StageMetrics] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    
    def get_performance_table(self) -> str:
        """生成性能表格（按耗时排序）"""
        if not self.stage_metrics:
            return "No metrics available"
        
        # 按耗时排序
        sorted_metrics = sorted(
            self.stage_metrics,
            key=lambda m: m.duration_ms,
            reverse=True
        )
        
        lines = [
            "┌" + "─" * 40 + "┬" + "─" * 12 + "┬" + "─" * 8 + "┐",
            "│ {:^38} │ {:^10} │ {:^6} │".format("Stage", "Time (ms)", "Status"),
            "├" + "─" * 40 + "┼" + "─" * 12 + "┼" + "─" * 8 + "┤",
        ]
        
        for m in sorted_metrics:
            status = "✅" if m.success else "❌"
            name = m.stage_name[:38]
            lines.append(
                "│ {:38} │ {:>10.2f} │ {:^6} │".format(name, m.duration_ms, status)
            )
        
        lines.append("├" + "─" * 40 + "┼" + "─" * 12 + "┼" + "─" * 8 + "┤")
        lines.append(
            "│ {:38} │ {:>10.2f} │        │".format("TOTAL", self.total_duration_ms)
        )
        lines.append("└" + "─" * 40 + "┴" + "─" * 12 + "┴" + "─" * 8 + "┘")
        
        return "\n".join(lines)
    
    def get_slowest_stages(self, n: int = 5) -> list[tuple[str, float]]:
        """获取最慢的 N 个阶段"""
        sorted_metrics = sorted(
            self.stage_metrics,
            key=lambda m: m.duration_ms,
            reverse=True
        )
        return [(m.stage_name, m.duration_ms) for m in sorted_metrics[:n]]
    
    def to_dict(self) -> dict:
        return {
            "total_duration_ms": round(self.total_duration_ms, 2),
            "stage_count": len(self.stage_metrics),
            "failed_count": len(self.failed_stages),
            "stages": [m.to_dict() for m in self.stage_metrics],
            "failed_stages": self.failed_stages,
        }


@dataclass
class PipelineConfig:
    """流水线配置"""
    # 是否在阶段失败时继续执行后续阶段
    continue_on_error: bool = True
    # 是否记录每个阶段的执行时间
    log_timing: bool = True
    # 阶段执行超时（秒），0 表示不超时
    stage_timeout: float = 0
    # 是否发送阶段开始/结束事件
    emit_stage_events: bool = True
    # 是否验证阶段依赖
    validate_dependencies: bool = True
    # 是否在 debug 模式下输出依赖图
    debug_mode: bool = False
    # 是否允许部分执行（指定起止阶段）
    start_stage: str | None = None
    stop_stage: str | None = None
    # 只执行单个阶段
    only_stage: str | None = None


@dataclass
class PipelineResult:
    """流水线执行结果"""
    success: bool
    total_duration_ms: float
    stage_results: list[StageResult] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    metrics: PipelineMetrics | None = None
    
    def get_failed_stage_names(self) -> list[str]:
        """获取失败阶段名称列表"""
        return [r.stage_name for r in self.stage_results if not r.success]
    
    def get_performance_summary(self) -> str:
        """获取性能摘要"""
        if self.metrics:
            return self.metrics.get_performance_table()
        return "No metrics available"


class Pipeline:
    """流水线执行器
    
    按顺序执行一系列 Stage，支持：
    - 同步和异步阶段的混合执行
    - 统一的错误处理和日志记录
    - 阶段执行时间统计
    - 事件回调通知
    - 依赖验证
    - 部分执行（中途截断）
    """
    
    def __init__(
        self,
        stages: list[Stage],
        config: PipelineConfig | None = None,
    ):
        """初始化流水线
        
        Args:
            stages: 阶段列表（将按 order 排序）
            config: 流水线配置
        
        Raises:
            DependencyError: 当依赖验证失败时
        """
        from .stages import StageDependencyValidator, DependencyError
        
        self.stages = sorted(stages, key=lambda s: s.order)
        self.config = config or PipelineConfig()
        self._before_stage_callbacks: list[Callable] = []
        self._after_stage_callbacks: list[Callable] = []
        self._stage_map = {s.name: s for s in self.stages}
        
        # 验证依赖
        if self.config.validate_dependencies:
            self._validate_dependencies()
        
        # 应用部分执行配置
        self._effective_stages = self._filter_stages()
    
    def _validate_dependencies(self) -> None:
        """验证阶段依赖关系"""
        from .stages import StageDependencyValidator, DependencyError
        
        validator = StageDependencyValidator(self.stages)
        result = validator.validate()
        
        if self.config.debug_mode:
            logger.info(result.dependency_graph)
        
        for warning in result.warnings:
            logger.warning(warning)
        
        if not result.valid:
            for error in result.errors:
                logger.error(error)
            raise DependencyError(
                f"依赖验证失败: {len(result.errors)} 个错误\n" +
                "\n".join(result.errors)
            )
    
    def _filter_stages(self) -> list[Stage]:
        """根据配置过滤需要执行的阶段"""
        if self.config.only_stage:
            # 只执行单个阶段
            stage = self._stage_map.get(self.config.only_stage)
            if not stage:
                available = ", ".join(sorted(self._stage_map.keys()))
                raise ValueError(
                    f"阶段 '{self.config.only_stage}' 不存在。可用阶段: {available}"
                )
            return [stage]
        
        stages = self.stages
        
        # 起始阶段
        if self.config.start_stage:
            start_idx = None
            for i, s in enumerate(stages):
                if s.name == self.config.start_stage:
                    start_idx = i
                    break
            if start_idx is None:
                raise ValueError(f"起始阶段 '{self.config.start_stage}' 不存在")
            stages = stages[start_idx:]
        
        # 终止阶段
        if self.config.stop_stage:
            stop_idx = None
            for i, s in enumerate(stages):
                if s.name == self.config.stop_stage:
                    stop_idx = i
                    break
            if stop_idx is None:
                raise ValueError(f"终止阶段 '{self.config.stop_stage}' 不存在")
            stages = stages[:stop_idx + 1]
        
        return stages
    
    def get_stage_names(self) -> list[str]:
        """获取所有阶段名称（用于调试）"""
        return [s.name for s in self.stages]
    
    def get_effective_stage_names(self) -> list[str]:
        """获取将要执行的阶段名称"""
        return [s.name for s in self._effective_stages]
    
    def get_dependency_graph(self) -> str:
        """获取依赖关系图（文本形式）"""
        from .stages import StageDependencyValidator
        validator = StageDependencyValidator(self.stages)
        result = validator.validate()
        return result.dependency_graph
    
    def add_before_stage_callback(self, callback: Callable[[Stage, SimulationContext], None]) -> None:
        """添加阶段执行前回调"""
        self._before_stage_callbacks.append(callback)
    
    def add_after_stage_callback(self, callback: Callable[[Stage, SimulationContext, StageResult], None]) -> None:
        """添加阶段执行后回调"""
        self._after_stage_callbacks.append(callback)
    
    async def execute(
        self,
        ctx: SimulationContext,
        engine: SimulationEngine,
    ) -> PipelineResult:
        """执行流水线
        
        Args:
            ctx: 回合上下文
            engine: 模拟引擎
        
        Returns:
            流水线执行结果
        """
        from .stages import StageResult
        
        start_time = time.perf_counter()
        stage_results: list[StageResult] = []
        failed_stages: list[str] = []
        stage_metrics: list[StageMetrics] = []
        overall_success = True
        
        # 使用过滤后的阶段列表
        stages_to_execute = self._effective_stages
        
        if self.config.debug_mode:
            logger.info(f"[Pipeline] 将执行 {len(stages_to_execute)} 个阶段")
            for s in stages_to_execute:
                logger.info(f"  [{s.order:3d}] {s.name}")
        
        for stage in stages_to_execute:
            # 执行前回调
            for callback in self._before_stage_callbacks:
                try:
                    callback(stage, ctx)
                except Exception as e:
                    logger.warning(f"[Pipeline] 前置回调失败: {e}")
            
            # 发送阶段开始事件
            if self.config.emit_stage_events:
                ctx.emit_event("pipeline_stage_start", f"开始: {stage.name}", "流水线")
            
            # 捕获阶段前的状态（用于计算变化量）
            pre_migration = ctx.migration_count
            pre_extinctions = len([r for r in ctx.combined_results if r.species.status == "extinct"]) if ctx.combined_results else 0
            
            # 在 debug 模式下捕获完整的 context 状态
            pre_context_state = capture_context_state(ctx) if self.config.debug_mode else {}
            
            # 执行阶段
            stage_start = time.perf_counter()
            result = await self._execute_stage(stage, ctx, engine)
            stage_duration = (time.perf_counter() - stage_start) * 1000
            
            result.duration_ms = stage_duration
            stage_results.append(result)
            
            # 计算 context 变化
            context_changes = {}
            if self.config.debug_mode:
                post_context_state = capture_context_state(ctx)
                context_changes = compute_context_diff(pre_context_state, post_context_state)
                if context_changes:
                    logger.debug(f"[Pipeline] [{stage.name}] Context 变化:")
                    logger.debug(format_context_diff(context_changes))
            
            # 构建阶段监控指标
            metrics = StageMetrics(
                stage_name=stage.name,
                duration_ms=stage_duration,
                success=result.success,
                error_message=str(result.error) if result.error else "",
                species_count=len(ctx.species_batch) if ctx.species_batch else 0,
                migration_count=ctx.migration_count - pre_migration,
                extinction_count=len([r for r in ctx.combined_results if r.species.status == "extinct"]) - pre_extinctions if ctx.combined_results else 0,
                speciation_count=len(ctx.branching_events) if ctx.branching_events else 0,
                ai_adjustments=len(ctx.ai_status_evals) if ctx.ai_status_evals else 0,
                context_changes=context_changes,
            )
            stage_metrics.append(metrics)
            
            if not result.success:
                failed_stages.append(stage.name)
                overall_success = False
                
                if not self.config.continue_on_error:
                    logger.error(f"[Pipeline] 阶段 '{stage.name}' 失败，终止流水线")
                    break
            
            # 记录时间
            if self.config.log_timing:
                logger.debug(f"[Pipeline] {stage.name}: {stage_duration:.1f}ms")
            
            # 发送阶段结束事件
            if self.config.emit_stage_events:
                status = "✅" if result.success else "❌"
                ctx.emit_event(
                    "pipeline_stage_end",
                    f"{status} {stage.name}: {stage_duration:.1f}ms",
                    "流水线"
                )
            
            # 执行后回调
            for callback in self._after_stage_callbacks:
                try:
                    callback(stage, ctx, result)
                except Exception as e:
                    logger.warning(f"[Pipeline] 后置回调失败: {e}")
        
        total_duration = (time.perf_counter() - start_time) * 1000
        
        # 构建流水线监控指标
        pipeline_metrics = PipelineMetrics(
            total_duration_ms=total_duration,
            stage_metrics=stage_metrics,
            failed_stages=failed_stages,
        )
        
        return PipelineResult(
            success=overall_success,
            total_duration_ms=total_duration,
            stage_results=stage_results,
            failed_stages=failed_stages,
            metrics=pipeline_metrics,
        )
    
    async def _execute_stage(
        self,
        stage: Stage,
        ctx: SimulationContext,
        engine: SimulationEngine,
    ) -> StageResult:
        """执行单个阶段
        
        Args:
            stage: 要执行的阶段
            ctx: 回合上下文
            engine: 模拟引擎
        
        Returns:
            阶段执行结果
        """
        from .stages import StageResult
        
        try:
            if self.config.stage_timeout > 0:
                await asyncio.wait_for(
                    stage.execute(ctx, engine),
                    timeout=self.config.stage_timeout
                )
            else:
                await stage.execute(ctx, engine)
            
            return StageResult(
                stage_name=stage.name,
                success=True,
            )
        except asyncio.TimeoutError:
            logger.error(f"[Pipeline] 阶段 '{stage.name}' 超时")
            return StageResult(
                stage_name=stage.name,
                success=False,
                error=asyncio.TimeoutError(f"Stage '{stage.name}' timed out"),
            )
        except Exception as e:
            logger.error(f"[Pipeline] 阶段 '{stage.name}' 执行失败: {e}")
            import traceback
            traceback.print_exc()
            return StageResult(
                stage_name=stage.name,
                success=False,
                error=e,
            )
    
    def get_stage_names(self) -> list[str]:
        """获取所有阶段名称"""
        return [s.name for s in self.stages]
    
    def get_stage_count(self) -> int:
        """获取阶段数量"""
        return len(self.stages)


class PipelineBuilder:
    """流水线构建器
    
    提供流畅的 API 来构建流水线配置。
    """
    
    def __init__(self):
        self._stages: list[Stage] = []
        self._config = PipelineConfig()
    
    def add_stage(self, stage: Stage) -> "PipelineBuilder":
        """添加阶段"""
        self._stages.append(stage)
        return self
    
    def add_stages(self, stages: list[Stage]) -> "PipelineBuilder":
        """批量添加阶段"""
        self._stages.extend(stages)
        return self
    
    def continue_on_error(self, value: bool = True) -> "PipelineBuilder":
        """设置是否在错误时继续"""
        self._config.continue_on_error = value
        return self
    
    def log_timing(self, value: bool = True) -> "PipelineBuilder":
        """设置是否记录时间"""
        self._config.log_timing = value
        return self
    
    def stage_timeout(self, seconds: float) -> "PipelineBuilder":
        """设置阶段超时"""
        self._config.stage_timeout = seconds
        return self
    
    def emit_events(self, value: bool = True) -> "PipelineBuilder":
        """设置是否发送事件"""
        self._config.emit_stage_events = value
        return self
    
    def build(self) -> Pipeline:
        """构建流水线"""
        return Pipeline(self._stages, self._config)

