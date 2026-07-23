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
import inspect
import logging
from dataclasses import dataclass
from typing import Sequence, Callable, Awaitable, Any

from ...ai.streaming_helper import stream_call_with_heartbeat
from ...schemas.responses import SpeciesSnapshot
from ...simulation.environment import ParsedPressure
from ...simulation.constants import get_time_config

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
    
    def _get_narrative_style(self, stats: dict, branching_events: Sequence | None, extinct_count: int) -> dict:
        """根据回合特征选择叙事风格"""
        avg_death_rate = stats.get('avg_death_rate', 0)
        avg_net_change = stats.get('avg_net_change', 0)
        
        # 根据事件类型和数据特征选择风格
        if extinct_count > 0:
            return {
                "tone": "哀婉反思",
                "focus": "生命的脆弱与消逝",
                "opening_style": "以灭绝物种的最后时刻开场，或用宏观视角俯瞰生命的起落",
                "narrative_arc": "繁盛 → 危机 → 消亡 → 延续的希望",
                "suggested_techniques": ["倒叙（从结局开始）", "对比（曾经vs现在）", "象征（个体代表整个物种）"],
            }
        elif branching_events:
            return {
                "tone": "惊喜期待",
                "focus": "新生命的诞生与可能性",
                "opening_style": "从一个微小的变异开始，或描绘环境压力如何催生新物种",
                "narrative_arc": "压力 → 适应 → 突变 → 新物种诞生",
                "suggested_techniques": ["特写镜头（聚焦个体）", "时间跨度（从基因到种群）", "因果链（环境→适应→分化）"],
            }
        elif avg_death_rate > 0.4:
            return {
                "tone": "紧张悬疑",
                "focus": "生存竞争与适者生存",
                "opening_style": "以一场生死攸关的场景开场，展现自然选择的残酷",
                "narrative_arc": "危机降临 → 挣扎求存 → 优胜劣汰 → 格局重塑",
                "suggested_techniques": ["紧迫感（倒计时）", "多线叙事（不同物种的命运）", "戏剧冲突"],
            }
        elif avg_net_change > 0.1:
            return {
                "tone": "乐观蓬勃",
                "focus": "生态繁荣与生命力",
                "opening_style": "描绘一幅生机盎然的画面，展现生态系统的活力",
                "narrative_arc": "稳定 → 繁衍 → 扩张 → 多样化",
                "suggested_techniques": ["全景式描写", "生动细节", "节奏明快"],
            }
        elif avg_net_change < -0.1:
            return {
                "tone": "忧虑警示",
                "focus": "衰退的迹象与潜在危机",
                "opening_style": "从细微的变化开始，暗示更大的危机",
                "narrative_arc": "表面平静 → 暗流涌动 → 危机显现 → 未来悬念",
                "suggested_techniques": ["伏笔", "隐喻", "留白"],
            }
        else:
            return {
                "tone": "平和从容",
                "focus": "生态平衡与日常运转",
                "opening_style": "像打开一扇窗户，展现生态系统的日常",
                "narrative_arc": "日升 → 觅食 → 竞争 → 日落",
                "suggested_techniques": ["白描", "平行叙事", "细节刻画"],
            }
    
    def _get_trophic_description(self, trophic_level: float) -> str:
        """获取营养级的生动描述"""
        if trophic_level < 1.5:
            return "🌱 生产者（光合作用的基石）"
        elif trophic_level < 2.5:
            return "🐛 初级消费者（食草动物）"
        elif trophic_level < 3.5:
            return "🦎 次级消费者（小型捕食者）"
        elif trophic_level < 4.5:
            return "🦁 高级消费者（顶级掠食者）"
        else:
            return "🦅 超级掠食者（生态系统的王者）"
    
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
        """构建让 LLM 生成叙事的 prompt - 清晰结构化版本"""
        
        stats = stats or {}
        extinct_species = [s for s in species if s.status == "extinct"]
        alive_species = [s for s in species if s.status != "extinct"]
        
        # 获取叙事风格建议
        style = self._get_narrative_style(stats, branching_events, len(extinct_species))
        
        prompt_parts: list[str] = []
        
        # ╔══════════════════════════════════════════════════════════════╗
        # ║                        系统角色设定                           ║
        # ╚══════════════════════════════════════════════════════════════╝
        prompt_parts.append("""<role>
你是一位资深自然纪录片旁白撰稿人，擅长将枯燥的科学数据转化为扣人心弦的演化故事。
你的作品风格融合了大卫·爱登堡的温情、《地球脉动》的壮阔、以及《演化》的深邃。
</role>""")
        
        # ╔══════════════════════════════════════════════════════════════╗
        # ║                        任务说明                              ║
        # ╚══════════════════════════════════════════════════════════════╝
        # 获取当前时代信息
        time_config = get_time_config(turn_index)
        years_per_turn = time_config["years_per_turn"]
        era_name = time_config["era_name"]
        current_year = time_config["current_year"]
        
        # 格式化时间跨度显示
        if years_per_turn >= 1_000_000:
            time_span_str = f"{years_per_turn // 1_000_000} 百万年"
        else:
            time_span_str = f"{years_per_turn // 10_000} 万年"
        
        # 格式化当前年份显示
        if current_year < 0:
            year_str = f"{abs(current_year) / 1_000_000:.1f} 亿年前" if abs(current_year) >= 100_000_000 else f"{abs(current_year) / 1_000_000:.1f} 百万年前"
        else:
            year_str = "现代"
        
        prompt_parts.append(f"""
<task>
请基于下方的【模拟数据】，撰写第 {turn_index} 回合的演化叙事报告。

⏱️ 时间背景：
- 当前时代：**{era_name}**
- 当前时间：约 {year_str}
- 本回合时间跨度：**{time_span_str}**

核心原则：
1. 数据忠实：所有数值已由张量计算引擎得出，请直接引用，不要推导或虚构新数据
2. 因果叙事：重点讲述「环境变化 → 物种适应 → 命运转折」的因果链
3. 画面感强：将抽象数据转化为可视化的场景描写
4. 重点突出：聚焦 1-3 个高光事件/物种，避免流水账
5. 时代感：叙事风格应符合当前地质时代的特点
</task>""")
        
        # ╔══════════════════════════════════════════════════════════════╗
        # ║                        叙事风格指导                           ║
        # ╚══════════════════════════════════════════════════════════════╝
        prompt_parts.append(f"""
<narrative_style>
本回合建议风格：「{style['tone']}」

叙事焦点：{style['focus']}
开场建议：{style['opening_style']}
叙事弧线：{style['narrative_arc']}
推荐技法：{', '.join(style['suggested_techniques'])}

注意：以上仅为建议，你可以根据数据特点自由发挥，但请保持风格的一致性。
</narrative_style>""")
        
        # ╔══════════════════════════════════════════════════════════════╗
        # ║                        输出格式要求                           ║
        # ╚══════════════════════════════════════════════════════════════╝
        prompt_parts.append("""
<format>
## 格式要求（必须遵守）

1. 使用 Markdown 格式
2. 用 `## 🌍 ` 等标题分段（建议 2-4 个段落）
3. 用 **粗体** 标注关键数据和物种名
4. 用 *斜体* 标注拉丁学名
5. 用 `代码格式` 标注物种谱系代码（如 `A1b`）
6. 重大事件可用 `>` 引用块突出
7. 长度控制在 **300-500 字**
8. 避免使用多级嵌套列表

## 标题风格参考（可自由组合）
- `## 🌍 环境变迁` / `## 🌋 大地的震颤` / `## ❄️ 寒流来袭`
- `## 🧬 新生命诞生` / `## 🌱 分化的契机` / `## 🔀 演化的岔路口`  
- `## 🐾 物种动态` / `## 🦎 适者生存` / `## ⚔️ 生存竞争`
- `## 💀 消逝与传承` / `## 🕯️ 最后的挽歌` / `## 📜 写入化石`
- `## ⚡ 关键时刻` / `## 🎯 命运的转折` / `## 🌟 高光瞬间`
</format>""")
        
        # ╔══════════════════════════════════════════════════════════════╗
        # ║                        模拟数据区                            ║
        # ╚══════════════════════════════════════════════════════════════╝
        prompt_parts.append(f"""
═══════════════════════════════════════════════════════════════════════
       【第 {turn_index} 回合 · {era_name} · {time_span_str}/回合】
═══════════════════════════════════════════════════════════════════════""")
        
        # --- 1. 环境状况 ---
        prompt_parts.append("""
<environment>
## 🌍 环境状况""")
        
        if pressures:
            for p in pressures:
                intensity_level = "🟢轻微" if p.intensity < 0.3 else "🟡中等" if p.intensity < 0.6 else "🔴强烈"
                prompt_parts.append(f"""
- **{p.kind}** [{intensity_level} | 强度 {p.intensity:.2f}]
  描述：{p.narrative}""")
        else:
            prompt_parts.append("""
- 环境相对稳定，无显著压力变化
  （这是一个难得的平静期，物种可以专注于繁衍和扩张）""")
        prompt_parts.append("</environment>")
        
        # --- 2. 地质变化 ---
        if map_changes:
            prompt_parts.append("""
<geological_changes>
## 🗺️ 地质变化""")
            for c in map_changes[:3]:
                desc = getattr(c, 'description', str(c))
                prompt_parts.append(f"- {desc}")
            prompt_parts.append("</geological_changes>")
        
        # --- 3. 生态概况 ---
        prompt_parts.append(f"""
<ecosystem_stats>
## 📊 生态系统概况

| 指标 | 数值 | 说明 |
|------|------|------|
| 物种总数 | {stats.get('total', 0)} 种 | 包含存活和灭绝 |
| 存活物种 | {stats.get('alive', 0)} 种 | 本回合末存活 |
| 本回合灭绝 | {stats.get('extinct', 0)} 种 | 本回合消亡 |
| 总生物量 | {stats.get('total_population', 0):,} 个体 | 所有存活物种总和 |
| 本回合出生 | +{stats.get('total_births', 0):,} | 新生个体数 |
| 本回合死亡 | -{stats.get('total_deaths', 0):,} | 死亡个体数 |
| 平均死亡率 | {stats.get('avg_death_rate', 0):.1%} | 死亡数/回合初种群 |
| 平均净变化率 | {stats.get('avg_net_change', 0):+.1%} | (期末-期初)/期初 |
</ecosystem_stats>""")
        
        # --- 4. 重大事件 ---
        events_section: list[str] = []
        
        if branching_events:
            events_section.append("""
### 🧬 物种分化事件（新物种诞生）""")
            for b in branching_events[:3]:
                parent = getattr(b, 'parent_lineage', '?')
                child = getattr(b, 'new_lineage', '?') or getattr(b, 'child_code', '?')
                child_name = getattr(b, 'child_name', '') or getattr(b, 'new_name', '')
                desc = getattr(b, 'description', '适应新的生态位')
                events_section.append(f"""
- `{parent}` **→** `{child}` {f'**{child_name}**' if child_name else ''}
  分化原因：{desc}""")
        
        if extinct_species:
            events_section.append("""
### 💀 灭绝事件""")
            for s in extinct_species[:3]:
                events_section.append(f"""
- **{s.common_name}** (*{s.latin_name}*) `{s.lineage_code}`
  曾拥有种群：{s.population + s.deaths:,} → 0
  灭绝原因：死亡率达到 {s.death_rate:.1%}，种群崩溃""")
        
        if major_events:
            events_section.append("""
### 🌋 环境重大事件""")
            for e in major_events[:3]:
                desc = getattr(e, 'description', str(e))
                events_section.append(f"- {desc}")
        
        if events_section:
            prompt_parts.append("""
<major_events>
## ⚡ 本回合重大事件
（这些是叙事的核心素材，请重点描写）""")
            prompt_parts.extend(events_section)
            prompt_parts.append("</major_events>")
        
        # --- 5. 重点物种档案 ---
        if highlight_species:
            prompt_parts.append("""
<highlight_species>
## 🌟 重点物种档案
（请在叙事中自然融入这些物种的故事，不要简单罗列）""")
            
            for h in highlight_species:
                # 查找对应的 species snapshot 获取更多数据
                snap = next((s for s in species if s.lineage_code == h.lineage_code), None)
                trophic_desc = self._get_trophic_description(snap.trophic_level) if snap and snap.trophic_level else "未知"
                
                prompt_parts.append(f"""
### ◆ {h.common_name} (*{h.latin_name}*) `{h.lineage_code}`
- **叙事价值**：{h.reason}
- **生态位**：{trophic_desc}""")
                if snap:
                    prompt_parts.append(f"- **种群规模**：{snap.population:,} 个体（占比 {snap.population_share:.1%}）")
                    prompt_parts.append(f"- **本回合表现**：死亡率 {snap.death_rate:.1%}，净变化 {getattr(snap, 'net_change_rate', 0):+.1%}")
                prompt_parts.append("- **关键数据点**：")
                for fact in h.key_facts:
                    prompt_parts.append(f"  - {fact}")
            
            prompt_parts.append("</highlight_species>")
        
        # --- 6. 其他物种简报 ---
        other_species = [s for s in alive_species 
                        if s.lineage_code not in {h.lineage_code for h in highlight_species}]
        if other_species:
            prompt_parts.append("""
<other_species>
## 📋 其他存活物种简报""")
            
            # 按死亡率排序，展示状态差异
            sorted_species = sorted(other_species, key=lambda x: x.death_rate)
            
            prompt_parts.append("""
| 物种 | 谱系码 | 种群 | 死亡率 | 状态 |
|------|--------|------|--------|------|""")
            
            for s in sorted_species[:8]:
                status = "🟢稳定" if s.death_rate < 0.15 else "🟡承压" if s.death_rate < 0.35 else "🔴危机"
                prompt_parts.append(f"| {s.common_name} | `{s.lineage_code}` | {s.population:,} | {s.death_rate:.1%} | {status} |")
            
            if len(other_species) > 8:
                prompt_parts.append(f"\n*（另有 {len(other_species) - 8} 个物种未列出）*")
            
            prompt_parts.append("</other_species>")
        
        # --- 7. 生态网络 ---
        # 构建简单的营养级分布
        trophic_distribution: dict[str, list[str]] = {
            "生产者": [],
            "初级消费者": [],
            "次级消费者": [],
            "高级消费者": [],
            "顶级掠食者": [],
        }
        
        for s in alive_species:
            tl = s.trophic_level or 1.0
            if tl < 1.5:
                trophic_distribution["生产者"].append(s.common_name)
            elif tl < 2.5:
                trophic_distribution["初级消费者"].append(s.common_name)
            elif tl < 3.5:
                trophic_distribution["次级消费者"].append(s.common_name)
            elif tl < 4.5:
                trophic_distribution["高级消费者"].append(s.common_name)
            else:
                trophic_distribution["顶级掠食者"].append(s.common_name)
        
        prompt_parts.append("""
<food_web>
## 🔗 生态网络结构（营养级金字塔）

```
       🦅 顶级掠食者""")
        prompt_parts.append(f"          [{', '.join(trophic_distribution['顶级掠食者'][:2]) or '空缺'}]")
        prompt_parts.append(f"       🦁 高级消费者")
        prompt_parts.append(f"          [{', '.join(trophic_distribution['高级消费者'][:3]) or '空缺'}]")
        prompt_parts.append(f"       🦎 次级消费者")
        prompt_parts.append(f"          [{', '.join(trophic_distribution['次级消费者'][:3]) or '空缺'}]")
        prompt_parts.append(f"       🐛 初级消费者")
        prompt_parts.append(f"          [{', '.join(trophic_distribution['初级消费者'][:3]) or '空缺'}]")
        prompt_parts.append(f"       🌱 生产者")
        prompt_parts.append(f"          [{', '.join(trophic_distribution['生产者'][:3]) or '空缺'}]")
        prompt_parts.append("```")
        prompt_parts.append("</food_web>")
        
        # ╔══════════════════════════════════════════════════════════════╗
        # ║                        写作指导                              ║
        # ╚══════════════════════════════════════════════════════════════╝
        prompt_parts.append("""
═══════════════════════════════════════════════════════════════════════
                           【写作指导】
═══════════════════════════════════════════════════════════════════════

<writing_tips>
## 本回合叙事要点""")
        
        # 根据数据特征给出具体建议
        tips: list[str] = []
        
        if extinct_species:
            tips.append(f"💀 有 {len(extinct_species)} 个物种灭绝 → 可以用追忆的笔触，讲述它们的最后时刻")
        
        if branching_events:
            tips.append(f"🧬 有 {len(branching_events)} 次物种分化 → 重点描写分化的「瞬间」，环境压力如何催生新物种")
        
        if stats.get('avg_death_rate', 0) > 0.35:
            tips.append(f"⚠️ 平均死亡率 {stats.get('avg_death_rate', 0):.1%} 较高 → 可以渲染生存竞争的残酷")
        elif stats.get('avg_death_rate', 0) < 0.1:
            tips.append(f"🌿 平均死亡率 {stats.get('avg_death_rate', 0):.1%} 较低 → 可以描绘生态系统的和谐")
        
        if stats.get('avg_net_change', 0) > 0.15:
            tips.append(f"📈 种群净增长 {stats.get('avg_net_change', 0):+.1%} → 生机勃勃的扩张期")
        elif stats.get('avg_net_change', 0) < -0.15:
            tips.append(f"📉 种群净下降 {stats.get('avg_net_change', 0):+.1%} → 衰退期，暗示危机")
        
        if pressures:
            tips.append(f"🌍 存在 {len(pressures)} 个环境压力 → 作为叙事的背景和驱动力")
        
        if highlight_species:
            names = [h.common_name for h in highlight_species[:3]]
            tips.append(f"🌟 重点物种：{', '.join(names)} → 以它们的视角串联叙事")
        
        if not tips:
            tips.append("📝 这是一个相对平静的回合，可以用白描手法展现生态系统的日常")
        
        for tip in tips:
            prompt_parts.append(f"- {tip}")
        
        prompt_parts.append("""
## 写作技巧提醒
- 开头要有「钩子」，吸引读者继续阅读
- 中间用具体数据支撑叙事，但要转化为画面
- 结尾可以留下悬念或哲理性的感悟
- 记住：你不是在写数据报告，而是在讲述生命的史诗
</writing_tips>

═══════════════════════════════════════════════════════════════════════

请开始撰写第 """ + str(turn_index) + f""" 回合（{era_name}，{time_span_str}/回合）的演化叙事报告：""")
        
        return "\n".join(prompt_parts)

    # ──────────────────────────────────────────────────────────
    # 3. 统计数据
    # ──────────────────────────────────────────────────────────
    def _generate_stats(self, species: Sequence[SpeciesSnapshot], turn_index: int = 0) -> dict:
        """生成统计数据"""
        if not species:
            return {
                "total": 0,
                "avg_death_rate": 0,
                "avg_net_change": 0,
                "total_deaths": 0,
                "total_births": 0,
                "turn_index": turn_index,
            }
        
        total = len(species)
        alive = [s for s in species if s.status != "extinct"]
        extinct_count = total - len(alive)
        total_pop = sum(s.population for s in alive)
        total_deaths = sum(s.deaths for s in species)
        total_births = sum(getattr(s, "births", 0) or 0 for s in species)
        avg_death_rate = sum(s.death_rate for s in species) / max(1, total)
        avg_net_change = sum(getattr(s, "net_change_rate", 0) or 0 for s in species) / max(1, total)
        
        return {
            "turn_index": turn_index,
            "total": total,
            "alive": len(alive),
            "extinct": extinct_count,
            "total_population": total_pop,
            "total_deaths": total_deaths,
            "avg_death_rate": avg_death_rate,
            "avg_net_change": avg_net_change,
            "total_births": total_births,
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
        heartbeat_callback: Callable[[int], Awaitable[None] | None] | None = None,
        event_callback: Callable[[str, str, str], None] | None = None,
    ) -> str:
        """生成 LLM 驱动的纪录片风格叙事
        
        Args:
            species: 物种快照列表
            pressures: 环境压力列表
            branching_events: 分化事件列表
            species_details: 物种详情字典
            turn_index: 当前回合数
            heartbeat_callback: 心跳回调，参数为已接收的chunk数量
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
        
        # Step 4: 调用 LLM 生成叙事 - 使用流式传输+心跳监测
        try:
            narrative = await self._stream_narrative_with_heartbeat(
                prompt=prompt,
                turn_index=turn_index,
                stream_callback=stream_callback,
                heartbeat_callback=heartbeat_callback,
                event_callback=event_callback,
            )
            
            if narrative and len(narrative) > 50:
                logger.info(f"[ReportV2] LLM叙事生成成功: 回合{turn_index}, {len(highlight_species)}个重点物种, {len(narrative)}字")
                return narrative
            else:
                logger.warning(f"[ReportV2] 流式生成返回空，使用简化报告")
                return self._generate_fallback_report(stats, pressures, highlight_species)
            
        except asyncio.TimeoutError:
            logger.warning(f"[ReportV2] LLM生成超时，使用简化报告")
            return self._generate_fallback_report(stats, pressures, highlight_species)
        except Exception as exc:
            logger.error(
                "[ReportV2] LLM生成失败 type=%s",
                type(exc).__name__,
            )
            return self._generate_fallback_report(stats, pressures, highlight_species)

    async def _stream_narrative_with_heartbeat(
        self,
        prompt: str,
        turn_index: int,
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
        heartbeat_callback: Callable[[int], Awaitable[None] | None] | None = None,
        event_callback: Callable[[str, str, str], None] | None = None,
    ) -> str:
        """使用流式传输生成叙事，支持心跳监测
        
        与分化逻辑一致：监测AI是否持续输出，而不是简单超时
        """
        messages = [{"role": "user", "content": prompt}]
        chunk_count = 0

        async def handle_chunk(chunk: str) -> None:
            nonlocal chunk_count
            chunk_count += 1

            if heartbeat_callback and chunk_count % 5 == 0:
                try:
                    result = heartbeat_callback(chunk_count)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    logger.debug(
                        "[ReportV2] 心跳回调异常 type=%s",
                        type(exc).__name__,
                    )

            if stream_callback:
                try:
                    result = stream_callback(chunk)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    logger.debug(
                        "[ReportV2] 流式回调异常 type=%s",
                        type(exc).__name__,
                    )

        outcome = await stream_call_with_heartbeat(
            router=self.router,
            capability="turn_report",
            messages=messages,
            task_name=f"第{turn_index}回合报告",
            event_callback=event_callback,
            chunk_callback=handle_chunk,
        )
        if not outcome.completed:
            logger.warning(
                "[ReportV2] 流式生成未完整结束 (%s)，使用简化报告",
                outcome.reason,
            )
            return ""

        narrative = outcome.content.strip()
        logger.info(
            "[ReportV2] 叙事接收完成: %s chunks, %s字",
            chunk_count,
            len(narrative),
        )
        return narrative

    def _generate_fallback_report(
        self, 
        stats: dict, 
        pressures: Sequence[ParsedPressure],
        highlights: list[SpeciesHighlight]
    ) -> str:
        """LLM 失败时的降级报告 - 提供丰富的 Markdown 格式报告"""
        turn_index = stats.get('turn_index', 0)
        lines: list[str] = []
        
        # 获取当前时代信息
        time_config = get_time_config(turn_index if isinstance(turn_index, int) else 0)
        years_per_turn = time_config["years_per_turn"]
        era_name = time_config["era_name"]
        current_year = time_config["current_year"]
        
        # 格式化时间跨度显示
        if years_per_turn >= 1_000_000:
            time_span_str = f"{years_per_turn // 1_000_000} 百万年"
        else:
            time_span_str = f"{years_per_turn // 10_000} 万年"
        
        # 格式化当前年份显示
        if current_year < 0:
            if abs(current_year) >= 100_000_000:
                year_str = f"{abs(current_year) / 100_000_000:.1f} 亿年前"
            else:
                year_str = f"{abs(current_year) / 1_000_000:.1f} 百万年前"
        else:
            year_str = "现代"
        
        # ═══ 标题 ═══
        lines.append(f"## 🕐 第 {turn_index} 回合")
        lines.append(f"**{era_name}** · {year_str} · {time_span_str}/回合")
        lines.append("")
        
        # ═══ 环境状况 ═══
        lines.append("### 🌍 环境变迁")
        if pressures:
            for p in pressures:
                if p.narrative:
                    lines.append(f"- {p.narrative}")
                else:
                    intensity_desc = "轻微" if p.intensity < 0.3 else "中等" if p.intensity < 0.6 else "强烈"
                    lines.append(f"- **{p.kind}** 压力 ({intensity_desc}，强度 {p.intensity:.1f})")
        else:
            lines.append("- 环境相对稳定，无显著压力变化")
        lines.append("")
        
        # ═══ 生态概况 ═══
        lines.append("### 📊 生态概况")
        
        total = stats.get('total', 0)
        alive = stats.get('alive', 0)
        extinct = stats.get('extinct', 0)
        total_pop = stats.get('total_population', 0)
        total_deaths = stats.get('total_deaths', 0)
        total_births = stats.get('total_births', 0)
        avg_death_rate = stats.get('avg_death_rate', 0)
        avg_net_change = stats.get('avg_net_change', 0)
        
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 存活物种 | **{alive}** 种 |")
        lines.append(f"| 总生物量 | **{total_pop:,}** 个体 |")
        
        if total_births > 0 or total_deaths > 0:
            net_change = total_births - total_deaths
            change_icon = "📈" if net_change > 0 else "📉" if net_change < 0 else "➡️"
            lines.append(f"| 本回合出生 | +{total_births:,} |")
            lines.append(f"| 本回合死亡 | -{total_deaths:,} |")
            lines.append(f"| 净变化 | {change_icon} {net_change:+,} |")
        
        # 死亡率评估
        rate_desc = "稳定" if avg_death_rate < 0.15 else "略高" if avg_death_rate < 0.3 else "较高" if avg_death_rate < 0.5 else "危机"
        lines.append(f"| 平均死亡率 | {avg_death_rate:.1%} ({rate_desc}) |")
        
        # 净变化率
        if avg_net_change != 0:
            change_desc = "增长" if avg_net_change > 0 else "收缩"
            lines.append(f"| 平均净变化率 | {avg_net_change:+.1%} ({change_desc}) |")
        
        if extinct > 0:
            lines.append(f"| ⚠️ 本回合灭绝 | {extinct} 种 |")
        
        lines.append("")
        
        # ═══ 值得关注的物种 ═══
        if highlights:
            lines.append("### 🐾 物种动态")
            lines.append("")
            
            for h in highlights:
                # 根据原因选择图标
                icon = "🧬" if "新物种" in h.reason or "分化" in h.reason else \
                       "🌟" if "适应" in h.reason else \
                       "👑" if "主导" in h.reason else \
                       "⚠️" if "危机" in h.reason or "挣扎" in h.reason else \
                       "🔬" if "器官" in h.reason else "📌"
                
                lines.append(f"**{icon} {h.common_name}** (*{h.latin_name}*) `{h.lineage_code}`")
                lines.append(f"> {h.reason}")
                for fact in h.key_facts:
                    lines.append(f"> - {fact}")
                lines.append("")
        
        # ═══ 小结 ═══
        lines.append("---")
        
        # 根据统计数据生成小结
        if extinct > 0:
            lines.append(f"*本回合 {extinct} 个物种消逝于自然选择的无情筛选中。生命脆弱，适者生存。*")
        elif avg_death_rate > 0.4:
            lines.append("*高压环境下，物种面临严峻考验。只有最适应的个体才能延续血脉。*")
        elif avg_net_change > 0.1:
            lines.append("*生态系统欣欣向荣，物种繁衍旺盛，生命之树茁壮成长。*")
        elif avg_net_change < -0.1:
            lines.append("*生态系统承受压力，种群数量有所下降，但生命仍在坚持。*")
        else:
            lines.append("*生态系统保持动态平衡，物种在竞争与共存中延续演化之路。*")
        
        return "\n".join(lines)


# 工厂函数
def create_report_builder_v2(router, batch_size: int = 5) -> ReportBuilderV2:
    """创建 ReportBuilderV2 实例"""
    return ReportBuilderV2(router, batch_size)
