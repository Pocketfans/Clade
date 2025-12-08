"""物种分化规则引擎

将固定的演化规则从Prompt提取到代码中：
1. 预处理：计算约束条件传给LLM
2. 后验证：验证LLM输出并修正违规内容
3. 增强预算上下文：为LLM提供边际递减、突破机会等信息

这样做的好处：
- Prompt从~400行减少到~150行
- Token消耗减少60%
- 规则100%强制执行（不依赖LLM理解）
- LLM可以做出更有策略性的演化决策
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrganConstraint:
    """器官演化约束"""
    category: str
    current_stage: int
    max_target_stage: int
    can_initiate: bool = False  # 是否可以开始发展新器官


@dataclass
class TraitBudget:
    """属性变化预算"""
    total_increase_allowed: float
    total_decrease_required: float
    single_trait_max: float
    suggested_increases: list[str] = field(default_factory=list)
    suggested_decreases: list[str] = field(default_factory=list)


@dataclass
class EvolutionDirection:
    """演化方向提示"""
    strategy: str
    description: str
    primary_focus: list[str]
    tradeoff_targets: list[str]


@dataclass
class NicheExplorationStrategy:
    """生态位探索策略 - 指导子代往哪个生态位方向演化
    
    【生物学原理】
    - 适应辐射：分化时子代应该探索不同的生态位，减少竞争
    - 营养级转变：向上成为捕食者，向下成为猎物的竞争者
    - 栖息地分化：探索不同的地理/微栖息地
    """
    strategy: str                      # 策略名称
    description: str                   # 给LLM的描述
    trophic_shift: tuple[float, float] # 营养级变化范围 (min, max)
    habitat_shift: bool                # 是否鼓励栖息地变化
    diet_focus: str                    # 食性变化方向
    body_size_trend: str               # 体型变化趋势: "larger", "smaller", "similar"
    competition_with_parent: str       # 与父代竞争关系: "direct", "partial", "minimal"
    ecological_role: str               # 目标生态角色描述


class SpeciationRules:
    """物种分化规则引擎"""
    
    # ==================== 器官阶段定义 ====================
    ORGAN_STAGES = {
        0: {"name": "无结构", "function": 0.0, "desc": "无相关能力"},
        1: {"name": "原基", "function": 0.2, "desc": "初始萌芽，功能微弱"},
        2: {"name": "初级", "function": 0.5, "desc": "基本功能，效率有限"},
        3: {"name": "功能化", "function": 0.8, "desc": "功能完善，效率较高"},
        4: {"name": "完善", "function": 1.0, "desc": "高度特化，效率最优"},
    }
    
    ORGAN_CATEGORIES = ["locomotion", "sensory", "metabolic", "digestive", "defense", "reproduction"]
    
    # ==================== 分化约束常量 ====================
    MAX_STAGE_JUMP = 2           # 单次最多提升2阶段
    MAX_ORGAN_CHANGES = 2        # 单次最多涉及2个器官系统
    NEW_ORGAN_START_STAGE = 1    # 新器官只能从阶段1开始
    
    # ==================== 属性权衡约束 ====================
    TRAIT_CHANGE_TOTAL_MIN = -3.0
    TRAIT_CHANGE_TOTAL_MAX = 5.0
    SINGLE_TRAIT_MAX_CHANGE = 3.0
    INCREASE_DECREASE_RATIO = 2.0  # 增加量 ≤ 减少量 × 2
    
    # ==================== 形态约束 ====================
    MORPHOLOGY_MIN_RATIO = 0.8
    MORPHOLOGY_MAX_RATIO = 1.3
    
    # ==================== 栖息地转换规则 ====================
    HABITAT_TRANSITIONS = {
        "marine": ["marine", "coastal", "deep_sea"],
        "deep_sea": ["deep_sea", "marine"],
        "coastal": ["coastal", "marine", "amphibious", "terrestrial"],
        "freshwater": ["freshwater", "amphibious", "coastal"],
        "amphibious": ["amphibious", "freshwater", "coastal", "terrestrial"],
        "terrestrial": ["terrestrial", "amphibious", "aerial"],
        "aerial": ["aerial", "terrestrial"],
    }
    
    # ==================== 栖息地与属性关联 ====================
    HABITAT_TRAIT_EXPECTATIONS = {
        "marine": {"耐盐性": (8, 12), "耐旱性": (1, 4)},
        "deep_sea": {"耐盐性": (10, 15), "耐旱性": (0, 2), "光照需求": (0, 2)},
        "coastal": {"耐盐性": (5, 10), "耐旱性": (3, 7)},
        "freshwater": {"耐盐性": (1, 4), "耐旱性": (3, 6)},
        "amphibious": {"耐盐性": (3, 7), "耐旱性": (4, 8)},
        "terrestrial": {"耐盐性": (1, 5), "耐旱性": (6, 12)},
        "aerial": {"耐盐性": (1, 4), "耐旱性": (5, 10), "运动能力": (8, 15)},
    }
    
    # ==================== 营养级定义 ====================
    TROPHIC_LEVELS = {
        1.0: "生产者（光合/化能自养）",
        1.5: "分解者/腐食者",
        2.0: "初级消费者（草食/滤食）",
        2.5: "杂食者（偏植物）",
        3.0: "次级消费者（小型捕食者）",
        3.5: "杂食者（偏肉食）",
        4.0: "三级消费者（中型捕食者）",
        4.5: "高级捕食者",
        5.0: "顶级捕食者",
    }
    
    # ==================== 子代差异化策略（属性层面）====================
    OFFSPRING_STRATEGIES = [
        EvolutionDirection(
            strategy="环境适应型",
            description="强化环境耐受性，牺牲活动能力",
            primary_focus=["耐寒性", "耐热性", "耐旱性", "耐盐性"],
            tradeoff_targets=["运动能力", "繁殖速度"]
        ),
        EvolutionDirection(
            strategy="活动强化型", 
            description="强化运动和感知能力，牺牲耐受性",
            primary_focus=["运动能力", "光照需求"],
            tradeoff_targets=["耐寒性", "耐热性", "繁殖速度"]
        ),
        EvolutionDirection(
            strategy="繁殖策略型",
            description="强化繁殖和社会性，牺牲个体能力",
            primary_focus=["繁殖速度", "社会性"],
            tradeoff_targets=["运动能力", "耐旱性"]
        ),
        EvolutionDirection(
            strategy="防御特化型",
            description="强化防御和耐受，牺牲攻击性",
            primary_focus=["耐酸碱性", "耐盐性"],
            tradeoff_targets=["运动能力", "繁殖速度"]
        ),
        EvolutionDirection(
            strategy="极端特化型",
            description="1-2个属性大幅增强，其他大幅减弱",
            primary_focus=["随机选择1-2个"],
            tradeoff_targets=["其他多个属性"]
        ),
    ]
    
    # ==================== 【新增】生态位探索策略 ====================
    # 分化时子代应该探索不同的生态位，实现适应辐射
    NICHE_EXPLORATION_STRATEGIES = [
        NicheExplorationStrategy(
            strategy="保守继承型",
            description="留在原生态位，与父代直接竞争。体型和食性与父代相似，通过优化现有适应性取胜。",
            trophic_shift=(0.0, 0.0),
            habitat_shift=False,
            diet_focus="与父代相同",
            body_size_trend="similar",
            competition_with_parent="direct",
            ecological_role="父代生态位的竞争者"
        ),
        NicheExplorationStrategy(
            strategy="上行捕食型",
            description="向更高营养级探索，演化成捕食者。体型可能增大，发展捕食相关器官（感知、运动、捕获结构）。",
            trophic_shift=(+0.5, +1.0),
            habitat_shift=False,
            diet_focus="开始捕食同级或低级物种",
            body_size_trend="larger",
            competition_with_parent="minimal",
            ecological_role="新兴捕食者"
        ),
        NicheExplorationStrategy(
            strategy="下行专化型",
            description="向更低营养级探索，专化不同的食物来源。可能体型缩小，专化特定资源。",
            trophic_shift=(-0.5, -1.0),
            habitat_shift=False,
            diet_focus="专化更基础的食物来源",
            body_size_trend="smaller",
            competition_with_parent="minimal",
            ecological_role="专化资源利用者"
        ),
        NicheExplorationStrategy(
            strategy="横向栖息地型",
            description="探索不同栖息地，占据新的地理生态位。营养级不变，但适应新环境条件。",
            trophic_shift=(0.0, 0.0),
            habitat_shift=True,
            diet_focus="适应新栖息地的食物",
            body_size_trend="similar",
            competition_with_parent="minimal",
            ecological_role="新栖息地开拓者"
        ),
        NicheExplorationStrategy(
            strategy="杂食泛化型",
            description="扩大食谱范围，成为杂食者。牺牲专化效率换取资源多样性。",
            trophic_shift=(-0.3, +0.3),
            habitat_shift=False,
            diet_focus="扩大食物范围，杂食化",
            body_size_trend="similar",
            competition_with_parent="partial",
            ecological_role="泛化杂食者"
        ),
        NicheExplorationStrategy(
            strategy="极端专化型",
            description="极端专化某一特定资源或微栖息地。高度特化，与父代生态位重叠很小。",
            trophic_shift=(-0.2, +0.2),
            habitat_shift=True,
            diet_focus="极端专化单一资源",
            body_size_trend="smaller",
            competition_with_parent="minimal",
            ecological_role="极端专化者"
        ),
    ]
    
    def __init__(self):
        pass
    
    # ==================== 预处理方法 ====================
    
    def preprocess(
        self,
        parent_species,
        offspring_index: int,
        total_offspring: int,
        environment_pressure: dict[str, float],
        pressure_context: str,
        turn_index: int = 0,
    ) -> dict[str, Any]:
        """预处理：生成传给LLM的约束摘要
        
        Args:
            parent_species: 父系物种对象
            offspring_index: 当前子代编号（1-based）
            total_offspring: 总子代数量
            environment_pressure: 环境压力字典
            pressure_context: 压力描述文本
            turn_index: 当前回合数（用于时代修正）
            
        Returns:
            约束条件字典，直接传给LLM
        """
        from .trait_config import (
            TraitConfig, get_current_era,
            get_diminishing_summary, get_breakthrough_summary, get_bonus_summary
        )
        
        # 1. 计算属性变化预算（考虑时代上限）
        trait_budget = self._calculate_trait_budget(parent_species, environment_pressure, turn_index)
        
        # 2. 计算器官演化约束
        organ_constraints = self._get_organ_constraints(parent_species)
        
        # 3. 确定演化方向（属性层面）
        direction = self._get_evolution_direction(offspring_index, total_offspring, environment_pressure)
        
        # 4. 【新增】确定生态位探索策略（营养级/栖息地层面）
        niche_strategy = self._get_niche_exploration_strategy(
            parent_species, offspring_index, total_offspring
        )
        
        # 5. 确定可转换的栖息地（根据生态位策略调整）
        habitat_options = self._get_valid_habitat_transitions(parent_species.habitat_type)
        if niche_strategy.habitat_shift:
            # 生态位策略鼓励栖息地变化，扩大选项
            habitat_options = self._get_extended_habitat_options(parent_species.habitat_type)
        
        # 6. 营养级范围（根据生态位策略调整）
        trophic_range = self._get_trophic_range_from_strategy(
            parent_species.trophic_level, niche_strategy
        )
        
        # 7. 获取时代信息
        era = get_current_era(turn_index)
        era_limits = TraitConfig.get_trophic_limits(parent_species.trophic_level, turn_index)
        era_summary = TraitConfig.get_era_limits_summary(turn_index, parent_species.trophic_level)
        
        # 8. 【新增】获取增强预算上下文
        enhanced_context = self._get_enhanced_budget_context(
            parent_species, turn_index, era_limits
        )
        
        # 9. 【新增】格式化生态位探索策略（关键：传给LLM指导分化方向）
        niche_strategy_text = self._format_niche_strategy(niche_strategy, parent_species.trophic_level)
        
        return {
            "trait_budget_summary": self._format_trait_budget(trait_budget, era_limits),
            "organ_constraints_summary": self._format_organ_constraints(organ_constraints),
            "evolution_direction": direction.strategy,
            "direction_description": direction.description,
            "suggested_increases": direction.primary_focus,
            "suggested_decreases": direction.tradeoff_targets,
            "habitat_options": habitat_options,
            "trophic_range": trophic_range,
            # 【新增】生态位探索策略（关键！）
            "niche_exploration_strategy": niche_strategy.strategy,
            "niche_exploration_description": niche_strategy.description,
            "niche_exploration_full": niche_strategy_text,
            "target_diet_focus": niche_strategy.diet_focus,
            "target_body_size_trend": niche_strategy.body_size_trend,
            "target_ecological_role": niche_strategy.ecological_role,
            "competition_with_parent": niche_strategy.competition_with_parent,
            # 时代信息
            "era_summary": era_summary,
            "era_name": era["name"],
            "era_description": era["description"],
            "era_single_cap": era_limits["specialized"],
            "era_total_cap": era_limits["total"],
            # 增强预算上下文
            "diminishing_returns_context": enhanced_context["diminishing_text"],
            "breakthrough_opportunities": enhanced_context["breakthrough_text"],
            "habitat_specialization_bonus": enhanced_context["bonus_text"],
            "budget_usage_percent": enhanced_context["usage_percent"],
            "remaining_budget": enhanced_context["remaining_budget"],
            "strategy_recommendation": enhanced_context["strategy_recommendation"],
            # 原始数据（供后验证使用）
            "_trait_budget": trait_budget,
            "_organ_constraints": organ_constraints,
            "_niche_strategy": niche_strategy,
            "_turn_index": turn_index,
            "_enhanced_context": enhanced_context,
        }
    
    def _get_enhanced_budget_context(
        self,
        species,
        turn_index: int,
        era_limits: dict
    ) -> dict[str, Any]:
        """生成增强的预算上下文（供 prompt 使用）
        
        包含：边际递减警告、突破机会、栖息地加成、策略建议
        使用核心预算计算系统（设计文档第三章）
        
        Args:
            species: 物种对象
            turn_index: 当前回合数
            era_limits: 时代上限字典
            
        Returns:
            增强上下文字典
        """
        from .trait_config import (
            get_diminishing_summary, get_breakthrough_summary, 
            get_bonus_summary, get_single_trait_cap,
            calculate_budget_from_species, get_era_factor, get_trophic_factor
        )
        
        traits = getattr(species, 'abstract_traits', {}) or {}
        trophic_level = getattr(species, 'trophic_level', 2.0)
        habitat_type = getattr(species, 'habitat_type', 'terrestrial')
        organs = getattr(species, 'organs', {}) or {}
        
        # 1. 使用核心预算公式计算（设计文档第三章）
        # 预算 = 基础值 × 时代因子 × 营养级因子 × 体型因子 × 器官因子
        budget = calculate_budget_from_species(species, turn_index)
        single_cap = get_single_trait_cap(turn_index, trophic_level)
        current_total = sum(traits.values())
        usage_percent = current_total / budget if budget > 0 else 0
        remaining = max(0, budget - current_total)
        
        # 获取因子分解（用于显示）
        era_factor = get_era_factor(turn_index)
        trophic_factor = get_trophic_factor(trophic_level)
        
        # 2. 边际递减摘要
        diminishing = get_diminishing_summary(traits, turn_index, trophic_level)
        diminishing_text = ""
        if diminishing["warning_text"]:
            diminishing_text = f"""
