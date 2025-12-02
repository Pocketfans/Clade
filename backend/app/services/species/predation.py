"""捕食网络(Predation Network)管理服务。

负责管理物种间的捕食关系，计算食物链效应，并提供真实的捕食网数据。

核心功能：
1. 捕食关系管理：添加、移除、查询捕食关系
2. 食物链效应：计算物种灭绝时的连锁影响
3. 捕食压力：根据真实捕食关系计算压力（而非仅营养级）
4. 捕食网数据：为前端提供真实的食物网络图数据

设计原则：
- 捕食关系存储在Species.prey_species字段中
- 支持多层级捕食关系（T2吃T1，T3吃T2等）
- 杂食动物可以有多个猎物来源
- 物种灭绝时自动检查依赖链

优化设计（解决物种数量爆炸问题）：
- 使用embedding相似度预筛选候选猎物，而非传所有物种给LLM
- 基于地块重叠过滤，只考虑空间上能接触的物种
- 营养级约束，只在合理范围内搜索
- 矩阵化批量计算捕食压力
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ..system.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class PredationLink:
    """捕食关系链接"""
    predator_code: str  # 捕食者代码
    prey_code: str  # 猎物代码
    preference: float  # 偏好比例 (0-1)
    is_critical: bool = False  # 是否为关键食物来源 (>50%依赖)


@dataclass
class FoodWebNode:
    """食物网节点"""
    lineage_code: str
    common_name: str
    trophic_level: float
    population: int
    diet_type: str
    prey_codes: list[str] = field(default_factory=list)
    predator_codes: list[str] = field(default_factory=list)
    is_keystone: bool = False  # 是否为关键物种（很多捕食者依赖）


@dataclass
class ExtinctionImpact:
    """灭绝影响分析"""
    extinct_species: str
    directly_affected: list[str]  # 直接受影响的捕食者
    indirectly_affected: list[str]  # 间接受影响（二级以上）
    food_chain_collapse_risk: float  # 食物链崩溃风险 (0-1)
    affected_biomass_percentage: float  # 受影响生物量百分比


class PredationService:
    """捕食网络管理服务
    
    管理物种间的捕食关系，计算食物链效应，提供真实捕食网数据。
    
    【优化设计】
    - 使用embedding相似度预筛选候选猎物
    - 基于地块重叠过滤
    - 矩阵化批量计算
    """
    
    def __init__(self, embedding_service: "EmbeddingService | None" = None):
        self._logger = logging.getLogger(__name__)
        self._embedding_service = embedding_service
        
        # 缓存：捕食关系矩阵
        self._predation_matrix: np.ndarray | None = None
        self._species_index: dict[str, int] = {}
        self._last_species_count: int = 0
    
    # ========== 捕食关系查询 ==========
    
    def get_prey_species(self, species: Species, all_species: Sequence[Species]) -> list[Species]:
        """获取该物种的所有猎物
        
        Args:
            species: 捕食者物种
            all_species: 所有物种列表
            
        Returns:
            猎物物种列表
        """
        prey_codes = species.prey_species or []
        species_map = {s.lineage_code: s for s in all_species}
        
        return [
            species_map[code] for code in prey_codes
            if code in species_map and species_map[code].status == "alive"
        ]
    
    def get_predators(self, species: Species, all_species: Sequence[Species]) -> list[Species]:
        """获取捕食该物种的所有捕食者
        
        Args:
            species: 猎物物种
            all_species: 所有物种列表
            
        Returns:
            捕食者物种列表
        """
        target_code = species.lineage_code
        predators = []
        
        for sp in all_species:
            if sp.status != "alive":
                continue
            if target_code in (sp.prey_species or []):
                predators.append(sp)
        
        return predators
    
    def get_food_dependency(self, species: Species, all_species: Sequence[Species]) -> float:
        """计算物种的食物依赖满足度
        
        如果猎物全部灭绝 → 0.0
        如果猎物全部存活 → 1.0
        部分存活 → 根据偏好比例加权
        
        Args:
            species: 目标物种
            all_species: 所有物种列表
            
        Returns:
            食物依赖满足度 (0-1)
        """
        prey_codes = species.prey_species or []
        if not prey_codes:
            # 无指定猎物（生产者或未配置）
            if species.trophic_level < 2.0:
                return 1.0  # 生产者不需要猎物
            else:
                return 0.8  # 消费者但未指定猎物，假设通用食性
        
        preferences = species.prey_preferences or {}
        species_map = {s.lineage_code: s for s in all_species}
        
        # 计算加权满足度
        total_weight = 0.0
        satisfied_weight = 0.0
        
        for prey_code in prey_codes:
            preference = preferences.get(prey_code, 1.0 / len(prey_codes))
            total_weight += preference
            
            prey = species_map.get(prey_code)
            if prey and prey.status == "alive":
                # 根据猎物种群计算部分满足度
                prey_pop = prey.morphology_stats.get("population", 0)
                if prey_pop > 100:
                    satisfied_weight += preference
                elif prey_pop > 10:
                    satisfied_weight += preference * 0.5
                elif prey_pop > 0:
                    satisfied_weight += preference * 0.2
        
        if total_weight <= 0:
            return 0.8
        
        return satisfied_weight / total_weight
    
    # ========== 捕食关系推断 ==========
    
    def infer_prey_from_trophic(
        self,
        species: Species,
        all_species: Sequence[Species],
        max_prey_count: int = 5
    ) -> list[str]:
        """基于营养级推断可能的猎物（简单版本）
        
        规则：
        - 营养级X可以捕食营养级 [X-1.5, X-0.5] 范围内的物种
        - 同一栖息地类型优先
        - 考虑体型匹配
        
        Args:
            species: 捕食者物种
            all_species: 所有物种列表
            max_prey_count: 最大猎物数量
            
        Returns:
            推断的猎物代码列表
        """
        if species.trophic_level < 2.0:
            return []  # 生产者不需要猎物
        
        # 定义捕食范围
        min_prey_level = max(1.0, species.trophic_level - 1.5)
        max_prey_level = species.trophic_level - 0.5
        
        candidates = []
        
        for prey in all_species:
            if prey.lineage_code == species.lineage_code:
                continue
            if prey.status != "alive":
                continue
            
            # 检查营养级范围
            if not (min_prey_level <= prey.trophic_level <= max_prey_level):
                continue
            
            # 计算匹配分数
            score = 1.0
            
            # 同栖息地加分
            if prey.habitat_type == species.habitat_type:
                score += 0.5
            
            # 体型匹配（捕食者通常比猎物大，但不能太大）
            predator_size = species.morphology_stats.get("body_length_cm", 1.0)
            prey_size = prey.morphology_stats.get("body_length_cm", 1.0)
            if prey_size > 0:
                size_ratio = predator_size / prey_size
                if 1.5 <= size_ratio <= 10:
                    score += 0.3
                elif 10 < size_ratio <= 100:
                    score += 0.1
            
            # 种群越大越可能被捕食
            prey_pop = prey.morphology_stats.get("population", 0)
            if prey_pop > 1000:
                score += 0.2
            
            candidates.append((prey.lineage_code, score))
        
        # 按分数排序，取前N个
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [code for code, _ in candidates[:max_prey_count]]
    
    def infer_prey_optimized(
        self,
        species: Species,
        all_species: Sequence[Species],
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
        embedding_matrix: np.ndarray | None = None,
        species_to_idx: dict[str, int] | None = None,
        max_prey_count: int = 5,
        hungry_tiles: set[int] | None = None,
        isolated_tiles: set[int] | None = None,
    ) -> list[str]:
        """基于多维度筛选推断可能的猎物（优化版本）
        
        【核心优化】
        1. 营养级约束：只考虑合理范围内的物种
        2. 地块重叠：只考虑空间上能接触的物种
        3. Embedding相似度：优先选择生态位相近的物种
        4. 栖息地类型匹配
        5. 【新增】区域权重：饥饿/孤立区域的同瓦片猎物权重更高
        6. 【新增】生物量考虑
        
        这个方法不需要把所有物种传给LLM，而是通过规则+embedding预筛选。
        
        Args:
            species: 捕食者物种
            all_species: 所有物种列表
            tile_species_map: {tile_id: set(species_codes)} 地块→物种映射
            species_tiles: {species_code: set(tile_ids)} 物种→地块映射
            embedding_matrix: 物种描述的embedding相似度矩阵
            species_to_idx: 物种代码→矩阵索引映射
            max_prey_count: 最大猎物数量
            hungry_tiles: 饥饿区域（高死亡率地块）
            isolated_tiles: 孤立区域（低连通性地块）
            
        Returns:
            推断的猎物代码列表
        """
        if species.trophic_level < 2.0:
            return []  # 生产者不需要猎物
        
        # 加载配置
        try:
            from ...core.config import get_settings, PROJECT_ROOT
            from ...repositories.environment_repository import environment_repository
            _settings = get_settings()
            ui_config = environment_repository.load_ui_config(PROJECT_ROOT / "data/settings.json")
            fw_cfg = ui_config.food_web
        except Exception:
            from ...models.config import FoodWebConfig
            fw_cfg = FoodWebConfig()
        
        # 定义捕食范围
        min_prey_level = max(1.0, species.trophic_level - 1.5)
        max_prey_level = species.trophic_level - 0.5
        
        # 获取捕食者的栖息地块
        predator_tiles = species_tiles.get(species.lineage_code, set()) if species_tiles else set()
        
        # 检查捕食者是否在饥饿/孤立区域
        in_hungry_region = bool(hungry_tiles and predator_tiles and (predator_tiles & hungry_tiles))
        in_isolated_region = bool(isolated_tiles and predator_tiles and (predator_tiles & isolated_tiles))
        
        candidates = []
        
        for prey in all_species:
            if prey.lineage_code == species.lineage_code:
                continue
            if prey.status != "alive":
                continue
            
            # 1. 营养级约束（硬性）
            if not (min_prey_level <= prey.trophic_level <= max_prey_level):
                continue
            
            # 计算综合匹配分数
            score = 0.0
            
            # 2. 地块重叠检查（权重 30%，可动态调整）
            tile_weight = 0.3
            if fw_cfg.enable_tile_weight:
                if in_hungry_region:
                    tile_weight += fw_cfg.hungry_region_weight_boost
                if in_isolated_region:
                    tile_weight += fw_cfg.isolated_region_weight_boost
            
            if species_tiles and tile_species_map:
                prey_tiles = species_tiles.get(prey.lineage_code, set())
                if predator_tiles and prey_tiles:
                    # 计算地块重叠比例
                    overlap = len(predator_tiles & prey_tiles)
                    total = len(predator_tiles | prey_tiles)
                    tile_overlap_ratio = overlap / total if total > 0 else 0
                    score += tile_overlap_ratio * tile_weight
                    
                    # 【新增】同瓦片猎物额外加成
                    if overlap > 0 and fw_cfg.enable_tile_weight:
                        score += fw_cfg.same_tile_prey_weight_boost
                    
                    # 如果完全不重叠，降低优先级但不排除
                    if overlap == 0:
                        score -= 0.1
            
            # 3. 栖息地类型匹配（权重 20%）
            if prey.habitat_type == species.habitat_type:
                score += 0.2
            elif self._habitats_compatible(species.habitat_type, prey.habitat_type):
                score += 0.1
            
            # 4. Embedding相似度（权重 25%）
            if embedding_matrix is not None and species_to_idx:
                pred_idx = species_to_idx.get(species.lineage_code)
                prey_idx = species_to_idx.get(prey.lineage_code)
                if pred_idx is not None and prey_idx is not None:
                    similarity = embedding_matrix[pred_idx, prey_idx]
                    score += similarity * 0.25
            
            # 5. 体型匹配（权重 15%）
            predator_size = species.morphology_stats.get("body_length_cm", 1.0)
            prey_size = prey.morphology_stats.get("body_length_cm", 1.0)
            if prey_size > 0:
                size_ratio = predator_size / prey_size
                if 1.5 <= size_ratio <= 10:
                    score += 0.15
                elif 0.5 <= size_ratio < 1.5 or 10 < size_ratio <= 100:
                    score += 0.05
            
            # 6. 种群丰度（权重 10%）
            prey_pop = prey.morphology_stats.get("population", 0)
            if prey_pop > 1000:
                score += 0.1
            elif prey_pop > 100:
                score += 0.05
            
            # 7. 【新增】生物量考虑
            if fw_cfg.enable_biomass_constraint:
                prey_weight = prey.morphology_stats.get("body_weight_g", 0.001)
                prey_biomass = prey_pop * prey_weight
                
                # 计算需要的最小生物量
                trophic_diff = species.trophic_level - prey.trophic_level
                required_biomass = fw_cfg.min_prey_biomass_g * (fw_cfg.biomass_trophic_multiplier ** trophic_diff)
                
                if prey_biomass < required_biomass:
                    score -= 0.2  # 生物量不足惩罚
                elif prey_biomass > required_biomass * 10:
                    score += 0.1  # 生物量充足奖励
            
            candidates.append((prey.lineage_code, score))
        
        # 按分数排序，取前N个
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [code for code, _ in candidates[:max_prey_count]]
    
    def _habitats_compatible(self, habitat_a: str, habitat_b: str) -> bool:
        """检查两个栖息地类型是否兼容（可能有物种交互）"""
        # 兼容性定义
        compatible_pairs = {
            ("marine", "coastal"),
            ("coastal", "marine"),
            ("freshwater", "amphibious"),
            ("amphibious", "freshwater"),
            ("terrestrial", "amphibious"),
            ("amphibious", "terrestrial"),
            ("terrestrial", "aerial"),
            ("aerial", "terrestrial"),
            ("coastal", "amphibious"),
            ("amphibious", "coastal"),
        }
        return (habitat_a, habitat_b) in compatible_pairs
    
    def auto_assign_prey(
        self,
        species: Species,
        all_species: Sequence[Species],
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
    ) -> tuple[list[str], dict[str, float]]:
        """自动为物种分配猎物和偏好
        
        Args:
            species: 目标物种
            all_species: 所有物种
            tile_species_map: {tile_id: set(species_codes)} 地块→物种映射
            species_tiles: {species_code: set(tile_ids)} 物种→地块映射
            
        Returns:
            (prey_codes, prey_preferences)
        """
        # 优先使用优化版本（带区域权重）
        if tile_species_map or species_tiles:
            prey_codes = self.infer_prey_optimized(
                species, all_species,
                tile_species_map=tile_species_map,
                species_tiles=species_tiles,
                max_prey_count=5
            )
        else:
            prey_codes = self.infer_prey_from_trophic(species, all_species)
        
        if not prey_codes:
            return [], {}
        
        # 根据营养级差分配偏好（带区域权重）
        preferences = {}
        species_map = {s.lineage_code: s for s in all_species}
        predator_tiles = species_tiles.get(species.lineage_code, set()) if species_tiles else set()
        
        total_weight = 0.0
        for code in prey_codes:
            prey = species_map.get(code)
            if not prey:
                continue
            
            # 营养级差越接近1.0，偏好越高
            level_diff = species.trophic_level - prey.trophic_level
            weight = 1.0 / (abs(level_diff - 1.0) + 0.5)
            
            # 【新增】区域权重：同瓦片猎物权重更高
            if species_tiles and predator_tiles:
                prey_tiles = species_tiles.get(code, set())
                if predator_tiles & prey_tiles:
                    weight *= 1.4  # 同瓦片加成 40%
            
            preferences[code] = weight
            total_weight += weight
        
        # 归一化
        if total_weight > 0:
            for code in preferences:
                preferences[code] /= total_weight
        
        return prey_codes, preferences
    
    # ========== 食物链效应计算 ==========
    
    def analyze_extinction_impact(
        self,
        extinct_species: Species,
        all_species: Sequence[Species]
    ) -> ExtinctionImpact:
        """分析物种灭绝的影响
        
        Args:
            extinct_species: 即将灭绝的物种
            all_species: 所有物种列表
            
        Returns:
            灭绝影响分析结果
        """
        extinct_code = extinct_species.lineage_code
        
        # 找出直接依赖该物种的捕食者
        directly_affected = []
        for sp in all_species:
            if sp.status != "alive":
                continue
            if extinct_code in (sp.prey_species or []):
                directly_affected.append(sp.lineage_code)
        
        # 分析二级影响（捕食者的捕食者）
        indirectly_affected = set()
        for affected_code in directly_affected:
            affected_sp = next((s for s in all_species if s.lineage_code == affected_code), None)
            if affected_sp:
                for sp in all_species:
                    if sp.status != "alive":
                        continue
                    if affected_code in (sp.prey_species or []):
                        if sp.lineage_code not in directly_affected:
                            indirectly_affected.add(sp.lineage_code)
        
        # 计算食物链崩溃风险
        # 风险因素：
        # 1. 直接依赖者数量
        # 2. 是否为关键物种（唯一食物来源）
        # 3. 受影响的生物量
        
        collapse_risk = 0.0
        critical_count = 0
        
        for affected_code in directly_affected:
            affected_sp = next((s for s in all_species if s.lineage_code == affected_code), None)
            if affected_sp:
                # 检查是否为唯一食物来源
                remaining_prey = [
                    code for code in (affected_sp.prey_species or [])
                    if code != extinct_code
                ]
                if not remaining_prey:
                    critical_count += 1
                    collapse_risk += 0.3
        
        collapse_risk = min(1.0, collapse_risk + len(directly_affected) * 0.1)
        
        # 计算受影响生物量百分比
        total_biomass = 0.0
        affected_biomass = 0.0
        
        for sp in all_species:
            if sp.status != "alive":
                continue
            pop = sp.morphology_stats.get("population", 0)
            weight = sp.morphology_stats.get("body_weight_g", 1.0)
            biomass = pop * weight
            total_biomass += biomass
            
            if sp.lineage_code in directly_affected or sp.lineage_code in indirectly_affected:
                affected_biomass += biomass
        
        affected_percentage = affected_biomass / total_biomass if total_biomass > 0 else 0.0
        
        return ExtinctionImpact(
            extinct_species=extinct_code,
            directly_affected=directly_affected,
            indirectly_affected=list(indirectly_affected),
            food_chain_collapse_risk=collapse_risk,
            affected_biomass_percentage=affected_percentage
        )
    
    def calculate_starvation_pressure(
        self,
        species: Species,
        all_species: Sequence[Species]
    ) -> float:
        """计算因食物短缺导致的死亡压力
        
        基于真实捕食关系计算，而非仅营养级。
        
        Args:
            species: 目标物种
            all_species: 所有物种
            
        Returns:
            饥饿压力 (0-1)，越高越危险
        """
        # 生产者不受饥饿压力
        if species.trophic_level < 2.0:
            return 0.0
        
        food_satisfaction = self.get_food_dependency(species, all_species)
        
        # 食物满足度转换为饥饿压力
        # 满足度1.0 → 压力0.0
        # 满足度0.5 → 压力0.25
        # 满足度0.0 → 压力1.0
        starvation_pressure = (1.0 - food_satisfaction) ** 2
        
        return starvation_pressure
    
    def calculate_predation_pressure(
        self,
        species: Species,
        all_species: Sequence[Species]
    ) -> float:
        """计算物种受到的捕食压力
        
        基于真实捕食者计算。
        
        Args:
            species: 目标物种（猎物）
            all_species: 所有物种
            
        Returns:
            捕食压力 (0-1)
        """
        predators = self.get_predators(species, all_species)
        
        if not predators:
            return 0.0
        
        prey_pop = species.morphology_stats.get("population", 1)
        prey_biomass = prey_pop * species.morphology_stats.get("body_weight_g", 1.0)
        
        # 计算捕食者总需求
        total_predator_demand = 0.0
        
        for pred in predators:
            pred_pop = pred.morphology_stats.get("population", 0)
            pred_weight = pred.morphology_stats.get("body_weight_g", 1.0)
            
            # 捕食者需求 = 种群 × 体重 × 代谢率系数
            demand = pred_pop * pred_weight * 0.1  # 每天需要体重10%的食物
            
            # 如果该物种是捕食者的唯一或主要猎物，压力更大
            preferences = pred.prey_preferences or {}
            preference = preferences.get(species.lineage_code, 1.0 / max(1, len(pred.prey_species or [])))
            
            total_predator_demand += demand * preference
        
        # 压力 = 捕食需求 / 猎物生物量
        if prey_biomass <= 0:
            return 1.0
        
        pressure_ratio = total_predator_demand / prey_biomass
        
        # 使用sigmoid函数平滑压力曲线
        # pressure_ratio = 1.0 → pressure ≈ 0.5
        # pressure_ratio = 2.0 → pressure ≈ 0.73
        # pressure_ratio = 5.0 → pressure ≈ 0.95
        pressure = 2.0 / (1.0 + 2.718 ** (-pressure_ratio)) - 1.0
        
        return max(0.0, min(1.0, pressure))
    
    # ========== 捕食网数据导出 ==========
    
    def build_food_web(self, all_species: Sequence[Species]) -> dict:
        """构建完整的食物网数据
        
        用于前端可视化。
        
        Args:
            all_species: 所有物种列表
            
        Returns:
            食物网数据：
            {
                "nodes": [...],
                "links": [...],
                "keystone_species": [...],
                "trophic_levels": {...}
            }
        """
        alive_species = [s for s in all_species if s.status == "alive"]
        species_map = {s.lineage_code: s for s in alive_species}
        
        nodes = []
        links = []
        predator_counts = defaultdict(int)  # 被多少物种捕食
        
        # 构建节点
        for sp in alive_species:
            # 统计该物种被多少捕食者依赖
            for other in alive_species:
                if sp.lineage_code in (other.prey_species or []):
                    predator_counts[sp.lineage_code] += 1
            
            node = {
                "id": sp.lineage_code,
                "name": sp.common_name,
                "trophic_level": sp.trophic_level,
                "population": sp.morphology_stats.get("population", 0),
                "diet_type": sp.diet_type,
                "habitat_type": sp.habitat_type,
                "prey_count": len(sp.prey_species or []),
                "predator_count": 0,  # 稍后填充
            }
            nodes.append(node)
        
        # 更新被捕食数量
        for node in nodes:
            node["predator_count"] = predator_counts[node["id"]]
        
        # 构建链接（捕食关系）
        for sp in alive_species:
            for prey_code in (sp.prey_species or []):
                if prey_code in species_map:
                    prey = species_map[prey_code]
                    preference = (sp.prey_preferences or {}).get(prey_code, 0.5)
                    
                    links.append({
                        "source": prey_code,  # 能量流向：猎物 → 捕食者
                        "target": sp.lineage_code,
                        "value": preference,
                        "predator_name": sp.common_name,
                        "prey_name": prey.common_name,
                    })
        
        # 识别关键物种（被3个以上物种依赖）
        keystone_species = [
            code for code, count in predator_counts.items()
            if count >= 3
        ]
        
        # 营养级统计
        trophic_levels = defaultdict(list)
        for sp in alive_species:
            level = int(sp.trophic_level)
            trophic_levels[level].append(sp.lineage_code)
        
        return {
            "nodes": nodes,
            "links": links,
            "keystone_species": keystone_species,
            "trophic_levels": dict(trophic_levels),
            "total_species": len(alive_species),
            "total_links": len(links),
        }
    
    def get_species_food_chain(
        self,
        species: Species,
        all_species: Sequence[Species],
        max_depth: int = 3
    ) -> dict:
        """获取单个物种的食物链
        
        Args:
            species: 目标物种
            all_species: 所有物种
            max_depth: 最大追溯深度
            
        Returns:
            该物种的食物链数据（上下游）
        """
        species_map = {s.lineage_code: s for s in all_species if s.status == "alive"}
        
        # 向下追溯（猎物）
        prey_chain = []
        self._trace_prey(species, species_map, prey_chain, 0, max_depth)
        
        # 向上追溯（捕食者）
        predator_chain = []
        self._trace_predators(species, species_map, predator_chain, 0, max_depth)
        
        return {
            "species": {
                "code": species.lineage_code,
                "name": species.common_name,
                "trophic_level": species.trophic_level,
            },
            "prey_chain": prey_chain,
            "predator_chain": predator_chain,
            "food_dependency": self.get_food_dependency(species, all_species),
            "predation_pressure": self.calculate_predation_pressure(species, all_species),
        }
    
    def _trace_prey(
        self,
        species: Species,
        species_map: dict[str, Species],
        result: list,
        depth: int,
        max_depth: int
    ):
        """递归追溯猎物"""
        if depth >= max_depth:
            return
        
        for prey_code in (species.prey_species or []):
            prey = species_map.get(prey_code)
            if prey:
                prey_info = {
                    "code": prey_code,
                    "name": prey.common_name,
                    "trophic_level": prey.trophic_level,
                    "depth": depth + 1,
                    "prey": []
                }
                self._trace_prey(prey, species_map, prey_info["prey"], depth + 1, max_depth)
                result.append(prey_info)
    
    def _trace_predators(
        self,
        species: Species,
        species_map: dict[str, Species],
        result: list,
        depth: int,
        max_depth: int
    ):
        """递归追溯捕食者"""
        if depth >= max_depth:
            return
        
        target_code = species.lineage_code
        for pred in species_map.values():
            if target_code in (pred.prey_species or []):
                pred_info = {
                    "code": pred.lineage_code,
                    "name": pred.common_name,
                    "trophic_level": pred.trophic_level,
                    "depth": depth + 1,
                    "predators": []
                }
                self._trace_predators(pred, species_map, pred_info["predators"], depth + 1, max_depth)
                result.append(pred_info)
    
    # ========== 矩阵化计算 ==========
    
    def build_predation_matrix(
        self,
        all_species: Sequence[Species]
    ) -> tuple[np.ndarray, dict[str, int]]:
        """构建捕食关系矩阵
        
        返回 N×N 的稀疏矩阵，matrix[i,j] > 0 表示物种i捕食物种j。
        值为捕食偏好比例 (0-1)。
        
        Args:
            all_species: 所有物种列表
            
        Returns:
            (predation_matrix, species_to_idx)
        """
        alive_species = [s for s in all_species if s.status == "alive"]
        n = len(alive_species)
        
        # 构建索引映射
        species_to_idx = {sp.lineage_code: i for i, sp in enumerate(alive_species)}
        
        # 初始化矩阵
        matrix = np.zeros((n, n), dtype=np.float32)
        
        # 填充捕食关系
        for sp in alive_species:
            predator_idx = species_to_idx[sp.lineage_code]
            for prey_code in (sp.prey_species or []):
                prey_idx = species_to_idx.get(prey_code)
                if prey_idx is not None:
                    preference = (sp.prey_preferences or {}).get(prey_code, 0.5)
                    matrix[predator_idx, prey_idx] = preference
        
        # 缓存
        self._predation_matrix = matrix
        self._species_index = species_to_idx
        self._last_species_count = n
        
        return matrix, species_to_idx
    
    def compute_predation_pressure_matrix(
        self,
        all_species: Sequence[Species],
        population_vector: np.ndarray | None = None
    ) -> np.ndarray:
        """批量计算所有物种的捕食压力
        
        使用矩阵运算一次性计算所有物种的：
        - 饥饿压力（作为捕食者，猎物不足）
        - 被捕食压力（作为猎物，被捕食过度）
        
        Args:
            all_species: 所有物种列表
            population_vector: 可选的种群数量向量（与species_to_idx对应）
            
        Returns:
            压力向量 (n,)，每个物种的综合捕食压力
        """
        alive_species = [s for s in all_species if s.status == "alive"]
        n = len(alive_species)
        
        if n == 0:
            return np.array([])
        
        # 确保矩阵是最新的
        if self._predation_matrix is None or self._last_species_count != n:
            self.build_predation_matrix(all_species)
        
        matrix = self._predation_matrix
        species_to_idx = self._species_index
        
        # 构建种群和体重向量
        if population_vector is None:
            population_vector = np.array([
                sp.morphology_stats.get("population", 0) 
                for sp in alive_species
            ], dtype=np.float64)
        
        weight_vector = np.array([
            sp.morphology_stats.get("body_weight_g", 1.0) 
            for sp in alive_species
        ], dtype=np.float64)
        
        # 生物量向量
        biomass_vector = population_vector * weight_vector
        
        # === 1. 饥饿压力（捕食者角度）===
        # 对于每个捕食者，检查其猎物的可用生物量
        # predator_demand[i] = 捕食者i的食物需求
        predator_demand = biomass_vector * 0.1  # 每天需要体重10%的食物
        
        # available_prey[i] = 捕食者i可获得的猎物生物量
        # = sum(matrix[i, j] * prey_biomass[j])
        available_prey = matrix @ biomass_vector
        
        # 饥饿压力 = 需求超过供给的比例
        with np.errstate(divide='ignore', invalid='ignore'):
            starvation_ratio = np.where(
                available_prey > 0,
                np.maximum(0, (predator_demand - available_prey) / predator_demand),
                0.0
            )
        starvation_ratio = np.nan_to_num(starvation_ratio, 0.0)
        
        # 营养级<2的物种（生产者）不受饥饿压力
        trophic_levels = np.array([sp.trophic_level for sp in alive_species])
        starvation_ratio = np.where(trophic_levels < 2.0, 0.0, starvation_ratio)
        
        starvation_pressure = starvation_ratio ** 1.5 * 0.5  # 指数放大严重短缺
        
        # === 2. 被捕食压力（猎物角度）===
        # predation_demand[j] = 所有捕食者对猎物j的总需求
        # = sum(matrix[:, j] * predator_biomass[:] * 0.1)
        predation_demand = (matrix.T @ (biomass_vector * 0.1))
        
        # 被捕食压力 = 需求/供给 的sigmoid
        with np.errstate(divide='ignore', invalid='ignore'):
            pressure_ratio = np.where(
                biomass_vector > 0,
                predation_demand / biomass_vector,
                0.0
            )
        pressure_ratio = np.nan_to_num(pressure_ratio, 0.0)
        
        # Sigmoid转换
        predation_pressure = 2.0 / (1.0 + np.exp(-pressure_ratio)) - 1.0
        predation_pressure = np.clip(predation_pressure, 0.0, 1.0) * 0.3
        
        # === 3. 综合压力 ===
        total_pressure = starvation_pressure + predation_pressure
        
        return np.clip(total_pressure, 0.0, 1.0)
    
    # ========== LLM上下文生成 ==========
    
    def generate_prey_candidates_context(
        self,
        species: Species,
        all_species: Sequence[Species],
        tile_species_map: dict[int, set[str]] | None = None,
        species_tiles: dict[str, set[int]] | None = None,
        max_candidates: int = 10
    ) -> str:
        """为LLM生成简洁的候选猎物列表
        
        【核心优化】
        不传所有物种给LLM，而是预筛选最相关的候选猎物。
        
        返回格式示例：
        "可选猎物（按相关性排序）：
        - A1 原初蓝藻 (T1.0, 海洋, 种群:50000)
        - A2 绿藻团 (T1.0, 海洋, 种群:30000)
        - B1 滤食虫 (T2.0, 海洋, 种群:5000)"
        
        Args:
            species: 捕食者物种
            all_species: 所有物种列表
            tile_species_map: 地块→物种映射
            species_tiles: 物种→地块映射
            max_candidates: 最大候选数量
            
        Returns:
            格式化的候选猎物字符串
        """
        if species.trophic_level < 2.0:
            return "自养生物（无需猎物）"
        
        # 使用优化的候选筛选
        candidates = self.infer_prey_optimized(
            species, all_species,
            tile_species_map=tile_species_map,
            species_tiles=species_tiles,
            max_prey_count=max_candidates
        )
        
        if not candidates:
            return "暂无合适的候选猎物"
        
        # 构建简洁的描述
        species_map = {s.lineage_code: s for s in all_species}
        lines = ["可选猎物（按相关性排序）："]
        
        for code in candidates:
            prey = species_map.get(code)
            if prey:
                pop = prey.morphology_stats.get("population", 0)
                lines.append(
                    f"- {code} {prey.common_name} "
                    f"(T{prey.trophic_level:.1f}, {prey.habitat_type}, 种群:{pop:,})"
                )
        
        return "\n".join(lines)
    
    def generate_existing_species_context(
        self,
        all_species: Sequence[Species],
        target_trophic_range: tuple[float, float] | None = None,
        target_habitat: str | None = None,
        max_species: int = 20
    ) -> str:
        """为LLM生成简洁的现有物种列表
        
        【核心优化】
        不传所有物种，而是根据条件筛选最相关的物种。
        
        Args:
            all_species: 所有物种列表
            target_trophic_range: 目标营养级范围（用于筛选）
            target_habitat: 目标栖息地类型（用于筛选）
            max_species: 最大返回数量
            
        Returns:
            格式化的物种列表字符串
        """
        alive_species = [s for s in all_species if s.status == "alive"]
        
        # 筛选
        candidates = []
        for sp in alive_species:
            score = 0.0
            
            # 营养级匹配
            if target_trophic_range:
                if target_trophic_range[0] <= sp.trophic_level <= target_trophic_range[1]:
                    score += 1.0
                elif abs(sp.trophic_level - target_trophic_range[0]) < 1.0:
                    score += 0.5
            else:
                score += 0.5  # 无条件时均匀分数
            
            # 栖息地匹配
            if target_habitat:
                if sp.habitat_type == target_habitat:
                    score += 0.5
                elif self._habitats_compatible(sp.habitat_type, target_habitat):
                    score += 0.2
            
            # 种群大的物种更重要
            pop = sp.morphology_stats.get("population", 0)
            if pop > 1000:
                score += 0.3
            
            candidates.append((sp, score))
        
        # 排序并截取
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [sp for sp, _ in candidates[:max_species]]
        
        if not selected:
            return "暂无相关物种"
        
        # 构建简洁描述
        lines = [f"现有物种（共{len(alive_species)}种，显示前{len(selected)}种相关物种）："]
        
        # 按营养级分组
        by_trophic = defaultdict(list)
        for sp in selected:
            level = int(sp.trophic_level)
            by_trophic[level].append(sp)
        
        for level in sorted(by_trophic.keys()):
            species_in_level = by_trophic[level]
            level_str = ["T1生产者", "T2初级消费者", "T3次级消费者", "T4三级消费者", "T5顶级捕食者"]
            level_name = level_str[level - 1] if 1 <= level <= 5 else f"T{level}"
            
            species_desc = ", ".join([
                f"{sp.lineage_code}({sp.common_name})"
                for sp in species_in_level[:5]  # 每级最多5个
            ])
            if len(species_in_level) > 5:
                species_desc += f" 等{len(species_in_level)}种"
            
            lines.append(f"【{level_name}】{species_desc}")
        
        return "\n".join(lines)

