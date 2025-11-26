from __future__ import annotations

import asyncio
from typing import Sequence, Callable, Awaitable

from ...schemas.responses import SpeciesSnapshot
from ...simulation.environment import ParsedPressure


class ReportBuilder:
    """Produces academic-style narratives for each turn."""

    def __init__(self, router) -> None:
        self.router = router

    async def build_turn_narrative_async(
        self,
        species: Sequence[SpeciesSnapshot],
        pressures: Sequence[ParsedPressure],
        background: Sequence | None = None,
        reemergence: Sequence | None = None,
        major_events: Sequence | None = None,
        map_changes: Sequence | None = None,
        migration_events: Sequence | None = None,
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> str:
        """生成结构化、易读的回合叙事 (Async)。"""
        
        # 构建数据摘要供 AI 使用
        pressure_lines = ", ".join(p.narrative for p in pressures) or "环境平稳"
        species_summary = []
        for snap in species:
            species_summary.append(
                f"{snap.common_name}({snap.lineage_code})：死亡{snap.death_rate:.0%}，"
                f"现存{snap.population:,}，生态位重叠{(snap.niche_overlap or 0):.2f}"
            )
        
        # 调用 AI 生成叙事
        payload = {
            "pressures": pressure_lines,
            "species": species_summary[:10],  # 只发送前10个物种避免token过多
            "background": [f"{item.role}:{item.survivor_population}存活" for item in (background or [])],
            "major_events": [f"{item.severity}-{item.description}" for item in (major_events or [])],
            "migrations": [f"{item.lineage_code}迁徙" for item in (migration_events or [])[:3]],
        }
        
        content_parts = []
        try:
            async for chunk in self.router.astream("turn_report", payload):
                # 处理可能的状态/错误事件字典
                if isinstance(chunk, dict):
                    if chunk.get("type") == "error":
                         print(f"[ReportBuilder] Stream error event: {chunk}")
                    continue
                
                # 确保 chunk 是字符串
                if not isinstance(chunk, str):
                    chunk = str(chunk)
                    
                content_parts.append(chunk)
                if stream_callback:
                    # 尝试调用回调，支持同步和异步
                    if asyncio.iscoroutinefunction(stream_callback):
                        await stream_callback(chunk)
                    else:
                        stream_callback(chunk)

        except Exception as e:
            print(f"[ReportBuilder] Stream error: {e}")
            
        full_text = "".join(content_parts)
        
        # turn_report 返回的是 Markdown 格式文本，无需 JSON 解析
        # 直接检查内容有效性即可
        narrative = full_text.strip() if full_text else None
        
        # 如果 AI 成功生成，直接返回（接受Markdown格式）
        if narrative and len(narrative) > 50:
            return narrative
        
        # 否则使用结构化模板（易读版本）
        sections = []
        
        # 环境压力
        sections.append(f"**环境压力**：{pressure_lines}")
        
        # 物种动态（分级显示）
        critical_species = [s for s in species if s.tier == "critical"]
        focus_species = [s for s in species if s.tier == "focus"]
        
        if critical_species:
            sections.append("\n**重点物种动态**：")
            for snap in critical_species[:5]:
                sections.append(
                    f"- {snap.common_name}（{snap.latin_name}，{snap.lineage_code}）：\n"
                    f"  种群从 {snap.population + snap.deaths:,} 减少至 {snap.population:,}（死亡率{snap.death_rate:.1%}），"
                    f"生态位竞争度{(snap.niche_overlap or 0):.2f}，资源压力{(snap.resource_pressure or 0):.2f}"
                )
        
        if focus_species and len(focus_species) > 0:
            sections.append(f"\n**次级物种**：{len(focus_species)}种，平均死亡率{sum(s.death_rate for s in focus_species)/len(focus_species):.1%}")
        
        # 背景物种
        if background:
            sections.append("\n**背景物种概况**：")
            for item in background:
                sections.append(f"- {item.role}：{item.total_population:,} → {item.survivor_population:,}")
        
        # 重大事件
        if major_events:
            sections.append("\n**重大事件**：")
            for event in major_events:
                sections.append(f"- {event.severity}级：{event.description}")
        
        # 迁徙事件
        if migration_events:
            sections.append("\n**物种迁徙**：")
            for mig in migration_events[:5]:
                sections.append(f"- {mig.lineage_code}：从{mig.origin}迁往{mig.destination}（{mig.rationale}）")
        
        # 地图演化
        if map_changes:
            sections.append("\n**地质变化**：")
            for change in map_changes:
                sections.append(f"- {change.stage}：{change.description}（{change.affected_region}）")
        
        return "\n".join(sections)

    def build_turn_narrative(self, *args, **kwargs):
        raise NotImplementedError("Use build_turn_narrative_async instead")
