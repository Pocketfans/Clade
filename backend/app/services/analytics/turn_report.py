"""
Turn Report Service - 回合报告服务

构建每回合的详细报告。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ...schemas.responses import TurnReport, SpeciesSnapshot
    from ..species.trophic_interaction import TrophicInteractionService

from ...schemas.responses import SpeciesSnapshot
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class TurnReportService:
    """回合报告服务
    
    负责构建每回合的详细报告。
    """
    
    def __init__(
        self,
        report_builder: Any,
        environment_repository: Any,
        trophic_service: "TrophicInteractionService",
        emit_event_fn: Callable[[str, str, str], None] | None = None,
    ):
        self.report_builder = report_builder
        self.environment_repository = environment_repository
        self.trophic_service = trophic_service
        self.emit_event_fn = emit_event_fn
    
    def _emit_event(self, event_type: str, message: str, category: str = "报告"):
        """发送事件"""
        if self.emit_event_fn:
            try:
                self.emit_event_fn(event_type, message, category)
            except Exception:
                pass
    
    def _get_ecological_role(self, trophic_level: float) -> str:
        """根据营养级确定生态角色"""
        if trophic_level < 1.5:
            return "生产者"
        elif trophic_level < 2.5:
            return "初级消费者"
        elif trophic_level < 3.5:
            return "次级消费者"
        elif trophic_level < 4.5:
            return "高级消费者"
        else:
            return "顶级掠食者"
    
    async def build_report(
        self,
        turn_index: int,
        mortality_results: List[Any],
        pressures: List[Any],
        branching_events: List[Any],
        background_summary: Any = None,
        reemergence_events: List[Any] | None = None,
        major_events: List[Any] | None = None,
        map_changes: List[Any] | None = None,
        migration_events: List[Any] | None = None,
        stream_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> "TurnReport":
        """构建回合报告
        
        Args:
            turn_index: 回合索引
            mortality_results: 死亡率结果
            pressures: 压力列表
            branching_events: 分化事件
            background_summary: 背景物种摘要
            reemergence_events: 重现事件
            major_events: 重大事件
            map_changes: 地图变化
            migration_events: 迁徙事件
            stream_callback: 流式输出回调
            
        Returns:
            TurnReport
        """
        from ...schemas.responses import TurnReport
        
        self._emit_event("info", "构建回合报告...", "报告")
        
        # 构建压力摘要
        pressure_summary = "环境稳定"
        if pressures:
            pressure_parts = []
            for p in pressures:
                if hasattr(p, 'kind') and hasattr(p, 'intensity'):
                    pressure_parts.append(f"{p.kind}: {p.intensity:.1f}")
            if pressure_parts:
                pressure_summary = ", ".join(pressure_parts)
        
        # 构建物种数据
        species_data = []
        total_population = sum(
            getattr(r, 'final_population', 0) or r.species.morphology_stats.get("population", 0)
            for r in mortality_results
            if hasattr(r, 'species')
        ) or 1  # 避免除零
        
        for result in mortality_results:
            if hasattr(result, 'species') and hasattr(result, 'death_rate'):
                pop = getattr(result, 'final_population', 0) or result.species.morphology_stats.get("population", 0)
                species_data.append({
                    "lineage_code": result.species.lineage_code,
                    "latin_name": result.species.latin_name,
                    "common_name": result.species.common_name,
                    "population": pop,
                    "population_share": pop / total_population,
                    "deaths": getattr(result, 'deaths', 0),
                    "death_rate": result.death_rate,
                    "ecological_role": self._get_ecological_role(result.species.trophic_level),
                    "status": result.species.status,
                    "notes": getattr(result, 'notes', []) or [],
                    "niche_overlap": getattr(result, 'niche_overlap', None),
                    "resource_pressure": getattr(result, 'resource_pressure', None),
                    "is_background": getattr(result, 'is_background', False),
                    "tier": getattr(result, 'tier', None),
                    "trophic_level": result.species.trophic_level,
                    "grazing_pressure": getattr(result, 'grazing_pressure', None),
                    "predation_pressure": getattr(result, 'predation_pressure', None),
                    "ai_narrative": getattr(result, 'ai_narrative', None),
                    "initial_population": getattr(result, 'initial_population', 0),
                    "births": getattr(result, 'births', 0),
                    "survivors": getattr(result, 'survivors', 0),
                })
        
        # ========== 检查 LLM 回合报告开关 ==========
        # 优先从 UI 配置读取，否则从系统配置读取
        try:
            from pathlib import Path
            settings = get_settings()
            ui_config_path = Path(settings.ui_config_path)
            ui_config = self.environment_repository.load_ui_config(ui_config_path)
            enable_turn_report_llm = ui_config.turn_report_llm_enabled
        except Exception:
            # 回退到系统配置
            settings = get_settings()
            enable_turn_report_llm = settings.enable_turn_report_llm
        
        # 如果开关关闭，直接使用简单模式，不调用 LLM
        if not enable_turn_report_llm:
            logger.info("[TurnReportService] LLM 回合报告已关闭，使用简单模式")
            self._emit_event("info", "📝 LLM 回合报告已关闭", "报告")
            
            narrative = f"回合 {turn_index} 完成。"
            
            if mortality_results:
                alive_count = sum(1 for r in mortality_results if r.species.status == "alive")
                narrative += f" 存活物种: {alive_count} 个。"
            
            if branching_events:
                narrative += f" 发生了 {len(branching_events)} 次物种分化。"
            
            if migration_events:
                narrative += f" 发生了 {len(migration_events)} 次迁徙。"
            
            # 简单模式下流式输出
            if stream_callback:
                for char in narrative:
                    await stream_callback(char)
                    await asyncio.sleep(0.01)
            
            return TurnReport(
                turn_index=turn_index,
                narrative=narrative,
                pressures_summary=pressure_summary,
                species=species_data,
                branching_events=branching_events or [],
                major_events=major_events or [],
            )
        
        # ========== 【修复】调用 LLM 叙事引擎 ==========
        # 将 mortality_results 转换为 SpeciesSnapshot 列表
        species_snapshots: List[SpeciesSnapshot] = []
        for result in mortality_results:
            if hasattr(result, 'species') and hasattr(result, 'death_rate'):
                pop = getattr(result, 'final_population', 0) or result.species.morphology_stats.get("population", 0)
                initial_pop = getattr(result, 'initial_population', 0) or pop
                deaths = getattr(result, 'deaths', 0)
                
                species_snapshots.append(SpeciesSnapshot(
                    lineage_code=result.species.lineage_code,
                    latin_name=result.species.latin_name,
                    common_name=result.species.common_name,
                    population=pop,
                    population_share=pop / total_population,
                    deaths=deaths,
                    death_rate=result.death_rate,
                    ecological_role=self._get_ecological_role(result.species.trophic_level),
                    status=result.species.status,
                    notes=getattr(result, 'notes', []) or [],
                    niche_overlap=getattr(result, 'niche_overlap', None),
                    resource_pressure=getattr(result, 'resource_pressure', None),
                    is_background=getattr(result, 'is_background', False),
                    tier=getattr(result, 'tier', None),
                    trophic_level=result.species.trophic_level,
                    grazing_pressure=getattr(result, 'grazing_pressure', None),
                    predation_pressure=getattr(result, 'predation_pressure', None),
                    ai_narrative=getattr(result, 'ai_narrative', None),
                    initial_population=initial_pop,
                    births=getattr(result, 'births', 0),
                    survivors=getattr(result, 'survivors', 0),
                    total_tiles=getattr(result, 'total_tiles', 0),
                    healthy_tiles=getattr(result, 'healthy_tiles', 0),
                    warning_tiles=getattr(result, 'warning_tiles', 0),
                    critical_tiles=getattr(result, 'critical_tiles', 0),
                ))
        
        # 调用 LLM 叙事引擎生成叙事
        narrative = ""
        try:
            if self.report_builder is not None:
                self._emit_event("info", "🤖 调用 AI 生成回合叙事...", "报告")
                
                narrative = await self.report_builder.build_turn_narrative_async(
                    species=species_snapshots,
                    pressures=pressures or [],
                    background=background_summary,
                    reemergence=reemergence_events,
                    major_events=major_events,
                    map_changes=map_changes,
                    migration_events=migration_events,
                    branching_events=branching_events,
                    stream_callback=stream_callback,
                )
                
                if narrative and len(narrative) > 50:
                    self._emit_event("info", "✅ AI 叙事生成完成", "报告")
                else:
                    self._emit_event("warning", "⚠️ AI 叙事过短，使用简单模式", "报告")
                    narrative = ""
            else:
                logger.warning("[TurnReportService] report_builder 未初始化，跳过 LLM 叙事")
        except asyncio.TimeoutError:
            logger.warning("[TurnReportService] LLM 叙事生成超时")
            self._emit_event("warning", "⏱️ AI 叙事超时", "报告")
            narrative = ""
        except Exception as e:
            logger.error(f"[TurnReportService] LLM 叙事生成失败: {e}")
            self._emit_event("warning", f"⚠️ AI 叙事失败: {e}", "报告")
            narrative = ""
        
        # 如果 LLM 失败，使用简单回退叙事
        if not narrative:
            narrative = f"回合 {turn_index} 完成。"
            
            if mortality_results:
                alive_count = sum(1 for r in mortality_results if r.species.status == "alive")
                narrative += f" 存活物种: {alive_count} 个。"
            
            if branching_events:
                narrative += f" 发生了 {len(branching_events)} 次物种分化。"
            
            if migration_events:
                narrative += f" 发生了 {len(migration_events)} 次迁徙。"
            
            # 简单模式下流式输出
            if stream_callback:
                for char in narrative:
                    await stream_callback(char)
                    await asyncio.sleep(0.01)
        
        return TurnReport(
            turn_index=turn_index,
            narrative=narrative,
            pressures_summary=pressure_summary,
            species=species_data,
            branching_events=branching_events or [],
            major_events=major_events or [],
        )


def create_turn_report_service(
    report_builder: Any,
    environment_repository: Any,
    trophic_service: "TrophicInteractionService",
    emit_event_fn: Callable[[str, str, str], None] | None = None,
) -> TurnReportService:
    """工厂函数：创建回合报告服务实例"""
    return TurnReportService(
        report_builder=report_builder,
        environment_repository=environment_repository,
        trophic_service=trophic_service,
        emit_event_fn=emit_event_fn,
    )

