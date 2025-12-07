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

from ...schemas.responses import SpeciesSnapshot, EcologicalRealismSnapshot, EcologicalRealismSummary
from ...core.config import get_settings
from ...simulation.constants import get_time_config

logger = logging.getLogger(__name__)


class TurnReportService:
    """回合报告服务
    
    负责构建每回合的详细报告。
    
    【增强版】提供更丰富的物种分析：
    - 继承特性分析（新物种从祖先继承了什么）
    - 霸主潜力预测（谁可能成为时代霸主）
    - 生态位竞争分析（谁在挤占谁的生态位）
    - 演化趋势与预测
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
    
    # ═══════════════════════════════════════════════════════════════
    # 【新增】深度物种分析方法
    # ═══════════════════════════════════════════════════════════════
    
    def _analyze_inherited_traits(
        self,
        child_species: Dict,
        parent_species: Dict | None,
        branching_event: Any | None,
    ) -> Dict[str, Any]:
        """分析新物种从祖先继承的特性
        
        返回继承分析结果，包括：
        - 继承的关键特征
        - 新发展的独特优势
        - 演化意义
        """
        result = {
            "inherited_traits": [],      # 继承的特征
            "new_adaptations": [],       # 新适应性
            "evolutionary_significance": "",  # 演化意义
            "parent_comparison": {},     # 与父代的对比
        }
        
        if not parent_species:
            return result
        
        # 比较抽象特征
        child_traits = child_species.get("abstract_traits", {})
        parent_traits = parent_species.get("abstract_traits", {})
        
        for trait, value in child_traits.items():
            parent_value = parent_traits.get(trait, 0)
            diff = value - parent_value
            
            if abs(diff) < 0.1:
                # 基本继承
                if value > 0.5:
                    result["inherited_traits"].append(f"保留了{trait}能力 ({value:.1f})")
            elif diff > 0.2:
                # 显著增强
                result["new_adaptations"].append(f"{trait}能力显著增强 ({parent_value:.1f}→{value:.1f})")
            elif diff < -0.2:
                # 特化退化
                result["parent_comparison"][trait] = {
                    "parent": parent_value,
                    "child": value,
                    "change": "退化",
                }
        
        # 比较器官
        child_organs = child_species.get("organs", {})
        parent_organs = parent_species.get("organs", {})
        
        new_organs = set(child_organs.keys()) - set(parent_organs.keys())
        for organ in new_organs:
            organ_info = child_organs.get(organ, {})
            organ_type = organ_info.get("type", organ)
            result["new_adaptations"].append(f"发展出新器官: {organ_type}")
        
        # 比较能力
        child_caps = set(child_species.get("capabilities", []))
        parent_caps = set(parent_species.get("capabilities", []))
        new_caps = child_caps - parent_caps
        for cap in list(new_caps)[:3]:
            result["new_adaptations"].append(f"获得新能力: {cap}")
        
        # 生成演化意义描述
        if result["new_adaptations"]:
            if any("器官" in a for a in result["new_adaptations"]):
                result["evolutionary_significance"] = "器官演化显著，可能开启新的生态位"
            elif any("增强" in a for a in result["new_adaptations"]):
                result["evolutionary_significance"] = "适应能力增强，竞争优势提升"
            else:
                result["evolutionary_significance"] = "特性多样化，生态位分化明显"
        
        return result
    
    def _analyze_dominance_potential(
        self,
        species_data: List[Dict],
        alive_species: List[Dict],
    ) -> List[Dict[str, Any]]:
        """分析霸主潜力和趋势预测
        
        返回潜在霸主列表，包含：
        - 物种信息
        - 霸主潜力分数
        - 支撑理由
        - 威胁因素
        """
        potentials = []
        
        for sp in alive_species:
            score = 0.0
            reasons = []
            threats = []
            
            pop = sp.get("population", 0)
            share = sp.get("population_share", 0)
            death_rate = sp.get("death_rate", 0)
            births = sp.get("births", 0)
            initial_pop = sp.get("initial_population", 0)
            net_change_rate = sp.get("net_change_rate", 0)
            trophic = sp.get("trophic_level", 1.0)
            
            # 1. 种群占比评分 (最高30分)
            if share > 0.3:
                score += 30
                reasons.append(f"种群占比高达 {share:.1%}")
            elif share > 0.15:
                score += 20
                reasons.append(f"种群占比可观 ({share:.1%})")
            elif share > 0.08:
                score += 10
            
            # 2. 死亡率评分 (最高25分)
            if death_rate < 0.05:
                score += 25
                reasons.append("适应能力极强（死亡率极低）")
            elif death_rate < 0.15:
                score += 15
                reasons.append("环境适应良好")
            elif death_rate > 0.4:
                threats.append(f"死亡率偏高 ({death_rate:.1%})")
                score -= 10
            
            # 3. 增长趋势评分 (最高25分)
            if net_change_rate > 0.2:
                score += 25
                reasons.append(f"种群快速扩张 ({net_change_rate:+.1%})")
            elif net_change_rate > 0.1:
                score += 15
                reasons.append("种群稳定增长")
            elif net_change_rate < -0.1:
                threats.append("种群正在萎缩")
                score -= 10
            
            # 4. 营养级优势 (最高20分)
            if trophic >= 3.5:
                score += 20
                reasons.append("处于食物链顶端")
            elif trophic >= 2.5:
                score += 10
            elif trophic < 1.5:
                # 生产者有不同的优势
                if share > 0.2:
                    score += 15
                    reasons.append("作为生产者主导生态基础")
            
            # 5. 繁殖优势 (额外加分)
            if births > 0 and initial_pop > 0:
                birth_rate = births / initial_pop
                if birth_rate > 0.3:
                    score += 10
                    reasons.append("繁殖能力旺盛")
            
            # 过滤低分物种
            if score >= 30:
                potentials.append({
                    "lineage_code": sp.get("lineage_code"),
                    "common_name": sp.get("common_name"),
                    "latin_name": sp.get("latin_name"),
                    "score": score,
                    "reasons": reasons,
                    "threats": threats,
                    "population": pop,
                    "share": share,
                    "trophic_level": trophic,
                })
        
        # 按分数排序
        potentials.sort(key=lambda x: -x["score"])
        return potentials[:5]  # 返回前5个
    
    def _analyze_niche_competition(
        self,
        species_data: List[Dict],
        alive_species: List[Dict],
    ) -> Dict[str, Any]:
        """分析生态位竞争关系
        
        返回竞争格局分析：
        - 同生态位竞争者
        - 被挤占风险
        - 竞争热点
        """
        # 按营养级分组
        trophic_groups: Dict[str, List[Dict]] = {
            "生产者": [],
            "初级消费者": [],
            "次级消费者": [],
            "高级消费者": [],
            "顶级掠食者": [],
        }
        
        for sp in alive_species:
            role = sp.get("ecological_role", "未知")
            if role in trophic_groups:
                trophic_groups[role].append(sp)
        
        competition_analysis = {
            "crowded_niches": [],     # 拥挤的生态位
            "displacement_risks": [], # 被挤占风险
            "competition_hotspots": [],  # 竞争热点
            "niche_summary": {},      # 各生态位概况
        }
        
        # 分析各生态位
        for role, members in trophic_groups.items():
            if len(members) < 2:
                continue
            
            total_pop = sum(m.get("population", 0) for m in members)
            
            competition_analysis["niche_summary"][role] = {
                "species_count": len(members),
                "total_population": total_pop,
                "members": [m.get("common_name") for m in members],
            }
            
            # 拥挤的生态位
            if len(members) >= 3:
                competition_analysis["crowded_niches"].append({
                    "niche": role,
                    "count": len(members),
                    "species": [m.get("common_name") for m in members],
                })
            
            # 分析被挤占风险
            # 排序：种群最大的可能挤占其他物种
            sorted_members = sorted(members, key=lambda x: -x.get("population", 0))
            
            if len(sorted_members) >= 2:
                dominant = sorted_members[0]
                
                for weak in sorted_members[1:]:
                    weak_pop = weak.get("population", 0)
                    dominant_pop = dominant.get("population", 0)
                    weak_death = weak.get("death_rate", 0)
                    
                    # 判断挤占风险
                    if dominant_pop > 0 and weak_pop > 0:
                        ratio = weak_pop / dominant_pop
                        if ratio < 0.2 and weak_death > 0.25:
                            competition_analysis["displacement_risks"].append({
                                "victim": weak.get("common_name"),
                                "victim_code": weak.get("lineage_code"),
                                "aggressor": dominant.get("common_name"),
                                "aggressor_code": dominant.get("lineage_code"),
                                "niche": role,
                                "severity": "高" if weak_death > 0.4 else "中",
                                "description": f"{weak.get('common_name')} 被 {dominant.get('common_name')} 挤占了{role}生态位",
                            })
        
        # 识别竞争热点
        high_death_species = [sp for sp in alive_species if sp.get("death_rate", 0) > 0.3]
        for sp in high_death_species:
            resource_pressure = sp.get("resource_pressure", 0)
            niche_overlap = sp.get("niche_overlap", 0)
            
            if resource_pressure and resource_pressure > 0.3:
                competition_analysis["competition_hotspots"].append({
                    "species": sp.get("common_name"),
                    "lineage_code": sp.get("lineage_code"),
                    "type": "资源竞争",
                    "pressure": resource_pressure,
                })
            elif niche_overlap and niche_overlap > 0.5:
                competition_analysis["competition_hotspots"].append({
                    "species": sp.get("common_name"),
                    "lineage_code": sp.get("lineage_code"),
                    "type": "生态位重叠",
                    "overlap": niche_overlap,
                })
        
        return competition_analysis
    
    def _analyze_evolution_trends(
        self,
        species_data: List[Dict],
        alive_species: List[Dict],
        branching_events: List[Any] | None,
        pressures: List[Any],
    ) -> Dict[str, Any]:
        """分析演化趋势和预测
        
        返回演化分析：
        - 演化方向
        - 适应趋势
        - 下一步预测
        """
        trends = {
            "dominant_direction": "",   # 主导演化方向
            "adaptation_trends": [],    # 适应趋势
            "speciation_outlook": "",   # 分化前景
            "extinction_warnings": [],  # 灭绝预警
            "emerging_strategies": [],  # 新兴生存策略
        }
        
        # 1. 分析环境压力驱动的演化方向
        if pressures:
            pressure_types = []
            for p in pressures:
                kind = getattr(p, 'kind', str(p))
                intensity = getattr(p, 'intensity', 0.5)
                if intensity > 0.3:
                    pressure_types.append(kind)
            
            if pressure_types:
                if any("温度" in p or "cold" in p.lower() or "heat" in p.lower() for p in pressure_types):
                    trends["adaptation_trends"].append("温度适应演化加速")
                if any("干旱" in p or "drought" in p.lower() for p in pressure_types):
                    trends["adaptation_trends"].append("耐旱特性正在被选择")
                if any("竞争" in p or "competition" in p.lower() for p in pressure_types):
                    trends["adaptation_trends"].append("竞争能力成为关键")
                if any("捕食" in p or "predation" in p.lower() for p in pressure_types):
                    trends["adaptation_trends"].append("防御/逃避机制强化")
        
        # 2. 分析分化事件的演化意义
        if branching_events:
            trends["speciation_outlook"] = f"本回合发生 {len(branching_events)} 次物种分化，生命多样性持续扩展"
            
            # 分析分化类型
            for b in branching_events[:3]:
                desc = getattr(b, 'description', '')
                if "适应" in desc:
                    trends["emerging_strategies"].append("适应性分化")
                elif "隔离" in desc:
                    trends["emerging_strategies"].append("地理隔离分化")
                elif "生态位" in desc:
                    trends["emerging_strategies"].append("生态位分化")
        
        # 3. 灭绝预警
        for sp in alive_species:
            death_rate = sp.get("death_rate", 0)
            pop = sp.get("population", 0)
            net_change = sp.get("net_change_rate", 0)
            
            warning_level = None
            reasons = []
            
            if death_rate > 0.5:
                warning_level = "critical"
                reasons.append(f"死亡率极高 ({death_rate:.1%})")
            elif death_rate > 0.35 and net_change < -0.2:
                warning_level = "high"
                reasons.append("死亡率高且种群萎缩")
            elif pop < 100 and death_rate > 0.2:
                warning_level = "high"
                reasons.append("种群过小且死亡率偏高")
            
            # 检查生态拟真数据
            eco_realism = sp.get("ecological_realism")
            if eco_realism:
                if eco_realism.is_below_mvp:
                    warning_level = warning_level or "high"
                    reasons.append("低于最小可存活种群")
                if eco_realism.disease_pressure > 0.3:
                    reasons.append(f"疾病压力较高 ({eco_realism.disease_pressure:.1%})")
            
            if warning_level:
                trends["extinction_warnings"].append({
                    "species": sp.get("common_name"),
                    "lineage_code": sp.get("lineage_code"),
                    "level": warning_level,
                    "reasons": reasons,
                    "population": pop,
                })
        
        # 4. 确定主导演化方向
        if trends["extinction_warnings"]:
            trends["dominant_direction"] = "自然选择加剧，适应性演化是关键"
        elif branching_events:
            trends["dominant_direction"] = "多样化扩张，生态位分化活跃"
        elif trends["adaptation_trends"]:
            trends["dominant_direction"] = "环境驱动的适应演化"
        else:
            trends["dominant_direction"] = "稳定期，微调优化"
        
        return trends
    
    def _build_ecological_realism_snapshot(
        self,
        lineage_code: str,
        ecological_realism_data: Dict[str, Any] | None,
    ) -> EcologicalRealismSnapshot | None:
        """构建物种的生态拟真快照"""
        if not ecological_realism_data:
            return None
        
        allee_results = ecological_realism_data.get("allee_results", {})
        disease_results = ecological_realism_data.get("disease_results", {})
        env_modifiers = ecological_realism_data.get("env_modifiers", {})
        assimilation = ecological_realism_data.get("assimilation_efficiencies", {})
        adaptation = ecological_realism_data.get("adaptation_penalties", {})
        mutualism_benefits = ecological_realism_data.get("mutualism_benefits", {})
        mutualism_links = ecological_realism_data.get("mutualism_links", [])
        
        # 获取该物种的数据
        allee = allee_results.get(lineage_code, {})
        disease = disease_results.get(lineage_code, {})
        
        # 获取共生伙伴
        partners = []
        for link in mutualism_links:
            if link.get("species_a") == lineage_code:
                partners.append(link.get("species_b", ""))
            elif link.get("species_b") == lineage_code:
                partners.append(link.get("species_a", ""))
        
        return EcologicalRealismSnapshot(
            is_below_mvp=allee.get("is_below_mvp", False),
            allee_reproduction_modifier=allee.get("reproduction_modifier", 1.0),
            disease_pressure=disease.get("disease_pressure", 0.0),
            disease_mortality_modifier=disease.get("mortality_modifier", 0.0),
            env_fluctuation_modifier=env_modifiers.get(lineage_code, 1.0),
            assimilation_efficiency=assimilation.get(lineage_code, 0.10),
            adaptation_penalty=adaptation.get(lineage_code, 0.0),
            mutualism_benefit=mutualism_benefits.get(lineage_code, 0.0),
            mutualism_partners=partners,
        )
    
    def _build_ecological_realism_summary(
        self,
        species_data: List[Dict],
        ecological_realism_data: Dict[str, Any] | None,
    ) -> EcologicalRealismSummary | None:
        """构建生态拟真系统整体统计"""
        if not ecological_realism_data:
            return None
        
        allee_results = ecological_realism_data.get("allee_results", {})
        disease_results = ecological_realism_data.get("disease_results", {})
        env_modifiers = ecological_realism_data.get("env_modifiers", {})
        adaptation = ecological_realism_data.get("adaptation_penalties", {})
        mutualism_links = ecological_realism_data.get("mutualism_links", [])
        mutualism_benefits = ecological_realism_data.get("mutualism_benefits", {})
        
        # 统计受影响的物种
        allee_affected = [code for code, data in allee_results.items() if data.get("is_below_mvp", False)]
        disease_affected = [code for code, data in disease_results.items() if data.get("disease_pressure", 0) > 0.1]
        adaptation_stressed = [code for code, pen in adaptation.items() if pen > 0.05]
        
        # 计算平均值
        disease_pressures = [d.get("disease_pressure", 0) for d in disease_results.values()]
        avg_disease = sum(disease_pressures) / len(disease_pressures) if disease_pressures else 0.0
        
        env_vals = list(env_modifiers.values())
        avg_env = sum(env_vals) / len(env_vals) if env_vals else 1.0
        
        # 统计共生物种
        mutualism_species = set()
        for link in mutualism_links:
            mutualism_species.add(link.get("species_a", ""))
            mutualism_species.add(link.get("species_b", ""))
        mutualism_species.discard("")
        
        return EcologicalRealismSummary(
            allee_affected_count=len(allee_affected),
            allee_affected_species=allee_affected[:10],  # 最多显示10个
            disease_affected_count=len(disease_affected),
            avg_disease_pressure=avg_disease,
            mutualism_links_count=len(mutualism_links),
            mutualism_species_count=len(mutualism_species),
            adaptation_stressed_count=len(adaptation_stressed),
            avg_env_modifier=avg_env,
        )
    
    def _build_simple_narrative(
        self,
        turn_index: int,
        species_data: List[Dict],
        pressures: List[Any],
        branching_events: List[Any] | None = None,
        major_events: List[Any] | None = None,
        migration_events: List[Any] | None = None,
        reemergence_events: List[Any] | None = None,
        gene_diversity_events: List[Dict] | None = None,
        all_species_lookup: Dict[str, Any] | None = None,  # 【新增】全物种查找表
    ) -> str:
        """构建简单模式下的丰富叙事（不使用 LLM）
        
        【增强版】新增内容：
        - 霸主潜力分析
        - 生态位竞争分析
        - 演化趋势预测
        - 新物种继承特性分析
        """
        lines: List[str] = []
        
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
        lines.append("### 🌍 环境状况")
        if pressures:
            for p in pressures:
                if hasattr(p, 'narrative') and p.narrative:
                    lines.append(f"- {p.narrative}")
                elif hasattr(p, 'kind') and hasattr(p, 'intensity'):
                    intensity_desc = "轻微" if p.intensity < 0.3 else "中等" if p.intensity < 0.6 else "强烈"
                    lines.append(f"- **{p.kind}** ({intensity_desc}，强度 {p.intensity:.1f})")
        else:
            lines.append("- 环境相对稳定，无显著压力变化")
        lines.append("")
        
        # ═══ 生态概况 ═══
        alive_species = [s for s in species_data if s.get("status") == "alive"]
        extinct_species = [s for s in species_data if s.get("status") == "extinct"]
        
        total_population = sum(s.get("population", 0) for s in alive_species)
        total_deaths = sum(s.get("deaths", 0) for s in species_data)
        total_births = sum(s.get("births", 0) for s in species_data)
        
        lines.append("### 📊 生态概况")
        lines.append(f"- **存活物种**: {len(alive_species)} 种")
        lines.append(f"- **总生物量**: {total_population:,} 个体")
        
        if total_births > 0 or total_deaths > 0:
            net_change = total_births - total_deaths
            change_icon = "📈" if net_change > 0 else "📉" if net_change < 0 else "➡️"
            lines.append(f"- **本回合变动**: 出生 +{total_births:,} / 死亡 -{total_deaths:,} ({change_icon} 净变化 {net_change:+,})")
        
        # 计算平均死亡率
        death_rates = [s.get("death_rate", 0) for s in alive_species if s.get("deaths", 0) > 0]
        if death_rates:
            avg_death_rate = sum(death_rates) / len(death_rates)
            rate_desc = "稳定" if avg_death_rate < 0.15 else "略高" if avg_death_rate < 0.3 else "较高" if avg_death_rate < 0.5 else "危机"
            lines.append(f"- **平均死亡率**: {avg_death_rate:.1%} ({rate_desc})")
        lines.append("")
        
        # ═══ 重大事件 ═══
        has_events = False
        
        # 物种分化（增强版）
        if branching_events:
            if not has_events:
                lines.append("### ⚡ 本回合事件")
                has_events = True
            lines.append("")
            lines.append("**🧬 物种分化**")
            for b in branching_events[:5]:
                parent_code = getattr(b, 'parent_lineage', '?')
                child_code = getattr(b, 'new_lineage', '?') or getattr(b, 'child_code', '?')
                desc = getattr(b, 'description', '')
                child_name = getattr(b, 'child_name', '')
                
                if child_name:
                    lines.append(f"> `{parent_code}` → `{child_code}` **{child_name}**")
                else:
                    lines.append(f"> `{parent_code}` → `{child_code}`")
                if desc:
                    lines.append(f"> _{desc[:100]}{'...' if len(desc) > 100 else ''}_")
                
                # 【新增】继承特性分析
                if all_species_lookup:
                    child_sp = next((s for s in species_data if s.get("lineage_code") == child_code), None)
                    parent_sp_obj = all_species_lookup.get(parent_code)
                    if child_sp and parent_sp_obj:
                        parent_dict = {
                            "abstract_traits": getattr(parent_sp_obj, 'abstract_traits', {}),
                            "organs": getattr(parent_sp_obj, 'organs', {}),
                            "capabilities": getattr(parent_sp_obj, 'capabilities', []),
                        }
                        inheritance = self._analyze_inherited_traits(child_sp, parent_dict, b)
                        
                        if inheritance["new_adaptations"]:
                            lines.append(f"> 🔬 **演化亮点**: {'; '.join(inheritance['new_adaptations'][:2])}")
                        if inheritance["evolutionary_significance"]:
                            lines.append(f"> 💡 *{inheritance['evolutionary_significance']}*")
                lines.append("")
        
        # 灭绝事件
        new_extinct = [s for s in extinct_species if s.get("deaths", 0) > 0]
        if new_extinct:
            if not has_events:
                lines.append("### ⚡ 本回合事件")
                has_events = True
            lines.append("")
            lines.append("**💀 物种灭绝**")
            for s in new_extinct[:3]:
                lines.append(f"> **{s.get('common_name', '未知')}** (*{s.get('latin_name', '')}*) 走向灭绝")
            lines.append("")
        
        # 重大事件
        if major_events:
            if not has_events:
                lines.append("### ⚡ 本回合事件")
                has_events = True
            lines.append("")
            lines.append("**🌋 环境事件**")
            for e in major_events[:3]:
                desc = getattr(e, 'description', str(e))
                lines.append(f"> {desc}")
            lines.append("")
        
        # 迁徙事件
        if migration_events:
            if not has_events:
                lines.append("### ⚡ 本回合事件")
                has_events = True
            lines.append("")
            lines.append(f"**🦅 物种迁徙**: 发生了 {len(migration_events)} 次迁徙活动")
            lines.append("")
        
        # 物种重现
        if reemergence_events:
            if not has_events:
                lines.append("### ⚡ 本回合事件")
                has_events = True
            lines.append("")
            lines.append(f"**🔄 物种重现**: {len(reemergence_events)} 个物种重新活跃")
            lines.append("")

        # 基因多样性变动
        if gene_diversity_events:
            if not has_events:
                lines.append("### ⚡ 本回合事件")
                has_events = True
            lines.append("")
            lines.append("**🧬 基因多样性变动**")
            for evt in gene_diversity_events[:6]:
                code = evt.get("lineage_code", "?")
                name = evt.get("name", code)
                old = evt.get("old", 0.0)
                new = evt.get("new", 0.0)
                reason = evt.get("reason", "自然演化")
                lines.append(f"- {name} ({code}): {old:.2f} → {new:.2f}（{reason}）")
            lines.append("")
        
        if not has_events:
            lines.append("### ⚡ 本回合事件")
            lines.append("- 未发生重大事件，生态系统平稳运转")
            lines.append("")
        
        # ═══ 【新增】霸主潜力分析 ═══
        dominance_potentials = self._analyze_dominance_potential(species_data, alive_species)
        if dominance_potentials:
            lines.append("### 👑 霸主潜力分析")
            lines.append("")
            
            for i, potential in enumerate(dominance_potentials[:3]):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
                lines.append(f"**{medal} {potential['common_name']}** (`{potential['lineage_code']}`)")
                lines.append(f"- 潜力评分: **{potential['score']:.0f}分** | 种群: {potential['population']:,} ({potential['share']:.1%})")
                
                if potential['reasons']:
                    lines.append(f"- ✅ 优势: {'; '.join(potential['reasons'][:3])}")
                if potential['threats']:
                    lines.append(f"- ⚠️ 挑战: {'; '.join(potential['threats'][:2])}")
                
                # 给出定性评价
                score = potential['score']
                if score >= 70:
                    lines.append(f"- 💡 *{potential['common_name']} 极有可能成为本时代的霸主，已具备压倒性优势*")
                elif score >= 50:
                    lines.append(f"- 💡 *{potential['common_name']} 有成为霸主的潜力，但仍需巩固地位*")
                else:
                    lines.append(f"- 💡 *{potential['common_name']} 是潜在竞争者，但面临不少挑战*")
                lines.append("")
        
        # ═══ 【新增】生态位竞争分析 ═══
        competition_analysis = self._analyze_niche_competition(species_data, alive_species)
        
        if competition_analysis["displacement_risks"] or competition_analysis["crowded_niches"]:
            lines.append("### ⚔️ 生态位竞争格局")
            lines.append("")
            
            # 拥挤的生态位
            if competition_analysis["crowded_niches"]:
                lines.append("**🔥 竞争热点生态位**")
                for niche in competition_analysis["crowded_niches"][:2]:
                    species_list = ', '.join(niche['species'][:4])
                    if len(niche['species']) > 4:
                        species_list += f" 等{len(niche['species'])}种"
                    lines.append(f"- **{niche['niche']}** ({niche['count']}种竞争): {species_list}")
                lines.append("")
            
            # 被挤占风险
            if competition_analysis["displacement_risks"]:
                lines.append("**⚠️ 生态位挤占预警**")
                for risk in competition_analysis["displacement_risks"][:3]:
                    severity_icon = "🔴" if risk['severity'] == "高" else "🟡"
                    lines.append(f"- {severity_icon} {risk['description']}")
                    lines.append(f"  - *{risk['victim']} 可能被逐出{risk['niche']}生态位*")
                lines.append("")
        
        # ═══ 物种动态 ═══
        lines.append("### 🐾 物种动态")
        
        # 按状态和变化率排序，展示关键物种
        # 1. 表现最好的（死亡率最低）
        thriving = sorted(
            [s for s in alive_species if s.get("deaths", 0) > 0],
            key=lambda x: x.get("death_rate", 1)
        )[:2]
        
        # 2. 面临压力的（死亡率最高）
        struggling = sorted(
            [s for s in alive_species if s.get("death_rate", 0) > 0.3],
            key=lambda x: -x.get("death_rate", 0)
        )[:2]
        
        # 3. 主导物种（占比最高）
        dominant = sorted(
            alive_species,
            key=lambda x: -x.get("population_share", 0)
        )[:2]
        
        if thriving:
            lines.append("")
            lines.append("**🌟 适应良好**")
            for s in thriving:
                dr = s.get("death_rate", 0)
                net_change = s.get("net_change_rate", 0)
                trend = "↑" if net_change > 0.05 else "↓" if net_change < -0.05 else "→"
                lines.append(f"- **{s.get('common_name')}** (`{s.get('lineage_code')}`) — 死亡率 {dr:.1%}，种群{trend}稳健")
        
        if struggling:
            lines.append("")
            lines.append("**⚠️ 面临压力**")
            for s in struggling:
                dr = s.get("death_rate", 0)
                pop = s.get("population", 0)
                resource_pressure = s.get("resource_pressure", 0)
                
                pressure_hint = ""
                if resource_pressure and resource_pressure > 0.3:
                    pressure_hint = "，资源匮乏"
                elif s.get("niche_overlap", 0) > 0.5:
                    pressure_hint = "，生态位被挤占"
                
                lines.append(f"- **{s.get('common_name')}** (`{s.get('lineage_code')}`) — 死亡率 {dr:.1%}，剩余 {pop:,} 个体{pressure_hint}")
        
        if dominant and not thriving and not struggling:
            lines.append("")
            lines.append("**👑 主导物种**")
            for s in dominant:
                share = s.get("population_share", 0)
                pop = s.get("population", 0)
                role = s.get("ecological_role", "")
                lines.append(f"- **{s.get('common_name')}** ({role}) — 占生物量 {share:.1%}，共 {pop:,} 个体")
        
        lines.append("")
        
        # ═══ 【新增】演化趋势与预测 ═══
        evolution_trends = self._analyze_evolution_trends(species_data, alive_species, branching_events, pressures)
        
        lines.append("### 🔮 演化趋势与预测")
        lines.append("")
        
        # 主导方向
        lines.append(f"**📈 当前演化方向**: {evolution_trends['dominant_direction']}")
        lines.append("")
        
        # 适应趋势
        if evolution_trends["adaptation_trends"]:
            lines.append("**🧬 适应趋势**")
            for trend in evolution_trends["adaptation_trends"][:3]:
                lines.append(f"- {trend}")
            lines.append("")
        
        # 灭绝预警
        if evolution_trends["extinction_warnings"]:
            lines.append("**🚨 灭绝风险预警**")
            for warning in evolution_trends["extinction_warnings"][:3]:
                level_icon = "🔴" if warning['level'] == "critical" else "🟠"
                reasons_str = "; ".join(warning['reasons'][:2])
                lines.append(f"- {level_icon} **{warning['species']}** (`{warning['lineage_code']}`): {reasons_str}")
            lines.append("")
        
        # 分化前景
        if evolution_trends["speciation_outlook"]:
            lines.append(f"**🌱 分化前景**: {evolution_trends['speciation_outlook']}")
            lines.append("")
        
        # ═══ 小结 ═══
        lines.append("---")
        
        # 根据情况生成更丰富的小结
        summary_parts = []
        
        if branching_events:
            summary_parts.append(f"本回合见证了 {len(branching_events)} 次物种分化，生命多样性持续扩展")
        
        if dominance_potentials and dominance_potentials[0]['score'] >= 60:
            top = dominance_potentials[0]
            summary_parts.append(f"**{top['common_name']}** 正在崛起为时代霸主")
        
        if competition_analysis["displacement_risks"]:
            victim = competition_analysis["displacement_risks"][0]
            summary_parts.append(f"{victim['victim']} 面临被挤占生态位的挑战")
        
        if new_extinct:
            summary_parts.append(f"{len(new_extinct)} 个物种在自然选择中消逝")
        
        if evolution_trends["extinction_warnings"]:
            count = len(evolution_trends["extinction_warnings"])
            summary_parts.append(f"{count} 个物种正处于灭绝风险中")
        
        if not summary_parts:
            if total_deaths > total_births:
                summary_parts.append("生态系统承受一定压力，整体种群有所下降")
            elif total_births > total_deaths * 1.5:
                summary_parts.append("生态繁荣，物种繁衍旺盛")
            else:
                summary_parts.append("生态系统保持动态平衡")
        
        # 组合小结
        if len(summary_parts) == 1:
            lines.append(f"*{summary_parts[0]}。*")
        elif len(summary_parts) == 2:
            lines.append(f"*{summary_parts[0]}；{summary_parts[1]}。*")
        else:
            lines.append(f"*{summary_parts[0]}；{summary_parts[1]}；{summary_parts[2]}。*")
        
        return "\n".join(lines)
    
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
        all_species: List[Any] | None = None,
        ecological_realism_data: Dict[str, Any] | None = None,  # 【新增】生态拟真数据
        gene_diversity_events: List[Dict] | None = None,
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
            all_species: 当前所有物种列表（从模拟上下文传入，避免数据库会话问题）
            
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
        
        # 构建物种数据 - 使用传入的物种列表（避免数据库会话隔离问题）
        # 如果没有传入，才从数据库查询（向后兼容）
        if all_species is None:
            from ...repositories.species_repository import species_repository
            all_species = species_repository.list_species()
            logger.warning("[TurnReport] 未传入 all_species，从数据库重新查询（可能数据不完整）")
        
        # 构建 mortality_results 的查找字典
        mortality_lookup: Dict[str, Any] = {}
        for result in mortality_results:
            if hasattr(result, 'species'):
                mortality_lookup[result.species.lineage_code] = result
        
        # 计算总生物量（只计算存活物种）
        total_population = sum(
            sp.morphology_stats.get("population", 0) or 0
            for sp in all_species
            if sp.status == "alive"
        ) or 1  # 避免除零
        
        species_data = []
        for species in all_species:
            pop = species.morphology_stats.get("population", 0) or 0
            
            # 尝试从 mortality_results 获取详细信息
            mortality_result = mortality_lookup.get(species.lineage_code)
            
            if mortality_result:
                # 有死亡率计算结果，使用更详细的数据
                pop = getattr(mortality_result, 'final_population', 0) or pop
                initial_pop = getattr(mortality_result, 'initial_population', 0) or pop
                births = getattr(mortality_result, 'births', 0)
                net_change_rate = (pop - initial_pop) / max(1, initial_pop)
                species_data.append({
                    "lineage_code": species.lineage_code,
                    "latin_name": species.latin_name,
                    "common_name": species.common_name,
                    "population": pop,
                    "population_share": pop / total_population if species.status == "alive" else 0,
                    "deaths": getattr(mortality_result, 'deaths', 0),
                    "death_rate": mortality_result.death_rate,
                    "net_change_rate": net_change_rate,
                    "ecological_role": self._get_ecological_role(species.trophic_level),
                    "status": species.status,
                    "notes": getattr(mortality_result, 'notes', []) or [],
                    "niche_overlap": getattr(mortality_result, 'niche_overlap', None),
                    "resource_pressure": getattr(mortality_result, 'resource_pressure', None),
                    "is_background": getattr(mortality_result, 'is_background', False),
                    "tier": getattr(mortality_result, 'tier', None),
                    "trophic_level": species.trophic_level,
                    "grazing_pressure": getattr(mortality_result, 'grazing_pressure', None),
                    "predation_pressure": getattr(mortality_result, 'predation_pressure', None),
                    "ai_narrative": getattr(mortality_result, 'ai_narrative', None),
                    "initial_population": initial_pop,
                    "births": births,
                    "survivors": getattr(mortality_result, 'survivors', 0),
                    # 【修复】地块分布统计
                    "total_tiles": getattr(mortality_result, 'total_tiles', 0),
                    "healthy_tiles": getattr(mortality_result, 'healthy_tiles', 0),
                    "warning_tiles": getattr(mortality_result, 'warning_tiles', 0),
                    "critical_tiles": getattr(mortality_result, 'critical_tiles', 0),
                    "best_tile_rate": getattr(mortality_result, 'best_tile_rate', 0.0),
                    "worst_tile_rate": getattr(mortality_result, 'worst_tile_rate', 1.0),
                    "has_refuge": getattr(mortality_result, 'has_refuge', True),
                    "distribution_status": getattr(mortality_result, 'distribution_status', ''),
                    # 【新增】生态拟真数据
                    "ecological_realism": self._build_ecological_realism_snapshot(
                        species.lineage_code, ecological_realism_data
                    ),
                })
            else:
                # 没有死亡率计算结果（新分化的物种或其他情况），使用基础数据
                species_data.append({
                    "lineage_code": species.lineage_code,
                    "latin_name": species.latin_name,
                    "common_name": species.common_name,
                    "population": pop,
                    "population_share": pop / total_population if species.status == "alive" else 0,
                    "deaths": 0,
                    "death_rate": 0.0,
                    "net_change_rate": 0.0,
                    "ecological_role": self._get_ecological_role(species.trophic_level),
                    "status": species.status,
                    "notes": [],
                    "niche_overlap": None,
                    "resource_pressure": None,
                    "is_background": species.is_background,
                    "tier": None,
                    "trophic_level": species.trophic_level,
                    "grazing_pressure": None,
                    "predation_pressure": None,
                    "ai_narrative": None,
                    "initial_population": pop,
                    "births": 0,
                    "survivors": pop,
                    # 【修复】地块分布统计（新物种无数据时给默认值）
                    "total_tiles": 0,
                    "healthy_tiles": 0,
                    "warning_tiles": 0,
                    "critical_tiles": 0,
                    "best_tile_rate": 0.0,
                    "worst_tile_rate": 1.0,
                    "has_refuge": True,
                    "distribution_status": "初始",
                    # 【新增】生态拟真数据
                    "ecological_realism": self._build_ecological_realism_snapshot(
                        species.lineage_code, ecological_realism_data
                    ),
                })
        
        logger.info(f"[TurnReport] 族谱物种总数: {len(all_species)}, 存活: {sum(1 for s in species_data if s['status'] == 'alive')}")
        
        # 【新增】构建物种查找表，用于继承特性分析
        all_species_lookup: Dict[str, Any] = {sp.lineage_code: sp for sp in all_species}
        
        # 【新增】为 species_data 添加更多分析字段
        for sp_data in species_data:
            lineage_code = sp_data.get("lineage_code")
            sp_obj = all_species_lookup.get(lineage_code)
            if sp_obj:
                # 添加抽象特征（用于继承分析）
                sp_data["abstract_traits"] = getattr(sp_obj, 'abstract_traits', {})
                # 添加器官信息
                sp_data["organs"] = getattr(sp_obj, 'organs', {})
                # 添加能力列表
                sp_data["capabilities"] = getattr(sp_obj, 'capabilities', [])
                # 添加父代代码
                sp_data["parent_code"] = getattr(sp_obj, 'parent_code', None)
                # 添加捕食关系
                sp_data["prey_species"] = getattr(sp_obj, 'prey_species', [])
                sp_data["diet_type"] = getattr(sp_obj, 'diet_type', 'omnivore')
                # 添加共生关系
                sp_data["symbiotic_dependencies"] = getattr(sp_obj, 'symbiotic_dependencies', [])
                # 添加栖息地类型
                sp_data["habitat_type"] = getattr(sp_obj, 'habitat_type', 'terrestrial')
                # 添加基因多样性
                sp_data["gene_diversity_radius"] = getattr(sp_obj, 'gene_diversity_radius', 0.35)
        
        # ========== 检查 LLM 回合报告开关 ==========
        # 优先从 UI 配置读取，否则从系统配置读取
        enable_turn_report_llm = False  # 默认值
        config_source = "默认"
        try:
            from pathlib import Path
            settings = get_settings()
            ui_config_path = Path(settings.ui_config_path)
            logger.info(f"[TurnReportService] 读取 UI 配置: {ui_config_path}")
            
            if ui_config_path.exists():
                ui_config = self.environment_repository.load_ui_config(ui_config_path)
                enable_turn_report_llm = ui_config.turn_report_llm_enabled
                config_source = "UI配置"
                logger.info(f"[TurnReportService] ✅ UI 配置读取成功，turn_report_llm_enabled={enable_turn_report_llm}")
            else:
                logger.warning(f"[TurnReportService] ⚠️ UI 配置文件不存在: {ui_config_path}，使用系统配置")
                enable_turn_report_llm = settings.enable_turn_report_llm
                config_source = "系统配置(文件不存在)"
        except Exception as e:
            # 回退到系统配置
            logger.warning(f"[TurnReportService] ⚠️ 读取 UI 配置失败: {e}，回退到系统配置")
            import traceback
            logger.debug(f"[TurnReportService] 异常详情: {traceback.format_exc()}")
            settings = get_settings()
            enable_turn_report_llm = settings.enable_turn_report_llm
            config_source = "系统配置(异常)"
        
        logger.info(f"[TurnReportService] 📊 最终配置: turn_report_llm_enabled={enable_turn_report_llm} (来源: {config_source})")
        
        # 如果开关关闭，直接使用简单模式，不调用 LLM
        if not enable_turn_report_llm:
            logger.info("[TurnReportService] LLM 回合报告已关闭，使用增强简单模式")
            self._emit_event("info", "📝 使用增强简单模式生成报告", "报告")
            
            narrative = self._build_simple_narrative(
                turn_index=turn_index,
                species_data=species_data,
                pressures=pressures,
                branching_events=branching_events,
                major_events=major_events,
                migration_events=migration_events,
                reemergence_events=reemergence_events,
                gene_diversity_events=gene_diversity_events,
                all_species_lookup=all_species_lookup,  # 【新增】传递物种查找表
            )
            
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
                ecological_realism=self._build_ecological_realism_summary(species_data, ecological_realism_data),
                gene_diversity_events=gene_diversity_events or [],
            )
        
        # ========== 【修复】调用 LLM 叙事引擎 ==========
        # 将 mortality_results 转换为 SpeciesSnapshot 列表
        species_snapshots: List[SpeciesSnapshot] = []
        for result in mortality_results:
            if hasattr(result, 'species') and hasattr(result, 'death_rate'):
                pop = getattr(result, 'final_population', 0) or result.species.morphology_stats.get("population", 0)
                initial_pop = getattr(result, 'initial_population', 0) or pop
                deaths = getattr(result, 'deaths', 0)
                births = getattr(result, 'births', 0)
                net_change_rate = (pop - initial_pop) / max(1, initial_pop)
                
                species_snapshots.append(SpeciesSnapshot(
                    lineage_code=result.species.lineage_code,
                    latin_name=result.species.latin_name,
                    common_name=result.species.common_name,
                    population=pop,
                    population_share=pop / total_population,
                    deaths=deaths,
                    death_rate=result.death_rate,
                    net_change_rate=net_change_rate,
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
                    births=births,
                    survivors=getattr(result, 'survivors', 0),
                    # 【修复】地块分布统计完整字段
                    total_tiles=getattr(result, 'total_tiles', 0),
                    healthy_tiles=getattr(result, 'healthy_tiles', 0),
                    warning_tiles=getattr(result, 'warning_tiles', 0),
                    critical_tiles=getattr(result, 'critical_tiles', 0),
                    best_tile_rate=getattr(result, 'best_tile_rate', 0.0),
                    worst_tile_rate=getattr(result, 'worst_tile_rate', 1.0),
                    has_refuge=getattr(result, 'has_refuge', True),
                    distribution_status=getattr(result, 'get_distribution_status', lambda: '')() if hasattr(result, 'get_distribution_status') else '',
                    # 【新增】基因数据（用于基因库显示）
                    abstract_traits=getattr(result.species, 'abstract_traits', None),
                    organs=getattr(result.species, 'organs', None),
                    capabilities=getattr(result.species, 'capabilities', None),
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
        
        # 如果 LLM 失败，使用丰富的回退叙事
        if not narrative:
            narrative = self._build_simple_narrative(
                turn_index=turn_index,
                species_data=species_data,
                pressures=pressures,
                branching_events=branching_events,
                major_events=major_events,
                migration_events=migration_events,
                reemergence_events=reemergence_events,
                gene_diversity_events=gene_diversity_events,
                all_species_lookup=all_species_lookup,  # 【新增】传递物种查找表
            )
            
            # 回退模式下流式输出
            if stream_callback:
                for char in narrative:
                    await stream_callback(char)
                    await asyncio.sleep(0.01)

        # 附加基因多样性摘要，确保即便LLM生成也能看到关键数据
        if gene_diversity_events:
            summary_lines = ["", "### 🧬 基因多样性变动"]
            for evt in gene_diversity_events[:8]:
                code = evt.get("lineage_code", "?")
                name = evt.get("name", code)
                old = evt.get("old", 0.0)
                new = evt.get("new", 0.0)
                reason = evt.get("reason", "自然演化")
                summary_lines.append(f"- {name} ({code}): {old:.2f} → {new:.2f}（{reason}）")
            narrative = narrative + "\n" + "\n".join(summary_lines)
        
        return TurnReport(
            turn_index=turn_index,
            narrative=narrative,
            pressures_summary=pressure_summary,
            species=species_data,
            branching_events=branching_events or [],
            major_events=major_events or [],
            ecological_realism=self._build_ecological_realism_summary(species_data, ecological_realism_data),
            gene_diversity_events=gene_diversity_events or [],
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

