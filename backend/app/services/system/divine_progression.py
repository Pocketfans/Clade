"""神力进阶系统

整合四大子系统：
1. 神格专精 (Divine Paths) - 选择神格路线，获得专属能力
2. 信仰系统 (Faith System) - 物种成为信徒，贡献神力
3. 神迹系统 (Miracles) - 史诗级大型技能
4. 预言赌注 (Divine Wager) - 投资物种未来，获取回报
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Literal

logger = logging.getLogger(__name__)


# ==================== 神格专精系统 ====================

class DivinePath(str, Enum):
    """四大神格路线"""
    NONE = "none"           # 未选择
    CREATOR = "creator"     # 创世之神
    GUARDIAN = "guardian"   # 守护之神
    CHAOS = "chaos"         # 混沌之神
    ECOLOGY = "ecology"     # 生态之神


@dataclass
class DivinePathInfo:
    """神格信息"""
    path: DivinePath
    name: str
    icon: str
    description: str
    passive_bonus: str
    skills: list[str]
    color: str  # 主题色


DIVINE_PATHS: dict[DivinePath, DivinePathInfo] = {
    DivinePath.CREATOR: DivinePathInfo(
        path=DivinePath.CREATOR,
        name="创世之神",
        icon="🌱",
        description="专精于创造与繁荣，掌握生命诞生的奥秘",
        passive_bonus="创造物种消耗-30%，新物种初始适应力+0.1",
        skills=["始祖恩赐", "生命火种", "神启分化"],
        color="#10b981",  # 绿色
    ),
    DivinePath.GUARDIAN: DivinePathInfo(
        path=DivinePath.GUARDIAN,
        name="守护之神",
        icon="🛡️",
        description="专精于保护与稳定，守护生命免受灾厄",
        passive_bonus="保护效果+50%，持续时间×2，被保护物种种群增长+20%",
        skills=["不灭圣域", "生命庇护", "复苏之光"],
        color="#3b82f6",  # 蓝色
    ),
    DivinePath.CHAOS: DivinePathInfo(
        path=DivinePath.CHAOS,
        name="混沌之神",
        icon="⚡",
        description="专精于灾变与突变，掌握毁灭与重生的力量",
        passive_bonus="环境压力消耗-50%，压力强度+2，突变概率×2",
        skills=["大灭绝", "混沌突变", "末日风暴"],
        color="#ef4444",  # 红色
    ),
    DivinePath.ECOLOGY: DivinePathInfo(
        path=DivinePath.ECOLOGY,
        name="生态之神",
        icon="🌿",
        description="专精于平衡与共生，编织生命之网",
        passive_bonus="每维持5个共生关系，回复+2/回合；共生物种适应力+0.05",
        skills=["生态共鸣", "食物链重塑", "万物归一"],
        color="#8b5cf6",  # 紫色
    ),
}


@dataclass 
class DivineSkill:
    """神力技能定义"""
    id: str
    name: str
    path: DivinePath
    description: str
    cost: int
    cooldown: int  # 回合冷却
    unlock_level: int  # 需要的神格等级
    icon: str


# 所有神力技能定义
DIVINE_SKILLS: dict[str, DivineSkill] = {
    # 创世之神技能
    "ancestor_blessing": DivineSkill(
        id="ancestor_blessing",
        name="始祖恩赐",
        path=DivinePath.CREATOR,
        description="指定物种获得「始祖」标记，可开辟全新谱系分支",
        cost=25,
        cooldown=10,
        unlock_level=1,
        icon="👑",
    ),
    "life_spark": DivineSkill(
        id="life_spark",
        name="生命火种",
        path=DivinePath.CREATOR,
        description="使用AI在指定区域创造一个适应当地环境的基础生产者物种",
        cost=40,
        cooldown=15,
        unlock_level=2,
        icon="✨",
    ),
    "divine_speciation": DivineSkill(
        id="divine_speciation",
        name="神启分化",
        path=DivinePath.CREATOR,
        description="强制指定物种立即产生一个适应性分化",
        cost=35,
        cooldown=8,
        unlock_level=3,
        icon="🧬",
    ),
    
    # 守护之神技能
    "immortal_sanctuary": DivineSkill(
        id="immortal_sanctuary",
        name="不灭圣域",
        path=DivinePath.GUARDIAN,
        description="创建一个神圣区域，区域内物种5回合内免疫灭绝",
        cost=45,
        cooldown=20,
        unlock_level=1,
        icon="🏛️",
    ),
    "life_shelter": DivineSkill(
        id="life_shelter",
        name="生命庇护",
        path=DivinePath.GUARDIAN,
        description="选择一个物种，使其永久免疫下一次灭绝危机",
        cost=30,
        cooldown=12,
        unlock_level=2,
        icon="💫",
    ),
    "revival_light": DivineSkill(
        id="revival_light",
        name="复苏之光",
        path=DivinePath.GUARDIAN,
        description="复活最近灭绝的物种，恢复其灭绝前50%的种群规模",
        cost=60,
        cooldown=25,
        unlock_level=3,
        icon="🌅",
    ),
    
    # 混沌之神技能
    "mass_extinction": DivineSkill(
        id="mass_extinction",
        name="大灭绝",
        path=DivinePath.CHAOS,
        description="清除所有适应力<0.25的物种，存活者获得+0.1适应力",
        cost=50,
        cooldown=30,
        unlock_level=1,
        icon="💀",
    ),
    "chaos_mutation": DivineSkill(
        id="chaos_mutation",
        name="混沌突变",
        path=DivinePath.CHAOS,
        description="对目标物种施加剧烈突变，随机大幅改变其特征",
        cost=25,
        cooldown=8,
        unlock_level=2,
        icon="🔮",
    ),
    "doom_storm": DivineSkill(
        id="doom_storm",
        name="末日风暴",
        path=DivinePath.CHAOS,
        description="在目标区域释放毁灭性灾害，强度12的全类型压力",
        cost=40,
        cooldown=15,
        unlock_level=3,
        icon="🌪️",
    ),
    
    # 生态之神技能
    "eco_resonance": DivineSkill(
        id="eco_resonance",
        name="生态共鸣",
        path=DivinePath.ECOLOGY,
        description="自动在区域内所有兼容物种间建立最优共生网络",
        cost=35,
        cooldown=12,
        unlock_level=1,
        icon="🔗",
    ),
    "food_chain_reshape": DivineSkill(
        id="food_chain_reshape",
        name="食物链重塑",
        path=DivinePath.ECOLOGY,
        description="重新分配区域内的捕食关系，优化食物网结构",
        cost=30,
        cooldown=10,
        unlock_level=2,
        icon="🕸️",
    ),
    "all_is_one": DivineSkill(
        id="all_is_one",
        name="万物归一",
        path=DivinePath.ECOLOGY,
        description="临时将区域内所有物种视为同一生态位，消除竞争5回合",
        cost=45,
        cooldown=20,
        unlock_level=3,
        icon="☯️",
    ),
}


@dataclass
class PathProgress:
    """神格进度"""
    path: DivinePath = DivinePath.NONE
    level: int = 0  # 0-5级
    experience: int = 0  # 经验值
    skills_used: dict[str, int] = field(default_factory=dict)  # 技能使用次数
    unlocked_skills: list[str] = field(default_factory=list)
    
    # 副神格（高级解锁）
    secondary_path: DivinePath | None = None
    
    def to_dict(self) -> dict:
        return {
            "path": self.path.value,
            "level": self.level,
            "experience": self.experience,
            "skills_used": self.skills_used,
            "unlocked_skills": self.unlocked_skills,
            "secondary_path": self.secondary_path.value if self.secondary_path else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PathProgress":
        return cls(
            path=DivinePath(data.get("path", "none")),
            level=data.get("level", 0),
            experience=data.get("experience", 0),
            skills_used=data.get("skills_used", {}),
            unlocked_skills=data.get("unlocked_skills", []),
            secondary_path=DivinePath(data["secondary_path"]) if data.get("secondary_path") else None,
        )


# ==================== 信仰系统 ====================

@dataclass
class Follower:
    """信徒物种"""
    lineage_code: str
    common_name: str
    faith_value: float  # 信仰值
    turns_as_follower: int  # 成为信徒后的回合数
    is_blessed: bool = False  # 是否被「显圣」
    is_sanctified: bool = False  # 是否被「圣化」
    contribution_per_turn: float = 0.5  # 每回合贡献
    
    def to_dict(self) -> dict:
        return {
            "lineage_code": self.lineage_code,
            "common_name": self.common_name,
            "faith_value": self.faith_value,
            "turns_as_follower": self.turns_as_follower,
            "is_blessed": self.is_blessed,
            "is_sanctified": self.is_sanctified,
            "contribution_per_turn": self.contribution_per_turn,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Follower":
        return cls(
            lineage_code=data["lineage_code"],
            common_name=data.get("common_name", ""),
            faith_value=data.get("faith_value", 0),
            turns_as_follower=data.get("turns_as_follower", 0),
            is_blessed=data.get("is_blessed", False),
            is_sanctified=data.get("is_sanctified", False),
            contribution_per_turn=data.get("contribution_per_turn", 0.5),
        )


@dataclass
class FaithState:
    """信仰系统状态"""
    followers: dict[str, Follower] = field(default_factory=dict)  # lineage_code -> Follower
    total_faith: float = 0.0
    faith_bonus_per_turn: float = 0.0
    betrayal_debuff_turns: int = 0  # 「背叛惩罚」剩余回合
    
    def to_dict(self) -> dict:
        return {
            "followers": {k: v.to_dict() for k, v in self.followers.items()},
            "total_faith": self.total_faith,
            "faith_bonus_per_turn": self.faith_bonus_per_turn,
            "betrayal_debuff_turns": self.betrayal_debuff_turns,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FaithState":
        followers = {}
        for k, v in data.get("followers", {}).items():
            followers[k] = Follower.from_dict(v)
        return cls(
            followers=followers,
            total_faith=data.get("total_faith", 0.0),
            faith_bonus_per_turn=data.get("faith_bonus_per_turn", 0.0),
            betrayal_debuff_turns=data.get("betrayal_debuff_turns", 0),
        )


# ==================== 神迹系统 ====================

@dataclass
class Miracle:
    """神迹定义"""
    id: str
    name: str
    icon: str
    description: str
    cost: int
    cooldown: int  # 回合冷却
    charge_turns: int  # 蓄力回合数
    one_time: bool = False  # 是否一次性


MIRACLES: dict[str, Miracle] = {
    "genesis_flood": Miracle(
        id="genesis_flood",
        name="创世洪水",
        icon="🌊",
        description="海平面剧烈变化，重塑海岸线，所有沿海物种强制适应或迁移",
        cost=80,
        cooldown=30,
        charge_turns=3,
    ),
    "tree_of_life": Miracle(
        id="tree_of_life",
        name="生命之树",
        icon="🌳",
        description="随机选择3个物种立即产生分化，诞生全新物种",
        cost=60,
        cooldown=20,
        charge_turns=2,
    ),
    "judgement_day": Miracle(
        id="judgement_day",
        name="末日审判",
        icon="⚖️",
        description="清除所有适应力<0.25的物种，存活者获得永久+0.1适应力",
        cost=70,
        cooldown=25,
        charge_turns=3,
    ),
    "divine_sanctuary": Miracle(
        id="divine_sanctuary",
        name="神圣避难所",
        icon="🏛️",
        description="在指定区域创建圣域，区域内所有物种10回合内免疫灭绝",
        cost=75,
        cooldown=40,
        charge_turns=3,
    ),
    "great_prosperity": Miracle(
        id="great_prosperity",
        name="大繁荣",
        icon="✨",
        description="全局生产力×2持续5回合，所有物种种群增长加速",
        cost=50,
        cooldown=15,
        charge_turns=1,
    ),
    "miracle_evolution": Miracle(
        id="miracle_evolution",
        name="奇迹进化",
        icon="💫",
        description="选择一个物种，AI生成一个超越常理的全新演化分支",
        cost=100,
        cooldown=999,  # 一次性
        charge_turns=5,
        one_time=True,
    ),
}


@dataclass
class MiracleState:
    """神迹系统状态"""
    cooldowns: dict[str, int] = field(default_factory=dict)  # miracle_id -> 剩余冷却
    charging: str | None = None  # 正在蓄力的神迹ID
    charge_progress: int = 0  # 蓄力进度
    charge_reserved_energy: int = 0  # 蓄力锁定的能量
    used_one_time: list[str] = field(default_factory=list)  # 已使用的一次性神迹
    miracles_cast: int = 0  # 总释放次数
    
    def to_dict(self) -> dict:
        return {
            "cooldowns": self.cooldowns,
            "charging": self.charging,
            "charge_progress": self.charge_progress,
            "charge_reserved_energy": self.charge_reserved_energy,
            "used_one_time": self.used_one_time,
            "miracles_cast": self.miracles_cast,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MiracleState":
        return cls(
            cooldowns=data.get("cooldowns", {}),
            charging=data.get("charging"),
            charge_progress=data.get("charge_progress", 0),
            charge_reserved_energy=data.get("charge_reserved_energy", 0),
            used_one_time=data.get("used_one_time", []),
            miracles_cast=data.get("miracles_cast", 0),
        )


# ==================== 预言赌注系统 ====================

class WagerType(str, Enum):
    """预言类型"""
    DOMINANCE = "dominance"      # 霸主预言
    EXTINCTION = "extinction"    # 灭绝预言
    EXPANSION = "expansion"      # 扩张预言
    EVOLUTION = "evolution"      # 演化预言
    DUEL = "duel"               # 对决预言


@dataclass
class WagerInfo:
    """预言信息"""
    type: WagerType
    name: str
    icon: str
    description: str
    min_bet: int
    max_bet: int
    duration: int  # 回合限制
    multiplier: float  # 回报倍率


WAGER_TYPES: dict[WagerType, WagerInfo] = {
    WagerType.DOMINANCE: WagerInfo(
        type=WagerType.DOMINANCE,
        name="霸主预言",
        icon="🏆",
        description="该物种在指定回合后成为同生态位种群最大",
        min_bet=15,
        max_bet=30,
        duration=10,
        multiplier=2.5,
    ),
    WagerType.EXTINCTION: WagerInfo(
        type=WagerType.EXTINCTION,
        name="灭绝预言",
        icon="💀",
        description="该物种在指定回合内灭绝",
        min_bet=10,
        max_bet=20,
        duration=5,
        multiplier=2.0,
    ),
    WagerType.EXPANSION: WagerInfo(
        type=WagerType.EXPANSION,
        name="扩张预言",
        icon="🌍",
        description="该物种扩展到3个以上新区域",
        min_bet=20,
        max_bet=40,
        duration=15,
        multiplier=3.0,
    ),
    WagerType.EVOLUTION: WagerInfo(
        type=WagerType.EVOLUTION,
        name="演化预言",
        icon="🧬",
        description="该物种产生分化或杂交后代",
        min_bet=25,
        max_bet=50,
        duration=20,
        multiplier=2.0,
    ),
    WagerType.DUEL: WagerInfo(
        type=WagerType.DUEL,
        name="对决预言",
        icon="⚔️",
        description="指定两物种，预测指定回合后谁存活",
        min_bet=30,
        max_bet=60,
        duration=15,
        multiplier=4.0,
    ),
}


@dataclass
class ActiveWager:
    """进行中的赌注"""
    id: str
    wager_type: WagerType
    target_species: str  # 主目标物种
    secondary_species: str | None = None  # 对决时的第二物种
    bet_amount: int = 0
    start_turn: int = 0
    end_turn: int = 0
    predicted_outcome: str = ""  # 预测结果（如对决时预测谁赢）
    initial_state: dict = field(default_factory=dict)  # 初始状态快照
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "wager_type": self.wager_type.value,
            "target_species": self.target_species,
            "secondary_species": self.secondary_species,
            "bet_amount": self.bet_amount,
            "start_turn": self.start_turn,
            "end_turn": self.end_turn,
            "predicted_outcome": self.predicted_outcome,
            "initial_state": self.initial_state,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ActiveWager":
        return cls(
            id=data["id"],
            wager_type=WagerType(data["wager_type"]),
            target_species=data["target_species"],
            secondary_species=data.get("secondary_species"),
            bet_amount=data.get("bet_amount", 0),
            start_turn=data.get("start_turn", 0),
            end_turn=data.get("end_turn", 0),
            predicted_outcome=data.get("predicted_outcome", ""),
            initial_state=data.get("initial_state", {}),
        )


@dataclass
class WagerState:
    """预言赌注系统状态"""
    active_wagers: dict[str, ActiveWager] = field(default_factory=dict)
    completed_wagers: list[dict] = field(default_factory=list)  # 历史记录
    total_bet: int = 0
    total_won: int = 0
    total_lost: int = 0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    faith_shaken_turns: int = 0  # 「神威动摇」剩余回合
    
    def to_dict(self) -> dict:
        return {
            "active_wagers": {k: v.to_dict() for k, v in self.active_wagers.items()},
            "completed_wagers": self.completed_wagers[-50:],  # 保留最近50条
            "total_bet": self.total_bet,
            "total_won": self.total_won,
            "total_lost": self.total_lost,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "faith_shaken_turns": self.faith_shaken_turns,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WagerState":
        active = {}
        for k, v in data.get("active_wagers", {}).items():
            active[k] = ActiveWager.from_dict(v)
        return cls(
            active_wagers=active,
            completed_wagers=data.get("completed_wagers", []),
            total_bet=data.get("total_bet", 0),
            total_won=data.get("total_won", 0),
            total_lost=data.get("total_lost", 0),
            consecutive_wins=data.get("consecutive_wins", 0),
            consecutive_losses=data.get("consecutive_losses", 0),
            faith_shaken_turns=data.get("faith_shaken_turns", 0),
        )


# ==================== 综合状态 ====================

@dataclass
class DivineProgressionState:
    """神力进阶系统完整状态"""
    path_progress: PathProgress = field(default_factory=PathProgress)
    faith_state: FaithState = field(default_factory=FaithState)
    miracle_state: MiracleState = field(default_factory=MiracleState)
    wager_state: WagerState = field(default_factory=WagerState)
    
    # 全局统计
    total_skills_used: int = 0
    total_miracles_cast: int = 0
    
    def to_dict(self) -> dict:
        return {
            "path_progress": self.path_progress.to_dict(),
            "faith_state": self.faith_state.to_dict(),
            "miracle_state": self.miracle_state.to_dict(),
            "wager_state": self.wager_state.to_dict(),
            "total_skills_used": self.total_skills_used,
            "total_miracles_cast": self.total_miracles_cast,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DivineProgressionState":
        return cls(
            path_progress=PathProgress.from_dict(data.get("path_progress", {})),
            faith_state=FaithState.from_dict(data.get("faith_state", {})),
            miracle_state=MiracleState.from_dict(data.get("miracle_state", {})),
            wager_state=WagerState.from_dict(data.get("wager_state", {})),
            total_skills_used=data.get("total_skills_used", 0),
            total_miracles_cast=data.get("total_miracles_cast", 0),
        )


# ==================== 服务类 ====================

class DivineProgressionService:
    """神力进阶服务
    
    管理所有神力进阶子系统。
    """
    
    # 神格升级所需经验
    LEVEL_EXP = [0, 100, 300, 600, 1000, 1500]  # 0-5级
    
    def __init__(self):
        self._state = DivineProgressionState()
        logger.info("[神力进阶] 服务初始化")
    
    def get_state(self) -> DivineProgressionState:
        """获取完整状态"""
        return self._state
    
    def load_state(self, data: dict) -> None:
        """从存档加载状态"""
        self._state = DivineProgressionState.from_dict(data)
        logger.info(f"[神力进阶] 状态已恢复，神格: {self._state.path_progress.path.value}")
    
    def export_state(self) -> dict:
        """导出状态用于存档"""
        return self._state.to_dict()
    
    def reset(self) -> None:
        """重置状态（新游戏）"""
        self._state = DivineProgressionState()
        logger.info("[神力进阶] 状态已重置")
    
    # ========== 神格系统 ==========
    
    def choose_path(self, path: DivinePath) -> tuple[bool, str]:
        """选择神格路线"""
        if self._state.path_progress.path != DivinePath.NONE:
            # 已有主神格，检查是否可选副神格
            if self._state.path_progress.level >= 4 and self._state.path_progress.secondary_path is None:
                self._state.path_progress.secondary_path = path
                logger.info(f"[神力进阶] 选择副神格: {path.value}")
                return True, f"已选择副神格「{DIVINE_PATHS[path].name}」"
            return False, "已选择神格，无法更改（4级后可选副神格）"
        
        self._state.path_progress.path = path
        self._state.path_progress.level = 1
        
        # 解锁1级技能
        for skill_id, skill in DIVINE_SKILLS.items():
            if skill.path == path and skill.unlock_level == 1:
                self._state.path_progress.unlocked_skills.append(skill_id)
        
        logger.info(f"[神力进阶] 选择神格: {path.value}")
        return True, f"已选择「{DIVINE_PATHS[path].name}」神格"
    
    def add_experience(self, amount: int) -> tuple[int, bool]:
        """增加神格经验，返回(当前等级, 是否升级)"""
        if self._state.path_progress.path == DivinePath.NONE:
            return 0, False
        
        self._state.path_progress.experience += amount
        old_level = self._state.path_progress.level
        
        # 检查升级
        for level, exp_needed in enumerate(self.LEVEL_EXP):
            if self._state.path_progress.experience >= exp_needed:
                self._state.path_progress.level = level
        
        # 限制最高5级
        self._state.path_progress.level = min(5, self._state.path_progress.level)
        
        # 解锁新技能
        if self._state.path_progress.level > old_level:
            path = self._state.path_progress.path
            for skill_id, skill in DIVINE_SKILLS.items():
                if skill.path == path and skill.unlock_level <= self._state.path_progress.level:
                    if skill_id not in self._state.path_progress.unlocked_skills:
                        self._state.path_progress.unlocked_skills.append(skill_id)
                        logger.info(f"[神力进阶] 解锁技能: {skill.name}")
            
            logger.info(f"[神力进阶] 升级! {old_level} -> {self._state.path_progress.level}")
        
        return self._state.path_progress.level, self._state.path_progress.level > old_level
    
    def get_path_info(self) -> dict | None:
        """获取当前神格信息"""
        path = self._state.path_progress.path
        if path == DivinePath.NONE:
            return None
        
        path_info = DIVINE_PATHS[path]
        return {
            "path": path.value,
            "name": path_info.name,
            "icon": path_info.icon,
            "description": path_info.description,
            "passive_bonus": path_info.passive_bonus,
            "color": path_info.color,
            "level": self._state.path_progress.level,
            "experience": self._state.path_progress.experience,
            "next_level_exp": self.LEVEL_EXP[min(self._state.path_progress.level + 1, 5)],
            "unlocked_skills": self._state.path_progress.unlocked_skills,
            "secondary_path": self._state.path_progress.secondary_path.value if self._state.path_progress.secondary_path else None,
        }
    
    def get_available_paths(self) -> list[dict]:
        """获取可选神格列表"""
        result = []
        for path, info in DIVINE_PATHS.items():
            result.append({
                "path": path.value,
                "name": info.name,
                "icon": info.icon,
                "description": info.description,
                "passive_bonus": info.passive_bonus,
                "skills": info.skills,
                "color": info.color,
            })
        return result
    
    def get_skill_info(self, skill_id: str) -> dict | None:
        """获取技能信息"""
        if skill_id not in DIVINE_SKILLS:
            return None
        skill = DIVINE_SKILLS[skill_id]
        return {
            "id": skill.id,
            "name": skill.name,
            "path": skill.path.value,
            "description": skill.description,
            "cost": skill.cost,
            "cooldown": skill.cooldown,
            "unlock_level": skill.unlock_level,
            "icon": skill.icon,
            "unlocked": skill_id in self._state.path_progress.unlocked_skills,
            "uses": self._state.path_progress.skills_used.get(skill_id, 0),
        }
    
    def get_cost_modifier(self, action: str) -> float:
        """获取神格带来的消耗修正"""
        path = self._state.path_progress.path
        if path == DivinePath.NONE:
            return 1.0
        
        if path == DivinePath.CREATOR and action in ("create_species", "introduce"):
            return 0.7  # -30%
        elif path == DivinePath.CHAOS and action == "pressure":
            return 0.5  # -50%
        
        return 1.0
    
    # ========== 信仰系统 ==========
    
    def add_follower(self, lineage_code: str, common_name: str, population: int, trophic_level: int) -> bool:
        """添加信徒"""
        if lineage_code in self._state.faith_state.followers:
            return False
        
        # 计算贡献值
        pop_factor = min(2.0, population / 1_000_000)  # 种群规模因子
        trophic_bonus = 1.0 + (trophic_level - 1) * 0.3  # 高营养级加成
        contribution = 0.5 * pop_factor * trophic_bonus
        
        follower = Follower(
            lineage_code=lineage_code,
            common_name=common_name,
            faith_value=10.0,
            turns_as_follower=0,
            contribution_per_turn=round(contribution, 2),
        )
        self._state.faith_state.followers[lineage_code] = follower
        self._recalculate_faith_bonus()
        
        logger.info(f"[信仰] 新增信徒: {common_name} (贡献 {contribution:.1f}/回合)")
        return True
    
    def remove_follower(self, lineage_code: str, reason: str = "extinction") -> float:
        """移除信徒，返回损失的信仰值"""
        if lineage_code not in self._state.faith_state.followers:
            return 0.0
        
        follower = self._state.faith_state.followers[lineage_code]
        faith_loss = follower.faith_value
        
        del self._state.faith_state.followers[lineage_code]
        self._recalculate_faith_bonus()
        
        logger.info(f"[信仰] 失去信徒: {follower.common_name} ({reason}), 信仰损失 {faith_loss:.1f}")
        return faith_loss
    
    def bless_follower(self, lineage_code: str) -> tuple[bool, str]:
        """显圣 - 赐福信徒"""
        if lineage_code not in self._state.faith_state.followers:
            return False, "该物种不是信徒"
        
        follower = self._state.faith_state.followers[lineage_code]
        if follower.is_blessed:
            return False, "该信徒已获得神眷"
        
        follower.is_blessed = True
        follower.faith_value += 20
        follower.contribution_per_turn *= 1.5
        self._recalculate_faith_bonus()
        
        return True, f"已对「{follower.common_name}」显圣，获得神眷标记"
    
    def sanctify_follower(self, lineage_code: str) -> tuple[bool, str]:
        """圣化 - 将信徒提升为圣物种"""
        if lineage_code not in self._state.faith_state.followers:
            return False, "该物种不是信徒"
        
        follower = self._state.faith_state.followers[lineage_code]
        if follower.is_sanctified:
            return False, "该信徒已被圣化"
        
        follower.is_sanctified = True
        follower.faith_value += 50
        follower.contribution_per_turn *= 2
        self._recalculate_faith_bonus()
        
        return True, f"「{follower.common_name}」已被圣化，成为圣物种"
    
    def process_turn_faith(self) -> float:
        """处理回合信仰贡献，返回额外能量"""
        bonus = 0.0
        for follower in self._state.faith_state.followers.values():
            follower.turns_as_follower += 1
            
            # 古老信徒加成
            ancient_bonus = 1.0
            if follower.turns_as_follower >= 20:
                ancient_bonus = 3.0
            elif follower.turns_as_follower >= 10:
                ancient_bonus = 2.0
            
            contribution = follower.contribution_per_turn * ancient_bonus
            follower.faith_value += contribution
            bonus += contribution
        
        self._state.faith_state.total_faith += bonus
        return bonus
    
    def _recalculate_faith_bonus(self) -> None:
        """重新计算信仰回复加成"""
        total = sum(f.contribution_per_turn for f in self._state.faith_state.followers.values())
        self._state.faith_state.faith_bonus_per_turn = round(total, 2)
    
    def get_faith_summary(self) -> dict:
        """获取信仰系统摘要"""
        followers_list = [
            {
                **f.to_dict(),
                "status": "sanctified" if f.is_sanctified else ("blessed" if f.is_blessed else "normal"),
            }
            for f in self._state.faith_state.followers.values()
        ]
        return {
            "total_followers": len(self._state.faith_state.followers),
            "total_faith": round(self._state.faith_state.total_faith, 1),
            "faith_bonus_per_turn": self._state.faith_state.faith_bonus_per_turn,
            "followers": sorted(followers_list, key=lambda x: -x["faith_value"]),
        }
    
    # ========== 神迹系统 ==========
    
    def start_miracle_charge(self, miracle_id: str) -> tuple[bool, str, int]:
        """开始蓄力神迹，返回(成功, 消息, 需要能量)"""
        if miracle_id not in MIRACLES:
            return False, "未知的神迹", 0
        
        miracle = MIRACLES[miracle_id]
        
        # 检查一次性神迹
        if miracle.one_time and miracle_id in self._state.miracle_state.used_one_time:
            return False, "该神迹只能使用一次", 0
        
        # 检查冷却
        if self._state.miracle_state.cooldowns.get(miracle_id, 0) > 0:
            remaining = self._state.miracle_state.cooldowns[miracle_id]
            return False, f"神迹冷却中，剩余 {remaining} 回合", 0
        
        # 检查是否已在蓄力
        if self._state.miracle_state.charging:
            return False, "已有神迹在蓄力中", 0
        
        self._state.miracle_state.charging = miracle_id
        self._state.miracle_state.charge_progress = 0
        self._state.miracle_state.charge_reserved_energy = miracle.cost
        
        return True, f"开始蓄力「{miracle.name}」，需要 {miracle.charge_turns} 回合", miracle.cost
    
    def cancel_miracle_charge(self) -> tuple[bool, int]:
        """取消蓄力，返回(成功, 返还能量)"""
        if not self._state.miracle_state.charging:
            return False, 0
        
        reserved = self._state.miracle_state.charge_reserved_energy
        refund = int(reserved * 0.8)  # 返还80%
        
        self._state.miracle_state.charging = None
        self._state.miracle_state.charge_progress = 0
        self._state.miracle_state.charge_reserved_energy = 0
        
        return True, refund
    
    def advance_miracle_charge(self) -> tuple[bool, str | None]:
        """推进蓄力，返回(是否完成, 完成的神迹ID)"""
        if not self._state.miracle_state.charging:
            return False, None
        
        miracle_id = self._state.miracle_state.charging
        miracle = MIRACLES[miracle_id]
        
        self._state.miracle_state.charge_progress += 1
        
        if self._state.miracle_state.charge_progress >= miracle.charge_turns:
            # 蓄力完成
            self._state.miracle_state.charging = None
            self._state.miracle_state.charge_progress = 0
            self._state.miracle_state.charge_reserved_energy = 0
            self._state.miracle_state.cooldowns[miracle_id] = miracle.cooldown
            self._state.miracle_state.miracles_cast += 1
            
            if miracle.one_time:
                self._state.miracle_state.used_one_time.append(miracle_id)
            
            return True, miracle_id
        
        return False, None
    
    def process_turn_cooldowns(self) -> None:
        """处理回合冷却"""
        for miracle_id in list(self._state.miracle_state.cooldowns.keys()):
            self._state.miracle_state.cooldowns[miracle_id] -= 1
            if self._state.miracle_state.cooldowns[miracle_id] <= 0:
                del self._state.miracle_state.cooldowns[miracle_id]
    
    def get_miracle_info(self, miracle_id: str) -> dict | None:
        """获取神迹信息"""
        if miracle_id not in MIRACLES:
            return None
        
        miracle = MIRACLES[miracle_id]
        cooldown = self._state.miracle_state.cooldowns.get(miracle_id, 0)
        is_charging = self._state.miracle_state.charging == miracle_id
        
        return {
            "id": miracle.id,
            "name": miracle.name,
            "icon": miracle.icon,
            "description": miracle.description,
            "cost": miracle.cost,
            "cooldown": miracle.cooldown,
            "charge_turns": miracle.charge_turns,
            "one_time": miracle.one_time,
            "current_cooldown": cooldown,
            "is_charging": is_charging,
            "charge_progress": self._state.miracle_state.charge_progress if is_charging else 0,
            "available": cooldown == 0 and not is_charging and (
                not miracle.one_time or miracle_id not in self._state.miracle_state.used_one_time
            ),
        }
    
    def get_all_miracles(self) -> list[dict]:
        """获取所有神迹信息"""
        return [self.get_miracle_info(mid) for mid in MIRACLES.keys()]
    
    def execute_miracle(self, miracle_id: str, current_turn: int) -> tuple[bool, str, dict]:
        """执行神迹（立即触发，非蓄力式）
        
        返回: (成功, 消息, 效果描述)
        """
        if miracle_id not in MIRACLES:
            return False, "未知的神迹", {}
        
        miracle = MIRACLES[miracle_id]
        
        # 检查一次性神迹
        if miracle.one_time and miracle_id in self._state.miracle_state.used_one_time:
            return False, f"「{miracle.name}」只能使用一次", {}
        
        # 检查冷却
        cooldown = self._state.miracle_state.cooldowns.get(miracle_id, 0)
        if cooldown > 0:
            return False, f"「{miracle.name}」冷却中（还需{cooldown}回合）", {}
        
        # 检查是否正在蓄力其他神迹
        if self._state.miracle_state.charging:
            return False, "正在蓄力另一个神迹，无法同时执行", {}
        
        # 检查能量（通过外部能量服务）
        from .divine_energy import energy_service
        if energy_service.get_state().current < miracle.cost:
            return False, f"神力不足（需要{miracle.cost}，当前{energy_service.get_state().current}）", {}
        
        # 消耗能量
        energy_service.spend(miracle.cost, f"执行神迹「{miracle.name}」")
        
        # 设置冷却
        self._state.miracle_state.cooldowns[miracle_id] = miracle.cooldown
        self._state.miracle_state.miracles_cast += 1
        
        # 记录一次性神迹
        if miracle.one_time:
            self._state.miracle_state.used_one_time.append(miracle_id)
        
        # 构建效果描述
        effect = {
            "miracle_id": miracle_id,
            "miracle_name": miracle.name,
            "miracle_icon": miracle.icon,
            "description": miracle.description,
            "cost": miracle.cost,
            "turn_executed": current_turn,
        }
        
        logger.info(f"[神迹] 执行「{miracle.name}」，消耗 {miracle.cost} 神力")
        
        return True, f"神迹「{miracle.name}」已触发！", effect
    
    def get_miracle_summary(self) -> dict:
        """获取神迹系统摘要"""
        return {
            "all_miracles": self.get_all_miracles(),
            "miracles_cast": self._state.miracle_state.miracles_cast,
            "charging": self._state.miracle_state.charging,
            "charge_progress": self._state.miracle_state.charge_progress,
        }
    
    # ========== 预言赌注系统 ==========
    
    def place_wager(
        self,
        wager_type: WagerType,
        target_species: str,
        bet_amount: int,
        current_turn: int,
        secondary_species: str | None = None,
        predicted_outcome: str = "",
        initial_state: dict | None = None,
    ) -> tuple[bool, str, str]:
        """下注预言，返回(成功, 消息, 预言ID)"""
        wager_info = WAGER_TYPES[wager_type]
        
        # 验证下注金额
        if bet_amount < wager_info.min_bet or bet_amount > wager_info.max_bet:
            return False, f"下注金额需在 {wager_info.min_bet}~{wager_info.max_bet} 之间", ""
        
        # 检查「神威动摇」状态
        if self._state.wager_state.faith_shaken_turns > 0:
            return False, f"神威动摇中，无法下注，剩余 {self._state.wager_state.faith_shaken_turns} 回合", ""
        
        # 对决预言需要第二物种
        if wager_type == WagerType.DUEL and not secondary_species:
            return False, "对决预言需要指定第二物种", ""
        
        wager_id = f"wager_{current_turn}_{len(self._state.wager_state.active_wagers)}"
        
        wager = ActiveWager(
            id=wager_id,
            wager_type=wager_type,
            target_species=target_species,
            secondary_species=secondary_species,
            bet_amount=bet_amount,
            start_turn=current_turn,
            end_turn=current_turn + wager_info.duration,
            predicted_outcome=predicted_outcome,
            initial_state=initial_state or {},
        )
        
        self._state.wager_state.active_wagers[wager_id] = wager
        self._state.wager_state.total_bet += bet_amount
        
        logger.info(f"[预言] 新下注: {wager_info.name} on {target_species}, {bet_amount} 能量")
        return True, f"已下注「{wager_info.name}」，押注 {bet_amount} 能量", wager_id
    
    def check_wager_result(
        self,
        wager_id: str,
        current_state: dict,
    ) -> tuple[bool | None, int]:
        """检查预言结果，返回(是否成功/None表示进行中, 奖励/损失金额)"""
        if wager_id not in self._state.wager_state.active_wagers:
            return None, 0
        
        wager = self._state.wager_state.active_wagers[wager_id]
        wager_info = WAGER_TYPES[wager.wager_type]
        
        # 这里简化判断逻辑，实际实现需要根据游戏状态判断
        # 返回 None 表示预言还在进行中
        return None, 0
    
    def resolve_wager(self, wager_id: str, success: bool) -> int:
        """结算预言，返回奖励/损失金额"""
        if wager_id not in self._state.wager_state.active_wagers:
            return 0
        
        wager = self._state.wager_state.active_wagers[wager_id]
        wager_info = WAGER_TYPES[wager.wager_type]
        
        if success:
            reward = int(wager.bet_amount * wager_info.multiplier)
            self._state.wager_state.total_won += reward
            self._state.wager_state.consecutive_wins += 1
            self._state.wager_state.consecutive_losses = 0
            result = reward
        else:
            self._state.wager_state.total_lost += wager.bet_amount
            self._state.wager_state.consecutive_losses += 1
            self._state.wager_state.consecutive_wins = 0
            result = -wager.bet_amount
            
            # 连续失败惩罚
            if self._state.wager_state.consecutive_losses >= 3:
                self._state.wager_state.faith_shaken_turns = 2
                logger.info("[预言] 神威动摇！连续失败3次")
        
        # 记录历史
        self._state.wager_state.completed_wagers.append({
            "id": wager_id,
            "wager_type": wager.wager_type.value,
            "target_species": wager.target_species,
            "bet_amount": wager.bet_amount,
            "success": success,
            "result": result,
        })
        
        del self._state.wager_state.active_wagers[wager_id]
        return result
    
    def process_turn_wagers(self) -> None:
        """处理回合预言状态"""
        if self._state.wager_state.faith_shaken_turns > 0:
            self._state.wager_state.faith_shaken_turns -= 1
    
    def get_wager_summary(self) -> dict:
        """获取预言系统摘要"""
        active_list = [w.to_dict() for w in self._state.wager_state.active_wagers.values()]
        return {
            "active_wagers": active_list,
            "total_bet": self._state.wager_state.total_bet,
            "total_won": self._state.wager_state.total_won,
            "total_lost": self._state.wager_state.total_lost,
            "net_profit": self._state.wager_state.total_won - self._state.wager_state.total_lost,
            "consecutive_wins": self._state.wager_state.consecutive_wins,
            "consecutive_losses": self._state.wager_state.consecutive_losses,
            "faith_shaken_turns": self._state.wager_state.faith_shaken_turns,
            "wager_types": [
                {
                    "type": wt.value,
                    "name": info.name,
                    "icon": info.icon,
                    "description": info.description,
                    "min_bet": info.min_bet,
                    "max_bet": info.max_bet,
                    "duration": info.duration,
                    "multiplier": info.multiplier,
                }
                for wt, info in WAGER_TYPES.items()
            ],
        }
    
    # ========== 综合接口 ==========
    
    def process_turn(self, current_turn: int) -> dict:
        """处理回合更新，返回本回合的所有事件"""
        events = []
        
        # 1. 信仰贡献
        faith_bonus = self.process_turn_faith()
        if faith_bonus > 0:
            events.append({
                "type": "faith_contribution",
                "amount": round(faith_bonus, 2),
            })
        
        # 2. 神迹蓄力
        miracle_ready, miracle_id = self.advance_miracle_charge()
        if miracle_ready and miracle_id:
            events.append({
                "type": "miracle_ready",
                "miracle_id": miracle_id,
                "miracle_name": MIRACLES[miracle_id].name,
            })
        
        # 3. 神迹冷却
        self.process_turn_cooldowns()
        
        # 4. 预言状态
        self.process_turn_wagers()
        
        return {
            "turn": current_turn,
            "events": events,
            "faith_bonus": round(faith_bonus, 2),
        }
    
    def get_full_status(self) -> dict:
        """获取完整状态概览"""
        return {
            "path": self.get_path_info(),
            "available_paths": self.get_available_paths() if self._state.path_progress.path == DivinePath.NONE else None,
            "faith": self.get_faith_summary(),
            "miracles": self.get_all_miracles(),
            "charging_miracle": self._state.miracle_state.charging,
            "wagers": self.get_wager_summary(),
            "stats": {
                "total_skills_used": self._state.total_skills_used,
                "total_miracles_cast": self._state.miracle_state.miracles_cast,
            },
        }


# 全局服务实例
divine_progression_service = DivineProgressionService()

