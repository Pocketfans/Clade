"""食物网管理服务 (Food Web Manager)

自动维护和更新生态系统中的食物链关系。

核心功能：
1. 自动为消费者分配猎物（如果缺失）
2. 检测并处理猎物灭绝后的替代
3. 将新物种加入食物网（作为潜在猎物）
4. 分析食物网健康状况和瓶颈

设计原则：
- 每回合开始时自动验证和修复食物网
- 使用 PredationService 的推断方法
- 不依赖 LLM，使用规则驱动
- 记录所有变更供叙事使用
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ...models.species import Species
    from ...repositories.species_repository import SpeciesRepository

from .predation import PredationService

logger = logging.getLogger(__name__)


@dataclass
class FoodWebChange:
    """食物网变更记录"""
    species_code: str
    species_name: str
    change_type: str  # "prey_assigned", "prey_replaced", "prey_added", "prey_lost"
    details: str
    old_prey: list[str] = field(default_factory=list)
    new_prey: list[str] = field(default_factory=list)


@dataclass
class FoodWebAnalysis:
    """食物网分析结果"""
    total_species: int
    total_links: int
    orphaned_consumers: list[str]  # 没有猎物的消费者
    starving_species: list[str]  # 猎物全部灭绝的物种
    keystone_species: list[str]  # 关键物种（被3+物种依赖）
    isolated_species: list[str]  # 既无猎物也无捕食者的物种
    avg_prey_per_consumer: float
    food_web_density: float  # 连接密度
    bottleneck_warnings: list[str]  # 瓶颈警告
    health_score: float  # 0-1, 食物网健康度


class FoodWebManager:
    """食物网管理服务
    
    负责自动维护和更新食物链关系，确保生态系统的食物网完整性。
    """
    
    def __init__(
        self,
        predation_service: PredationService | None = None,
    ):
        self._predation = predation_service or PredationService()
        self._logger = logging.getLogger(__name__)
        
        # 本回合的变更记录
        self._changes: list[FoodWebChange] = []
    
    def clear_changes(self):
        """清空变更记录（每回合开始时调用）"""
        self._changes = []
    
    def get_changes(self) -> list[FoodWebChange]:
        """获取本回合的所有变更"""
        return self._changes
    
    # ========== 核心功能：自动维护食物网 ==========
    
    def maintain_food_web(
        self,
        all_species: Sequence[Species],
        species_repository: "SpeciesRepository",
        turn_index: int = 0,
    ) -> FoodWebAnalysis:
        """维护食物网（每回合开始时调用）
        
        自动执行以下任务：
        1. 检测没有猎物的消费者，自动分配
        2. 检测猎物已灭绝的物种，寻找替代
        3. 分析食物网健康状况
        
        Args:
            all_species: 所有物种列表
            species_repository: 物种仓库（用于保存变更）
            turn_index: 当前回合数
            
        Returns:
            食物网分析结果
        """
        self.clear_changes()
        
        alive_species = [s for s in all_species if s.status == "alive"]
        alive_codes = {s.lineage_code for s in alive_species}
        species_map = {s.lineage_code: s for s in alive_species}
        
        modified_species = []
        
        # 1. 处理缺少猎物的消费者
        for sp in alive_species:
            if sp.trophic_level < 2.0:
                continue  # 跳过生产者
            
            current_prey = sp.prey_species or []
            
            # 检查是否需要分配猎物
            if not current_prey:
                # 完全没有猎物，自动分配
                new_prey, new_prefs = self._predation.auto_assign_prey(sp, alive_species)
                if new_prey:
                    self._assign_prey(sp, new_prey, new_prefs, "prey_assigned")
                    modified_species.append(sp)
                    self._logger.info(
                        f"[食物网] {sp.common_name}({sp.lineage_code}) 自动分配猎物: {new_prey}"
                    )
            else:
                # 检查猎物是否都还活着
                valid_prey = [code for code in current_prey if code in alive_codes]
                extinct_prey = [code for code in current_prey if code not in alive_codes]
                
                if extinct_prey:
                    # 有猎物灭绝了
                    self._logger.info(
                        f"[食物网] {sp.common_name} 的猎物 {extinct_prey} 已灭绝"
                    )
                    
                    if not valid_prey:
                        # 所有猎物都灭绝了，需要完全重新分配
                        new_prey, new_prefs = self._predation.auto_assign_prey(sp, alive_species)
                        if new_prey:
                            self._assign_prey(
                                sp, new_prey, new_prefs, "prey_replaced",
                                old_prey=current_prey
                            )
                            modified_species.append(sp)
                            self._logger.info(
                                f"[食物网] {sp.common_name} 猎物全灭绝，替换为: {new_prey}"
                            )
                        else:
                            # 找不到替代猎物，记录警告
                            self._changes.append(FoodWebChange(
                                species_code=sp.lineage_code,
                                species_name=sp.common_name,
                                change_type="prey_lost",
                                details=f"所有猎物灭绝，无法找到替代食物源",
                                old_prey=current_prey,
                                new_prey=[],
                            ))
                    else:
                        # 部分猎物灭绝，寻找替代并更新偏好
                        replacement = self._find_replacement_prey(
                            sp, extinct_prey, valid_prey, alive_species
                        )
                        if replacement:
                            # 合并有效猎物和替代猎物
                            new_prey_list = valid_prey + replacement
                            new_prefs = self._recalculate_preferences(
                                sp, new_prey_list, species_map
                            )
                            self._assign_prey(
                                sp, new_prey_list, new_prefs, "prey_added",
                                old_prey=current_prey
                            )
                            modified_species.append(sp)
                            self._logger.info(
                                f"[食物网] {sp.common_name} 添加替代猎物: {replacement}"
                            )
        
        # 2. 保存修改
        for sp in modified_species:
            species_repository.upsert(sp)
        
        # 3. 分析食物网状况
        analysis = self.analyze_food_web(alive_species)
        
        if modified_species:
            self._logger.info(
                f"[食物网维护] 回合{turn_index}: 修改了 {len(modified_species)} 个物种的食物关系"
            )
        
        return analysis
    
    def _assign_prey(
        self,
        species: Species,
        prey_codes: list[str],
        preferences: dict[str, float],
        change_type: str,
        old_prey: list[str] | None = None,
    ):
        """分配猎物给物种"""
        old_prey = old_prey or list(species.prey_species or [])
        
        species.prey_species = prey_codes
        species.prey_preferences = preferences
        
        # 同时更新 diet_type
        if prey_codes:
            if species.trophic_level >= 3.5:
                species.diet_type = "carnivore"
            elif species.trophic_level >= 2.5:
                species.diet_type = "omnivore"
            else:
                species.diet_type = "herbivore"
        
        self._changes.append(FoodWebChange(
            species_code=species.lineage_code,
            species_name=species.common_name,
            change_type=change_type,
            details=f"猎物: {old_prey} → {prey_codes}",
            old_prey=old_prey,
            new_prey=prey_codes,
        ))
    
    def _find_replacement_prey(
        self,
        predator: Species,
        extinct_prey: list[str],
        valid_prey: list[str],
        all_species: Sequence[Species],
    ) -> list[str]:
        """为灭绝的猎物寻找替代
        
        规则：
        - 寻找与灭绝猎物营养级相近的物种
        - 优先同栖息地类型
        - 不重复添加已有的猎物
        """
        species_map = {s.lineage_code: s for s in all_species if s.status == "alive"}
        
        # 计算灭绝猎物的平均营养级（从历史数据推断）
        # 假设猎物营养级比捕食者低0.5-1.5
        target_trophic = predator.trophic_level - 1.0
        
        # 使用优化的推断方法
        candidates = self._predation.infer_prey_from_trophic(
            predator, all_species, max_prey_count=len(extinct_prey) + 2
        )
        
        # 过滤掉已有的猎物
        new_candidates = [c for c in candidates if c not in valid_prey]
        
        # 限制数量（与灭绝的猎物数量相当）
        return new_candidates[:len(extinct_prey)]
    
    def _recalculate_preferences(
        self,
        predator: Species,
        prey_codes: list[str],
        species_map: dict[str, Species],
    ) -> dict[str, float]:
        """重新计算猎物偏好比例"""
        if not prey_codes:
            return {}
        
        weights = {}
        total_weight = 0.0
        
        for code in prey_codes:
            prey = species_map.get(code)
            if not prey:
                weights[code] = 1.0
            else:
                # 基于营养级差和种群大小计算权重
                level_diff = predator.trophic_level - prey.trophic_level
                # 营养级差越接近1.0，权重越高
                base_weight = 1.0 / (abs(level_diff - 1.0) + 0.5)
                
                # 种群越大，可用性越高
                pop = prey.morphology_stats.get("population", 100)
                pop_factor = min(1.5, 0.5 + (pop / 10000))
                
                weights[code] = base_weight * pop_factor
            
            total_weight += weights[code]
        
        # 归一化
        if total_weight > 0:
            for code in weights:
                weights[code] /= total_weight
        
        return weights
    
    # ========== 食物网分析 ==========
    
    def analyze_food_web(self, all_species: Sequence[Species]) -> FoodWebAnalysis:
        """分析食物网健康状况
        
        Args:
            all_species: 所有存活物种
            
        Returns:
            食物网分析结果
        """
        alive_species = [s for s in all_species if s.status == "alive"]
        alive_codes = {s.lineage_code for s in alive_species}
        
        total_species = len(alive_species)
        total_links = 0
        orphaned_consumers = []
        starving_species = []
        prey_counts = {}  # 每个物种被多少捕食者依赖
        
        consumer_count = 0
        total_prey_count = 0
        
        for sp in alive_species:
            prey_codes = sp.prey_species or []
            valid_prey = [c for c in prey_codes if c in alive_codes]
            total_links += len(valid_prey)
            
            # 统计被捕食
            for prey_code in valid_prey:
                prey_counts[prey_code] = prey_counts.get(prey_code, 0) + 1
            
            # 检查消费者状态
            if sp.trophic_level >= 2.0:
                consumer_count += 1
                total_prey_count += len(valid_prey)
                
                if not valid_prey:
                    if not prey_codes:
                        orphaned_consumers.append(sp.lineage_code)
                    else:
                        starving_species.append(sp.lineage_code)
        
        # 识别关键物种（被3+物种依赖）
        keystone_species = [
            code for code, count in prey_counts.items()
            if count >= 3
        ]
        
        # 识别孤立物种（既无猎物也无捕食者）
        isolated_species = []
        for sp in alive_species:
            has_prey = bool(sp.prey_species and any(c in alive_codes for c in sp.prey_species))
            has_predator = sp.lineage_code in prey_counts
            
            if not has_prey and not has_predator and sp.trophic_level >= 2.0:
                isolated_species.append(sp.lineage_code)
        
        # 计算统计指标
        avg_prey = total_prey_count / consumer_count if consumer_count > 0 else 0
        
        # 连接密度 = 实际链接数 / 可能的最大链接数
        max_links = total_species * (total_species - 1) / 2
        density = total_links / max_links if max_links > 0 else 0
        
        # 生成瓶颈警告
        warnings = []
        if orphaned_consumers:
            warnings.append(f"⚠️ {len(orphaned_consumers)} 个消费者没有猎物")
        if starving_species:
            warnings.append(f"🚨 {len(starving_species)} 个物种的猎物已全部灭绝")
        if keystone_species:
            warnings.append(f"⭐ {len(keystone_species)} 个关键物种（被3+物种依赖）")
        if avg_prey < 1.5 and consumer_count > 3:
            warnings.append(f"📉 平均猎物种类偏低 ({avg_prey:.1f})")
        
        # 计算健康度评分
        health = self._calculate_health_score(
            total_species, total_links, len(orphaned_consumers),
            len(starving_species), len(keystone_species), avg_prey
        )
        
        return FoodWebAnalysis(
            total_species=total_species,
            total_links=total_links,
            orphaned_consumers=orphaned_consumers,
            starving_species=starving_species,
            keystone_species=keystone_species,
            isolated_species=isolated_species,
            avg_prey_per_consumer=round(avg_prey, 2),
            food_web_density=round(density, 4),
            bottleneck_warnings=warnings,
            health_score=round(health, 2),
        )
    
    def _calculate_health_score(
        self,
        total_species: int,
        total_links: int,
        orphaned: int,
        starving: int,
        keystone: int,
        avg_prey: float,
    ) -> float:
        """计算食物网健康度评分 (0-1)"""
        if total_species == 0:
            return 0.0
        
        score = 1.0
        
        # 孤立消费者惩罚
        orphan_ratio = orphaned / total_species
        score -= orphan_ratio * 0.3
        
        # 饥饿物种惩罚（更严重）
        starving_ratio = starving / total_species
        score -= starving_ratio * 0.5
        
        # 链接密度奖励
        links_per_species = total_links / total_species
        if links_per_species >= 2:
            score += 0.1
        elif links_per_species < 1:
            score -= 0.1
        
        # 平均猎物种类奖励
        if avg_prey >= 2:
            score += 0.1
        elif avg_prey < 1:
            score -= 0.1
        
        # 关键物种奖励（表示食物网有结构）
        if keystone > 0:
            score += min(0.1, keystone * 0.02)
        
        return max(0.0, min(1.0, score))
    
    # ========== 新物种集成 ==========
    
    def integrate_new_species(
        self,
        new_species: Species,
        all_species: Sequence[Species],
        species_repository: "SpeciesRepository",
    ) -> list[FoodWebChange]:
        """将新物种集成到食物网中
        
        1. 如果是消费者，自动分配猎物
        2. 检查是否可以成为其他捕食者的猎物
        
        Args:
            new_species: 新物种
            all_species: 所有物种
            species_repository: 物种仓库
            
        Returns:
            变更记录列表
        """
        changes = []
        alive_species = [s for s in all_species if s.status == "alive"]
        species_map = {s.lineage_code: s for s in alive_species}
        
        # 1. 为消费者分配猎物
        if new_species.trophic_level >= 2.0 and not new_species.prey_species:
            prey_codes, preferences = self._predation.auto_assign_prey(
                new_species, alive_species
            )
            if prey_codes:
                new_species.prey_species = prey_codes
                new_species.prey_preferences = preferences
                species_repository.upsert(new_species)
                
                changes.append(FoodWebChange(
                    species_code=new_species.lineage_code,
                    species_name=new_species.common_name,
                    change_type="prey_assigned",
                    details=f"新物种自动分配猎物: {prey_codes}",
                    old_prey=[],
                    new_prey=prey_codes,
                ))
                
                self._logger.info(
                    f"[食物网] 新物种 {new_species.common_name} 分配猎物: {prey_codes}"
                )
        
        # 2. 检查是否可以成为其他捕食者的猎物
        # （保守策略：只在猎物严重不足的捕食者中添加）
        new_code = new_species.lineage_code
        new_trophic = new_species.trophic_level
        
        for predator in alive_species:
            if predator.lineage_code == new_code:
                continue
            if predator.trophic_level <= new_trophic:
                continue  # 营养级不够高
            
            # 检查是否适合作为猎物
            trophic_diff = predator.trophic_level - new_trophic
            if not (0.5 <= trophic_diff <= 1.5):
                continue
            
            # 检查栖息地兼容性
            if predator.habitat_type != new_species.habitat_type:
                if not self._predation._habitats_compatible(
                    predator.habitat_type, new_species.habitat_type
                ):
                    continue
            
            current_prey = predator.prey_species or []
            alive_prey = [c for c in current_prey if c in species_map]
            
            # 只在猎物不足时添加（最多2种猎物时考虑添加）
            if len(alive_prey) <= 2 and new_code not in current_prey:
                # 添加为新猎物
                new_prey_list = alive_prey + [new_code]
                new_prefs = self._recalculate_preferences(
                    predator, new_prey_list, species_map | {new_code: new_species}
                )
                
                predator.prey_species = new_prey_list
                predator.prey_preferences = new_prefs
                species_repository.upsert(predator)
                
                changes.append(FoodWebChange(
                    species_code=predator.lineage_code,
                    species_name=predator.common_name,
                    change_type="prey_added",
                    details=f"添加新猎物 {new_species.common_name}",
                    old_prey=current_prey,
                    new_prey=new_prey_list,
                ))
                
                self._logger.info(
                    f"[食物网] {predator.common_name} 添加新猎物: {new_species.common_name}"
                )
        
        return changes
    
    # ========== 批量操作 ==========
    
    def batch_assign_prey(
        self,
        species_list: Sequence[Species],
        all_species: Sequence[Species],
        species_repository: "SpeciesRepository",
    ) -> int:
        """批量为物种分配猎物（用于初始化或修复）
        
        Args:
            species_list: 需要处理的物种列表
            all_species: 所有物种
            species_repository: 物种仓库
            
        Returns:
            修改的物种数量
        """
        modified_count = 0
        
        for sp in species_list:
            if sp.trophic_level < 2.0:
                continue
            if sp.prey_species:
                continue
            
            prey_codes, preferences = self._predation.auto_assign_prey(sp, all_species)
            if prey_codes:
                sp.prey_species = prey_codes
                sp.prey_preferences = preferences
                species_repository.upsert(sp)
                modified_count += 1
                
                self._logger.info(
                    f"[批量分配] {sp.common_name}: {prey_codes}"
                )
        
        return modified_count





