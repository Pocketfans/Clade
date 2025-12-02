"""智能游戏提示服务

基于当前游戏状态生成实时策略提示，帮助玩家理解生态系统动态。

提示类型：
- warning: 警告类（物种濒危、生态失衡）
- opportunity: 机会类（空白生态位、适宜扩张）
- evolution: 演化类（分化可能、适应趋势）
- competition: 竞争类（生态位重叠、资源争夺）
- ecosystem: 生态类（食物链问题、多样性变化）
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ...models.species import Species
    from ...schemas.responses import TurnReport

logger = logging.getLogger(__name__)


class HintPriority(str, Enum):
    """提示优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HintType(str, Enum):
    """提示类型"""
    WARNING = "warning"  # 警告
    OPPORTUNITY = "opportunity"  # 机会
    EVOLUTION = "evolution"  # 演化
    COMPETITION = "competition"  # 竞争
    ECOSYSTEM = "ecosystem"  # 生态


@dataclass
class GameHint:
    """游戏提示"""
    hint_type: HintType
    priority: HintPriority
    title: str
    message: str
    icon: str
    related_species: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "type": self.hint_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "message": self.message,
            "icon": self.icon,
            "related_species": self.related_species,
            "suggested_actions": self.suggested_actions,
        }


class GameHintsService:
    """智能游戏提示服务
    
    分析游戏状态并生成有用的提示。
    """
    
    # 优先级权重（用于排序）
    PRIORITY_WEIGHTS = {
        HintPriority.CRITICAL: 100,
        HintPriority.HIGH: 50,
        HintPriority.MEDIUM: 20,
        HintPriority.LOW: 5,
    }
    
    def __init__(self, max_hints: int = 5):
        """
        Args:
            max_hints: 每次最多返回的提示数
        """
        self.max_hints = max_hints
        self._last_hints: list[GameHint] = []
        self._hint_cooldown: dict[str, int] = {}  # 提示冷却（避免重复）
    
    def generate_hints(
        self,
        all_species: Sequence["Species"],
        current_turn: int,
        recent_report: "TurnReport | None" = None,
        previous_report: "TurnReport | None" = None,
    ) -> list[GameHint]:
        """生成游戏提示
        
        Args:
            all_species: 所有物种
            current_turn: 当前回合
            recent_report: 最近的回合报告
            previous_report: 上一回合报告（用于比较）
        
        Returns:
            提示列表（按优先级排序）
        """
        hints: list[GameHint] = []
        alive_species = [sp for sp in all_species if sp.status == "alive"]
        
        # 更新冷却
        expired_keys = [k for k, v in self._hint_cooldown.items() if v <= current_turn]
        for k in expired_keys:
            del self._hint_cooldown[k]
        
        # === 濒危警告 ===
        hints.extend(self._check_endangered_species(alive_species, current_turn))
        
        # === 生态失衡 ===
        hints.extend(self._check_ecosystem_balance(alive_species, current_turn))
        
        # === 演化机会 ===
        hints.extend(self._check_evolution_opportunities(alive_species, current_turn, recent_report))
        
        # === 竞争警告 ===
        hints.extend(self._check_competition(alive_species, current_turn))
        
        # === 食物链问题 ===
        hints.extend(self._check_food_chain(alive_species, current_turn))
        
        # === 多样性提示 ===
        hints.extend(self._check_biodiversity(alive_species, current_turn, recent_report, previous_report))
        
        # 过滤冷却中的提示
        hints = [h for h in hints if self._get_hint_key(h) not in self._hint_cooldown]
        
        # 按优先级排序
        hints.sort(key=lambda h: self.PRIORITY_WEIGHTS.get(h.priority, 0), reverse=True)
        
        # 限制数量
        hints = hints[:self.max_hints]
        
        # 设置冷却
        for hint in hints:
            key = self._get_hint_key(hint)
            cooldown_turns = 3 if hint.priority in (HintPriority.LOW, HintPriority.MEDIUM) else 5
            self._hint_cooldown[key] = current_turn + cooldown_turns
        
        self._last_hints = hints
        return hints
    
    def _get_hint_key(self, hint: GameHint) -> str:
        """获取提示的唯一标识（用于冷却判断）"""
        species_key = "_".join(sorted(hint.related_species[:2])) if hint.related_species else ""
        return f"{hint.hint_type.value}:{hint.title}:{species_key}"
    
    def _check_endangered_species(self, alive_species: Sequence["Species"], turn: int) -> list[GameHint]:
        """检查濒危物种"""
        hints = []
        
        for sp in alive_species:
            pop = sp.morphology_stats.get("population", 0) or 0
            
            # 极度濒危（<100）
            if pop < 100 and pop > 0:
                hints.append(GameHint(
                    hint_type=HintType.WARNING,
                    priority=HintPriority.CRITICAL,
                    title="物种濒临灭绝",
                    message=f"{sp.common_name}（{sp.lineage_code}）种群仅剩 {pop:,} 个体，随时可能灭绝！",
                    icon="🆘",
                    related_species=[sp.lineage_code],
                    suggested_actions=[
                        "考虑使用「保护」干预降低死亡率",
                        "减少对该栖息地的环境压力",
                        "检查其猎物是否充足"
                    ],
                ))
            # 濒危（<1000）
            elif pop < 1000:
                hints.append(GameHint(
                    hint_type=HintType.WARNING,
                    priority=HintPriority.HIGH,
                    title="物种数量告急",
                    message=f"{sp.common_name} 种群下降至 {pop:,}，需要关注。",
                    icon="⚠️",
                    related_species=[sp.lineage_code],
                    suggested_actions=[
                        "观察种群趋势",
                        "检查生态位竞争情况"
                    ],
                ))
        
        return hints
    
    def _check_ecosystem_balance(self, alive_species: Sequence["Species"], turn: int) -> list[GameHint]:
        """检查生态系统平衡"""
        hints = []
        
        if len(alive_species) < 3:
            hints.append(GameHint(
                hint_type=HintType.ECOSYSTEM,
                priority=HintPriority.HIGH,
                title="生态系统脆弱",
                message=f"当前仅有 {len(alive_species)} 个存活物种，生态系统极不稳定。",
                icon="🏜️",
                suggested_actions=[
                    "考虑引入新物种丰富生态系统",
                    "避免施加过强的环境压力"
                ],
            ))
            return hints
        
        # 统计营养级分布
        trophic_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for sp in alive_species:
            level = min(5, max(1, int(sp.trophic_level)))
            trophic_counts[level] += 1
        
        # 检查生产者不足
        if trophic_counts[1] == 0:
            hints.append(GameHint(
                hint_type=HintType.ECOSYSTEM,
                priority=HintPriority.CRITICAL,
                title="缺乏生产者",
                message="生态系统没有生产者（T1），整个食物链将崩溃！",
                icon="🌱",
                suggested_actions=[
                    "立即引入生产者物种（如藻类、植物）",
                    "降低环境压力以保护现有物种"
                ],
            ))
        elif trophic_counts[1] < 2:
            hints.append(GameHint(
                hint_type=HintType.ECOSYSTEM,
                priority=HintPriority.HIGH,
                title="生产者稀少",
                message="生产者物种过少，可能无法支撑整个食物链。",
                icon="🌿",
                suggested_actions=["考虑引入更多生产者物种"],
            ))
        
        # 检查消费者过多
        producers_pop = sum(
            sp.morphology_stats.get("population", 0) or 0
            for sp in alive_species if sp.trophic_level < 2
        )
        consumers_pop = sum(
            sp.morphology_stats.get("population", 0) or 0
            for sp in alive_species if sp.trophic_level >= 2
        )
        
        if producers_pop > 0 and consumers_pop / producers_pop > 0.5:
            hints.append(GameHint(
                hint_type=HintType.ECOSYSTEM,
                priority=HintPriority.MEDIUM,
                title="消费者压力过大",
                message="消费者种群相对于生产者过多，可能导致食物短缺。",
                icon="⚖️",
                suggested_actions=[
                    "增强生产者种群",
                    "适度压制部分消费者"
                ],
            ))
        
        return hints
    
    def _check_evolution_opportunities(
        self, 
        alive_species: Sequence["Species"], 
        turn: int,
        recent_report: "TurnReport | None"
    ) -> list[GameHint]:
        """检查演化机会"""
        hints = []
        
        for sp in alive_species:
            pop = sp.morphology_stats.get("population", 0) or 0
            
            # 高种群 + 压力可能触发分化
            if pop > 100000:
                stress = sp.stress_exposure or {}
                total_stress = sum(stress.values())
                
                if total_stress > 3:
                    hints.append(GameHint(
                        hint_type=HintType.EVOLUTION,
                        priority=HintPriority.MEDIUM,
                        title="分化条件成熟",
                        message=f"{sp.common_name} 种群庞大且承受环境压力，可能即将分化出新物种。",
                        icon="🧬",
                        related_species=[sp.lineage_code],
                        suggested_actions=[
                            "继续施加压力促进分化",
                            "观察下一回合的演化事件"
                        ],
                    ))
        
        # 最近有分化事件
        if recent_report and recent_report.branching_events:
            # 使用 new_lineage 属性（BranchingEvent 的正确属性名）
            new_species = [e.new_lineage for e in recent_report.branching_events]
            if new_species:
                hints.append(GameHint(
                    hint_type=HintType.EVOLUTION,
                    priority=HintPriority.LOW,
                    title="新物种诞生",
                    message=f"物种分化产生了 {len(new_species)} 个新物种，它们可能有独特的适应性。",
                    icon="✨",
                    related_species=new_species,
                    suggested_actions=[
                        "观察新物种的生态位",
                        "关注它们与祖先的竞争关系"
                    ],
                ))
        
        return hints
    
    def _check_competition(self, alive_species: Sequence["Species"], turn: int) -> list[GameHint]:
        """检查竞争情况"""
        hints = []
        
        # 按营养级分组
        by_trophic: dict[int, list["Species"]] = {}
        for sp in alive_species:
            level = int(sp.trophic_level)
            if level not in by_trophic:
                by_trophic[level] = []
            by_trophic[level].append(sp)
        
        # 检查同营养级竞争
        for level, species_list in by_trophic.items():
            if len(species_list) >= 3:
                # 同营养级物种过多
                names = [sp.common_name for sp in species_list[:3]]
                hints.append(GameHint(
                    hint_type=HintType.COMPETITION,
                    priority=HintPriority.MEDIUM,
                    title=f"T{level} 竞争激烈",
                    message=f"{', '.join(names)} 等 {len(species_list)} 个物种在同一营养级竞争资源。",
                    icon="🥊",
                    related_species=[sp.lineage_code for sp in species_list[:3]],
                    suggested_actions=[
                        "施加压力可能淘汰弱势物种",
                        "观察生态位分化是否发生"
                    ],
                ))
        
        # 检查同栖息地竞争
        by_habitat: dict[str, list["Species"]] = {}
        for sp in alive_species:
            habitat = sp.habitat_type or "unknown"
            if habitat not in by_habitat:
                by_habitat[habitat] = []
            by_habitat[habitat].append(sp)
        
        for habitat, species_list in by_habitat.items():
            if len(species_list) >= 5:
                hints.append(GameHint(
                    hint_type=HintType.COMPETITION,
                    priority=HintPriority.LOW,
                    title=f"{habitat} 栖息地拥挤",
                    message=f"{len(species_list)} 个物种聚集在 {habitat} 栖息地，可能存在资源竞争。",
                    icon="🏠",
                    related_species=[sp.lineage_code for sp in species_list[:2]],
                    suggested_actions=["考虑引导物种向其他栖息地迁徙"],
                ))
        
        return hints
    
    def _check_food_chain(self, alive_species: Sequence["Species"], turn: int) -> list[GameHint]:
        """检查食物链问题"""
        hints = []
        
        # 统计猎物关系
        species_map = {sp.lineage_code: sp for sp in alive_species}
        
        for sp in alive_species:
            if sp.trophic_level < 2:
                continue  # 生产者不需要猎物
            
            prey_codes = sp.prey_species or []
            alive_prey = [code for code in prey_codes if code in species_map]
            
            # 猎物全部灭绝
            if prey_codes and not alive_prey:
                hints.append(GameHint(
                    hint_type=HintType.WARNING,
                    priority=HintPriority.CRITICAL,
                    title="食物来源断绝",
                    message=f"{sp.common_name} 的所有猎物已灭绝，它将面临饥荒！",
                    icon="🍽️",
                    related_species=[sp.lineage_code],
                    suggested_actions=[
                        "引入新的猎物物种",
                        "期待该物种适应新食物来源"
                    ],
                ))
            # 猎物稀少
            elif prey_codes and len(alive_prey) == 1:
                prey_sp = species_map.get(alive_prey[0])
                prey_name = prey_sp.common_name if prey_sp else alive_prey[0]
                hints.append(GameHint(
                    hint_type=HintType.WARNING,
                    priority=HintPriority.HIGH,
                    title="食物来源单一",
                    message=f"{sp.common_name} 仅依赖 {prey_name} 为食，食物链非常脆弱。",
                    icon="🔗",
                    related_species=[sp.lineage_code, alive_prey[0]],
                    suggested_actions=["保护猎物物种", "观察是否发展出替代食物来源"],
                ))
        
        return hints
    
    def _check_biodiversity(
        self,
        alive_species: Sequence["Species"],
        turn: int,
        recent_report: "TurnReport | None",
        previous_report: "TurnReport | None",
    ) -> list[GameHint]:
        """检查多样性变化"""
        hints = []
        
        current_count = len(alive_species)
        
        # 与上一回合比较
        if recent_report and previous_report:
            prev_alive = sum(1 for sp in previous_report.species if sp.status == "alive")
            
            # 物种急剧减少
            if prev_alive > 0:
                loss_rate = (prev_alive - current_count) / prev_alive
                if loss_rate > 0.3:
                    hints.append(GameHint(
                        hint_type=HintType.ECOSYSTEM,
                        priority=HintPriority.CRITICAL,
                        title="物种大量灭绝",
                        message=f"本回合有 {prev_alive - current_count} 个物种灭绝（损失 {loss_rate*100:.0f}%）",
                        icon="💀",
                        suggested_actions=[
                            "降低环境压力强度",
                            "考虑保护剩余物种"
                        ],
                    ))
                elif loss_rate > 0.1:
                    hints.append(GameHint(
                        hint_type=HintType.WARNING,
                        priority=HintPriority.HIGH,
                        title="多样性下降",
                        message=f"本回合损失了 {prev_alive - current_count} 个物种。",
                        icon="📉",
                        suggested_actions=["关注濒危物种"],
                    ))
            
            # 物种快速增加（分化爆发）
            if current_count > prev_alive * 1.3 and current_count - prev_alive >= 3:
                hints.append(GameHint(
                    hint_type=HintType.EVOLUTION,
                    priority=HintPriority.LOW,
                    title="适应辐射",
                    message=f"物种数量从 {prev_alive} 增加到 {current_count}，演化正在加速！",
                    icon="🌟",
                    suggested_actions=["这是丰富生态系统的好机会"],
                ))
        
        # 空白生态位提示
        trophic_levels = set(int(sp.trophic_level) for sp in alive_species)
        missing_levels = [i for i in range(1, 5) if i not in trophic_levels]
        
        if missing_levels and current_count >= 3:
            hints.append(GameHint(
                hint_type=HintType.OPPORTUNITY,
                priority=HintPriority.LOW,
                title="空缺生态位",
                message=f"T{', T'.join(map(str, missing_levels))} 营养级没有物种，存在演化机会。",
                icon="🎯",
                suggested_actions=[
                    "引入相应营养级的物种",
                    "施加压力促进现有物种填补空缺"
                ],
            ))
        
        return hints
    
    def get_last_hints(self) -> list[GameHint]:
        """获取上次生成的提示"""
        return self._last_hints
    
    def clear_cooldown(self) -> None:
        """清除提示冷却（新存档时调用）"""
        self._hint_cooldown.clear()
        self._last_hints.clear()


# 模块级单例
game_hints_service = GameHintsService()
