"""生态拟真阶段 (Ecological Realism Stage)

将生态拟真服务集成到模拟流水线中，在死亡率计算之前应用高级生态学机制。

【核心功能】
1. 应用 Allee 效应修正繁殖效率
2. 计算密度依赖疾病压力
3. 应用环境波动修正承载力
4. 更新互利共生网络
5. 追踪环境变化用于适应滞后计算

【执行时机】
在死亡率计算阶段（MortalityStage）之前执行，
为后续阶段提供生态学修正因子。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .stages import BaseStage, StageDependency, StageOrder

if TYPE_CHECKING:
    from .context import SimulationContext
    from .engine import SimulationEngine
    from ..services.ecology.ecological_realism import (
        EcologicalRealismService,
        AlleeEffectResult,
        DiseaseResult,
        MutualismLink,
    )

logger = logging.getLogger(__name__)


@dataclass
class EcologicalRealismResults:
    """生态拟真计算结果"""
    # Allee 效应
    allee_results: dict[str, 'AlleeEffectResult'] = field(default_factory=dict)
    
    # 密度依赖疾病
    disease_results: dict[str, 'DiseaseResult'] = field(default_factory=dict)
    
    # 环境波动修正
    env_modifiers: dict[str, float] = field(default_factory=dict)
    
    # 垂直生态位竞争修正
    vertical_competition_modifiers: dict[tuple[str, str], float] = field(default_factory=dict)
    
    # 空间捕食效率
    spatial_predation_efficiency: dict[tuple[str, str], float] = field(default_factory=dict)
    
    # 同化效率
    assimilation_efficiencies: dict[str, float] = field(default_factory=dict)
    
    # 适应滞后惩罚
    adaptation_penalties: dict[str, float] = field(default_factory=dict)
    
    # 互利共生
    mutualism_links: list['MutualismLink'] = field(default_factory=list)
    mutualism_benefits: dict[str, float] = field(default_factory=dict)


class EcologicalRealismStage(BaseStage):
    """生态拟真阶段
    
    在每回合的死亡率计算之前执行，计算各种生态学修正因子。
    """
    
    def __init__(self):
        # 在 tiering_and_niche (StageOrder.TIERING_AND_NICHE=180) 之后
        # 在 preliminary_mortality (StageOrder.PRELIMINARY_MORTALITY=200) 之前
        super().__init__(order=190, name="生态拟真")
        self._logger = logging.getLogger(__name__)
    
    def get_dependency(self) -> StageDependency:
        """声明阶段依赖"""
        return StageDependency(
            requires_stages={"获取物种列表", "物种分层与生态位"},
            requires_fields={"species_batch", "all_tiles", "all_habitats"},
            writes_fields={"plugin_data"},
            optional_stages={"资源计算"},
        )
    
    async def execute(self, ctx: 'SimulationContext', engine: 'SimulationEngine') -> None:
        """执行生态拟真计算"""
        # 获取生态拟真服务
        eco_service = getattr(engine, 'ecological_realism_service', None)
        if eco_service is None:
            self._logger.warning("[生态拟真] 服务未注入，跳过生态拟真计算")
            return
        
        results = EcologicalRealismResults()
        
        # 获取所有存活物种
        alive_species = ctx.species_batch
        if not alive_species:
            return
        
        self._logger.info(f"[生态拟真] 开始计算，{len(alive_species)} 个物种")
        
        # 【关键优化】批量预热物种向量，避免后续大量单独的embedding API调用
        # - force_refresh=True: 确保使用最新的物种描述（进化/杂交后描述可能变化）
        # - 底层EmbeddingService有基于文本内容的磁盘缓存，未变化的描述不会触发API调用
        # - 这将把可能的数十万次单独API调用减少为一次批量调用
        if hasattr(eco_service, 'warmup_species_vectors'):
            warmup_count = eco_service.warmup_species_vectors(alive_species, force_refresh=True)
            if warmup_count > 0:
                self._logger.info(f"[生态拟真] 批量预热 {warmup_count} 个物种向量完成")
        
        # 1. 追踪环境变化（用于适应滞后）
        self._track_environment(ctx, eco_service)
        
        # 2. 更新互利共生网络
        results.mutualism_links = eco_service.discover_mutualism_links(
            alive_species, ctx.turn_index
        )
        
        # 3. 计算各物种的生态学修正
        for species in alive_species:
            code = species.lineage_code
            
            # Allee 效应
            carrying_capacity = self._get_carrying_capacity(species, ctx)
            results.allee_results[code] = eco_service.calculate_allee_effect(
                species, carrying_capacity
            )
            
            # 密度依赖疾病
            density_ratio = self._get_density_ratio(species, carrying_capacity)
            results.disease_results[code] = eco_service.calculate_disease_pressure(
                species, density_ratio
            )
            
            # 环境波动
            latitude = self._get_species_latitude(species, ctx)
            results.env_modifiers[code] = eco_service.calculate_env_fluctuation_modifier(
                species, ctx.turn_index, latitude
            )
            
            # 同化效率
            results.assimilation_efficiencies[code] = eco_service.calculate_assimilation_efficiency(
                species
            )
            
            # 适应滞后惩罚
            results.adaptation_penalties[code] = eco_service.calculate_adaptation_lag_penalty(
                species
            )
            
            # 互利共生收益
            results.mutualism_benefits[code] = eco_service.get_mutualism_benefit(
                species, alive_species
            )
        
        # 4. 计算物种对之间的交互修正
        species_tiles = self._get_species_tiles(ctx)
        
        for i, sp_a in enumerate(alive_species):
            for sp_b in alive_species[i+1:]:
                # 垂直生态位竞争
                overlap = eco_service.calculate_vertical_niche_overlap(sp_a, sp_b)
                results.vertical_competition_modifiers[(sp_a.lineage_code, sp_b.lineage_code)] = overlap
                
                # 空间捕食效率（如果存在捕食关系）
                if sp_b.lineage_code in (sp_a.prey_species or []):
                    tiles_a = species_tiles.get(sp_a.lineage_code, set())
                    tiles_b = species_tiles.get(sp_b.lineage_code, set())
                    efficiency = eco_service.calculate_spatial_predation_efficiency(
                        sp_a, sp_b, tiles_a, tiles_b
                    )
                    results.spatial_predation_efficiency[(sp_a.lineage_code, sp_b.lineage_code)] = efficiency
                
                if sp_a.lineage_code in (sp_b.prey_species or []):
                    tiles_a = species_tiles.get(sp_a.lineage_code, set())
                    tiles_b = species_tiles.get(sp_b.lineage_code, set())
                    efficiency = eco_service.calculate_spatial_predation_efficiency(
                        sp_b, sp_a, tiles_b, tiles_a
                    )
                    results.spatial_predation_efficiency[(sp_b.lineage_code, sp_a.lineage_code)] = efficiency
        
        # 5. 将结果存入 Context 的 plugin_data
        ctx.plugin_data["ecological_realism"] = {
            "allee_results": {k: v.__dict__ for k, v in results.allee_results.items()},
            "disease_results": {k: v.__dict__ for k, v in results.disease_results.items()},
            "env_modifiers": results.env_modifiers,
            "vertical_competition_modifiers": {
                f"{k[0]}_{k[1]}": v for k, v in results.vertical_competition_modifiers.items()
            },
            "spatial_predation_efficiency": {
                f"{k[0]}_{k[1]}": v for k, v in results.spatial_predation_efficiency.items()
            },
            "assimilation_efficiencies": results.assimilation_efficiencies,
            "adaptation_penalties": results.adaptation_penalties,
            "mutualism_links": [
                {
                    "species_a": link.species_a,
                    "species_b": link.species_b,
                    "relationship_type": link.relationship_type,
                    "strength": link.strength,
                }
                for link in results.mutualism_links
            ],
            "mutualism_benefits": results.mutualism_benefits,
        }
        
        # 记录统计
        allee_affected = sum(1 for r in results.allee_results.values() if r.is_below_mvp)
        disease_affected = sum(1 for r in results.disease_results.values() if r.disease_pressure > 0.1)
        mutualism_count = len(results.mutualism_links)
        
        self._logger.info(
            f"[生态拟真] 完成: "
            f"Allee效应影响 {allee_affected} 种, "
            f"疾病压力影响 {disease_affected} 种, "
            f"共生关系 {mutualism_count} 对"
        )
        
        ctx.emit_event(
            "ecological_realism",
            f"生态拟真分析完成：Allee效应 {allee_affected}，疾病压力 {disease_affected}，共生关系 {mutualism_count}",
            "生态系统"
        )
    
    def _track_environment(
        self,
        ctx: 'SimulationContext',
        eco_service: 'EcologicalRealismService',
    ) -> None:
        """追踪环境变化"""
        # 计算全局平均温度和湿度
        if not ctx.all_tiles:
            return
        
        total_temp = 0.0
        total_humidity = 0.0
        total_resources = 0.0
        count = 0
        
        for tile in ctx.all_tiles:
            total_temp += getattr(tile, 'temperature', 20.0)
            total_humidity += getattr(tile, 'humidity', 0.5)
            total_resources += getattr(tile, 'resources', 100)
            count += 1
        
        if count > 0:
            eco_service.track_environment_change(
                ctx.turn_index,
                total_temp / count,
                total_humidity / count,
                total_resources / count / 1000.0,  # 归一化
            )
    
    def _get_carrying_capacity(
        self,
        species,
        ctx: 'SimulationContext',
    ) -> int:
        """获取物种的承载力"""
        # 尝试从资源快照获取
        if ctx.resource_snapshot:
            # 使用资源快照的平均承载力
            if ctx.resource_snapshot.t1_capacity_vector is not None:
                avg_capacity = float(ctx.resource_snapshot.t1_capacity_vector.mean())
                # 根据营养级调整
                trophic = species.trophic_level
                if trophic >= 2:
                    # 消费者的承载力按生态效率递减
                    efficiency = 0.15 ** (trophic - 1)
                    avg_capacity *= efficiency
                return max(1000, int(avg_capacity))
        
        # 回退：使用 PopulationCalculator
        from ..services.species.population_calculator import PopulationCalculator
        body_length = species.morphology_stats.get("body_length_cm", 10.0)
        body_weight = species.morphology_stats.get("body_weight_g")
        _, max_pop = PopulationCalculator.calculate_reasonable_population(
            body_length, body_weight
        )
        return max(1000, max_pop)
    
    def _get_density_ratio(
        self,
        species,
        carrying_capacity: int,
    ) -> float:
        """计算物种的密度比例"""
        population = species.morphology_stats.get("population", 0)
        if carrying_capacity <= 0:
            return 0.0
        return population / carrying_capacity
    
    def _get_species_latitude(
        self,
        species,
        ctx: 'SimulationContext',
    ) -> float:
        """获取物种的平均纬度 (0=赤道, 1=极地)"""
        # 从栖息地获取物种分布
        if not ctx.all_habitats:
            return 0.5  # 默认中纬度
        
        species_habitats = [
            h for h in ctx.all_habitats
            if h.species_id == species.id
        ]
        
        if not species_habitats:
            return 0.5
        
        # 计算加权平均纬度
        from ..simulation.constants import LOGIC_RES_Y
        tile_dict = {t.id: t for t in ctx.all_tiles} if ctx.all_tiles else {}
        
        total_y = 0.0
        total_weight = 0.0
        
        for habitat in species_habitats:
            tile = tile_dict.get(habitat.tile_id)
            if tile:
                y = getattr(tile, 'y', LOGIC_RES_Y // 2)
                weight = habitat.suitability
                total_y += y * weight
                total_weight += weight
        
        if total_weight <= 0:
            return 0.5
        
        avg_y = total_y / total_weight
        # 转换为纬度 (0=赤道, 1=极地)
        half_height = LOGIC_RES_Y / 2.0
        latitude = abs(avg_y - half_height) / half_height
        return min(1.0, max(0.0, latitude))
    
    def _get_species_tiles(
        self,
        ctx: 'SimulationContext',
    ) -> dict[str, set[int]]:
        """获取物种到地块的映射"""
        species_tiles: dict[str, set[int]] = {}
        
        if not ctx.all_habitats:
            return species_tiles
        
        species_id_to_code = {
            sp.id: sp.lineage_code
            for sp in ctx.all_species
            if sp.id
        }
        
        for habitat in ctx.all_habitats:
            code = species_id_to_code.get(habitat.species_id)
            if code:
                if code not in species_tiles:
                    species_tiles[code] = set()
                species_tiles[code].add(habitat.tile_id)
        
        return species_tiles
    


def apply_ecological_realism_to_mortality(
    ctx: 'SimulationContext',
    base_mortality: float,
    species_code: str,
) -> float:
    """应用生态拟真修正到死亡率
    
    这是一个辅助函数，供死亡率计算阶段使用。
    
    Args:
        ctx: 模拟上下文
        base_mortality: 基础死亡率
        species_code: 物种代码
        
    Returns:
        修正后的死亡率
    """
    eco_data = ctx.plugin_data.get("ecological_realism", {})
    if not eco_data:
        return base_mortality
    
    modified_mortality = base_mortality
    
    # 1. 应用疾病压力
    disease_results = eco_data.get("disease_results", {})
    disease = disease_results.get(species_code, {})
    disease_pressure = disease.get("mortality_modifier", 0.0)
    modified_mortality += disease_pressure
    
    # 2. 应用适应滞后惩罚
    adaptation_penalties = eco_data.get("adaptation_penalties", {})
    adaptation_penalty = adaptation_penalties.get(species_code, 0.0)
    modified_mortality += adaptation_penalty
    
    # 3. 应用互利共生收益（负值减少死亡率）
    mutualism_benefits = eco_data.get("mutualism_benefits", {})
    mutualism = mutualism_benefits.get(species_code, 0.0)
    modified_mortality -= mutualism  # 正收益减少死亡率，负收益（惩罚）增加死亡率
    
    return max(0.01, min(0.95, modified_mortality))


def apply_ecological_realism_to_reproduction(
    ctx: 'SimulationContext',
    base_growth_rate: float,
    species_code: str,
) -> float:
    """应用生态拟真修正到繁殖率
    
    这是一个辅助函数，供繁殖计算阶段使用。
    
    Args:
        ctx: 模拟上下文
        base_growth_rate: 基础繁殖率
        species_code: 物种代码
        
    Returns:
        修正后的繁殖率
    """
    eco_data = ctx.plugin_data.get("ecological_realism", {})
    if not eco_data:
        return base_growth_rate
    
    modified_rate = base_growth_rate
    
    # 1. 应用 Allee 效应
    allee_results = eco_data.get("allee_results", {})
    allee = allee_results.get(species_code, {})
    reproduction_modifier = allee.get("reproduction_modifier", 1.0)
    modified_rate *= reproduction_modifier
    
    # 2. 应用环境波动修正
    env_modifiers = eco_data.get("env_modifiers", {})
    env_mod = env_modifiers.get(species_code, 1.0)
    modified_rate *= env_mod
    
    # 3. 应用互利共生收益（正收益提高繁殖率）
    mutualism_benefits = eco_data.get("mutualism_benefits", {})
    mutualism = mutualism_benefits.get(species_code, 0.0)
    if mutualism > 0:
        modified_rate *= (1.0 + mutualism)
    
    return max(0.1, modified_rate)


def get_vertical_niche_competition(
    ctx: 'SimulationContext',
    species_a_code: str,
    species_b_code: str,
) -> float:
    """获取两物种的垂直生态位竞争系数
    
    Args:
        ctx: 模拟上下文
        species_a_code: 物种A代码
        species_b_code: 物种B代码
        
    Returns:
        竞争系数 (0-1)
    """
    eco_data = ctx.plugin_data.get("ecological_realism", {})
    if not eco_data:
        return 1.0  # 默认完全竞争
    
    vertical_mods = eco_data.get("vertical_competition_modifiers", {})
    
    key = f"{species_a_code}_{species_b_code}"
    if key in vertical_mods:
        return vertical_mods[key]
    
    key_rev = f"{species_b_code}_{species_a_code}"
    if key_rev in vertical_mods:
        return vertical_mods[key_rev]
    
    return 1.0


def get_spatial_predation_efficiency(
    ctx: 'SimulationContext',
    predator_code: str,
    prey_code: str,
) -> float:
    """获取空间捕食效率
    
    Args:
        ctx: 模拟上下文
        predator_code: 捕食者代码
        prey_code: 猎物代码
        
    Returns:
        捕食效率 (0-1)
    """
    eco_data = ctx.plugin_data.get("ecological_realism", {})
    if not eco_data:
        return 1.0  # 默认完全效率
    
    spatial_mods = eco_data.get("spatial_predation_efficiency", {})
    key = f"{predator_code}_{prey_code}"
    return spatial_mods.get(key, 1.0)


def get_assimilation_efficiency(
    ctx: 'SimulationContext',
    species_code: str,
) -> float:
    """获取物种的同化效率
    
    Args:
        ctx: 模拟上下文
        species_code: 物种代码
        
    Returns:
        同化效率 (0.05-0.35)
    """
    eco_data = ctx.plugin_data.get("ecological_realism", {})
    if not eco_data:
        return 0.10  # 默认 10%
    
    efficiencies = eco_data.get("assimilation_efficiencies", {})
    return efficiencies.get(species_code, 0.10)

