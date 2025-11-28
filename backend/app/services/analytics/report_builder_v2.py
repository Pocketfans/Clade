"""
报告生成器 V2 - LLM 纪录片旁白版

核心设计：
1. 完全由 LLM 生成纪录片风格的叙事
2. 提供丰富的上下文（环境、事件、物种数据）让 LLM 自由发挥
3. 自然地融入明星物种的故事，不刻意标注
4. 支持流式输出

Token 使用：约 500-1500（取决于物种数量）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Sequence, Callable, Awaitable, Any

from ...schemas.responses import SpeciesSnapshot
from ...simulation.environment import ParsedPressure

logger = logging.getLogger(__name__)


@dataclass
class SpeciesHighlight:
    """值得特别叙述的物种"""
    lineage_code: str
    common_name: str
    latin_name: str
    reason: str           # 为什么值得关注
    key_facts: list[str]  # 关键数据点


class ReportBuilderV2:
    """LLM 驱动的纪录片风格报告生成器
    
    设计原则：
    - LLM 自由发挥，不使用固定模板
    - 提供结构化数据，让 LLM 编织成自然叙事
    - 明星物种自然融入故事，不刻意突出
    """

    def __init__(self, router, batch_size: int = 5) -> None:
        self.router = router
        self.batch_size = batch_size
        
        # 事件阈值
        self.crash_threshold = 0.4
        self.low_death_threshold = 0.10  # 低死亡率阈值
        self.high_population_threshold = 0.25  # 高占比阈值

    # ──────────────────────────────────────────────────────────
    # 1. 识别值得叙述的物种（不是"明星"，只是有故事的物种）
    # ──────────────────────────────────────────────────────────
    def _identify_highlight_species(
        self,
        species: Sequence[SpeciesSnapshot],
        branching_events: Sequence | None = None,
        species_details: dict[str, Any] | None = None,
    ) -> list[SpeciesHighlight]:
        """识别值得在叙事中特别提及的物种"""
        if not species:
            return []
        
        highlights: list[SpeciesHighlight] = []
        alive_species = [s for s in species if s.status != "extinct"]
        selected_codes = set()
        
        # 1. 本回合新分化的物种
        if branching_events:
            for branch in branching_events[:3]:
                new_lineage = getattr(branch, 'new_lineage', '') or getattr(branch, 'child_code', '')
                new_sp = next((s for s in species if s.lineage_code == new_lineage), None)
                if new_sp and new_lineage not in selected_codes:
                    description = getattr(branch, 'description', '')
                    facts = [f"本回合从祖先分化而来"]
                    if description:
                        facts.append(f"分化原因: {description[:60]}")
                    if species_details and new_lineage in species_details:
                        detail = species_details[new_lineage]
                        if detail.get('capabilities'):
                            facts.append(f"具备能力: {', '.join(detail['capabilities'][:3])}")
                    
                    highlights.append(SpeciesHighlight(
                        lineage_code=new_lineage,
                        common_name=new_sp.common_name,
                        latin_name=new_sp.latin_name,
                        reason="新物种诞生",
                        key_facts=facts,
                    ))
                    selected_codes.add(new_lineage)
        
        # 2. 死亡率最低的物种（适应良好）
        candidates = [s for s in alive_species 
                     if s.lineage_code not in selected_codes 
                     and s.deaths > 0 
                     and s.death_rate < self.low_death_threshold]
        if candidates:
            best = min(candidates, key=lambda s: s.death_rate)
            facts = [f"死亡率仅 {best.death_rate:.1%}，适应能力出众"]
            if best.trophic_level:
                facts.append(f"营养级 T{best.trophic_level:.1f}")
            if species_details and best.lineage_code in species_details:
                detail = species_details[best.lineage_code]
                traits = detail.get('abstract_traits', {})
                if traits:
                    top = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:2]
                    facts.append(f"擅长: {', '.join(f'{k}' for k, v in top)}")
            
            highlights.append(SpeciesHighlight(
                lineage_code=best.lineage_code,
                common_name=best.common_name,
                latin_name=best.latin_name,
                reason="适应能力出众",
                key_facts=facts,
            ))
            selected_codes.add(best.lineage_code)
        
        # 3. 占比最高的物种（生态主导）
        candidates = [s for s in alive_species 
                     if s.lineage_code not in selected_codes 
                     and s.population_share > self.high_population_threshold]
        if candidates:
            dominant = max(candidates, key=lambda s: s.population_share)
            facts = [
                f"占全球生物量 {dominant.population_share:.1%}",
                f"种群数量 {dominant.population:,}",
            ]
            highlights.append(SpeciesHighlight(
                lineage_code=dominant.lineage_code,
                common_name=dominant.common_name,
                latin_name=dominant.latin_name,
                reason="生态系统中占主导地位",
                key_facts=facts,
            ))
            selected_codes.add(dominant.lineage_code)
        
        # 4. 死亡率最高的物种（正在挣扎）
        struggling = [s for s in alive_species 
                     if s.lineage_code not in selected_codes 
                     and s.death_rate > self.crash_threshold]
        if struggling:
            worst = max(struggling, key=lambda s: s.death_rate)
            facts = [
                f"死亡率高达 {worst.death_rate:.1%}",
                f"种群从 {worst.population + worst.deaths:,} 锐减至 {worst.population:,}",
            ]
            highlights.append(SpeciesHighlight(
                lineage_code=worst.lineage_code,
                common_name=worst.common_name,
                latin_name=worst.latin_name,
                reason="正面临生存危机",
                key_facts=facts,
            ))
            selected_codes.add(worst.lineage_code)
        
        # 5. 有高级器官的物种
        if species_details:
            for snap in alive_species:
                if snap.lineage_code in selected_codes or len(highlights) >= 5:
                    break
                detail = species_details.get(snap.lineage_code, {})
                organs = detail.get('organs', {})
                advanced = [(k, v) for k, v in organs.items() 
                           if v.get('is_active') and v.get('stage', 0) >= 2]
                if advanced:
                    organ_names = [v.get('type', k) for k, v in advanced[:3]]
                    facts = [f"发展出高级器官: {', '.join(organ_names)}"]
                    if detail.get('capabilities'):
                        facts.append(f"解锁能力: {', '.join(detail['capabilities'][:2])}")
                    
                    highlights.append(SpeciesHighlight(
                        lineage_code=snap.lineage_code,
                        common_name=snap.common_name,
                        latin_name=snap.latin_name,
                        reason="器官演化显著",
                        key_facts=facts,
                    ))
                    selected_codes.add(snap.lineage_code)
        
        return highlights[:5]  # 最多5个

    # ──────────────────────────────────────────────────────────
    # 2. 构建 LLM Prompt
    # ──────────────────────────────────────────────────────────
    def _build_narrative_prompt(
        self,
        turn_index: int,
        pressures: Sequence[ParsedPressure],
        species: Sequence[SpeciesSnapshot],
        highlight_species: list[SpeciesHighlight],
        branching_events: Sequence | None = None,
        major_events: Sequence | None = None,
        map_changes: Sequence | None = None,
        stats: dict | None = None,
    ) -> str:
        """构建让 LLM 生成叙事的 prompt"""
        
        # === 基本信息 ===
        prompt_parts = [
            "你是一位自然纪录片的旁白撰稿人，请根据以下演化模拟数据，撰写一段富有画面感和情感的叙事报告。",
            "",
            "【写作要求】",
            "- 像 BBC 自然纪录片旁白一样，富有画面感和情感",
            "- 自然流畅地讲述这一回合发生的故事",
            "- 将数据转化为生动的叙事，不要简单罗列",
            "- 特别关注值得讲述的物种，将它们的故事自然融入叙事",
            "- 长度：300-500字",
            "",
            "【Markdown 格式要求 - 必须遵守】",
            "请使用以下 Markdown 格式，确保渲染后美观易读：",
            "- 用 ## 标题分段（如：## 🌍 环境变迁、## 🧬 物种动态、## ⚡ 关键事件）",
            "- 用 **粗体** 强调关键数据和物种名称",
            "- 用 *斜体* 表示拉丁学名",
            "- 用 `代码格式` 标注物种代码（如 `A1`, `B2a`）",
            "- 用 > 引用块 突出显示重大事件或转折点",
            "- 可用列表 - 分点描述多个物种的状况",
            "- 用 --- 分隔大段落",
            "",
            f"═══════════════════════════════════════",
            f"【第 {turn_index} 回合】（每回合代表约50万年）",
            f"═══════════════════════════════════════",
            "",
        ]
        
        # === 环境压力 ===
        prompt_parts.append("【环境状况】")
        if pressures:
            for p in pressures:
                prompt_parts.append(f"- {p.narrative}")
        else:
            prompt_parts.append("- 环境相对稳定")
        prompt_parts.append("")
        
        # === 地质变化 ===
        if map_changes:
            prompt_parts.append("【地质变化】")
            for c in map_changes[:3]:
                desc = getattr(c, 'description', str(c))
                prompt_parts.append(f"- {desc}")
            prompt_parts.append("")
        
        # === 重大事件 ===
        events_added = False
        if branching_events:
            prompt_parts.append("【物种分化事件】")
            for b in branching_events[:3]:
                parent = getattr(b, 'parent_lineage', '?')
                child = getattr(b, 'new_lineage', '?')
                desc = getattr(b, 'description', '新物种诞生')
                prompt_parts.append(f"- {parent} → {child}: {desc}")
            prompt_parts.append("")
            events_added = True
        
        # 灭绝事件
        extinct_species = [s for s in species if s.status == "extinct"]
        if extinct_species:
            prompt_parts.append("【灭绝事件】")
            for s in extinct_species[:3]:
                prompt_parts.append(f"- {s.common_name}（{s.latin_name}）走向灭绝")
            prompt_parts.append("")
            events_added = True
        
        if major_events:
            prompt_parts.append("【环境重大事件】")
            for e in major_events[:2]:
                prompt_parts.append(f"- {getattr(e, 'description', str(e))}")
            prompt_parts.append("")
            events_added = True
        
        # === 生态概况 ===
        if stats:
            prompt_parts.append("【生态概况】")
            prompt_parts.append(f"- 物种总数: {stats.get('total', 0)}")
            prompt_parts.append(f"- 存活物种: {stats.get('alive', 0)}")
            if stats.get('extinct', 0) > 0:
                prompt_parts.append(f"- 本回合灭绝: {stats.get('extinct', 0)}")
            prompt_parts.append(f"- 总死亡个体: {stats.get('total_deaths', 0):,}")
            prompt_parts.append(f"- 平均死亡率: {stats.get('avg_death_rate', 0):.1%}")
            prompt_parts.append("")
        
        # === 值得关注的物种 ===
        if highlight_species:
            prompt_parts.append("【值得特别叙述的物种】")
            prompt_parts.append("（请在叙事中自然地提及这些物种的故事，不要简单罗列）")
            prompt_parts.append("")
            for h in highlight_species:
                prompt_parts.append(f"◆ {h.common_name}（{h.latin_name}）— {h.reason}")
                for fact in h.key_facts:
                    prompt_parts.append(f"  · {fact}")
                prompt_parts.append("")
        
        # === 其他存活物种简况 ===
        other_species = [s for s in species 
                        if s.status != "extinct" 
                        and s.lineage_code not in {h.lineage_code for h in highlight_species}]
        if other_species:
            prompt_parts.append("【其他物种简况】")
            for s in other_species[:5]:
                prompt_parts.append(f"- {s.common_name}: 数量{s.population:,}, 死亡率{s.death_rate:.1%}")
            prompt_parts.append("")
        
        # === 写作提示 ===
        prompt_parts.append("【写作提示】")
        
        # 根据事件类型给出不同的写作方向
        if extinct_species:
            prompt_parts.append("- 这是一个有物种灭绝的回合，可以带有一些哀伤和反思的基调")
        elif branching_events:
            prompt_parts.append("- 这是一个有新物种诞生的回合，可以突出生命的创造力和多样性")
        elif stats and stats.get('avg_death_rate', 0) > 0.3:
            prompt_parts.append("- 这是一个高压力的回合，可以描写物种的挣扎与适应")
        else:
            prompt_parts.append("- 这是一个相对平稳的回合，可以描写生态系统的日常运转")
        
        prompt_parts.append("- 记得将数据转化为画面感的描述")
        prompt_parts.append("- 让读者感受到演化的宏大和生命的脆弱")
        prompt_parts.append("")
        prompt_parts.append("请开始撰写：")
        
        return "\n".join(prompt_parts)

    # ──────────────────────────────────────────────────────────
    # 3. 统计数据
    # ──────────────────────────────────────────────────────────
    def _generate_stats(self, species: Sequence[SpeciesSnapshot], turn_index: int = 0) -> dict:
        """生成统计数据"""
        if not species:
            return {"total": 0, "avg_death_rate": 0, "total_deaths": 0, "turn_index": turn_index}
        
        total = len(species)
        alive = [s for s in species if s.status != "extinct"]
        extinct_count = total - len(alive)
        total_pop = sum(s.population for s in alive)
        total_deaths = sum(s.deaths for s in species)
        avg_death_rate = sum(s.death_rate for s in species) / max(1, total)
        
        return {
            "turn_index": turn_index,
            "total": total,
            "alive": len(alive),
            "extinct": extinct_count,
            "total_population": total_pop,
            "total_deaths": total_deaths,
            "avg_death_rate": avg_death_rate,
        }

    # ──────────────────────────────────────────────────────────
    # 4. 主入口
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
        species_details: dict[str, Any] | None = None,
        turn_index: int = 0,
    ) -> str:
        """生成 LLM 驱动的纪录片风格叙事
        
        Args:
            species: 物种快照列表
            pressures: 环境压力列表
            branching_events: 分化事件列表
            species_details: 物种详情字典
            turn_index: 当前回合数
        """
        
        # Step 1: 识别值得叙述的物种
        highlight_species = self._identify_highlight_species(
            species, branching_events, species_details
        )
        
        # Step 2: 生成统计数据
        stats = self._generate_stats(species, turn_index)
        
        # Step 3: 构建 prompt
        prompt = self._build_narrative_prompt(
            turn_index=turn_index,
            pressures=pressures,
            species=species,
            highlight_species=highlight_species,
            branching_events=branching_events,
            major_events=major_events,
            map_changes=map_changes,
            stats=stats,
        )
        
        # Step 4: 调用 LLM 生成叙事
        try:
            narrative = await asyncio.wait_for(
                self.router.chat(prompt, capability="turn_report"),
                timeout=60  # 60秒超时
            )
            narrative = narrative.strip() if isinstance(narrative, str) else str(narrative).strip()
            
            # 流式回调
            if stream_callback and narrative:
                chunk_size = 50
                for i in range(0, len(narrative), chunk_size):
                    chunk = narrative[i:i+chunk_size]
                    if asyncio.iscoroutinefunction(stream_callback):
                        await stream_callback(chunk)
                    else:
                        stream_callback(chunk)
                    await asyncio.sleep(0.01)
            
            logger.info(f"[ReportV2] LLM叙事生成成功: 回合{turn_index}, {len(highlight_species)}个重点物种, {len(narrative)}字")
            return narrative
            
        except asyncio.TimeoutError:
            logger.warning(f"[ReportV2] LLM生成超时，使用简化报告")
            return self._generate_fallback_report(stats, pressures, highlight_species)
        except Exception as e:
            logger.error(f"[ReportV2] LLM生成失败: {e}")
            return self._generate_fallback_report(stats, pressures, highlight_species)

    def _generate_fallback_report(
        self, 
        stats: dict, 
        pressures: Sequence[ParsedPressure],
        highlights: list[SpeciesHighlight]
    ) -> str:
        """LLM 失败时的降级报告"""
        lines = [f"# 第 {stats.get('turn_index', '?')} 回合", ""]
        
        # 环境
        if pressures:
            lines.append("## 环境")
            for p in pressures:
                lines.append(f"- {p.narrative}")
            lines.append("")
        
        # 概况
        lines.append("## 概况")
        lines.append(f"物种总数 {stats.get('total', 0)}，")
        lines.append(f"死亡 {stats.get('total_deaths', 0):,} 个体，")
        lines.append(f"平均死亡率 {stats.get('avg_death_rate', 0):.1%}。")
        lines.append("")
        
        # 重点物种
        if highlights:
            lines.append("## 值得关注")
            for h in highlights:
                lines.append(f"- **{h.common_name}**: {h.reason}")
        
        return "\n".join(lines)


# 工厂函数
def create_report_builder_v2(router, batch_size: int = 5) -> ReportBuilderV2:
    """创建 ReportBuilderV2 实例"""
    return ReportBuilderV2(router, batch_size)