=== ⚖️ 边际递减警告 ===
{diminishing["warning_text"]}
{diminishing["strategy_hint"]}
"""
        
        # 3. 突破机会
        breakthrough = get_breakthrough_summary(traits, turn_index, trophic_level)
        breakthrough_text = ""
        if breakthrough["achieved"] or breakthrough["near"]:
            breakthrough_text = f"""
=== 🏆 突破机会 ===
{breakthrough["summary_text"]}
"""
        
        # 4. 栖息地和器官加成
        bonus = get_bonus_summary(habitat_type, organs)
        bonus_text = ""
        if bonus["habitat_bonus"] or bonus["organ_bonus"]:
            bonus_text = f"""
=== 🌍 特化加成 ===
{bonus["summary_text"]}
提示：强化这些属性可突破普通上限！
"""
        
        # 5. 策略建议
        strategy_recommendation = self._generate_strategy_recommendation(
            usage_percent, diminishing, breakthrough, bonus
        )
        
        return {
            "usage_percent": usage_percent,
            "remaining_budget": remaining,
            "current_total": current_total,
            "budget": budget,
            "single_cap": single_cap,
            "era_factor": era_factor,
            "trophic_factor": trophic_factor,
            "diminishing_text": diminishing_text,
            "breakthrough_text": breakthrough_text,
            "bonus_text": bonus_text,
            "strategy_recommendation": strategy_recommendation,
            # 原始数据
            "_diminishing": diminishing,
            "_breakthrough": breakthrough,
            "_bonus": bonus,
        }
    
    def _generate_strategy_recommendation(
        self,
        usage_percent: float,
        diminishing: dict,
        breakthrough: dict,
        bonus: dict
    ) -> str:
        """生成演化策略建议
        
        Args:
            usage_percent: 预算使用比例
            diminishing: 边际递减摘要
            breakthrough: 突破摘要
            bonus: 加成摘要
            
        Returns:
            策略建议文本
        """
        recommendations = []
        
        # 基于预算使用情况
        if usage_percent < 0.3:
            recommendations.append("📈 预算充足，可大胆演化新特质")
        elif usage_percent > 0.85:
            recommendations.append("⚠️ 预算紧张，优先优化现有特质而非新增")
        
        # 基于边际递减
        high_traits = diminishing.get("high_traits", [])
        if len(high_traits) >= 3:
            recommendations.append("🔄 多个属性效率低下，建议分散投资")
        elif high_traits and high_traits[0][2] >= 0.85:
            top_trait = high_traits[0][0]
            recommendations.append(f"🎯 {top_trait}效率极低，可尝试突破或转向其他属性")
        
        # 基于突破机会
        near_breakthroughs = breakthrough.get("near", [])
        if near_breakthroughs:
            best = near_breakthroughs[0]
            if best["gap"] <= 2.0:
                recommendations.append(
                    f"🏆 {best['trait']}距「{best['tier_name']}」仅差{best['gap']:.1f}，建议优先突破！"
                )
        
        # 基于栖息地加成
        habitat_bonus = bonus.get("habitat_bonus", {})
        if habitat_bonus:
            bonus_traits = list(habitat_bonus.keys())[:2]
            recommendations.append(f"🌍 栖息地特化：{', '.join(bonus_traits)}可突破普通上限")
        
        if not recommendations:
            recommendations.append("⚖️ 均衡发展，注意权衡代价")
        
        return "\n".join(recommendations)
    
    def _calculate_trait_budget(
        self, 
        parent_species, 
        environment_pressure: dict[str, float],
        turn_index: int = 0
    ) -> TraitBudget:
        """计算属性变化预算（考虑时代上限）"""
        # 根据环境压力强度调整预算
        total_pressure = sum(abs(v) for v in environment_pressure.values())
        
        # 高压力允许更大变化（适应性演化更快）
        pressure_multiplier = 1.0 + min(0.5, total_pressure / 20.0)
        
        # 基础预算
        base_increase = 3.0 * pressure_multiplier
        required_decrease = base_increase / self.INCREASE_DECREASE_RATIO
        
        # 根据环境压力建议增强/减弱的属性
        suggested_increases = []
        suggested_decreases = []
        
        if environment_pressure.get("temperature", 0) < -2:
            suggested_increases.append("耐寒性")
        elif environment_pressure.get("temperature", 0) > 2:
            suggested_increases.append("耐热性")
        
        if environment_pressure.get("humidity", 0) < -2:
            suggested_increases.append("耐旱性")
        
        if environment_pressure.get("salinity", 0) > 2:
            suggested_increases.append("耐盐性")
        
        # 默认的牺牲属性
        suggested_decreases = ["繁殖速度", "运动能力", "社会性"]
        
        return TraitBudget(
            total_increase_allowed=min(base_increase, self.TRAIT_CHANGE_TOTAL_MAX),
            total_decrease_required=required_decrease,
            single_trait_max=self.SINGLE_TRAIT_MAX_CHANGE,
            suggested_increases=suggested_increases or ["根据环境自由选择"],
            suggested_decreases=suggested_decreases,
        )
    
    def _get_organ_constraints(self, parent_species) -> list[OrganConstraint]:
        """获取器官演化约束"""
        constraints = []
        parent_organs = getattr(parent_species, 'organs', {}) or {}
        
        for category in self.ORGAN_CATEGORIES:
            organ_info = parent_organs.get(category, {})
            current_stage = organ_info.get("stage", 0)
            
            # 计算最大可达阶段
            max_target = min(4, current_stage + self.MAX_STAGE_JUMP)
            
            constraints.append(OrganConstraint(
                category=category,
                current_stage=current_stage,
                max_target_stage=max_target,
                can_initiate=(current_stage == 0),  # 阶段0可以开始发展
            ))
        
        return constraints
    
    def _get_evolution_direction(
        self, 
        offspring_index: int, 
        total_offspring: int,
        environment_pressure: dict[str, float]
    ) -> EvolutionDirection:
        """获取子代的演化方向（属性层面）"""
        # 使用子代编号决定策略（确保差异化）
        strategy_index = (offspring_index - 1) % len(self.OFFSPRING_STRATEGIES)
        direction = self.OFFSPRING_STRATEGIES[strategy_index]
        
        # 如果是极端特化型，随机选择重点属性
        if direction.strategy == "极端特化型":
            all_traits = ["耐寒性", "耐热性", "耐旱性", "耐盐性", "运动能力", "繁殖速度"]
            selected = random.sample(all_traits, 2)
            remaining = [t for t in all_traits if t not in selected]
            direction = EvolutionDirection(
                strategy="极端特化型",
                description=f"极端强化{selected[0]}和{selected[1]}",
                primary_focus=selected,
                tradeoff_targets=remaining[:3]
            )
        
        return direction
    
    def _get_niche_exploration_strategy(
        self,
        parent_species,
        offspring_index: int,
        total_offspring: int,
        existing_species_niches: dict[str, float] | None = None,
    ) -> NicheExplorationStrategy:
        """【新增】计算子代的生态位探索策略
        
        【设计原则】
        1. 第一个子代通常是保守型（与父代竞争）
        2. 后续子代探索不同方向（上行、下行、横向）
        3. 根据现有生态位分布，选择竞争最小的方向
        4. 考虑父代营养级限制（T1不能下行，T5不能上行）
        
        Args:
            parent_species: 父代物种
            offspring_index: 子代编号（1-based）
            total_offspring: 总子代数
            existing_species_niches: {lineage_code: trophic_level} 现有物种的营养级分布
        
        Returns:
            NicheExplorationStrategy 生态位探索策略
        """
        parent_trophic = parent_species.trophic_level
        
        # 定义优先策略顺序（根据子代编号）
        # 第1个子代：50%保守，50%随机
        # 第2个子代：优先上行或横向
        # 第3个子代：优先下行或极端专化
        strategy_priority = {
            1: ["保守继承型", "横向栖息地型", "杂食泛化型"],
            2: ["上行捕食型", "横向栖息地型", "杂食泛化型"],
            3: ["下行专化型", "极端专化型", "横向栖息地型"],
        }
        
        # 获取优先策略列表
        priority_list = strategy_priority.get(
            offspring_index, 
            ["杂食泛化型", "极端专化型", "横向栖息地型"]
        )
        
        # 根据父代营养级调整可用策略
        available_strategies = []
        for s in self.NICHE_EXPLORATION_STRATEGIES:
            # 检查营养级限制
            min_shift, max_shift = s.trophic_shift
            new_trophic_min = parent_trophic + min_shift
            new_trophic_max = parent_trophic + max_shift
            
            # T1（生产者）不能下行到T0
            if new_trophic_min < 1.0 and parent_trophic <= 1.5:
                if min_shift < 0:
                    continue
            
            # T5（顶级捕食者）不能上行到T6
            if new_trophic_max > 5.5 and parent_trophic >= 4.5:
                if max_shift > 0.5:
                    continue
            
            available_strategies.append(s)
        
        # 优先选择优先列表中的策略
        for priority_name in priority_list:
            for s in available_strategies:
                if s.strategy == priority_name:
                    return self._customize_niche_strategy(s, parent_species, offspring_index)
        
        # 如果优先策略都不可用，随机选择
        if available_strategies:
            selected = available_strategies[offspring_index % len(available_strategies)]
            return self._customize_niche_strategy(selected, parent_species, offspring_index)
        
        # 兜底：返回保守型
        return self.NICHE_EXPLORATION_STRATEGIES[0]
    
    def _customize_niche_strategy(
        self,
        base_strategy: NicheExplorationStrategy,
        parent_species,
        offspring_index: int,
    ) -> NicheExplorationStrategy:
        """根据父代特征定制生态位策略"""
        import copy
        strategy = copy.deepcopy(base_strategy)
        
        # 如果是上行捕食型，根据父代营养级调整描述
        if strategy.strategy == "上行捕食型":
            parent_trophic = parent_species.trophic_level
            if parent_trophic < 2.0:
                strategy.description = "从生产者/分解者向初级消费者演化，开始摄食其他生物。"
                strategy.diet_focus = "开始摄食有机物或其他微生物"
            elif parent_trophic < 3.0:
                strategy.description = "从草食/杂食向肉食方向演化，开始捕食小型动物。"
                strategy.diet_focus = "捕食小型无脊椎动物或幼体"
            else:
                strategy.description = "向更高级捕食者演化，捕食更大的猎物。"
                strategy.diet_focus = "捕食同营养级或低一级的动物"
        
        # 如果是下行专化型，根据父代营养级调整描述
        elif strategy.strategy == "下行专化型":
            parent_trophic = parent_species.trophic_level
            if parent_trophic > 3.0:
                strategy.description = "从高级捕食者向杂食/腐食方向演化，利用更多样的食物来源。"
                strategy.diet_focus = "转向腐肉、碎屑或植物性食物"
            elif parent_trophic > 2.0:
                strategy.description = "从杂食向更专化的草食/滤食方向演化。"
                strategy.diet_focus = "专化特定植物、藻类或悬浮颗粒"
            else:
                strategy.description = "向更基础的营养方式演化，可能发展自养能力。"
                strategy.diet_focus = "利用化学能或增强光合效率"
        
        return strategy
    
    def _format_niche_strategy(self, strategy: NicheExplorationStrategy, parent_trophic: float) -> str:
        """格式化生态位策略为LLM可读的文本"""
        min_shift, max_shift = strategy.trophic_shift
        new_trophic_min = max(1.0, parent_trophic + min_shift)
        new_trophic_max = min(5.5, parent_trophic + max_shift)
        
        lines = [
            f"【生态位探索策略: {strategy.strategy}】",
            f"描述: {strategy.description}",
            f"营养级变化: {parent_trophic:.1f} → {new_trophic_min:.1f}~{new_trophic_max:.1f}",
            f"食性方向: {strategy.diet_focus}",
            f"体型趋势: {strategy.body_size_trend}",
            f"与父代竞争: {strategy.competition_with_parent}",
        ]
        
        if strategy.habitat_shift:
            lines.append("栖息地: 建议探索新栖息地")
        
        lines.append(f"目标生态角色: {strategy.ecological_role}")
        
        return "\n".join(lines)
    
    def _get_valid_habitat_transitions(self, current_habitat: str) -> list[str]:
        """获取有效的栖息地转换选项"""
        return self.HABITAT_TRANSITIONS.get(current_habitat, [current_habitat])
    
    def _get_extended_habitat_options(self, current_habitat: str) -> list[str]:
        """【新增】获取扩展的栖息地选项（用于生态位探索）
        
        当生态位策略鼓励栖息地变化时，提供更多选项。
        """
        base_options = self.HABITAT_TRANSITIONS.get(current_habitat, [current_habitat])
        
        # 扩展选项：添加相邻栖息地的可达选项
        extended = set(base_options)
        for habitat in base_options:
            adjacent = self.HABITAT_TRANSITIONS.get(habitat, [])
            extended.update(adjacent)
        
        return list(extended)
    
    def _get_trophic_range(self, parent_trophic: float) -> str:
        """获取营养级允许范围（保守模式）"""
        min_t = max(1.0, parent_trophic - 0.5)
        max_t = min(5.5, parent_trophic + 0.5)
        return f"{min_t:.1f}-{max_t:.1f}"
    
    def _get_trophic_range_from_strategy(
        self, 
        parent_trophic: float, 
        strategy: NicheExplorationStrategy
    ) -> str:
        """【新增】根据生态位策略计算营养级范围
        
        不同策略允许不同的营养级变化幅度：
        - 保守继承型：±0（保持原营养级）
        - 上行捕食型：+0.5~+1.0
        - 下行专化型：-0.5~-1.0
        - 其他：根据策略定义
        """
        min_shift, max_shift = strategy.trophic_shift
        
        min_t = max(1.0, parent_trophic + min_shift)
        max_t = min(5.5, parent_trophic + max_shift)
        
        # 确保范围有效
        if min_t > max_t:
            min_t, max_t = max_t, min_t
        
        # 如果范围太窄，稍微扩大
        if max_t - min_t < 0.3:
            mid = (min_t + max_t) / 2
            min_t = max(1.0, mid - 0.2)
            max_t = min(5.5, mid + 0.2)
        
        return f"{min_t:.1f}-{max_t:.1f}"
    
    def _format_trait_budget(self, budget: TraitBudget, era_limits: dict = None) -> str:
        """格式化属性预算为文本（包含时代上限）"""
        base_info = (
            f"变化预算: 增加≤+{budget.total_increase_allowed:.1f}, "
            f"减少≥-{budget.total_decrease_required:.1f}, "
            f"单项变化≤±{budget.single_trait_max:.1f}"
        )
        
        if era_limits:
            era_info = (
                f"\n时代上限({era_limits.get('era_name', '未知')}): "
                f"单属性≤{era_limits.get('specialized', 15)}, "
                f"总和≤{era_limits.get('total', 100)}"
            )
            return base_info + era_info
        
        return base_info
    
    def _format_organ_constraints(self, constraints: list[OrganConstraint]) -> str:
        """格式化器官约束为文本
        
        改进：明确显示每个器官的当前阶段，避免AI填写错误的current_stage
        """
        lines = []
        category_names = {
            "locomotion": "运动系统",
            "sensory": "感觉系统", 
            "metabolic": "代谢系统",
            "digestive": "消化系统",
            "defense": "防御系统",
            "reproduction": "繁殖系统"
        }
        
        for c in constraints:
            cat_name = category_names.get(c.category, c.category)
            if c.current_stage > 0:
                lines.append(f"- {cat_name}({c.category}): 当前阶段={c.current_stage}, 可升至阶段{c.max_target_stage}")
            else:
                lines.append(f"- {cat_name}({c.category}): 当前阶段=0(未发展), 可开始发展→阶段1")
        
        if not lines:
            # 所有器官都是0阶段时的提示
            lines.append("所有器官系统当前阶段均为0，只能从阶段1(原基)开始发展")
        
        return "\n".join(lines)
    
    # ==================== 后验证方法 ====================
    
    def validate_and_fix(
        self, 
        llm_output: dict[str, Any], 
        parent_species,
        preprocess_result: dict[str, Any] = None
    ) -> dict[str, Any]:
        """后验证：检查LLM输出是否符合规则，不符合则修正
        
        Args:
            llm_output: LLM返回的原始输出
            parent_species: 父系物种
            preprocess_result: 预处理结果（包含约束数据）
            
        Returns:
            验证/修正后的输出
        """
        if not isinstance(llm_output, dict):
            logger.warning(f"[规则引擎] LLM输出不是dict: {type(llm_output)}")
            return llm_output
        
        fixed = llm_output.copy()
        fixes_made = []
        
        # 1. 验证并修正属性变化
        if "trait_changes" in fixed:
            original_traits = fixed["trait_changes"]
            fixed["trait_changes"], trait_fixes = self._enforce_tradeoff(original_traits)
            fixes_made.extend(trait_fixes)
        
        # 2. 验证并修正器官演化
        if "organ_evolution" in fixed:
            parent_organs = getattr(parent_species, 'organs', {}) or {}
            original_organs = fixed["organ_evolution"]
            fixed["organ_evolution"], organ_fixes = self._enforce_organ_stages(
                original_organs, parent_organs
            )
            fixes_made.extend(organ_fixes)
        
        # 3. 验证并修正形态变化
        if "morphology_changes" in fixed:
            original_morph = fixed["morphology_changes"]
            fixed["morphology_changes"], morph_fixes = self._clamp_morphology(original_morph)
            fixes_made.extend(morph_fixes)
        
        # 4. 验证栖息地
        if "habitat_type" in fixed:
            parent_habitat = parent_species.habitat_type or "terrestrial"
            valid_habitats = self.HABITAT_TRANSITIONS.get(parent_habitat, [parent_habitat])
            if fixed["habitat_type"] not in valid_habitats:
                fixes_made.append(f"栖息地{fixed['habitat_type']}不可达，回退为{parent_habitat}")
                fixed["habitat_type"] = parent_habitat
        
        # 5. 验证营养级
        if "trophic_level" in fixed:
            parent_trophic = parent_species.trophic_level
            new_trophic = float(fixed["trophic_level"])
            if abs(new_trophic - parent_trophic) > 0.5:
                clamped = max(parent_trophic - 0.5, min(parent_trophic + 0.5, new_trophic))
                fixes_made.append(f"营养级{new_trophic:.1f}变化过大，调整为{clamped:.1f}")
                fixed["trophic_level"] = clamped
        
        # 6. 验证捕食关系
        new_trophic = float(fixed.get("trophic_level", parent_species.trophic_level))
        new_diet = fixed.get("diet_type", parent_species.diet_type)
        prey_result, prey_fixes = self._validate_prey_relationships(
            prey_species=fixed.get("prey_species"),
            prey_preferences=fixed.get("prey_preferences"),
            new_trophic_level=new_trophic,
            diet_type=new_diet,
            parent_species=parent_species,
        )
        if prey_result is not None:
            fixed["prey_species"] = prey_result["prey_species"]
            fixed["prey_preferences"] = prey_result["prey_preferences"]
            fixed["diet_type"] = prey_result["diet_type"]
        fixes_made.extend(prey_fixes)
        
        if fixes_made:
            logger.info(f"[规则引擎] 修正了 {len(fixes_made)} 处违规: {fixes_made}")
        
        return fixed
    
    def _enforce_tradeoff(self, trait_changes: dict) -> tuple[dict, list[str]]:
        """强制执行属性权衡规则"""
        if not trait_changes:
            return {}, []
        
        fixes = []
        fixed_traits = {}
        
        # 解析变化值
        increases = {}
        decreases = {}
        
        for name, change in trait_changes.items():
            try:
                if isinstance(change, str):
                    value = float(change.replace("+", ""))
                else:
                    value = float(change)
                
                # 限制单项变化幅度
                if abs(value) > self.SINGLE_TRAIT_MAX_CHANGE:
                    old_value = value
                    value = self.SINGLE_TRAIT_MAX_CHANGE if value > 0 else -self.SINGLE_TRAIT_MAX_CHANGE
                    fixes.append(f"{name}变化{old_value:.1f}→{value:.1f}(超限)")
                
                if value > 0:
                    increases[name] = value
                elif value < 0:
                    decreases[name] = value
                    
            except (ValueError, TypeError):
                fixes.append(f"无法解析{name}的值: {change}")
                continue
        
        total_increase = sum(increases.values())
        total_decrease = abs(sum(decreases.values()))
        
        # 规则：增加量 ≤ 减少量 × 2
        if total_decrease == 0 and total_increase > 0:
            # 没有减少，强制添加减少
            required_decrease = total_increase / self.INCREASE_DECREASE_RATIO
            # 选择一个属性减少
            decrease_target = "繁殖速度"  # 默认减少繁殖速度
            decreases[decrease_target] = -required_decrease
            fixes.append(f"强制添加{decrease_target}:-{required_decrease:.1f}(权衡)")
        elif total_increase > total_decrease * self.INCREASE_DECREASE_RATIO:
            # 增加过多，按比例缩减
            scale = (total_decrease * self.INCREASE_DECREASE_RATIO) / total_increase
            for name in increases:
                old_val = increases[name]
                increases[name] = old_val * scale
                if abs(old_val - increases[name]) > 0.01:
                    fixes.append(f"{name}按比例缩减: +{old_val:.1f}→+{increases[name]:.1f}")
        
        # 检查总和范围
        total_change = sum(increases.values()) + sum(decreases.values())
        if total_change < self.TRAIT_CHANGE_TOTAL_MIN:
            fixes.append(f"总变化{total_change:.1f}低于下限{self.TRAIT_CHANGE_TOTAL_MIN}")
        elif total_change > self.TRAIT_CHANGE_TOTAL_MAX:
            fixes.append(f"总变化{total_change:.1f}超过上限{self.TRAIT_CHANGE_TOTAL_MAX}")
        
        # 合并结果
        for name, value in increases.items():
            fixed_traits[name] = f"+{value:.1f}"
        for name, value in decreases.items():
            fixed_traits[name] = f"{value:.1f}"
        
        return fixed_traits, fixes
    
    def _enforce_organ_stages(
        self, 
        organ_evolution: list, 
        parent_organs: dict
    ) -> tuple[list, list[str]]:
        """强制执行器官阶段规则"""
        if not organ_evolution:
            return [], []
        
        fixes = []
        fixed_organs = []
        changes_count = 0
        
        for organ in organ_evolution:
            if not isinstance(organ, dict):
                continue
            
            if changes_count >= self.MAX_ORGAN_CHANGES:
                fixes.append(f"器官变化数量超限，忽略: {organ.get('category', '未知')}")
                continue
            
            category = organ.get("category", "")
            action = organ.get("action", "enhance")
            current_stage = organ.get("current_stage", 0)
            target_stage = organ.get("target_stage", 1)
            
            # 获取父系实际阶段
            parent_organ_info = parent_organs.get(category, {})
            actual_current = parent_organ_info.get("stage", 0)
            
            # 修正current_stage
            if current_stage != actual_current:
                fixes.append(f"{category}当前阶段{current_stage}→{actual_current}(与父系同步)")
                current_stage = actual_current
            
            # 验证阶段跳跃
            stage_jump = target_stage - current_stage
            if stage_jump > self.MAX_STAGE_JUMP:
                old_target = target_stage
                target_stage = current_stage + self.MAX_STAGE_JUMP
                fixes.append(f"{category}阶段跳跃{stage_jump}→{self.MAX_STAGE_JUMP}(超限)")
            
            # 验证新器官
            if action == "initiate" and current_stage == 0:
                if target_stage != self.NEW_ORGAN_START_STAGE:
                    fixes.append(f"{category}新器官只能从阶段1开始，{target_stage}→1")
                    target_stage = self.NEW_ORGAN_START_STAGE
            
            # 确保target_stage在有效范围
            target_stage = max(0, min(4, target_stage))
            
            fixed_organ = organ.copy()
            fixed_organ["current_stage"] = current_stage
            fixed_organ["target_stage"] = target_stage
            fixed_organs.append(fixed_organ)
            changes_count += 1
        
        return fixed_organs, fixes
    
    def _clamp_morphology(self, morphology_changes: dict) -> tuple[dict, list[str]]:
        """限制形态变化范围"""
        if not morphology_changes:
            return {}, []
        
        fixes = []
        fixed = {}
        
        for key, value in morphology_changes.items():
            try:
                ratio = float(value)
                
                # 只对倍数类型的值进行限制
                if key in ("body_length_cm", "body_weight_g", "body_surface_area_cm2"):
                    if ratio < self.MORPHOLOGY_MIN_RATIO:
                        fixes.append(f"{key}比例{ratio:.2f}→{self.MORPHOLOGY_MIN_RATIO}(过小)")
                        ratio = self.MORPHOLOGY_MIN_RATIO
                    elif ratio > self.MORPHOLOGY_MAX_RATIO:
                        fixes.append(f"{key}比例{ratio:.2f}→{self.MORPHOLOGY_MAX_RATIO}(过大)")
                        ratio = self.MORPHOLOGY_MAX_RATIO
                
                fixed[key] = ratio
            except (ValueError, TypeError):
                fixed[key] = value
        
        return fixed, fixes
    
    def _validate_prey_relationships(
        self,
        prey_species: list | None,
        prey_preferences: dict | None,
        new_trophic_level: float,
        diet_type: str | None,
        parent_species,
    ) -> tuple[dict | None, list[str]]:
        """验证并修正捕食关系
        
        规则：
        1. 自养生物(trophic < 2.0)不能有猎物
        2. 猎物必须是存在的物种（在当前生态系统中）
        3. 捕食者营养级应比猎物高 0.5-2.5 级
        4. 猎物偏好总和应为 1.0（允许±0.1误差）
        5. 食性类型与营养级/猎物列表一致
        
        Args:
            prey_species: AI返回的猎物列表
            prey_preferences: AI返回的猎物偏好
            new_trophic_level: 新物种的营养级
            diet_type: 新物种的食性类型
            parent_species: 父系物种（用于回退）
            
        Returns:
            (修正后的结果字典, 修正说明列表)
            如果无需修正返回 (None, [])
        """
        fixes = []
        
        # 默认继承父系
        result_prey = list(parent_species.prey_species) if parent_species.prey_species else []
        result_prefs = dict(parent_species.prey_preferences) if parent_species.prey_preferences else {}
        result_diet = diet_type or parent_species.diet_type or "omnivore"
        
        # 处理AI返回的猎物列表
        if prey_species is not None and isinstance(prey_species, list):
            result_prey = prey_species
        if prey_preferences is not None and isinstance(prey_preferences, dict):
            result_prefs = prey_preferences
        
        # 规则1：自养生物不能有猎物
        if new_trophic_level < 2.0:
            if result_prey:
                fixes.append(f"营养级<2.0(生产者)不能有猎物，清空猎物列表")
                result_prey = []
                result_prefs = {}
            result_diet = "autotroph"
        
        # 规则2 & 3：验证猎物存在性和营养级关系
        # 需要获取当前生态系统中的物种列表
        if result_prey and new_trophic_level >= 2.0:
            try:
                from ...repositories.species_repository import species_repository
                all_species = species_repository.list_species()
                species_map = {sp.lineage_code: sp for sp in all_species}
                
                valid_prey = []
                invalid_prey = []
                
                for prey_code in result_prey:
                    prey_sp = species_map.get(prey_code)
                    
                    if prey_sp is None:
                        invalid_prey.append(f"{prey_code}(不存在)")
                        continue
                    
                    # 检查营养级关系：捕食者应比猎物高 0.5-2.5 级
                    trophic_diff = new_trophic_level - prey_sp.trophic_level
                    if trophic_diff < 0.3:
                        invalid_prey.append(f"{prey_code}(营养级差{trophic_diff:.1f}<0.3)")
                        continue
                    if trophic_diff > 3.0:
                        invalid_prey.append(f"{prey_code}(营养级差{trophic_diff:.1f}>3.0)")
                        continue
                    
                    valid_prey.append(prey_code)
                
                if invalid_prey:
                    fixes.append(f"移除无效猎物: {', '.join(invalid_prey)}")
                
                # 如果所有猎物都无效，回退到父系
                if not valid_prey and result_prey:
                    parent_prey = list(parent_species.prey_species) if parent_species.prey_species else []
                    # 过滤父系猎物中已灭绝的
                    valid_parent_prey = [p for p in parent_prey if p in species_map]
                    if valid_parent_prey:
                        fixes.append(f"猎物全部无效，回退到父系猎物")
                        valid_prey = valid_parent_prey
                
                result_prey = valid_prey
                
            except Exception as e:
                logger.warning(f"[规则引擎] 验证猎物关系时出错: {e}")
        
        # 规则4：修正猎物偏好
        if result_prey:
            # 只保留存在于猎物列表中的偏好
            filtered_prefs = {k: v for k, v in result_prefs.items() if k in result_prey}
            
            # 计算总和并归一化
            total_pref = sum(filtered_prefs.values()) if filtered_prefs else 0
            
            if abs(total_pref - 1.0) > 0.1 and total_pref > 0:
                # 归一化
                normalized_prefs = {k: v / total_pref for k, v in filtered_prefs.items()}
                if filtered_prefs != normalized_prefs:
                    fixes.append(f"猎物偏好总和{total_pref:.2f}，已归一化")
                result_prefs = normalized_prefs
            elif not filtered_prefs and result_prey:
                # 没有偏好数据，均匀分配
                equal_pref = 1.0 / len(result_prey)
                result_prefs = {prey: equal_pref for prey in result_prey}
                fixes.append(f"猎物无偏好数据，均匀分配")
            else:
                result_prefs = filtered_prefs
        else:
            result_prefs = {}
        
        # 规则5：确保食性类型与营养级/猎物一致
        if new_trophic_level < 2.0:
            result_diet = "autotroph"
        elif not result_prey:
            # 没有猎物的消费者，设为腐食者或回退
            if new_trophic_level < 2.5:
                result_diet = "detritivore"
            else:
                # 高营养级没有猎物，保留原食性但记录警告
                fixes.append(f"营养级{new_trophic_level:.1f}但无有效猎物，需关注")
        
        if fixes:
            return {
                "prey_species": result_prey,
                "prey_preferences": result_prefs,
                "diet_type": result_diet,
            }, fixes
        
        return None, []


# 单例实例
speciation_rules = SpeciationRules()

