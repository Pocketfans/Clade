from __future__ import annotations

import asyncio
from typing import Sequence, Callable, Awaitable

from ...schemas.responses import SpeciesSnapshot
from ...simulation.environment import ParsedPressure


import logging
logger = logging.getLogger(__name__)

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
        # 【修复】如果 stream_callback 为 None，说明是超时回退或测试模式，跳过AI直接返回结构化模板
        if stream_callback is None:
             logger.info("[ReportBuilder] 跳过 AI 生成，直接使用结构化模板")
             full_text = "" 
        else:
            payload = {
                "pressures": pressure_lines,
                "species": species_summary[:10],  # 只发送前10个物种避免token过多
                "background": [f"{item.role}:{item.survivor_population}存活" for item in (background or [])],
                "major_events": [f"{item.severity}-{item.description}" for item in (major_events or [])],
                "migrations": [f"{item.lineage_code}迁徙" for item in (migration_events or [])[:3]],
            }
            
            content_parts = []
            chunk_count = 0
            
            # 【优化】流式读取的超时保护
            async def stream_with_timeout():
                nonlocal content_parts, chunk_count
                last_chunk_time = asyncio.get_event_loop().time()
                chunk_timeout = 20.0  # 单个chunk最长等待20秒（减少等待）
                
                async for chunk in self.router.astream("turn_report", payload):
                    current_time = asyncio.get_event_loop().time()
                    
                    # 【新增】检查单个 chunk 超时
                    if current_time - last_chunk_time > chunk_timeout:
                        logger.warning(f"[ReportBuilder] 单个chunk超时（{chunk_timeout}秒），提前结束流读取")
                        break
                    
                    # 处理可能的状态/错误事件字典
                    if isinstance(chunk, dict):
                        event_type = chunk.get("type")
                        event_state = chunk.get("state")
                        
                        if event_type == "error":
                            logger.warning(f"[ReportBuilder] Stream error event: {chunk}")
                            break  # 遇到错误时退出
                        
                        # 【关键修复】处理completed状态，结束流读取
                        if event_type == "status" and event_state == "completed":
                            logger.debug("[ReportBuilder] Stream completed signal received")
                            break
                        
                        continue
                    
                    # 更新最后一次收到数据的时间
                    last_chunk_time = current_time
                    chunk_count += 1
                    
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
                
                # 流正常结束时记录
                if chunk_count > 0:
                    logger.info(f"[ReportBuilder] 流式读取完成，共收到 {chunk_count} 个chunks")
            
            try:
                # 【优化】整体流式读取超时减少到60秒（原90秒太长）
                await asyncio.wait_for(stream_with_timeout(), timeout=60.0)
            except asyncio.TimeoutError:
                # 【优化】超时后记录更多信息，帮助诊断
                logger.error(f"[ReportBuilder] 流式读取超时（60秒），已收到 {chunk_count} 个chunks，使用已收到的内容")
            except Exception as e:
                logger.error(f"[ReportBuilder] Stream error: {e}, 已收到 {chunk_count} 个chunks")
                
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
