"""
报告生成器 V2 - 精简版

核心设计：
1. 事件驱动：只报告关键事件，不罗列所有物种
2. 模板优先：90% 内容用模板生成，0 token
3. 可选润色：只对 1-2 个亮点用 LLM（有重大事件时才调用）

Token 使用：0 ~ 800（比 V1 更省）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Sequence, Callable, Awaitable

from ...schemas.responses import SpeciesSnapshot
from ...simulation.environment import ParsedPressure

logger = logging.getLogger(__name__)


@dataclass
class ReportableEvent:
    """可报道的事件"""
    event_type: str  # extinction | speciation | population_crash | competition | migration | environmental
    severity: int    # 1-5，5最严重
    title: str
    description: str
    species_name: str = ""
    lineage_code: str = ""
    

class ReportBuilderV2:
    """精简版报告生成器
    
    设计原则：
    - 模板优先，LLM 可选
    - 只报告关键事件，不罗列物种
    - 报告控制在 200-400 字
    """

    def __init__(self, router, batch_size: int = 5) -> None:
        self.router = router
        self.batch_size = batch_size  # 保留参数兼容性，但不再用于分批
        
        # 事件阈值
        self.crash_threshold = 0.4      # 死亡率 > 40% 视为崩溃
        self.overlap_threshold = 0.7    # 生态位重叠 > 0.7 视为竞争激化
        
        # 控制是否使用 LLM 润色
        self.enable_llm_polish = True
        self.max_highlight_events = 2   # 最多润色2个事件

    # ──────────────────────────────────────────────────────────
    # 1. 事件抽取（纯规则，0 token）
    # ──────────────────────────────────────────────────────────
    def _extract_events(
        self,
        species: Sequence[SpeciesSnapshot],
        branching_events: Sequence | None = None,
        major_events: Sequence | None = None,
        migration_events: Sequence | None = None,
    ) -> list[ReportableEvent]:
        """从数据中抽取关键事件"""
        events = []
        
        # 1. 灭绝事件（最高优先级）
        extinct_species = [s for s in species if s.status == "extinct"]
        for snap in extinct_species:
            events.append(ReportableEvent(
                event_type="extinction",
                severity=5,
                title=f"{snap.common_name}灭绝",
                description=f"{snap.common_name}（{snap.latin_name}）未能适应环境变化，走向灭绝",
                species_name=snap.common_name,
                lineage_code=snap.lineage_code,
            ))
        
        # 2. 分化事件（高优先级）
        if branching_events:
            for branch in branching_events[:3]:  # 最多3个
                child_name = getattr(branch, 'child_name', None) or getattr(branch, 'common_name', '新物种')
                parent_name = getattr(branch, 'parent_name', '祖先')
                # 使用 new_lineage 属性（BranchingEvent 的正确属性名）
                lineage = getattr(branch, 'new_lineage', '') or getattr(branch, 'child_code', '')
                events.append(ReportableEvent(
                    event_type="speciation",
                    severity=4,
                    title=f"新物种诞生：{child_name}",
                    description=f"从{parent_name}分化出新物种{child_name}",
                    species_name=child_name,
                    lineage_code=lineage,
                ))
        
        # 3. 种群崩溃（中高优先级）- 只选最严重的1个
        crash_species = [
            s for s in species 
            if s.death_rate > self.crash_threshold 
            and s.status != "extinct"
            and s.tier in ("critical", "focus")
        ]
        if crash_species:
            worst = max(crash_species, key=lambda s: s.death_rate)
            events.append(ReportableEvent(
                event_type="population_crash",
                severity=3,
                title=f"{worst.common_name}种群危机",
                description=f"死亡率高达{worst.death_rate:.0%}，种群从{worst.population + worst.deaths:,}锐减至{worst.population:,}",
                species_name=worst.common_name,
                lineage_code=worst.lineage_code,
            ))
        
        # 4. 重大环境事件
        if major_events:
            for event in major_events[:2]:
                events.append(ReportableEvent(
                    event_type="environmental",
                    severity=4,
                    title=getattr(event, 'title', '环境剧变'),
                    description=getattr(event, 'description', ''),
                ))
        
        # 按严重程度排序
        events.sort(key=lambda e: e.severity, reverse=True)
        return events

    # ──────────────────────────────────────────────────────────
    # 2. 统计摘要（纯规则，0 token）
    # ──────────────────────────────────────────────────────────
    def _generate_stats(self, species: Sequence[SpeciesSnapshot]) -> dict:
        """生成统计数据"""
        if not species:
            return {"total": 0, "avg_death_rate": 0, "total_deaths": 0}
        
        total = len(species)
        alive = [s for s in species if s.status != "extinct"]
        extinct_count = total - len(alive)
        total_pop = sum(s.population for s in alive)
        total_deaths = sum(s.deaths for s in species)
        avg_death_rate = sum(s.death_rate for s in species) / max(1, total)
        
        # 分层统计
        critical = [s for s in species if s.tier == "critical"]
        focus = [s for s in species if s.tier == "focus"]
        background = [s for s in species if s.tier == "background" or s.is_background]
        
        return {
            "total": total,
            "alive": len(alive),
            "extinct": extinct_count,
            "total_population": total_pop,
            "total_deaths": total_deaths,
            "avg_death_rate": avg_death_rate,
            "critical_count": len(critical),
            "focus_count": len(focus),
            "background_count": len(background),
        }

    # ──────────────────────────────────────────────────────────
    # 3. 模板生成（纯规则，0 token）
    # ──────────────────────────────────────────────────────────
    def _build_template_report(
        self,
        pressures: Sequence[ParsedPressure],
        events: list[ReportableEvent],
        stats: dict,
        map_changes: Sequence | None = None,
    ) -> str:
        """用模板生成报告主体"""
        sections = []
        
        # === 环境概况 ===
        pressure_text = "、".join(p.narrative for p in pressures) if pressures else "环境相对稳定"
        sections.append(f"## 🌏 环境态势\n\n{pressure_text}。")
        
        # 地质变化（如果有）
        if map_changes:
            changes = [getattr(c, 'description', str(c)) for c in map_changes[:2]]
            if changes:
                sections.append(f"地质层面，{'；'.join(changes)}。")
        
        # === 关键事件 ===
        if events:
            event_section = ["## ⚡ 本回合要事"]
            for e in events[:3]:  # 最多显示3个事件
                icon = self._get_event_icon(e.event_type)
                event_section.append(f"\n{icon} **{e.title}**：{e.description}")
            sections.append("\n".join(event_section))
        
        # === 生态概览（简短统计）===
        overview = f"## 📊 生态概览\n\n"
        overview += f"物种总数 **{stats['total']}** 种"
        if stats['extinct'] > 0:
            overview += f"（本回合灭绝 {stats['extinct']} 种）"
        overview += f"，总死亡 **{stats['total_deaths']:,}** 个体，平均死亡率 **{stats['avg_death_rate']:.1%}**。"
        sections.append(overview)
        
        return "\n\n".join(sections)

    def _get_event_icon(self, event_type: str) -> str:
        """获取事件图标"""
        icons = {
            "extinction": "💀",
            "speciation": "🧬",
            "population_crash": "📉",
            "competition": "⚔️",
            "migration": "🦅",
            "environmental": "🌋",
        }
        return icons.get(event_type, "📌")

    # ──────────────────────────────────────────────────────────
    # 4. LLM 润色（可选，只对亮点事件）
    # ──────────────────────────────────────────────────────────
    async def _polish_highlight(self, events: list[ReportableEvent]) -> str | None:
        """对亮点事件进行 LLM 润色（可选）
        
        只在有高优先级事件时调用，生成 2-3 句话的"史诗感"描述
        """
        if not self.enable_llm_polish:
            return None
        
        # 只选严重程度 >= 4 的事件
        highlights = [e for e in events if e.severity >= 4][:self.max_highlight_events]
        
        if not highlights:
            return None
        
        # 构建简短 prompt
        event_desc = "\n".join(f"- {e.title}: {e.description}" for e in highlights)
        prompt = f"""用2-3句话，以自然纪录片旁白的语气，描述这些演化事件的历史意义：

