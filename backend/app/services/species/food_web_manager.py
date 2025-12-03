"""食物网管理服务 (Food Web Manager)

自动维护和更新生态系统中的食物链关系。

核心功能：
1. 自动为消费者分配猎物（如果缺失）
2. 检测并处理猎物灭绝后的替代
3. 将新物种加入食物网（作为潜在猎物）
4. 分析食物网健康状况和瓶颈
5. 【新增】猎物多样性阈值检查和自动补充
6. 【新增】新物种自动集成到食物网
7. 【新增】生成 trophic_interactions 反馈信号

设计原则：
- 每回合开始时自动验证和修复食物网
- 使用 PredationService 的推断方法
- 不依赖 LLM，使用规则驱动
- 记录所有变更供叙事使用
- 参数可配置化
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ...models.species import Species
    from ...repositories.species_repository import SpeciesRepository

from .predation import PredationService
from ...models.config import FoodWebConfig

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
    
    # 【新增】用于 trophic_interactions 反馈
    prey_shortage_species: list[str] = field(default_factory=list)  # 猎物数量低于阈值的物种
    new_producers: list[str] = field(default_factory=list)  # 本回合新增的生产者/初级消费者
    hungry_regions: list[int] = field(default_factory=list)  # 饥饿区域（地块ID）


class FoodWebManager:
    """食物网管理服务
    
    负责自动维护和更新食物链关系，确保生态系统的食物网完整性。
    
    【依赖注入】
    配置必须通过构造函数注入，内部方法不再调用 _load_food_web_config。
    如需刷新配置，使用 reload_config() 显式更新。
    """
    
    def __init__(
        self,
        predation_service: PredationService | None = None,
        config: FoodWebConfig | None = None,
    ):
        self._predation = predation_service or PredationService()
        self._logger = logging.getLogger(__name__)
        
        # 配置注入 - 如未提供则使用默认值并警告
        if config is None:
            self._logger.warning("[食物网] config 未注入，使用默认值")
            config = FoodWebConfig()
        self._config = config
        
        # 本回合的变更记录
        self._changes: list[FoodWebChange] = []
    
    def reload_config(self, config: FoodWebConfig | None = None) -> None:
        """热更新配置
        
        Args:
            config: 食物网配置（必须由调用方提供）
            
        注意: 配置应由 SimulationEngine.reload_configs() 统一从容器获取后传入。
        """
        if config is not None:
            self._config = config
            logger.info("[食物网管理] 配置已重新加载")
        self._logger.info("[食物网] 配置已重新加载")
    
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
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
        previous_species_codes: set[str] | None = None,
    ) -> FoodWebAnalysis:
        """维护食物网（每回合开始时调用）
        
        【v2增强】自动执行以下任务：
        1. 检测没有猎物的消费者，自动分配
        2. 检测猎物已灭绝的物种，寻找替代
        3. 【新增】猎物多样性阈值检查，不足时自动补充
        4. 【新增】检测新物种（T1/T2），集成到消费者的猎物列表
        5. 分析食物网健康状况
        
        Args:
            all_species: 所有物种列表
            species_repository: 物种仓库（用于保存变更）
            turn_index: 当前回合数
            tile_species_map: {tile_id: set(species_codes)} 地块→物种映射
            species_tiles: {species_code: set(tile_ids)} 物种→地块映射
            previous_species_codes: 上回合的物种代码集合（用于检测新物种）
            
        Returns:
            食物网分析结果
        """
        self.clear_changes()
        
        # 使用注入的配置
        cfg = self._config
        
        alive_species = [s for s in all_species if s.status == "alive"]
        alive_codes = {s.lineage_code for s in alive_species}
        species_map = {s.lineage_code: s for s in alive_species}
        
        modified_species = []
        prey_shortage_species = []
        new_producers = []
        
        # 【新增】检测本回合新增的物种（尤其是 T1/T2）
        if previous_species_codes is not None:
            new_species_codes = alive_codes - previous_species_codes
            for code in new_species_codes:
                sp = species_map.get(code)
                if sp and sp.trophic_level < 3.0:  # T1 或 T2
                    new_producers.append(code)
                    self._logger.info(f"[食物网] 检测到新 T{sp.trophic_level:.0f} 物种: {sp.common_name}")
        
        # 1. 处理缺少猎物的消费者
        for sp in alive_species:
            if sp.trophic_level < 2.0:
                continue  # 跳过生产者
            
            current_prey = sp.prey_species or []
            valid_prey = [code for code in current_prey if code in alive_codes]
            extinct_prey = [code for code in current_prey if code not in alive_codes]
            
            # 获取该营养级的最低猎物数量阈值
            min_prey_count = self._get_min_prey_count(sp.trophic_level, cfg)
            
            # 情况A: 完全没有猎物
            if not current_prey:
                new_prey, new_prefs = self._predation.auto_assign_prey(
                    sp, alive_species, 
                    tile_species_map=tile_species_map,
                    species_tiles=species_tiles
                )
                if new_prey:
                    self._assign_prey(sp, new_prey, new_prefs, "prey_assigned")
                    modified_species.append(sp)
                    self._logger.info(
                        f"[食物网] {sp.common_name}({sp.lineage_code}) 自动分配猎物: {new_prey}"
                    )
                    
            # 情况B: 有猎物灭绝
            elif extinct_prey:
                self._logger.info(
                    f"[食物网] {sp.common_name} 的猎物 {extinct_prey} 已灭绝"
                )
                
                if not valid_prey:
                    # 所有猎物都灭绝了，需要完全重新分配
                    new_prey, new_prefs = self._predation.auto_assign_prey(
                        sp, alive_species,
                        tile_species_map=tile_species_map,
                        species_tiles=species_tiles
                    )
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
                        sp, extinct_prey, valid_prey, alive_species,
                        tile_species_map=tile_species_map,
                        species_tiles=species_tiles
                    )
                    if replacement:
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
            
            # 【新增】情况C: 猎物存活但数量低于多样性阈值
            elif cfg.enable_prey_diversity_补充 and len(valid_prey) < min_prey_count:
                shortage = min_prey_count - len(valid_prey)
                additions_needed = min(shortage, cfg.max_prey_additions_per_turn)
                
                # 记录猎物不足
                prey_shortage_species.append(sp.lineage_code)
                
                # 寻找额外猎物
                additional_prey = self._find_additional_prey(
                    sp, valid_prey, alive_species, additions_needed,
                    tile_species_map=tile_species_map,
                    species_tiles=species_tiles,
                    new_producers=new_producers,
                    cfg=cfg
                )
                
                if additional_prey:
                    new_prey_list = valid_prey + additional_prey
                    new_prefs = self._recalculate_preferences(
                        sp, new_prey_list, species_map
                    )
                    self._assign_prey(
                        sp, new_prey_list, new_prefs, "prey_added",
                        old_prey=current_prey
                    )
                    modified_species.append(sp)
                    self._logger.info(
                        f"[食物网] {sp.common_name} 猎物多样性不足 ({len(valid_prey)}/{min_prey_count})，"
                        f"补充猎物: {additional_prey}"
                    )
        
        # 【新增】2. 将新生产者/初级消费者集成到现有消费者的猎物列表
        if cfg.auto_integrate_new_producers and new_producers:
            additional_modified = self._integrate_new_producers_to_consumers(
                new_producers, alive_species, species_map, species_repository,
                tile_species_map=tile_species_map,
                species_tiles=species_tiles,
                cfg=cfg
            )
            modified_species.extend(additional_modified)
        
        # 3. 保存修改
        unique_modified = list({sp.lineage_code: sp for sp in modified_species}.values())
        for sp in unique_modified:
            species_repository.upsert(sp)
        
        # 4. 分析食物网状况
        analysis = self.analyze_food_web(alive_species)
        
        # 【新增】附加反馈信息
        analysis.prey_shortage_species = prey_shortage_species
        analysis.new_producers = new_producers
        
        if unique_modified:
            self._logger.info(
                f"[食物网维护] 回合{turn_index}: 修改了 {len(unique_modified)} 个物种的食物关系"
            )
        
        return analysis
    
    def _get_min_prey_count(self, trophic_level: float, cfg: FoodWebConfig) -> int:
        """获取指定营养级的最低猎物数量阈值"""
        if trophic_level < 3.0:
            return cfg.min_prey_count_t2
        elif trophic_level < 4.0:
            return cfg.min_prey_count_t3
        elif trophic_level < 5.0:
            return cfg.min_prey_count_t4
        else:
            return cfg.min_prey_count_t5
    
    def _find_additional_prey(
        self,
        predator: Species,
        existing_prey: list[str],
        all_species: Sequence[Species],
        count: int,
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
        new_producers: list[str] | None = None,
        cfg: FoodWebConfig | None = None,
    ) -> list[str]:
        """寻找额外的猎物以满足多样性阈值
        
        【优先级】
        1. 新出现的生产者/初级消费者（如果栖息地重叠）
        2. 同瓦片的其他合适物种
        3. 按标准推断的候选物种
        """
        cfg = cfg or self._config
        candidates = []
        species_map = {s.lineage_code: s for s in all_species if s.status == "alive"}
        
        # 定义捕食范围
        min_prey_level = max(1.0, predator.trophic_level - 1.5)
        max_prey_level = predator.trophic_level - 0.5
        
        # 获取捕食者的栖息地块
        predator_tiles = species_tiles.get(predator.lineage_code, set()) if species_tiles else set()
        
        # 优先考虑新出现的生产者
        if new_producers:
            for code in new_producers:
                if code in existing_prey:
                    continue
                prey = species_map.get(code)
                if not prey:
                    continue
                    
                # 检查营养级是否在范围内
                if not (min_prey_level <= prey.trophic_level <= max_prey_level):
                    continue
                
                # 检查栖息地重叠
                prey_tiles = species_tiles.get(code, set()) if species_tiles else set()
                tile_overlap = len(predator_tiles & prey_tiles) / max(1, len(predator_tiles | prey_tiles)) if predator_tiles or prey_tiles else 0
                
                # 检查生物量约束
                if cfg.enable_biomass_constraint:
                    if not self._check_biomass_constraint(predator, prey, cfg):
                        continue
                
                # 计算综合分数
                score = 0.5  # 新物种基础分
                
                if tile_overlap >= cfg.new_species_habitat_overlap_threshold:
                    score += 0.3
                    
                if predator.habitat_type == prey.habitat_type:
                    score += 0.2
                    
                candidates.append((code, score))
        
        # 标准推断
        standard_candidates = self._predation.infer_prey_optimized(
            predator, all_species,
            tile_species_map=tile_species_map,
            species_tiles=species_tiles,
            max_prey_count=count + 5
        )
        
        for code in standard_candidates:
            if code in existing_prey or any(c[0] == code for c in candidates):
                continue
            prey = species_map.get(code)
            if prey and cfg.enable_biomass_constraint:
                if not self._check_biomass_constraint(predator, prey, cfg):
                    continue
            candidates.append((code, 0.3))
        
        # 按分数排序，取前count个
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [code for code, _ in candidates[:count]]
    
    def _check_biomass_constraint(
        self,
        predator: Species,
        prey: Species,
        cfg: FoodWebConfig
    ) -> bool:
        """检查猎物是否满足生物量约束
        
        高营养级捕食者不应过度依赖微小的单一生产者。
        """
        prey_pop = prey.morphology_stats.get("population", 0)
        prey_weight = prey.morphology_stats.get("body_weight_g", 0.001)
        prey_biomass = prey_pop * prey_weight
        
        # 计算该营养级需要的最小生物量
        trophic_diff = predator.trophic_level - prey.trophic_level
        required_biomass = cfg.min_prey_biomass_g * (cfg.biomass_trophic_multiplier ** trophic_diff)
        
        return prey_biomass >= required_biomass
    
    def _integrate_new_producers_to_consumers(
        self,
        new_producer_codes: list[str],
        all_species: Sequence[Species],
        species_map: dict[str, Species],
        species_repository: "SpeciesRepository",
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
        cfg: FoodWebConfig | None = None,
    ) -> list[Species]:
        """将新生产者集成到猎物不足的消费者中
        
        【策略】
        - 只对猎物数量 ≤ integrate_priority_when_prey_below 的消费者添加
        - 检查栖息地/瓦片重叠
        """
        cfg = cfg or self._config
        modified = []
        
        for consumer in all_species:
            if consumer.status != "alive" or consumer.trophic_level < 2.0:
                continue
            
            current_prey = consumer.prey_species or []
            alive_codes = {s.lineage_code for s in all_species if s.status == "alive"}
            valid_prey = [c for c in current_prey if c in alive_codes]
            
            # 只对猎物不足的消费者添加
            if len(valid_prey) > cfg.integrate_priority_when_prey_below:
                continue
            
            # 获取消费者的栖息地块
            consumer_tiles = species_tiles.get(consumer.lineage_code, set()) if species_tiles else set()
            
            added = []
            for producer_code in new_producer_codes:
                if producer_code in current_prey:
                    continue
                    
                producer = species_map.get(producer_code)
                if not producer:
                    continue
                
                # 检查营养级
                trophic_diff = consumer.trophic_level - producer.trophic_level
                if not (0.5 <= trophic_diff <= 1.5):
                    continue
                
                # 检查栖息地兼容性
                if not self._predation._habitats_compatible(consumer.habitat_type, producer.habitat_type):
                    if consumer.habitat_type != producer.habitat_type:
                        continue
                
                # 检查瓦片重叠
                if species_tiles:
                    producer_tiles = species_tiles.get(producer_code, set())
                    if consumer_tiles and producer_tiles:
                        overlap = len(consumer_tiles & producer_tiles)
                        if overlap == 0:
                            continue  # 完全不重叠，跳过
                
                # 检查生物量约束
                if cfg.enable_biomass_constraint:
                    if not self._check_biomass_constraint(consumer, producer, cfg):
                        continue
                
                added.append(producer_code)
                
                # 每个消费者最多添加2个新猎物
                if len(added) >= 2:
                    break
            
            if added:
                new_prey_list = valid_prey + added
                new_prefs = self._recalculate_preferences(consumer, new_prey_list, species_map)
                self._assign_prey(consumer, new_prey_list, new_prefs, "prey_added", old_prey=current_prey)
                modified.append(consumer)
                
                self._logger.info(
                    f"[食物网] {consumer.common_name} 集成新猎物: {added}"
                )
        
        return modified
    
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
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
    ) -> list[str]:
        """为灭绝的猎物寻找替代
        
        规则：
        - 寻找与灭绝猎物营养级相近的物种
        - 优先同栖息地类型
        - 【新增】优先同瓦片物种
        - 不重复添加已有的猎物
        """
        species_map = {s.lineage_code: s for s in all_species if s.status == "alive"}
        cfg = self._config
        
        # 使用优化的推断方法
        candidates = self._predation.infer_prey_optimized(
            predator, all_species,
            tile_species_map=tile_species_map,
            species_tiles=species_tiles,
            max_prey_count=len(extinct_prey) + 4
        )
        
        # 过滤掉已有的猎物，并检查生物量约束
        new_candidates = []
        for code in candidates:
            if code in valid_prey:
                continue
            prey = species_map.get(code)
            if prey and cfg.enable_biomass_constraint:
                if not self._check_biomass_constraint(predator, prey, cfg):
                    continue
            new_candidates.append(code)
        
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
    
    # ========== trophic_interactions 信号生成 ==========
    
    def generate_trophic_signals(
        self,
        analysis: FoodWebAnalysis,
        all_species: Sequence[Species],
    ) -> dict[str, float]:
        """根据食物网分析生成 trophic_interactions 信号
        
        这些信号将被死亡率/迁徙阶段使用，产生以下效应：
        - 饥饿物种：增加死亡率，增加迁徙概率
        - 孤立消费者：增加死亡率
        - 猎物丰富：降低死亡率
        
        Args:
            analysis: 食物网分析结果
            all_species: 所有物种
            
        Returns:
            {信号名: 强度} 字典
        """
        cfg = self._config
        signals: dict[str, float] = {}
        
        alive_species = [s for s in all_species if s.status == "alive"]
        species_map = {s.lineage_code: s for s in alive_species}
        
        # 1. 按营养级计算饥饿压力
        # 饥饿物种 = 没有猎物或猎物极少的消费者
        t2_starving = 0
        t3_starving = 0
        t4_starving = 0
        t2_total = 0
        t3_total = 0
        t4_total = 0
        
        for sp in alive_species:
            if sp.trophic_level < 2.0:
                continue
            
            prey_codes = sp.prey_species or []
            alive_prey = [c for c in prey_codes if c in species_map]
            is_starving = len(alive_prey) == 0
            
            if sp.trophic_level < 3.0:
                t2_total += 1
                if is_starving:
                    t2_starving += 1
            elif sp.trophic_level < 4.0:
                t3_total += 1
                if is_starving:
                    t3_starving += 1
            else:
                t4_total += 1
                if is_starving:
                    t4_starving += 1
        
        # 计算各营养级的饥饿比例（转化为 scarcity 信号）
        if t2_total > 0:
            signals["t2_scarcity"] = (t2_starving / t2_total) * 2.0  # 0-2 范围
        if t3_total > 0:
            signals["t3_scarcity"] = (t3_starving / t3_total) * 2.0
        if t4_total > 0:
            signals["t4_scarcity"] = (t4_starving / t4_total) * 2.0
        
        # 2. 为特定物种生成死亡率修正信号
        for code in analysis.starving_species:
            sp = species_map.get(code)
            if sp:
                # 完全饥饿的物种获得额外死亡率惩罚
                signals[f"food_web_mortality_{code}"] = cfg.starving_mortality_coefficient
        
        for code in analysis.orphaned_consumers:
            sp = species_map.get(code)
            if sp:
                # 孤立消费者获得额外死亡率惩罚
                signals[f"food_web_mortality_{code}"] = cfg.orphaned_mortality_coefficient
        
        # 3. 猎物不足但未完全饥饿的物种
        for code in analysis.prey_shortage_species:
            if code not in analysis.starving_species:
                signals[f"food_web_mortality_{code}"] = cfg.starving_mortality_coefficient * 0.5
        
        # 4. 迁徙信号（无猎物时增加迁徙倾向）
        for code in analysis.starving_species:
            signals[f"food_web_migration_{code}"] = cfg.no_prey_migration_boost
        
        # 5. 食物网健康度影响
        if analysis.health_score < 0.5:
            # 食物网不健康时，所有消费者受到轻微惩罚
            signals["food_web_global_penalty"] = (0.5 - analysis.health_score) * 0.1
        
        return signals
    
    def rebuild_food_web(
        self,
        all_species: Sequence[Species],
        species_repository: "SpeciesRepository",
        preserve_valid_links: bool = True,
    ) -> int:
        """重建食物网（存档恢复时使用）
        
        Args:
            all_species: 所有物种
            species_repository: 物种仓库
            preserve_valid_links: 是否保留现有的有效链接
            
        Returns:
            修改的物种数量
        """
        cfg = self._config
        alive_species = [s for s in all_species if s.status == "alive"]
        alive_codes = {s.lineage_code for s in alive_species}
        
        modified_count = 0
        
        for sp in alive_species:
            if sp.trophic_level < 2.0:
                continue
            
            current_prey = sp.prey_species or []
            
            if preserve_valid_links and cfg.preserve_valid_links_on_rebuild:
                # 保留有效链接
                valid_prey = [c for c in current_prey if c in alive_codes]
            else:
                # 清空重建
                valid_prey = []
            
            # 获取最低猎物数量
            min_prey_count = self._get_min_prey_count(sp.trophic_level, cfg)
            
            if len(valid_prey) < min_prey_count:
                # 需要补充猎物
                additional = self._predation.infer_prey_from_trophic(
                    sp, alive_species, 
                    max_prey_count=min_prey_count + 2
                )
                
                for code in additional:
                    if code not in valid_prey and len(valid_prey) < min_prey_count:
                        valid_prey.append(code)
                
                if valid_prey != current_prey:
                    sp.prey_species = valid_prey
                    sp.prey_preferences = self._recalculate_preferences(
                        sp, valid_prey, {s.lineage_code: s for s in alive_species}
                    )
                    species_repository.upsert(sp)
                    modified_count += 1
                    
                    self._logger.info(
                        f"[食物网重建] {sp.common_name}: {current_prey} → {valid_prey}"
                    )
        
        self._logger.info(f"[食物网重建] 完成，修改了 {modified_count} 个物种")
        return modified_count









