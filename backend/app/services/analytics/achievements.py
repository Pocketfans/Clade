"""成就系统服务

负责跟踪玩家的游戏进度并解锁成就。

成就类型：
- 物种相关：培养顶级捕食者、保持多样性等
- 生态系统相关：建立食物网、达成生态平衡等
- 回合相关：存活指定回合、连续无灭绝等
- 灾难相关：触发大灭绝、物种复苏等
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ...models.species import Species
    from ...schemas.responses import TurnReport

logger = logging.getLogger(__name__)


class AchievementCategory(str, Enum):
    """成就分类"""
    SPECIES = "species"  # 物种相关
    ECOSYSTEM = "ecosystem"  # 生态系统相关
    SURVIVAL = "survival"  # 生存相关
    DISASTER = "disaster"  # 灾难相关
    SPECIAL = "special"  # 特殊成就


class AchievementRarity(str, Enum):
    """成就稀有度"""
    COMMON = "common"  # 普通
    UNCOMMON = "uncommon"  # 罕见
    RARE = "rare"  # 稀有
    EPIC = "epic"  # 史诗
    LEGENDARY = "legendary"  # 传说


@dataclass
class AchievementDefinition:
    """成就定义"""
    id: str
    name: str
    description: str
    category: AchievementCategory
    rarity: AchievementRarity
    icon: str  # Emoji 图标
    target_value: int = 1  # 目标值（如需要达成的次数）
    hidden: bool = False  # 是否隐藏成就（达成前不显示）
    

@dataclass
class AchievementProgress:
    """成就进度"""
    achievement_id: str
    current_value: int = 0
    unlocked: bool = False
    unlock_time: str | None = None
    unlock_turn: int | None = None


@dataclass
class AchievementUnlockEvent:
    """成就解锁事件"""
    achievement: AchievementDefinition
    turn_index: int
    timestamp: str


# 所有成就定义
ACHIEVEMENTS: dict[str, AchievementDefinition] = {
    # ===== 物种相关 =====
    "first_speciation": AchievementDefinition(
        id="first_speciation",
        name="生命之树",
        description="首次触发物种分化",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.COMMON,
        icon="🌱",
    ),
    "apex_predator": AchievementDefinition(
        id="apex_predator",
        name="顶级捕食者",
        description="培养出一个 T5 营养级物种",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.RARE,
        icon="🦖",
    ),
    "biodiversity_10": AchievementDefinition(
        id="biodiversity_10",
        name="多样性守护者",
        description="同时存在 10 个存活物种",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.UNCOMMON,
        icon="🌈",
        target_value=10,
    ),
    "biodiversity_20": AchievementDefinition(
        id="biodiversity_20",
        name="生态繁荣",
        description="同时存在 20 个存活物种",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.RARE,
        icon="🌳",
        target_value=20,
    ),
    "population_million": AchievementDefinition(
        id="population_million",
        name="百万生命",
        description="单个物种种群突破 100 万",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.UNCOMMON,
        icon="👥",
        target_value=1_000_000,
    ),
    "population_billion": AchievementDefinition(
        id="population_billion",
        name="生命海洋",
        description="单个物种种群突破 10 亿",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.EPIC,
        icon="🌊",
        target_value=1_000_000_000,
    ),
    "hybrid_creator": AchievementDefinition(
        id="hybrid_creator",
        name="杂交先锋",
        description="首次出现杂交物种",
        category=AchievementCategory.SPECIES,
        rarity=AchievementRarity.UNCOMMON,
        icon="🧬",
    ),
    "all_trophic_levels": AchievementDefinition(
        id="all_trophic_levels",
        name="完整食物链",
        description="同时存在 T1-T4 所有营养级的物种",
        category=AchievementCategory.ECOSYSTEM,
        rarity=AchievementRarity.UNCOMMON,
        icon="🔗",
    ),
    
    # ===== 生态系统相关 =====
    "food_web_10": AchievementDefinition(
        id="food_web_10",
        name="生态网络",
        description="建立 10 条捕食关系",
        category=AchievementCategory.ECOSYSTEM,
        rarity=AchievementRarity.UNCOMMON,
        icon="🕸️",
        target_value=10,
    ),
    "food_web_30": AchievementDefinition(
        id="food_web_30",
        name="复杂生态",
        description="建立 30 条捕食关系",
        category=AchievementCategory.ECOSYSTEM,
        rarity=AchievementRarity.RARE,
        icon="🌐",
        target_value=30,
    ),
    "keystone_species": AchievementDefinition(
        id="keystone_species",
        name="关键物种",
        description="培养出一个被 5 个以上物种依赖的关键物种",
        category=AchievementCategory.ECOSYSTEM,
        rarity=AchievementRarity.RARE,
        icon="⭐",
        target_value=5,
    ),
    "ecosystem_balance": AchievementDefinition(
        id="ecosystem_balance",
        name="生态平衡",
        description="生态系统健康评分达到 A 级",
        category=AchievementCategory.ECOSYSTEM,
        rarity=AchievementRarity.EPIC,
        icon="⚖️",
    ),
    
    # ===== 生存相关 =====
    "survive_10_turns": AchievementDefinition(
        id="survive_10_turns",
        name="初露锋芒",
        description="存活 10 回合",
        category=AchievementCategory.SURVIVAL,
        rarity=AchievementRarity.COMMON,
        icon="🌅",
        target_value=10,
    ),
    "survive_50_turns": AchievementDefinition(
        id="survive_50_turns",
        name="演化之路",
        description="存活 50 回合",
        category=AchievementCategory.SURVIVAL,
        rarity=AchievementRarity.UNCOMMON,
        icon="🌄",
        target_value=50,
    ),
    "survive_100_turns": AchievementDefinition(
        id="survive_100_turns",
        name="时间长河",
        description="存活 100 回合",
        category=AchievementCategory.SURVIVAL,
        rarity=AchievementRarity.RARE,
        icon="⏳",
        target_value=100,
    ),
    "no_extinction_10": AchievementDefinition(
        id="no_extinction_10",
        name="生命守护",
        description="连续 10 回合无物种灭绝",
        category=AchievementCategory.SURVIVAL,
        rarity=AchievementRarity.UNCOMMON,
        icon="🛡️",
        target_value=10,
    ),
    "ancient_species": AchievementDefinition(
        id="ancient_species",
        name="活化石",
        description="一个物种连续存活超过 50 回合",
        category=AchievementCategory.SURVIVAL,
        rarity=AchievementRarity.RARE,
        icon="🦴",
        target_value=50,
    ),
    
    # ===== 灾难相关 =====
    "mass_extinction": AchievementDefinition(
        id="mass_extinction",
        name="大灭绝",
        description="一回合内有 5 个物种灭绝",
        category=AchievementCategory.DISASTER,
        rarity=AchievementRarity.UNCOMMON,
        icon="☄️",
        target_value=5,
    ),
    "survivor": AchievementDefinition(
        id="survivor",
        name="幸存者",
        description="在大灭绝后至少有一个物种存活",
        category=AchievementCategory.DISASTER,
        rarity=AchievementRarity.RARE,
        icon="🌟",
    ),
    "phoenix": AchievementDefinition(
        id="phoenix",
        name="浴火重生",
        description="物种数量从 1 个恢复到 10 个",
        category=AchievementCategory.DISASTER,
        rarity=AchievementRarity.EPIC,
        icon="🔥",
    ),
    "pressure_master": AchievementDefinition(
        id="pressure_master",
        name="天灾使者",
        description="使用过 10 种不同的环境压力",
        category=AchievementCategory.DISASTER,
        rarity=AchievementRarity.UNCOMMON,
        icon="⚡",
        target_value=10,
    ),
    
    # ===== 特殊成就 =====
    "first_turn": AchievementDefinition(
        id="first_turn",
        name="创世纪",
        description="完成第一回合演化",
        category=AchievementCategory.SPECIAL,
        rarity=AchievementRarity.COMMON,
        icon="✨",
    ),
    "creator": AchievementDefinition(
        id="creator",
        name="造物主",
        description="手动创建一个物种",
        category=AchievementCategory.SPECIAL,
        rarity=AchievementRarity.COMMON,
        icon="🎨",
    ),
    "explorer": AchievementDefinition(
        id="explorer",
        name="探索者",
        description="查看族谱、食物网、生态位对比",
        category=AchievementCategory.SPECIAL,
        rarity=AchievementRarity.COMMON,
        icon="🔍",
        target_value=3,
    ),
    "domination": AchievementDefinition(
        id="domination",
        name="生态霸主",
        description="单个物种占据总种群的 50% 以上",
        category=AchievementCategory.SPECIAL,
        rarity=AchievementRarity.RARE,
        icon="👑",
    ),
}


class AchievementService:
    """成就服务
    
    跟踪玩家进度并解锁成就。
    """
    
    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self._progress: dict[str, AchievementProgress] = {}
        self._pending_unlocks: list[AchievementUnlockEvent] = []
        
        # 追踪变量
        self._consecutive_no_extinction: int = 0
        self._used_pressure_kinds: set[str] = set()
        self._min_species_count: int = 999
        self._exploration_flags: set[str] = set()
        
        # 加载进度
        self._load_progress()
    
    def _get_progress_file(self) -> Path:
        """获取成就进度文件路径"""
        return self.data_dir / "achievements.json"
    
    def _load_progress(self) -> None:
        """加载成就进度"""
        progress_file = self._get_progress_file()
        if progress_file.exists():
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for ach_id, prog_data in data.get("progress", {}).items():
                        self._progress[ach_id] = AchievementProgress(
                            achievement_id=ach_id,
                            current_value=prog_data.get("current_value", 0),
                            unlocked=prog_data.get("unlocked", False),
                            unlock_time=prog_data.get("unlock_time"),
                            unlock_turn=prog_data.get("unlock_turn"),
                        )
                    # 恢复追踪变量
                    self._consecutive_no_extinction = data.get("consecutive_no_extinction", 0)
                    self._used_pressure_kinds = set(data.get("used_pressure_kinds", []))
                    self._min_species_count = data.get("min_species_count", 999)
                    self._exploration_flags = set(data.get("exploration_flags", []))
                logger.info(f"[成就] 加载进度: {len(self._progress)} 条记录")
            except Exception as e:
                logger.warning(f"[成就] 加载进度失败: {e}")
    
    def _save_progress(self) -> None:
        """保存成就进度"""
        progress_file = self._get_progress_file()
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "progress": {
                ach_id: {
                    "current_value": prog.current_value,
                    "unlocked": prog.unlocked,
                    "unlock_time": prog.unlock_time,
                    "unlock_turn": prog.unlock_turn,
                }
                for ach_id, prog in self._progress.items()
            },
            "consecutive_no_extinction": self._consecutive_no_extinction,
            "used_pressure_kinds": list(self._used_pressure_kinds),
            "min_species_count": self._min_species_count,
            "exploration_flags": list(self._exploration_flags),
        }
        
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _get_progress(self, achievement_id: str) -> AchievementProgress:
        """获取成就进度（不存在则创建）"""
        if achievement_id not in self._progress:
            self._progress[achievement_id] = AchievementProgress(achievement_id=achievement_id)
        return self._progress[achievement_id]
    
    def _unlock(self, achievement_id: str, turn_index: int) -> AchievementUnlockEvent | None:
        """解锁成就"""
        if achievement_id not in ACHIEVEMENTS:
            return None
        
        progress = self._get_progress(achievement_id)
        if progress.unlocked:
            return None
        
        progress.unlocked = True
        progress.unlock_time = datetime.now().isoformat()
        progress.unlock_turn = turn_index
        
        achievement = ACHIEVEMENTS[achievement_id]
        event = AchievementUnlockEvent(
            achievement=achievement,
            turn_index=turn_index,
            timestamp=progress.unlock_time,
        )
        self._pending_unlocks.append(event)
        self._save_progress()
        
        logger.info(f"[成就] 解锁: {achievement.name} ({achievement.icon})")
        return event
    
    def _update_progress(self, achievement_id: str, value: int, turn_index: int) -> AchievementUnlockEvent | None:
        """更新成就进度"""
        if achievement_id not in ACHIEVEMENTS:
            return None
        
        achievement = ACHIEVEMENTS[achievement_id]
        progress = self._get_progress(achievement_id)
        
        if progress.unlocked:
            return None
        
        progress.current_value = max(progress.current_value, value)
        
        if progress.current_value >= achievement.target_value:
            return self._unlock(achievement_id, turn_index)
        
        self._save_progress()
        return None
    
    def check_after_turn(
        self,
        report: "TurnReport",
        all_species: Sequence["Species"],
        pressure_kinds: list[str],
    ) -> list[AchievementUnlockEvent]:
        """回合结束后检查成就
        
        Args:
            report: 回合报告
            all_species: 所有物种
            pressure_kinds: 本回合使用的压力类型
        
        Returns:
            新解锁的成就列表
        """
        self._pending_unlocks.clear()
        turn_index = report.turn_index
        
        alive_species = [sp for sp in all_species if sp.status == "alive"]
        alive_count = len(alive_species)
        
        # === 回合相关 ===
        
        # 第一回合
        if turn_index == 0:
            self._unlock("first_turn", turn_index)
        
        # 存活回合数
        self._update_progress("survive_10_turns", turn_index + 1, turn_index)
        self._update_progress("survive_50_turns", turn_index + 1, turn_index)
        self._update_progress("survive_100_turns", turn_index + 1, turn_index)
        
        # === 物种相关 ===
        
        # 物种多样性
        self._update_progress("biodiversity_10", alive_count, turn_index)
        self._update_progress("biodiversity_20", alive_count, turn_index)
        
        # 物种分化
        if report.branching_events:
            self._unlock("first_speciation", turn_index)
        
        # 杂交物种
        for sp in alive_species:
            if sp.hybrid_parent_codes:
                self._unlock("hybrid_creator", turn_index)
                break
        
        # 顶级捕食者
        for sp in alive_species:
            if sp.trophic_level >= 5.0:
                self._unlock("apex_predator", turn_index)
                break
        
        # 种群数量
        for sp in alive_species:
            pop = sp.morphology_stats.get("population", 0) or 0
            self._update_progress("population_million", pop, turn_index)
            self._update_progress("population_billion", pop, turn_index)
        
        # 活化石
        for sp in alive_species:
            age = turn_index - (sp.created_turn or 0)
            self._update_progress("ancient_species", age, turn_index)
        
        # === 生态系统相关 ===
        
        # 完整食物链
        trophic_levels = set()
        for sp in alive_species:
            level = int(sp.trophic_level)
            if 1 <= level <= 4:
                trophic_levels.add(level)
        if len(trophic_levels) >= 4:
            self._unlock("all_trophic_levels", turn_index)
        
        # 食物网
        total_links = sum(len(sp.prey_species or []) for sp in alive_species)
        self._update_progress("food_web_10", total_links, turn_index)
        self._update_progress("food_web_30", total_links, turn_index)
        
        # 关键物种
        prey_count: dict[str, int] = {}
        for sp in alive_species:
            for prey_code in (sp.prey_species or []):
                prey_count[prey_code] = prey_count.get(prey_code, 0) + 1
        max_dependents = max(prey_count.values()) if prey_count else 0
        self._update_progress("keystone_species", max_dependents, turn_index)
        
        # 生态霸主
        if alive_species:
            total_pop = sum(sp.morphology_stats.get("population", 0) or 0 for sp in alive_species)
            if total_pop > 0:
                for sp in alive_species:
                    pop = sp.morphology_stats.get("population", 0) or 0
                    if pop / total_pop > 0.5:
                        self._unlock("domination", turn_index)
                        break
        
        # === 灾难相关 ===
        
        # 记录使用的压力
        for kind in pressure_kinds:
            self._used_pressure_kinds.add(kind)
        self._update_progress("pressure_master", len(self._used_pressure_kinds), turn_index)
        
        # 灭绝统计
        extinctions_this_turn = sum(1 for snap in report.species if snap.status == "extinct")
        
        if extinctions_this_turn >= 5:
            self._unlock("mass_extinction", turn_index)
            # 大灭绝后有幸存者
            if alive_count > 0:
                self._unlock("survivor", turn_index)
        
        # 连续无灭绝
        if extinctions_this_turn == 0:
            self._consecutive_no_extinction += 1
        else:
            self._consecutive_no_extinction = 0
        self._update_progress("no_extinction_10", self._consecutive_no_extinction, turn_index)
        
        # 浴火重生
        if self._min_species_count <= 1 and alive_count >= 10:
            self._unlock("phoenix", turn_index)
        self._min_species_count = min(self._min_species_count, alive_count)
        
        self._save_progress()
        return self._pending_unlocks.copy()
    
    def record_species_creation(self, turn_index: int) -> AchievementUnlockEvent | None:
        """记录手动创建物种"""
        return self._unlock("creator", turn_index)
    
    def record_exploration(self, feature: str, turn_index: int) -> AchievementUnlockEvent | None:
        """记录探索功能
        
        Args:
            feature: 功能名称 (genealogy, foodweb, niche)
            turn_index: 当前回合
        """
        self._exploration_flags.add(feature)
        return self._update_progress("explorer", len(self._exploration_flags), turn_index)
    
    def record_ecosystem_health(self, grade: str, turn_index: int) -> AchievementUnlockEvent | None:
        """记录生态系统健康评级"""
        if grade == "A":
            return self._unlock("ecosystem_balance", turn_index)
        return None
    
    def get_all_achievements(self) -> list[dict]:
        """获取所有成就及其状态"""
        result = []
        for ach_id, achievement in ACHIEVEMENTS.items():
            progress = self._get_progress(ach_id)
            result.append({
                "id": achievement.id,
                "name": achievement.name,
                "description": achievement.description,
                "category": achievement.category.value,
                "rarity": achievement.rarity.value,
                "icon": achievement.icon,
                "target_value": achievement.target_value,
                "current_value": progress.current_value,
                "unlocked": progress.unlocked,
                "unlock_time": progress.unlock_time,
                "unlock_turn": progress.unlock_turn,
                "hidden": achievement.hidden and not progress.unlocked,
            })
        return result
    
    def get_unlocked_achievements(self) -> list[dict]:
        """获取已解锁的成就"""
        return [a for a in self.get_all_achievements() if a["unlocked"]]
    
    def get_pending_unlocks(self) -> list[AchievementUnlockEvent]:
        """获取待通知的解锁事件（获取后清空）"""
        events = self._pending_unlocks.copy()
        self._pending_unlocks.clear()
        return events
    
    def reset(self) -> None:
        """重置所有成就进度（新存档时调用）"""
        self._progress.clear()
        self._pending_unlocks.clear()
        self._consecutive_no_extinction = 0
        self._used_pressure_kinds.clear()
        self._min_species_count = 999
        self._exploration_flags.clear()
        
        progress_file = self._get_progress_file()
        if progress_file.exists():
            progress_file.unlink()
        
        logger.info("[成就] 进度已重置")
    
    def get_stats(self) -> dict:
        """获取成就统计"""
        total = len(ACHIEVEMENTS)
        unlocked = sum(1 for p in self._progress.values() if p.unlocked)
        
        by_category = {}
        for ach in ACHIEVEMENTS.values():
            cat = ach.category.value
            if cat not in by_category:
                by_category[cat] = {"total": 0, "unlocked": 0}
            by_category[cat]["total"] += 1
            progress = self._get_progress(ach.id)
            if progress.unlocked:
                by_category[cat]["unlocked"] += 1
        
        by_rarity = {}
        for ach in ACHIEVEMENTS.values():
            rarity = ach.rarity.value
            if rarity not in by_rarity:
                by_rarity[rarity] = {"total": 0, "unlocked": 0}
            by_rarity[rarity]["total"] += 1
            progress = self._get_progress(ach.id)
            if progress.unlocked:
                by_rarity[rarity]["unlocked"] += 1
        
        return {
            "total": total,
            "unlocked": unlocked,
            "percentage": round(unlocked / total * 100, 1) if total > 0 else 0,
            "by_category": by_category,
            "by_rarity": by_rarity,
        }