{event_desc}

要求：语气宏大，突出因果，不超过80字。只输出描述，不要标题。"""

        try:
            response = await asyncio.wait_for(
                self.router.chat(prompt, capability="turn_report"),
                timeout=15  # 缩短超时，快速降级
            )
            result = response if isinstance(response, str) else str(response)
            return result.strip() if result else None
        except asyncio.TimeoutError:
            logger.warning(f"[ReportV2] LLM润色超时（15秒），降级为模板")
            return None
        except Exception as e:
            logger.warning(f"[ReportV2] LLM润色失败（降级为模板）: {e}")
            return None

    # ──────────────────────────────────────────────────────────
    # 5. 主入口
    # ──────────────────────────────────────────────────────────
    async def build_turn_narrative_async(
        self,
        species: Sequence[SpeciesSnapshot],
        pressures: Sequence[ParsedPressure],
        background: Sequence | None = None,
        reemergence: Sequence | None = None,
        major_events: Sequence | None = None,
        map_changes: Sequence | None = None,
        migration_events: Sequence | None = None,
        branching_events: Sequence | None = None,
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> str:
        """生成回合叙事
        
        流程：
        1. 事件抽取（规则）
        2. 统计计算（规则）
        3. 模板生成（规则）
        4. 可选润色（LLM，仅重大事件）
        5. 合并输出
        """
        
        # Step 1: 事件抽取
        events = self._extract_events(
            species, branching_events, major_events, migration_events
        )
        
        # Step 2: 统计计算
        stats = self._generate_stats(species)
        
        # Step 3: 模板生成
        template_report = self._build_template_report(
            pressures, events, stats, map_changes
        )
        
        # Step 4: 可选的 LLM 润色
        polish_text = None
        high_priority_events = [e for e in events if e.severity >= 4]
        
        if high_priority_events and self.enable_llm_polish:
            polish_text = await self._polish_highlight(events)
        
        # Step 5: 合并输出
        if polish_text:
            # 在关键事件后插入润色文字
            narrative = template_report + f"\n\n---\n\n*{polish_text}*"
        else:
            narrative = template_report
        
        # 流式回调（模拟）
        if stream_callback and narrative:
            chunk_size = 100
            for i in range(0, len(narrative), chunk_size):
                chunk = narrative[i:i+chunk_size]
                if asyncio.iscoroutinefunction(stream_callback):
                    await stream_callback(chunk)
                else:
                    stream_callback(chunk)
                await asyncio.sleep(0.01)
        
        logger.info(f"[ReportV2] 报告生成完成: {len(events)}个事件, LLM润色={'是' if polish_text else '否'}")
        return narrative


# 工厂函数
def create_report_builder_v2(router, batch_size: int = 5) -> ReportBuilderV2:
    """创建 ReportBuilderV2 实例"""
    return ReportBuilderV2(router, batch_size)
