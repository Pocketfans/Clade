from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from ..models.species import Species


@dataclass(slots=True)
class TieringConfig:
    critical_limit: int
    focus_batch_size: int
    focus_batch_limit: int
    background_threshold: int


@dataclass(slots=True)
class TieredSpecies:
    critical: list[Species]
    focus: list[Species]
    background: list[Species]


class SpeciesTieringService:
    """按照关注/重点/背景三级策略划分物种。
    
    三层结构：
    1. Critical（关注层）：玩家主动标记的物种，最多 critical_limit 个（通常3个）
       - 默认情况下为空，只有玩家主动标记才会有物种
       - 获得最详细的 AI 分析和报告
    
    2. Focus（重点层）：生态强度最高的物种 + watchlist 中未进入 critical 的物种
       - 种群规模大、生态角色重要的物种
       - 获得批量 AI 处理
    
    3. Background（背景层）：种群低于阈值或生态强度低的物种
       - 使用规则计算，不消耗 AI 资源
    """

    def __init__(self, config: TieringConfig) -> None:
        self.config = config

    def classify(
        self, species_list: Sequence[Species], watchlist: set[str] | None = None
    ) -> TieredSpecies:
        """将物种列表分为三层。
        
        Args:
            species_list: 所有物种列表
            watchlist: 玩家关注的物种代码集合（用于 critical 层）
        
        Returns:
            TieredSpecies: 分层后的物种
        """
        watchlist = watchlist or set()
        background: list[Species] = []
        candidates: list[Species] = []
        for species in species_list:
            population = int(species.morphology_stats.get("population", 0) or 0)
            if population < self.config.background_threshold:
                species.is_background = True
                background.append(species)
            else:
                species.is_background = False
                candidates.append(species)

        score_map = {
            species.lineage_code: self._ecological_strength(species, watchlist)
            for species in candidates
        }
        scored = sorted(
            candidates,
            key=lambda sp: score_map[sp.lineage_code],
            reverse=True,
        )

        # Critical 层级：只包含玩家主动标记的物种（watchlist），最多 critical_limit 个
        # 如果 watchlist 为空，critical 就是空的
        critical: list[Species] = []
        if watchlist:
            critical_limit = max(1, self.config.critical_limit)
            watched_species = [sp for sp in scored if sp.lineage_code in watchlist]
            # 按生态强度排序，取前 critical_limit 个
            critical = sorted(
                watched_species,
                key=lambda sp: score_map[sp.lineage_code],
                reverse=True,
            )[:critical_limit]

        focus_limit = self.config.focus_batch_size * max(1, self.config.focus_batch_limit)
        focus: list[Species] = []
        for species in scored:
            if species in critical:
                continue
            if len(focus) >= focus_limit:
                break
            focus.append(species)

        extra_watchers = [
            species
            for species in scored
            if species.lineage_code in watchlist and species not in critical and species not in focus
        ]
        focus.extend(extra_watchers)
        if len(focus) > focus_limit:
            focus = sorted(
                focus,
                key=lambda sp: score_map.get(sp.lineage_code, 0.0),
                reverse=True,
            )[:focus_limit]

        focus_codes = {sp.lineage_code for sp in focus}
        for species in scored:
            if species in critical or species in focus:
                species.is_background = False
                continue
            species.is_background = True
            background.append(species)

        return TieredSpecies(critical=critical, focus=focus, background=background)

    def _ecological_strength(self, species: Species, watchlist: set[str]) -> float:
        """计算物种的生态强度，用于分层排序。
        
        基于生态学原理的多维度评分系统：
        1. 营养级权重（不同生态位的基础重要性）
        2. 相对种群规模（在同营养级内比较）
        3. 濒危程度（小种群的脆弱性）
        4. 生态位竞争强度（资源饱和度反映重要性）
        5. 观察列表加成
        
        设计理念：
        - 顶级捕食者即使种群小也应优先关注（关键物种效应）
        - 初级生产者按生物量评估（基础生态功能）
        - 濒危物种（种群<10万）获得保护性加权
        """
        population = float(species.morphology_stats.get("population", 0) or 0)
        desc = species.description.lower()
        
        # 1. 营养级基础权重（替代简单的对数种群）
        trophic_weight = self._get_trophic_weight(desc)
        
        # 2. 相对种群评分（归一化到 0-10 范围，避免数量级差异）
        # 使用对数但压缩范围
        if population > 0:
            # log(100) = 4.6, log(1000000) = 13.8
            # 归一化到 0-10: (log(pop) - 4) / 10 * 10
            pop_normalized = min(10.0, max(0.0, (math.log1p(population) - 4.0) / 1.0))
        else:
            pop_normalized = 0.0
        
        # 3. 营养级调整后的种群评分
        # 顶级捕食者：种群权重降低（小种群也重要）
        # 生产者：种群权重提高（需要大生物量支撑生态系统）
        if trophic_weight >= 4.0:  # 顶级捕食者/关键物种
            pop_factor = 0.3  # 30%权重给种群
            base_score = trophic_weight * 3.0  # 基础分高
        elif trophic_weight >= 2.5:  # 次级消费者
            pop_factor = 0.5  # 50%权重给种群
            base_score = trophic_weight * 2.0
        else:  # 生产者/初级消费者
            pop_factor = 0.7  # 70%权重给种群
            base_score = trophic_weight * 1.5
        
        population_score = pop_normalized * pop_factor
        
        # 4. 濒危度加成（小种群的保护性加权）
        endangerment_bonus = 0.0
        if 0 < population < 10000:  # 极度濒危
            endangerment_bonus = 3.0
        elif population < 50000:  # 濒危
            endangerment_bonus = 2.0
        elif population < 100000:  # 易危
            endangerment_bonus = 1.0
        
        # 5. 特殊生态角色加成
        role_bonus = 0.0
        if any(k in desc for k in ("关键", "keystone", "工程", "engineer")):
            role_bonus = 2.0  # 关键物种/生态工程师
        elif any(k in desc for k in ("旗舰", "flagship", "伞护", "umbrella")):
            role_bonus = 1.5  # 旗舰物种/伞护物种
        
        # 6. 观察列表巨大加成（玩家关注的必然重要）
        watch_bonus = 20.0 if species.lineage_code in watchlist else 0.0
        
        # 综合评分
        strength = base_score + population_score + endangerment_bonus + role_bonus + watch_bonus
        
        return strength
    
    def _get_trophic_weight(self, desc_lower: str) -> float:
        """根据描述推断营养级权重。
        
        营养级理论：
        - 顶级捕食者：种群小但控制整个食物网结构（关键物种效应）
        - 次级消费者：中等重要性
        - 初级生产者：需要大生物量但个体可替代性强
        
        Returns:
            float: 营养级权重（1.0-5.0）
        """
        # 顶级捕食者 / 关键物种（营养级 4-5）
        if any(k in desc_lower for k in ("顶级", "顶端", "apex", "顶级捕食", "霸主")):
            return 5.0
        if any(k in desc_lower for k in ("大型捕食", "掠食者", "猛禽", "猛兽")):
            return 4.5
        
        # 次级捕食者（营养级 3）
        if any(k in desc_lower for k in ("捕食", "肉食", "carnivore", "猎食")):
            return 3.5
        
        # 杂食动物（营养级 2.5-3）
        if any(k in desc_lower for k in ("杂食", "omnivore")):
            return 3.0
        
        # 草食动物 / 初级消费者（营养级 2）
        if any(k in desc_lower for k in ("草食", "herbivore", "植食", "滤食", "浮游动物")):
            return 2.0
        
        # 初级生产者（营养级 1）
        if any(k in desc_lower for k in ("生产者", "producer", "光合", "photosynth", "自养", "autotroph", "藻类", "浮游植物")):
            return 1.5
        
        # 分解者（特殊生态位，重要但可替代）
        if any(k in desc_lower for k in ("分解", "decomposer", "腐食", "清道夫", "scavenger")):
            return 2.5
        
        # 默认：中等重要性
        return 2.0
