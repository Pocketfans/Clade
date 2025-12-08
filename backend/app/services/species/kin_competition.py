"""亲缘差异化竞争系统 - 实现同属竞争优胜劣汰

核心理念：
1. 同属近缘（≤4代共同祖先）+ 同生态位 → 激烈竞争，赢者通吃
2. 异属远缘 + 同生态位 → 温和竞争，按比例瓜分资源
3. 不同营养级 → 捕食关系，非竞争关系

竞争结果：
- 同属强者：死亡率↓，繁殖率↑（竞争优势）
- 同属弱者：死亡率↑，繁殖率↓（被淘汰）
- 异属物种：按种群比例承担资源压力（共存）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.config import EcologyBalanceConfig

logger = logging.getLogger(__name__)


@dataclass
class CompetitionResult:
    """单个物种的竞争结果"""
    lineage_code: str
    # 竞争修正值：正数=优势（死亡率减少），负数=劣势（死亡率增加）
    mortality_modifier: float = 0.0
    # 繁殖修正值：正数=优势（繁殖率增加），负数=劣势
    reproduction_modifier: float = 0.0
    # 竞争状态描述
    status: str = "neutral"  # "dominant", "subordinate", "neutral", "coexisting"
    # 主要竞争对手
    main_competitor: str = ""
    # 适应度得分
    fitness_score: float = 0.0


class KinCompetitionCalculator:
    """亲缘差异化竞争计算器
    
    实现"同属竞争优胜劣汰、异属瓜分共存"的生态机制。
    """
    
    def __init__(self, config: EcologyBalanceConfig | None = None):
        self._config = config
        # 缓存：物种谱系路径 {lineage_code: [ancestor_codes]}
        self._lineage_cache: dict[str, list[str]] = {}
        # 缓存：物种间亲缘代数 {(code1, code2): generations}
        self._kinship_cache: dict[tuple[str, str], int] = {}
    
    def reload_config(self, config: EcologyBalanceConfig) -> None:
        self._config = config
    
    def calculate_competition(
        self,
        species_list: Sequence[Species],
        tile_populations: dict[str, dict[int, float]] | None = None,
        niche_overlaps: dict[str, float] | None = None,
    ) -> dict[str, CompetitionResult]:
        """计算所有物种的竞争结果
        
        Args:
            species_list: 存活物种列表
            tile_populations: {lineage_code: {tile_id: population}} 地块种群分布
            niche_overlaps: {lineage_code: overlap_score} 生态位重叠度
            
        Returns:
            {lineage_code: CompetitionResult} 每个物种的竞争结果
        """
        if not self._config or not self._config.enable_kin_competition:
            # 未启用差异化竞争，返回空结果
            return {sp.lineage_code: CompetitionResult(lineage_code=sp.lineage_code) 
                    for sp in species_list}
        
        cfg = self._config
        results: dict[str, CompetitionResult] = {}
        
        # 1. 按营养级分组
        trophic_groups = self._group_by_trophic_level(species_list)
        
        # 2. 计算每个物种的适应度
        fitness_scores = self._calculate_fitness_scores(species_list)
        
        # 3. 在每个营养级内计算竞争
        for trophic_level, group in trophic_groups.items():
            if len(group) <= 1:
                # 独占营养级，无竞争
                for sp in group:
                    results[sp.lineage_code] = CompetitionResult(
                        lineage_code=sp.lineage_code,
                        status="dominant",
                        fitness_score=fitness_scores.get(sp.lineage_code, 0.5),
                    )
                continue
            
            # 计算组内竞争
            group_results = self._calculate_intra_trophic_competition(
                group, fitness_scores, niche_overlaps, cfg
            )
            results.update(group_results)
        
        return results
    
    def _group_by_trophic_level(
        self, species_list: Sequence[Species]
    ) -> dict[float, list[Species]]:
        """按营养级分组（四舍五入到0.5）"""
        groups: dict[float, list[Species]] = {}
        for sp in species_list:
            # 四舍五入到0.5，如 1.3→1.5, 2.7→2.5
            tl = round(sp.trophic_level * 2) / 2
            if tl not in groups:
                groups[tl] = []
            groups[tl].append(sp)
        return groups
    
    def _calculate_fitness_scores(
        self, species_list: Sequence[Species]
    ) -> dict[str, float]:
        """计算每个物种的综合适应度得分 (0-1)
        
        【生物学改进】综合考虑：
        - 种群数量（相对于同营养级平均）- 种群大=竞争优势
        - 繁殖速度 - r策略物种恢复快
        - 环境适应性（抗性）- 广适性物种更稳定
        - 生态位专化度 - 专化物种在特定环境更强
        - 【新增】种群趋势 - 正在增长的物种更有优势
        - 【新增】物种年龄 - 老物种可能有演化包袱
        """
        cfg = self._config
        scores: dict[str, float] = {}
        
        # 计算各营养级的平均种群
        trophic_pops: dict[float, list[float]] = {}
        for sp in species_list:
            tl = round(sp.trophic_level * 2) / 2
            pop = float(sp.morphology_stats.get("population", 0) or 0)
            if tl not in trophic_pops:
                trophic_pops[tl] = []
            trophic_pops[tl].append(pop)
        
        trophic_avg_pop = {
            tl: np.mean(pops) if pops else 1.0 
            for tl, pops in trophic_pops.items()
        }
        
        for sp in species_list:
            tl = round(sp.trophic_level * 2) / 2
            avg_pop = trophic_avg_pop.get(tl, 1.0) or 1.0
            
            # 1. 种群因子（相对于同营养级平均）
            pop = float(sp.morphology_stats.get("population", 0) or 0)
            pop_factor = min(2.0, pop / avg_pop) / 2.0  # 归一化到 0-1
            
            # 2. 繁殖速度因子
            repro_speed = sp.abstract_traits.get("繁殖速度", 5) / 10.0
            
            # 3. 环境适应性因子（抗性平均值）
            resistances = [
                sp.abstract_traits.get("耐热性", 5),
                sp.abstract_traits.get("耐寒性", 5),
                sp.abstract_traits.get("耐旱性", 5),
                sp.abstract_traits.get("耐盐性", 5),
            ]
            resistance_factor = np.mean(resistances) / 10.0
            
            # 4. 专化度因子（演化潜力的反面）
            evo_potential = sp.hidden_traits.get("evolution_potential", 0.5)
            specialization = 1.0 - evo_potential  # 高演化潜力=低专化
            
            # 5. 【新增】种群趋势因子 - 正在增长的物种有优势
            # 使用死亡率作为代理：低死亡率=正在繁荣
            recent_death_rate = sp.morphology_stats.get("death_rate", 0.3) or 0.3
            trend_factor = max(0.0, 1.0 - recent_death_rate * 1.5)  # 死亡率低=趋势好
            
            # 6. 【新增】物种年龄因子 - 新物种有适应性优势，老物种可能有演化包袱
            species_age = sp.morphology_stats.get("age_turns", 0) or 0
            if species_age <= 3:
                age_factor = 0.7  # 新物种：适应性优势
            elif species_age <= 10:
                age_factor = 0.5  # 中等年龄
            else:
                age_factor = 0.3  # 老物种：可能有演化包袱
            
            # 加权综合（权重总和=1.0）
            fitness = (
                pop_factor * cfg.fitness_weight_population * 0.8 +       # 种群权重略降
                repro_speed * cfg.fitness_weight_reproduction * 0.8 +    # 繁殖权重略降
                resistance_factor * cfg.fitness_weight_resistance +      # 抗性保持
                specialization * cfg.fitness_weight_specialization +     # 专化保持
                trend_factor * 0.15 +                                    # 趋势因子
                age_factor * 0.05                                        # 年龄因子
            )
            
            scores[sp.lineage_code] = min(1.0, max(0.0, fitness))
        
        return scores
    
    def _calculate_intra_trophic_competition(
        self,
        group: list[Species],
        fitness_scores: dict[str, float],
        niche_overlaps: dict[str, float] | None,
        cfg: EcologyBalanceConfig,
    ) -> dict[str, CompetitionResult]:
        """计算同营养级内的竞争
        
        核心逻辑：
        1. 同属近缘：激烈竞争，适应度高者获优势，低者被惩罚
        2. 异属远缘：温和竞争，按比例共存
        """
        results: dict[str, CompetitionResult] = {}
        
        # 初始化结果
        for sp in group:
            results[sp.lineage_code] = CompetitionResult(
                lineage_code=sp.lineage_code,
                fitness_score=fitness_scores.get(sp.lineage_code, 0.5),
            )
        
        # 两两比较
        for i, sp1 in enumerate(group):
            for sp2 in group[i+1:]:
                code1, code2 = sp1.lineage_code, sp2.lineage_code
                
                # 计算亲缘代数
                kin_generations = self._get_kinship_generations(sp1, sp2)
                is_kin = kin_generations <= cfg.kin_generation_threshold
                
                # 获取生态位重叠度
                overlap1 = niche_overlaps.get(code1, 0.5) if niche_overlaps else 0.5
                overlap2 = niche_overlaps.get(code2, 0.5) if niche_overlaps else 0.5
                avg_overlap = (overlap1 + overlap2) / 2
                
                # 获取适应度
                fit1 = fitness_scores.get(code1, 0.5)
                fit2 = fitness_scores.get(code2, 0.5)
                
                # 【生物学修正】竞争强度主要由生态位重叠度决定，亲缘关系作为修饰因子
                # 高重叠度（>0.6）：激烈竞争，无论亲缘关系
                # 中等重叠度（0.3-0.6）：同属激烈竞争，异属温和竞争
                # 低重叠度（<0.3）：几乎不竞争（生态位分化）
                
                if avg_overlap > 0.6:
                    # === 高生态位重叠：激烈竞争（趋同进化/同生态位）===
                    # 亲缘关系增强竞争强度，但远缘高重叠也会激烈竞争
                    kin_bonus = 1.3 if is_kin else 1.0  # 同属额外+30%强度
                    self._apply_kin_competition(
                        results, code1, code2, fit1, fit2, avg_overlap * kin_bonus, cfg, sp1, sp2
                    )
                elif avg_overlap > 0.3:
                    if is_kin:
                        # === 中等重叠 + 同属：激烈竞争 ===
                        self._apply_kin_competition(
                            results, code1, code2, fit1, fit2, avg_overlap, cfg, sp1, sp2
                        )
                    else:
                        # === 中等重叠 + 异属：温和竞争（资源分割共存）===
                        self._apply_coexistence_competition(
                            results, code1, code2, fit1, fit2, avg_overlap, cfg
                        )
                # 低重叠度（<0.3）：生态位分化，几乎不竞争（适应辐射成功）
        
        return results
    
    def _apply_kin_competition(
        self,
        results: dict[str, CompetitionResult],
        code1: str, code2: str,
        fit1: float, fit2: float,
        overlap: float,
        cfg: EcologyBalanceConfig,
        sp1: Species | None = None,
        sp2: Species | None = None,
    ) -> None:
        """应用同属竞争：优胜劣汰
        
        【生物学原理】
        - 竞争排斥原则：同生态位物种不能长期共存
        - 世代时间影响：快繁殖物种竞争效果更快显现
        - 避难所效应：弱者可在边缘栖息地存活
        """
        fitness_diff = fit1 - fit2
        
        # 【生物学改进】世代时间影响竞争速度
        # 快繁殖物种（如细菌、昆虫）竞争结果更快显现
        # 慢繁殖物种（如大型哺乳动物）竞争是渐进的
        generation_speed_factor = 1.0
        if sp1 and sp2:
            repro1 = sp1.abstract_traits.get("繁殖速度", 5)
            repro2 = sp2.abstract_traits.get("繁殖速度", 5)
            avg_repro = (repro1 + repro2) / 2
            # 繁殖速度 1-10，中值5。高于5加速，低于5减速
            generation_speed_factor = 0.6 + avg_repro * 0.08  # 范围 0.68-1.4
        
        # 只有差距超过阈值才触发优胜劣汰
        if abs(fitness_diff) < cfg.kin_disadvantage_threshold:
            # 势均力敌，双方都承受一定压力
            penalty = overlap * cfg.kin_competition_multiplier * 0.05
            results[code1].mortality_modifier -= penalty
            results[code2].mortality_modifier -= penalty
            results[code1].status = "contested"
            results[code2].status = "contested"
            return
        
        # 确定强者和弱者
        if fitness_diff > 0:
            winner_code, loser_code = code1, code2
            advantage = fitness_diff
        else:
            winner_code, loser_code = code2, code1
            advantage = -fitness_diff
        
        # 计算修正值（与适应度差距和生态位重叠成正比）
        # 【生物学改进】世代速度因子影响竞争效果显现速度
        intensity = overlap * cfg.kin_competition_multiplier * advantage * generation_speed_factor
        
        # 强者获得优势
        winner_bonus = min(cfg.kin_winner_mortality_reduction, intensity * 0.5)
        results[winner_code].mortality_modifier += winner_bonus
        results[winner_code].reproduction_modifier += winner_bonus * 0.5
        results[winner_code].status = "dominant"
        results[winner_code].main_competitor = loser_code
        
        # 弱者被惩罚（惩罚更重，实现淘汰）
        loser_penalty = min(cfg.kin_loser_mortality_penalty, intensity * 1.0)
        
        # 【生物学改进】避难所效应 (Refuge Effect)
        # 即使被竞争排斥，弱势物种仍可能在边缘栖息地存活
        # 生态位重叠度越低，避难所越大，惩罚越小
        refuge_factor = 1.0 - (1.0 - overlap) * 0.5  # 重叠70%时，惩罚降到85%
        loser_penalty *= refuge_factor
        
        results[loser_code].mortality_modifier -= loser_penalty
        results[loser_code].reproduction_modifier -= loser_penalty * 0.3
        results[loser_code].status = "subordinate"
        results[loser_code].main_competitor = winner_code
        
        logger.debug(
            f"[同属竞争] {winner_code} vs {loser_code}: "
            f"适应度差={advantage:.2f}, 重叠={overlap:.2f}, "
            f"强者bonus={winner_bonus:.3f}, 弱者penalty={loser_penalty:.3f} (避难所系数={refuge_factor:.2f})"
        )
    
    def _apply_coexistence_competition(
        self,
        results: dict[str, CompetitionResult],
        code1: str, code2: str,
        fit1: float, fit2: float,
        overlap: float,
        cfg: EcologyBalanceConfig,
    ) -> None:
        """应用异属竞争：按比例共存"""
        # 异属竞争较温和，双方按适应度比例承担压力
        total_fit = fit1 + fit2 + 0.01  # 防止除零
        
        # 基础压力（较低）
        base_pressure = overlap * cfg.non_kin_competition_multiplier * 0.1
        
        # 按适应度反比分配压力（适应度低的承担更多）
        pressure1 = base_pressure * (1 - fit1 / total_fit)
        pressure2 = base_pressure * (1 - fit2 / total_fit)
        
        results[code1].mortality_modifier -= pressure1
        results[code2].mortality_modifier -= pressure2
        results[code1].status = "coexisting"
        results[code2].status = "coexisting"
    
    def _get_kinship_generations(self, sp1: Species, sp2: Species) -> int:
        """计算两个物种的亲缘代数（共享几代祖先）
        
        返回值：
        - 0: 同一物种
        - 1: 父子关系
        - 2: 祖孙关系或兄弟关系
        - N: 需要追溯N代才能找到共同祖先
        - 999: 无共同祖先（不同属）
        """
        code1, code2 = sp1.lineage_code, sp2.lineage_code
        
        # 检查缓存
        cache_key = (min(code1, code2), max(code1, code2))
        if cache_key in self._kinship_cache:
            return self._kinship_cache[cache_key]
        
        # 构建祖先链
        ancestors1 = self._get_ancestor_chain(sp1)
        ancestors2 = self._get_ancestor_chain(sp2)
        
        # 查找共同祖先
        for gen1, anc1 in enumerate(ancestors1):
            if anc1 in ancestors2:
                gen2 = ancestors2.index(anc1)
                result = max(gen1, gen2)
                self._kinship_cache[cache_key] = result
                return result
        
        # 无共同祖先
        self._kinship_cache[cache_key] = 999
        return 999
    
    def _get_ancestor_chain(self, sp: Species) -> list[str]:
        """获取物种的祖先链 [self, parent, grandparent, ...]"""
        code = sp.lineage_code
        if code in self._lineage_cache:
            return self._lineage_cache[code]
        
        chain = [code]
        current = sp
        
        # 追溯最多10代
        for _ in range(10):
            parent_code = getattr(current, 'parent_code', None)
            if not parent_code:
                break
            chain.append(parent_code)
            # 尝试获取父代物种对象（如果有的话）
            # 这里简化处理，只使用 lineage_code 前缀判断
            current = None
            break
        
        # 备用方案：使用 lineage_code 前缀推断
        # 例如 "A1B2C1" 的祖先链是 ["A1B2C1", "A1B2", "A1", "A"]
        if len(chain) == 1:
            chain = self._infer_ancestors_from_code(code)
        
        self._lineage_cache[code] = chain
        return chain
    
    def _infer_ancestors_from_code(self, code: str) -> list[str]:
        """从 lineage_code 推断祖先链
        
        例如 "A1B2C1" → ["A1B2C1", "A1B2", "A1", "A"]
        """
        chain = [code]
        
        # lineage_code 格式: 字母+数字 重复
        # 逐步去掉最后一个"字母+数字"组合
        import re
        pattern = re.compile(r'^(.+?)([A-Z]\d+)$')
        
        current = code
        for _ in range(10):
            match = pattern.match(current)
            if match:
                current = match.group(1)
                if current:
                    chain.append(current)
            else:
                break
        
        return chain
    
    def clear_cache(self) -> None:
        """清除缓存（新回合时调用）"""
        self._lineage_cache.clear()
        self._kinship_cache.clear()


# 单例
_kin_competition_calculator: KinCompetitionCalculator | None = None


def get_kin_competition_calculator() -> KinCompetitionCalculator:
    """获取亲缘竞争计算器单例"""
    global _kin_competition_calculator
    if _kin_competition_calculator is None:
        _kin_competition_calculator = KinCompetitionCalculator()
    return _kin_competition_calculator
