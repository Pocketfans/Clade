"""物种繁殖与种群增长系统。

一个回合代表50万年的演化时间，物种应该有显著的种群增长。

区域承载力
- 每个地块独立计算承载力
- 物种种群按栖息地分布到各地块
- 地块间存在生物量流动和压力传导
"""

from __future__ import annotations

import logging
import math
from typing import Sequence, TYPE_CHECKING

from ...models.species import Species
from ...models.environment import MapTile, HabitatPopulation
from ...repositories.environment_repository import environment_repository
from .population_calculator import PopulationCalculator
from ...core.config import get_settings

if TYPE_CHECKING:
    from .habitat_manager import HabitatManager

logger = logging.getLogger(__name__)

# 获取配置
_settings = get_settings()


class ReproductionService:
    """处理物种在回合间的自然繁殖和种群增长。
    
    增长模型基于 Logistic Growth 时间积分公式：
    P(t) = K / (1 + ((K - P0) / P0) * e^(-r * t))
    
    其中：
    - K: 环境承载力 (Carrying Capacity) - 现在支持动态和区域化计算
    - P0: 初始种群
    - r: 内禀增长率 (Intrinsic Growth Rate)
    - t: 经历的代数 (Generations)
    """
    
    def __init__(self, 
                 global_carrying_capacity: int = 1_000_000_000_000, 
                 turn_years: int = 500_000,
                 enable_regional_capacity: bool = True):  # P3: 默认启用区域承载力
        """初始化繁殖服务。
        
        Args:
            global_carrying_capacity: 全球总承载力（生态负荷单位kg，而非绝对个体数）
                建议值：1万亿kg = 1 Gt（地球总生物量约550 Gt，模拟单个地块约占1/500）
                注意：这是生物量单位，不是个体数量
            turn_years: 每回合代表的年数（默认50万年）
            enable_regional_capacity: 是否启用区域承载力（P3）
                - True: 使用地块级承载力（默认，更精确）✅
                - False: 使用全局承载力（兼容旧系统）
        """
        self.global_carrying_capacity = global_carrying_capacity
        self.turn_years = turn_years
        self.enable_regional_capacity = enable_regional_capacity
        self.env_modifier = 1.0  # P2: 动态承载力修正系数
    
    def update_environmental_modifier(self, temp_change: float, sea_level_change: float):
        """更新环境动态修正系数
        
        根据全局环境变化调整承载力：
        - 温度剧变：降低承载力
        - 海平面剧变：降低承载力
        - 稳定环境：承载力恢复
        
        Args:
            temp_change: 温度变化（°C）
            sea_level_change: 海平面变化（m）
        """
        modifier = 1.0
        
        # 温度变化影响（±2°C内无影响，超过后逐渐降低）
        if abs(temp_change) > 2.0:
            temp_impact = min(0.3, abs(temp_change - 2.0) / 10.0)
            modifier *= (1.0 - temp_impact)
            logger.debug(f"[动态承载力] 温度变化{temp_change:.1f}°C，降低{temp_impact:.1%}")
        
        # 海平面变化影响（±10m内无影响，超过后逐渐降低）
        if abs(sea_level_change) > 10.0:
            sea_impact = min(0.2, abs(sea_level_change - 10.0) / 50.0)
            modifier *= (1.0 - sea_impact)
            logger.debug(f"[动态承载力] 海平面变化{sea_level_change:.1f}m，降低{sea_impact:.1%}")
        
        # 缓慢恢复机制（每回合恢复5%向1.0）
        if self.env_modifier < 1.0:
            self.env_modifier = min(1.0, self.env_modifier + 0.05)
        
        # 应用新修正
        self.env_modifier = modifier
        
        if abs(modifier - 1.0) > 0.01:
            logger.info(f"[动态承载力] 环境修正系数: {modifier:.2f}")
    
    def apply_reproduction(
        self,
        species_list: Sequence[Species],
        niche_metrics: dict[str, tuple[float, float]],  # {lineage_code: (overlap, saturation)}
        survival_rates: dict[str, float],  # {lineage_code: survival_rate}
        habitat_manager: 'HabitatManager | None' = None,  # P3: 需要用于计算区域承载力
    ) -> dict[str, int]:
        """计算所有物种的繁殖增长，返回新的种群数量。
        
        P3改进：如果启用区域承载力，将按地块分别计算
        
        Args:
            species_list: 所有存活物种
            niche_metrics: 生态位重叠和资源饱和度
            survival_rates: 上一回合的存活率（1 - 死亡率）
            habitat_manager: 栖息地管理器（P3需要）
            
        Returns:
            {lineage_code: new_population}
        """
        if self.enable_regional_capacity and habitat_manager:
            # P3: 区域承载力模式
            return self._apply_reproduction_regional(
                species_list, niche_metrics, survival_rates, habitat_manager
            )
        else:
            # 传统全局承载力模式
            return self._apply_reproduction_global(
                species_list, niche_metrics, survival_rates
            )
    
    def _apply_reproduction_global(
        self,
        species_list: Sequence[Species],
        niche_metrics: dict[str, tuple[float, float]],
        survival_rates: dict[str, float],
    ) -> dict[str, int]:
        """传统的全局承载力模式（兼容旧系统）"""
        total_current = sum(int(sp.morphology_stats.get("population", 0)) for sp in species_list)
        
        # 全局承载力压力（渐进式）
        # 0-70%: 无压力
        # 70-90%: 轻微压力
        # 90-100%: 显著压力
        # >100%: 严重压力
        global_utilization = total_current / self.global_carrying_capacity
        
        if global_utilization < 0.7:
            global_pressure = 0.0
        elif global_utilization < 0.9:
            global_pressure = (global_utilization - 0.7) / 0.2 * 0.5  # 0.7-0.9 -> 0.0-0.5
        else:
            global_pressure = 0.5 + (global_utilization - 0.9) / 0.1 * 0.5  # 0.9-1.0 -> 0.5-1.0
        
        global_pressure = min(1.0, global_pressure)
        
        new_populations = {}
        
        for species in species_list:
            current_pop = int(species.morphology_stats.get("population", 0))
            
            if current_pop <= 0:
                new_populations[species.lineage_code] = 0
                continue
            
            # 获取生态位数据
            overlap, saturation = niche_metrics.get(species.lineage_code, (0.0, 0.0))
            survival_rate = survival_rates.get(species.lineage_code, 0.5)
            
            # 计算该物种的理论最大承载力 K
            # 使用 PopulationCalculator 根据体型估算
            body_length = species.morphology_stats.get("body_length_cm", 10.0)
            body_weight = species.morphology_stats.get("body_weight_g")
            _, max_pop_k = PopulationCalculator.calculate_reasonable_population(
                body_length, body_weight
            )
            
            # 受到资源和竞争影响，实际 K 值会降低
            # 资源饱和度越高，K 值越低
            # 生态位重叠越高，K 值越低（竞争排斥）
            k_modifier = 1.0
            if saturation > 0.8:
                k_modifier *= max(0.1, 1.0 - (saturation - 0.8) * 5) # 饱和度0.8-1.0时急剧下降
            
            if overlap > 0.5:
                k_modifier *= max(0.2, 1.0 - (overlap - 0.5) * 1.5)
            
            # 全局压力影响（渐进式）
            if global_pressure > 0:
                k_modifier *= (1.0 - global_pressure * 0.5)  # 最多降低50%
            
            # P2: 应用环境动态修正
            k_modifier *= self.env_modifier
            
            effective_k = int(max_pop_k * k_modifier)
            
            # 计算新种群
            new_pop = self._calculate_logistic_growth(
                species=species,
                current_pop=current_pop,
                carrying_capacity=effective_k,
                survival_rate=survival_rate,
                resource_saturation=saturation
            )
            
            # 确保不超过全球承载力的硬性限制
            # 单一物种最多占全球承载力的20%（更合理的生态上限）
            max_single_species = int(self.global_carrying_capacity * 0.2)
            if new_pop > max_single_species:
                logger.warning(f"[种群上限] {species.common_name} 超过单物种上限: {new_pop} -> {max_single_species}")
                new_pop = max_single_species
            
            # 记录日志
            if abs(new_pop - current_pop) / max(current_pop, 1) > 0.5:
                logger.info(f"[种群爆炸] {species.common_name}: {current_pop} -> {new_pop} (K={effective_k})")
            else:
                logger.debug(f"[种群波动] {species.common_name}: {current_pop} -> {new_pop}")
            
            new_populations[species.lineage_code] = new_pop
        
        return new_populations
    
    def _apply_reproduction_regional(
        self,
        species_list: Sequence[Species],
        niche_metrics: dict[str, tuple[float, float]],
        survival_rates: dict[str, float],
        habitat_manager: 'HabitatManager',
    ) -> dict[str, int]:
        """P3: 区域承载力模式 - 每个地块独立计算
        
        核心改进：
        1. 获取所有物种的栖息地分布
        2. 计算每个地块的承载力（改进：营养级级联）
        3. 按地块分别计算种群增长
        4. 汇总各地块种群得到总种群
        """
        logger.info(f"[P3区域承载力] 启用地块级承载力计算")
        
        # 1. 获取所有地块和栖息地数据
        all_tiles = environment_repository.list_tiles()
        all_habitats = environment_repository.latest_habitats()
        
        # 构建地块字典和栖息地字典
        tile_dict = {tile.id: tile for tile in all_tiles if tile.id is not None}
        
        # 按物种组织栖息地: {species_id: [HabitatPopulation, ...]}
        species_habitats: dict[int, list[HabitatPopulation]] = {}
        for habitat in all_habitats:
            if habitat.species_id not in species_habitats:
                species_habitats[habitat.species_id] = []
            species_habitats[habitat.species_id].append(habitat)
        
        # 2. 计算全局环境状态（用于动态承载力）
        global_state = {
            "temp_change": 0.0,  # TODO: 从engine传入
            "sea_level_change": 0.0,
        }
        
        # 【核心改进】3. 计算每个地块的营养级承载力级联
        tile_capacities = self._calculate_tile_trophic_capacities(
            species_list, species_habitats, tile_dict, habitat_manager, global_state
        )
        
        # 4. 为每个物种计算区域种群
        new_populations = {}
        
        for species in species_list:
            if not species.id:
                new_populations[species.lineage_code] = 0
                continue
            
            current_total_pop = int(species.morphology_stats.get("population", 0))
            if current_total_pop <= 0:
                new_populations[species.lineage_code] = 0
                continue
            
            # 获取该物种的栖息地分布
            habitats = species_habitats.get(species.id, [])
            if not habitats:
                logger.warning(f"[P3] {species.common_name} 没有栖息地记录，使用全局模式")
                # 回退到全局模式
                new_populations[species.lineage_code] = self._calculate_single_species_global(
                    species, niche_metrics, survival_rates, current_total_pop
                )
                continue
            
            # 5. 计算适宜度总和（用于分配种群到各地块）
            total_suitability = sum(h.suitability for h in habitats)
            
            # 【风险修复】适宜度过低的处理
            if total_suitability < 0.01:  # 改为阈值而非0
                logger.warning(
                    f"[风险] {species.common_name} 总适宜度过低({total_suitability:.4f})，"
                    f"可能由于多次迁徙累积衰减。回退到全局模式。"
                )
                # 回退到全局模式，避免物种意外灭绝
                new_populations[species.lineage_code] = self._calculate_single_species_global(
                    species, niche_metrics, survival_rates, current_total_pop
                )
                
                # 尝试重新计算栖息地（恢复适宜度）
                self._recalculate_habitat_if_needed(species, habitats, all_tiles)
                continue
            
            # 6. 按适宜度分配当前种群到各地块
            tile_populations: dict[int, int] = {}
            for habitat in habitats:
                tile_pop = int(current_total_pop * (habitat.suitability / total_suitability))
                tile_populations[habitat.tile_id] = tile_pop
            
            # 7. 对每个地块分别计算繁殖增长
            new_tile_populations: dict[int, int] = {}
            
            # P3优化：计算地块间的种群压力传导
            tile_pressure_modifiers = self._calculate_cross_tile_pressure(
                habitats, tile_populations, tile_dict, species
            )
            
            for habitat in habitats:
                tile_id = habitat.tile_id
                tile = tile_dict.get(tile_id)
                
                if not tile:
                    logger.warning(f"[P3] 地块{tile_id}不存在")
                    continue
                
                tile_pop = tile_populations.get(tile_id, 0)
                if tile_pop <= 0:
                    new_tile_populations[tile_id] = 0
                    continue
                
                # 【核心改进】使用营养级承载力
                tile_capacity_key = (tile_id, species.id)
                effective_tile_capacity = tile_capacities.get(tile_capacity_key, 0)
                
                if effective_tile_capacity <= 0:
                    # 没有预计算承载力时，使用回退计算
                    # 这可能发生在新物种或迁移到新地块时
                    body_length = species.morphology_stats.get("body_length_cm", 10.0)
                    body_weight = species.morphology_stats.get("body_weight_g")
                    _, fallback_k = PopulationCalculator.calculate_reasonable_population(
                        body_length, body_weight
                    )
                    # 地块级别的回退承载力（总承载力的1/总地块数）
                    num_tiles = max(len(habitats), 1)
                    effective_tile_capacity = max(1000, int(fallback_k / num_tiles / 10))
                    logger.warning(
                        f"[P3] {species.common_name} 在地块{tile_id}无预设承载力，"
                        f"使用回退值 {effective_tile_capacity:,}"
                    )
                
                # 获取生态位数据和存活率
                overlap, saturation = niche_metrics.get(species.lineage_code, (0.0, 0.0))
                survival_rate = survival_rates.get(species.lineage_code, 0.5)
                
                # 应用生态位压力修正（在营养级承载力基础上）
                k_modifier = 1.0
                if saturation > 0.8:
                    k_modifier *= max(0.1, 1.0 - (saturation - 0.8) * 5)
                if overlap > 0.5:
                    k_modifier *= max(0.2, 1.0 - (overlap - 0.5) * 1.5)
                
                # P3优化：应用跨地块压力修正
                cross_tile_modifier = tile_pressure_modifiers.get(tile_id, 1.0)
                k_modifier *= cross_tile_modifier
                
                final_capacity = int(effective_tile_capacity * k_modifier)
                
                # 计算该地块的种群增长
                new_tile_pop = self._calculate_logistic_growth(
                    species=species,
                    current_pop=tile_pop,
                    carrying_capacity=final_capacity,
                    survival_rate=survival_rate,
                    resource_saturation=saturation
                )
                
                new_tile_populations[tile_id] = new_tile_pop
            
            # 7. 汇总各地块的种群
            new_total_pop = sum(new_tile_populations.values())
            
            # 8. 全局上限检查（防止单一物种过度繁殖）
            max_single_species = int(self.global_carrying_capacity * 0.2)
            if new_total_pop > max_single_species:
                logger.warning(f"[P3种群上限] {species.common_name} 超过单物种上限: {new_total_pop:,} -> {max_single_species:,}")
                new_total_pop = max_single_species
            
            # 记录日志
            if abs(new_total_pop - current_total_pop) / max(current_total_pop, 1) > 0.5:
                logger.info(
                    f"[P3种群爆炸] {species.common_name}: {current_total_pop:,} -> {new_total_pop:,} "
                    f"(分布在{len(habitats)}个地块)"
                )
            else:
                logger.debug(f"[P3种群波动] {species.common_name}: {current_total_pop:,} -> {new_total_pop:,}")
            
            new_populations[species.lineage_code] = new_total_pop
        
        logger.info(f"[P3区域承载力] 完成，处理了{len(new_populations)}个物种")
        return new_populations
    
    def _calculate_single_species_global(
        self,
        species: Species,
        niche_metrics: dict[str, tuple[float, float]],
        survival_rates: dict[str, float],
        current_pop: int,
    ) -> int:
        """单个物种的全局模式计算（当没有栖息地数据时的回退）"""
        overlap, saturation = niche_metrics.get(species.lineage_code, (0.0, 0.0))
        survival_rate = survival_rates.get(species.lineage_code, 0.5)
        
        body_length = species.morphology_stats.get("body_length_cm", 10.0)
        body_weight = species.morphology_stats.get("body_weight_g")
        _, max_pop_k = PopulationCalculator.calculate_reasonable_population(
            body_length, body_weight
        )
        
        k_modifier = 1.0
        if saturation > 0.8:
            k_modifier *= max(0.1, 1.0 - (saturation - 0.8) * 5)
        if overlap > 0.5:
            k_modifier *= max(0.2, 1.0 - (overlap - 0.5) * 1.5)
        k_modifier *= self.env_modifier
        
        effective_k = int(max_pop_k * k_modifier)
        
        return self._calculate_logistic_growth(
            species, current_pop, effective_k, survival_rate, saturation
        )
    
    def _calculate_cross_tile_pressure(
        self,
        habitats: list[HabitatPopulation],
        tile_populations: dict[int, int],
        tile_dict: dict[int, MapTile],
        species: Species,
    ) -> dict[int, float]:
        """P3优化：计算跨地块的种群压力传导
        
        当相邻地块的种群密度差异大时，会产生扩散压力：
        - 高密度地块向低密度地块扩散
        - 降低高密度地块的承载力
        - 提高低密度地块的承载力（接收溢出）
        
        Args:
            habitats: 物种的所有栖息地
            tile_populations: 各地块的当前种群 {tile_id: population}
            tile_dict: 地块字典 {tile_id: MapTile}
            species: 物种对象
            
        Returns:
            {tile_id: pressure_modifier} - 修正系数（0.8-1.2）
        """
        pressure_modifiers: dict[int, float] = {}
        
        # 计算平均种群密度（用于判断相对压力）
        total_pop = sum(tile_populations.values())
        num_tiles = len(habitats)
        avg_density = total_pop / num_tiles if num_tiles > 0 else 0
        
        if avg_density == 0:
            return {h.tile_id: 1.0 for h in habitats}
        
        for habitat in habitats:
            tile_id = habitat.tile_id
            tile_pop = tile_populations.get(tile_id, 0)
            
            # 计算该地块相对于平均密度的偏离
            relative_density = tile_pop / avg_density if avg_density > 0 else 1.0
            
            # 高密度地块（>1.5倍平均）：压力增加，承载力降低
            if relative_density > 1.5:
                # 最多降低20%承载力
                pressure_mod = 1.0 - min(0.2, (relative_density - 1.5) * 0.1)
                pressure_modifiers[tile_id] = pressure_mod
            
            # 低密度地块（<0.5倍平均）：压力减小，承载力提高
            elif relative_density < 0.5:
                # 最多提高20%承载力
                pressure_mod = 1.0 + min(0.2, (0.5 - relative_density) * 0.2)
                pressure_modifiers[tile_id] = pressure_mod
            
            # 中等密度地块：无修正
            else:
                pressure_modifiers[tile_id] = 1.0
        
        return pressure_modifiers
    
    def _calculate_tile_trophic_capacities(
        self,
        species_list: Sequence[Species],
        species_habitats: dict[int, list[HabitatPopulation]],
        tile_dict: dict[int, MapTile],
        habitat_manager: 'HabitatManager',
        global_state: dict,
    ) -> dict[tuple[int, int], float]:
        """【核心改进】计算每个地块的营养级级联承载力
        
        改进：精确处理浮点营养级（1.0-5.5）
        
        原理：
        1. T1（生产者）承载力 = f(地块资源, 物种适应性)
        2. T2（初级消费者）承载力 = f(T1总生物量) × 生态效率(15%)
        3. T3+（高级消费者）承载力 = f(T2总生物量) × 生态效率(15%)
        4. 杂食动物（如T2.5）：从多个营养级获取能量
        
        Args:
            species_list: 所有物种
            species_habitats: 物种栖息地映射
            tile_dict: 地块字典
            habitat_manager: 栖息地管理器
            global_state: 全局环境状态
            
        Returns:
            {(tile_id, species_id): carrying_capacity_kg}
        """
        tile_capacities: dict[tuple[int, int], float] = {}
        
        # 1. 按地块组织物种
        tile_species: dict[int, list[tuple[Species, float]]] = {}  # {tile_id: [(species, suitability), ...]}
        
        for species in species_list:
            if not species.id or species.status != "alive":
                continue
            
            habitats = species_habitats.get(species.id, [])
            for habitat in habitats:
                tile_id = habitat.tile_id
                if tile_id not in tile_species:
                    tile_species[tile_id] = []
                tile_species[tile_id].append((species, habitat.suitability))
        
        # 2. 对每个地块，计算营养级级联承载力
        for tile_id, sp_list in tile_species.items():
            tile = tile_dict.get(tile_id)
            if not tile:
                continue
            
            # 【改进】按精确营养级分组，支持浮点数
            # 使用0.5的间隔分组：[1.0-1.5), [1.5-2.0), [2.0-2.5), ...
            by_trophic_range: dict[float, list[tuple[Species, float]]] = {}
            
            for species, suitability in sp_list:
                t_level = species.trophic_level
                # 计算所属范围：1.3 → 1.0, 1.7 → 1.5, 2.2 → 2.0
                t_range = self._get_trophic_range(t_level)
                
                if t_range not in by_trophic_range:
                    by_trophic_range[t_range] = []
                by_trophic_range[t_range].append((species, suitability))
            
            # 3. 计算T1范围（1.0-1.5）的基础承载力
            # T1依赖地块资源（光、水、营养）
            t1_base_capacity = tile.resources * 100_000  # 资源1 = 10万kg
            
            # 应用P2动态修正（环境变化）
            if global_state:
                temp_change = global_state.get("temp_change", 0.0)
                sea_level_change = global_state.get("sea_level_change", 0.0)
                
                if abs(temp_change) > 2.0:
                    t1_base_capacity *= (1.0 - min(0.3, abs(temp_change) / 10.0))
                if abs(sea_level_change) > 10.0:
                    t1_base_capacity *= (1.0 - min(0.2, abs(sea_level_change) / 50.0))
            
            # 4. 分配T1承载力（生产者共享资源）
            t1_species = by_trophic_range.get(1.0, [])
            if t1_species:
                t1_total_suitability = sum(suitability for _, suitability in t1_species)
                for species, suitability in t1_species:
                    if t1_total_suitability > 0:
                        species_share = suitability / t1_total_suitability
                        species_capacity = t1_base_capacity * species_share
                    else:
                        species_capacity = 0
                    
                    # 应用物种特定修正
                    species_capacity *= self._get_species_suitability_for_tile(species, tile)
                    species_capacity *= self._get_body_size_modifier(species, is_producer=True)
                    
                    tile_capacities[(tile_id, species.id)] = max(1000, species_capacity)
            
            # 5. 计算各营养级的生物量池（用于上层承载力计算）
            # 建立连续的营养级生物量分布
            trophic_biomass_pools = self._calculate_trophic_biomass_pools(
                by_trophic_range, species_habitats, tile_id
            )
            
            # 6. 计算T1.5-T5.5的承载力（基于下层生物量）
            for t_range in sorted([t for t in by_trophic_range.keys() if t >= 1.5]):
                tx_species = by_trophic_range[t_range]
                
                # 计算该营养级可以从哪些下层获取能量
                available_biomass = self._calculate_available_prey_biomass(
                    t_range, trophic_biomass_pools, by_trophic_range
                )
                
                if available_biomass <= 0:
                    # 没有猎物时提供保底承载力（杂食/机会主义者）
                    # 这允许消费者在生态系统早期存活，但增长受限
                    fallback_capacity = t1_base_capacity * 0.05  # 生产者承载力的5%
                    for species, suitability in tx_species:
                        # 按适宜度分配保底承载力
                        tx_total_suitability = sum(s for _, s in tx_species) or 1.0
                        species_capacity = fallback_capacity * (suitability / tx_total_suitability)
                        species_capacity *= self._get_species_suitability_for_tile(species, tile)
                        species_capacity *= self._get_body_size_modifier(species, is_producer=False)
                        tile_capacities[(tile_id, species.id)] = max(1000, species_capacity)
                        logger.debug(
                            f"[保底承载力] {species.common_name} T{t_range} 无猎物，"
                            f"分配保底承载力 {species_capacity:.0f}"
                        )
                    continue
                
                # Tx物种之间共享可用生物量
                tx_total_suitability = sum(suitability for _, suitability in tx_species)
                for species, suitability in tx_species:
                    if tx_total_suitability > 0:
                        species_share = suitability / tx_total_suitability
                        species_capacity = available_biomass * species_share
                    else:
                        species_capacity = 0
                    
                    # 应用物种特定修正
                    species_capacity *= self._get_species_suitability_for_tile(species, tile)
                    species_capacity *= self._get_body_size_modifier(species, is_producer=False)
                    
                    tile_capacities[(tile_id, species.id)] = max(1000, species_capacity)
        
        # 记录日志
        logger.info(f"[营养级承载力] 计算完成，{len(tile_capacities)}个地块×物种组合")
        return tile_capacities
    
    def _get_species_suitability_for_tile(self, species: Species, tile: MapTile) -> float:
        """计算物种对地块的基础适宜度（用于承载力修正）"""
        # 温度适应性
        temp_pref = species.abstract_traits.get("耐热性", 5)
        cold_pref = species.abstract_traits.get("耐寒性", 5)
        
        if tile.temperature > 20:
            temp_score = temp_pref / 10.0
        elif tile.temperature < 5:
            temp_score = cold_pref / 10.0
        else:
            temp_score = 0.8
        
        # 湿度适应性
        drought_pref = species.abstract_traits.get("耐旱性", 5)
        humidity_score = 1.0 - abs(tile.humidity - (1.0 - drought_pref / 10.0))
        
        # 综合评分
        return max(0.1, (temp_score * 0.5 + humidity_score * 0.5))
    
    def _get_trophic_range(self, trophic_level: float) -> float:
        """将精确营养级映射到0.5间隔的范围
        
        示例：
        - 1.0-1.49 → 1.0 (纯生产者)
        - 1.5-1.99 → 1.5 (杂食植物)
        - 2.0-2.49 → 2.0 (初级消费者)
        - 2.5-2.99 → 2.5 (初级杂食者)
        - 3.0-3.49 → 3.0 (次级消费者)
        - 3.5+ → 3.5, 4.0, 4.5, 5.0, 5.5 (高级捕食者)
        
        Args:
            trophic_level: 精确营养级 (1.0-5.5)
            
        Returns:
            范围基准值 (1.0, 1.5, 2.0, ...)
        """
        import math
        # 向下取整到最近的0.5
        return math.floor(trophic_level * 2) / 2.0
    
    def _calculate_trophic_biomass_pools(
        self,
        by_trophic_range: dict[float, list[tuple[Species, float]]],
        species_habitats: dict[int, list[HabitatPopulation]],
        tile_id: int
    ) -> dict[float, float]:
        """计算各营养级范围的总生物量
        
        Args:
            by_trophic_range: 按营养级分组的物种
            species_habitats: 物种栖息地映射
            tile_id: 当前地块ID
            
        Returns:
            {trophic_range: total_biomass_kg}
        """
        biomass_pools: dict[float, float] = {}
        
        for t_range, species_list in by_trophic_range.items():
            total_biomass = 0.0
            
            for species, suitability in species_list:
                # 获取物种的总种群
                pop = species.morphology_stats.get("population", 0)
                weight = species.morphology_stats.get("body_weight_g", 1.0)
                
                # 按该地块的适宜度分配生物量
                tile_biomass = pop * weight * suitability
                total_biomass += tile_biomass
            
            biomass_pools[t_range] = total_biomass
        
        return biomass_pools
    
    def _calculate_available_prey_biomass(
        self,
        predator_trophic: float,
        biomass_pools: dict[float, float],
        by_trophic_range: dict[float, list[tuple[Species, float]]]
    ) -> float:
        """计算捕食者可获得的猎物生物量
        
        关键改进：杂食动物可以从多个营养级获取能量
        
        示例：
        - T2.0 (初级消费者): 只吃 T1.0-T1.5
        - T2.5 (初级杂食者): 吃 T1.0-T2.0 (植物+小型动物)
        - T3.0 (次级消费者): 吃 T1.5-T2.5
        - T3.5 (次级杂食者): 吃 T2.0-T3.0
        
        规则：营养级X可以捕食营养级 [X-1.5, X-0.5] 范围内的物种
        
        Args:
            predator_trophic: 捕食者营养级
            biomass_pools: 各营养级的生物量池
            by_trophic_range: 物种分组（用于检查是否存在）
            
        Returns:
            可用猎物生物量 (kg)
        """
        available_biomass = 0.0
        
        # 定义捕食范围：可以吃比自己低0.5-1.5级的物种
        min_prey_level = max(1.0, predator_trophic - 1.5)
        max_prey_level = predator_trophic - 0.5
        
        # 汇总所有可捕食范围内的生物量
        for prey_level, prey_biomass in biomass_pools.items():
            if min_prey_level <= prey_level <= max_prey_level:
                # 检查该营养级是否真的有物种
                if prey_level in by_trophic_range and by_trophic_range[prey_level]:
                    available_biomass += prey_biomass
        
        # 应用生态效率：15%可用率
        # （可食用部分、捕获成功率、消化效率等综合因素）
        return available_biomass * 0.15
    
    def _get_body_size_modifier(self, species: Species, is_producer: bool) -> float:
        """根据体型调整承载力修正系数
        
        Args:
            species: 物种
            is_producer: 是否为生产者
            
        Returns:
            体型修正系数 (0.3-2.0)
        """
        body_size = species.morphology_stats.get("body_length_cm", 1.0)
        
        if is_producer:
            # 生产者：小型微生物效率高，大型植物需要更多空间
            if body_size < 0.1:  # 微生物
                return 2.0
            elif body_size < 1:  # 小型藻类
                return 1.5
            elif body_size > 100:  # 大型植物
                return 0.5
            else:
                return 1.0
        else:
            # 消费者：大型捕食者需要更大领地
            if body_size < 1:  # 小型无脊椎动物
                return 1.8
            elif body_size < 10:  # 中小型动物
                return 1.5
            elif body_size < 100:  # 中大型动物
                return 1.0
            elif body_size < 500:  # 大型动物
                return 0.5
            else:  # 超大型动物
                return 0.3
    
    def _recalculate_habitat_if_needed(
        self,
        species: Species,
        current_habitats: list[HabitatPopulation],
        all_tiles: list[MapTile]
    ) -> None:
        """【风险修复】当适宜度过低时，尝试重新计算栖息地
        
        场景：多次迁徙后，适宜度可能累积衰减到接近0
        解决：基于物种当前生态特征，重新评估栖息地适宜度
        
        Args:
            species: 需要修复的物种
            current_habitats: 当前的栖息地记录
            all_tiles: 所有可用地块
        """
        if not current_habitats:
            return
        
        logger.info(f"[适宜度修复] 尝试为 {species.common_name} 重新计算栖息地适宜度")
        
        # 获取当前栖息地的地块ID
        current_tile_ids = {h.tile_id for h in current_habitats}
        
        # 重新计算适宜度
        recalculated_habitats = []
        for tile in all_tiles:
            if tile.id in current_tile_ids:
                # 重新计算适宜度
                new_suitability = self._get_species_suitability_for_tile(species, tile)
                
                if new_suitability > 0.1:  # 只保留有效适宜度
                    recalculated_habitats.append((tile.id, new_suitability))
        
        if not recalculated_habitats:
            logger.warning(f"[适宜度修复] {species.common_name} 重新计算后仍无合适栖息地")
            return
        
        # 归一化适宜度
        total_suit = sum(s for _, s in recalculated_habitats)
        if total_suit == 0:
            return
        
        # 更新栖息地记录（下回合生效）
        from ...models.environment import HabitatPopulation
        
        new_habitats = []
        turn_index = current_habitats[0].turn_index + 1  # 下一回合
        
        for tile_id, raw_suitability in recalculated_habitats:
            normalized = raw_suitability / total_suit
            new_habitats.append(
                HabitatPopulation(
                    tile_id=tile_id,
                    species_id=species.id,
                    population=0,
                    suitability=normalized,
                    turn_index=turn_index,
                )
            )
        
        if new_habitats:
            environment_repository.write_habitats(new_habitats)
            logger.info(f"[适宜度修复] {species.common_name} 已重新计算 {len(new_habitats)} 个栖息地")
    
    def _calculate_logistic_growth(
        self,
        species: Species,
        current_pop: int,
        carrying_capacity: int,
        survival_rate: float,
        resource_saturation: float
    ) -> int:
        """使用逻辑斯谛方程计算时间积分后的种群。
        
        公式: P(t) = K / (1 + ((K - P0) / P0) * e^(-r * t))
        
        其中 t 为代数 (Generations)。
        
        **重要改进**：按每个世代应用死亡率，而不是一次性增长。
        """
        # 1. 计算代数 (t)
        generation_time_days = species.morphology_stats.get("generation_time_days", 365)
        total_days = self.turn_years * 365.25
        generations = total_days / max(1.0, generation_time_days)
        
        # 2. 计算内禀增长率 (r) - 每代的净增长率
        # r = ln(R0) / T
        # 简化模型：r 基于繁殖速度和生存率
        # 繁殖速度 1-10 -> 基础 r 0.01 - 0.2 (每代增长1%-20%)
        repro_speed = species.abstract_traits.get("繁殖速度", 5)
        # 【修改】大幅提高基础增长率，确保物种能够恢复
        # 原来：repro_speed * 0.002 -> 0.002-0.02 (太低，无法抵消死亡率)
        # 现在：repro_speed * 0.008 -> 0.008-0.08 (合理，50万年内可以恢复)
        base_r = repro_speed * 0.008
        
        # ========== 【世代感知模型】应用世代数缩放 ==========
        if _settings.enable_generational_growth:
            # 引入世代数对数缩放，避免微生物种群爆炸
            # 原理：快速繁殖生物虽然每代增长快，但更快达到承载力平衡
            generation_scale = math.log10(max(10, generations)) / _settings.generation_scale_factor
            base_r = base_r * generation_scale
            
            logger.debug(
                f"[世代增长率] {species.common_name}: {generations:.0f}代, "
                f"基础r={repro_speed * 0.008:.4f} → 缩放r={base_r:.4f}"
            )
        
        # 生存率修正：
        # 生存率 < 0.5 时 r 变为负值
        # 生存率 0.5 = 0
        # 生存率 > 0.5 = 正增长
        # ⚠️ 修改：降低生存率对增长率的负面影响
        survival_modifier = max(-0.3, (survival_rate - 0.5) * 1.5)  # 限制负向影响，从2.0降至1.5
        
        # 资源匮乏修正：
        # 资源饱和度 > 1.0 时，r 变为负值（强行抑制）
        resource_impact = 0.0
        if resource_saturation > 1.2:  # 从1.0提高到1.2，增加容忍度
            resource_impact = -0.03 * (resource_saturation - 1.2) # 从-0.05降至-0.03，降低惩罚
        
        effective_r = base_r + (survival_modifier * 0.015) + resource_impact  # 从0.02降至0.015
        
        # 确保 r 不会过小导致无法恢复 (限制在 -0.05 到 0.1 之间)
        effective_r = max(-0.05, min(0.1, effective_r))  # 提高上限从0.05到0.1
        
        # 3. 【关键修改】模拟逐代演化，每代应用死亡率
        # 而不是一次性计算所有代的结果
        current = float(current_pop)
        
        # 为了性能，如果世代数太多，采样计算
        if generations > 1000:
            # 每100代计算一次
            step = int(generations / 1000)
            effective_gens = int(generations / step)
        else:
            step = 1
            effective_gens = int(generations)
        
        # 【关键修复】设置绝对种群上限，防止溢出
        # 地球总生物量约550 Gt，单一物种不应超过10%
        MAX_POPULATION = 10_000_000_000_000  # 10万亿作为绝对上限
        
        for gen in range(effective_gens):
            if current <= 0:
                break
            
            # 【关键修复】检查是否已达到上限
            if current >= MAX_POPULATION:
                current = MAX_POPULATION
                break
            
            # 逻辑斯谛增长（单步）
            if current < carrying_capacity:
                growth = effective_r * current * (1 - current / carrying_capacity) * step
                
                # 【关键修复】限制单步增长率，防止种群爆炸
                # 每步最多增长20%
                max_growth = current * 0.2
                growth = min(growth, max_growth)
                
                current += growth
            else:
                # 超过承载力，施加负增长
                # 【关键修复】限制单步衰减比例，防止种群瞬间归零
                overshoot = (current - carrying_capacity) / carrying_capacity
                
                # 计算衰减比例，但限制在每步最多衰减10%
                # 这模拟了生态系统中种群调整的时间惯性
                raw_decline_rate = effective_r * overshoot * step * 2
                max_decline_rate = 0.1  # 每步最多衰减10%
                actual_decline_rate = min(raw_decline_rate, max_decline_rate)
                
                decline = current * actual_decline_rate
                current -= decline
            
            # ⚠️ 移除了每代死亡率应用
            # 死亡率已在 MortalityEngine 中应用，这里只计算繁殖增长
            # 如果在这里再次应用，会导致死亡率的指数累积（0.7^1000 ≈ 0）
            
            # 确保不为负且不溢出
            current = max(0, min(current, MAX_POPULATION))
        
        # 【关键修复】处理无穷大和NaN
        if math.isinf(current) or math.isnan(current):
            logger.warning(f"[种群计算] 检测到异常值，重置为承载力: {carrying_capacity}")
            current = min(carrying_capacity, MAX_POPULATION)
        
        return int(min(current, MAX_POPULATION))
        
        # 旧的一次性计算方式已移除
