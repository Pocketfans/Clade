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
from ...simulation.constants import get_time_config

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
    
    # JavaScript安全整数上限，作为技术上限而非生态上限
    MAX_SAFE_POPULATION = 9_007_199_254_740_991
    
    def __init__(self, 
                 global_carrying_capacity: int = MAX_SAFE_POPULATION, 
                 turn_years: int = 500_000,
                 enable_regional_capacity: bool = True):  # P3: 默认启用区域承载力
        """初始化繁殖服务。
        
        Args:
            global_carrying_capacity: 全球总承载力（仅作为技术安全上限）
                实际种群由生态因素软性限制：竞争、捕食、资源、环境等
                默认值：JavaScript安全整数上限 ≈ 9千万亿
            turn_years: 每回合代表的年数（默认50万年）
            enable_regional_capacity: 是否启用区域承载力（P3）
                - True: 使用地块级承载力（默认，更精确）✅
                - False: 使用全局承载力（兼容旧系统）
        """
        self.global_carrying_capacity = global_carrying_capacity
        self.turn_years = turn_years
        self.enable_regional_capacity = enable_regional_capacity
        self.env_modifier = 1.0  # P2: 动态承载力修正系数
        self.resource_boost = 1.0  # 【新增v8】资源繁荣时的繁殖率加成
    
    def update_resource_boost(self, pressure_modifiers: dict[str, float]) -> None:
        """【新增v8】根据正面压力更新繁殖率加成
        
        资源繁荣等正面条件会提高繁殖效率：
        - resource_boost: 资源丰富 -> 最多+20%繁殖
        - productivity: 高生产力 -> 最多+15%繁殖
        - competition 负值: 竞争减弱 -> 最多+10%繁殖
        
        Args:
            pressure_modifiers: 压力修饰符字典
        """
        resource_boost_val = pressure_modifiers.get('resource_boost', 0.0)
        productivity_val = pressure_modifiers.get('productivity', 0.0)
        competition_val = pressure_modifiers.get('competition', 0.0)
        
        # 计算繁殖加成（最大+35%）
        bonus = 1.0
        bonus += min(0.20, resource_boost_val * 0.20)     # 资源丰富最多+20%
        bonus += min(0.15, productivity_val * 0.15)       # 高生产力最多+15%
        if competition_val < 0:  # 竞争减弱（负值）
            bonus += min(0.10, abs(competition_val) * 0.30)  # 竞争减弱最多+10%
        
        self.resource_boost = min(1.35, bonus)  # 上限1.35倍
        
        if self.resource_boost > 1.01:
            logger.info(f"[繁殖加成] 资源繁荣加成: {self.resource_boost:.0%} "
                       f"(资源={resource_boost_val:.1f}, 生产力={productivity_val:.1f}, 竞争={competition_val:.1f})")
    
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
        turn_index: int = 0,  # 【新增】当前回合索引，用于新物种繁殖率加成
    ) -> dict[str, int]:
        """计算所有物种的繁殖增长，返回新的种群数量。
        
        P3改进：如果启用区域承载力，将按地块分别计算
        
        【v4新增】新物种繁殖率加成：
        - 新分化物种在前几回合获得繁殖率加成
        - 这体现了新物种适应性优势的另一个维度
        
        Args:
            species_list: 所有存活物种
            niche_metrics: 生态位重叠和资源饱和度
            survival_rates: 上一回合的存活率（1 - 死亡率）
            habitat_manager: 栖息地管理器（P3需要）
            turn_index: 当前回合索引
            
        Returns:
            {lineage_code: new_population}
        """
        # 【新增】保存 turn_index 供子方法使用
        self._current_turn_index = turn_index
        
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
            
            # 【移除硬上限】只保留技术安全限制（JavaScript整数上限）
            # 生态上限由竞争、捕食、资源等因素决定，不再使用20%硬性限制
            new_pop = min(new_pop, self.MAX_SAFE_POPULATION)
            
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
            # 【改进v5】使用指数权重 + 低阈值截断，让物种更集中在高适宜度地块
            from ...core.config import PROJECT_ROOT
            # 注意：environment_repository 已在模块顶部导入，此处不要重复导入
            try:
                ui_cfg = environment_repository.load_ui_config(PROJECT_ROOT / "data/settings.json")
                eco_cfg = ui_cfg.ecology_balance
                suitability_alpha = eco_cfg.suitability_weight_alpha
                suitability_cutoff = eco_cfg.suitability_cutoff
            except Exception:
                suitability_alpha = 1.5
                suitability_cutoff = 0.25
            
            # 过滤低于阈值的地块，并应用指数权重
            weighted_habitats = []
            for habitat in habitats:
                if habitat.suitability >= suitability_cutoff:
                    weight = habitat.suitability ** suitability_alpha
                    weighted_habitats.append((habitat, weight))
            
            # 如果所有地块都被过滤，使用原始宜居度最高的前3个
            if not weighted_habitats:
                sorted_habs = sorted(habitats, key=lambda h: h.suitability, reverse=True)[:3]
                for habitat in sorted_habs:
                    weight = max(0.1, habitat.suitability) ** suitability_alpha
                    weighted_habitats.append((habitat, weight))
            
            total_weight = sum(w for _, w in weighted_habitats)
            tile_populations: dict[int, int] = {}
            for habitat, weight in weighted_habitats:
                tile_pop = int(current_total_pop * (weight / total_weight))
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
            
            # 【移除硬上限】只保留技术安全限制
            # 生态上限由地块资源、竞争、捕食等因素决定
            new_total_pop = min(new_total_pop, self.MAX_SAFE_POPULATION)
            
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
        
        【改进】支持植物散布能力：
        - 植物的"散布能力"特质影响扩散效率
        - 高散布能力的植物更容易占领新地块
        
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
        from .trait_config import PlantTraitConfig
        
        pressure_modifiers: dict[int, float] = {}
        
        # 计算平均种群密度（用于判断相对压力）
        total_pop = sum(tile_populations.values())
        num_tiles = len(habitats)
        avg_density = total_pop / num_tiles if num_tiles > 0 else 0
        
        if avg_density == 0:
            return {h.tile_id: 1.0 for h in habitats}
        
        # 【新增】植物散布能力修正
        is_plant = PlantTraitConfig.is_plant(species)
        dispersal_bonus = 1.0
        if is_plant:
            # 植物散布能力（0-10）影响扩散效率
            dispersal_ability = species.abstract_traits.get("散布能力", 3.0)
            # 散布能力5为基准，每超过1点增加10%扩散效率
            dispersal_bonus = 1.0 + (dispersal_ability - 5.0) * 0.1
            dispersal_bonus = max(0.5, min(1.5, dispersal_bonus))  # 限制在0.5-1.5
        
        for habitat in habitats:
            tile_id = habitat.tile_id
            tile_pop = tile_populations.get(tile_id, 0)
            
            # 计算该地块相对于平均密度的偏离
            relative_density = tile_pop / avg_density if avg_density > 0 else 1.0
            
            # 高密度地块（>1.5倍平均）：压力增加，承载力降低
            if relative_density > 1.5:
                # 最多降低20%承载力
                # 【新增】植物高散布能力可以更有效地缓解高密度压力
                base_pressure = (relative_density - 1.5) * 0.1
                if is_plant:
                    base_pressure = base_pressure / dispersal_bonus  # 高散布能力降低压力影响
                pressure_mod = 1.0 - min(0.2, base_pressure)
                pressure_modifiers[tile_id] = pressure_mod
            
            # 低密度地块（<0.5倍平均）：压力减小，承载力提高
            elif relative_density < 0.5:
                # 最多提高20%承载力
                # 【新增】植物高散布能力可以更好地利用新地块
                base_bonus = (0.5 - relative_density) * 0.2
                if is_plant:
                    base_bonus = base_bonus * dispersal_bonus  # 高散布能力增强扩张能力
                pressure_mod = 1.0 + min(0.2, base_bonus)
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
            # 【改进v8】直接使用ResourceManager的计算结果，确保NPP逻辑统一
            # 获取地块资源状态
            from ..ecology.resource_manager import get_resource_manager
            try:
                # 尝试从容器或上下文获取资源管理器（这里暂时用单例模式回退）
                resource_manager = get_resource_manager()
                tile_state = resource_manager.get_tile_state(tile_id)
                if tile_state:
                    # 使用 T1 承载力 (kg)
                    t1_base_capacity = tile_state.t1_capacity_kg
                else:
                    # 回退逻辑（如果未初始化）
                    t1_base_capacity = tile.resources * 100_000
            except Exception:
                # 异常回退
                t1_base_capacity = tile.resources * 100_000
            
            # 应用P2动态修正（环境变化）
            # 注意：如果使用了 ResourceManager，这一步可能在 calculate_npp 中已经包含了部分环境影响
            # 但这里是针对短期的剧烈波动（temp_change），可以保留作为额外修正
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
            
            # 5. 【改进】基于生态效率计算各营养级承载力
            # 使用默认生态效率值（避免依赖全局资源管理器）
            eff_t1_t2 = 0.12  # T1→T2 效率
            eff_t2_t3 = 0.10  # T2→T3 效率
            eff_t3_t4 = 0.10  # T3→T4 效率
            eff_t4_t5 = 0.08  # T4→T5 效率
            
            # 计算各营养级的理论承载力
            # T1.0 = 100%, T1.5 = 40%, T2.0 = 12%, T2.5 = 6%, T3.0 = 1.2%, ...
            trophic_capacities = {1.0: t1_base_capacity}
            for t in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5]:
                if t == 1.5:
                    # T1.5 (分解者) 承载力较高，约为 T1 的 40%
                    trophic_capacities[t] = t1_base_capacity * 0.4
                else:
                    # 其他消费者按照生态效率递减
                    prev_level = t - 0.5
                    prev_cap = trophic_capacities.get(prev_level, t1_base_capacity * 0.01)
                    
                    # 根据营养级选择合适的效率
                    base_level = int(t)
                    if base_level == 2:
                        efficiency = eff_t1_t2
                    elif base_level == 3:
                        efficiency = eff_t2_t3
                    elif base_level == 4:
                        efficiency = eff_t3_t4
                    else:
                        efficiency = eff_t4_t5
                    
                    trophic_capacities[t] = prev_cap * efficiency
            
            # 6. 检查猎物是否存在（用于食物链断裂检测）
            # 获取当前地块存在的营养级
            existing_trophic_levels = set(by_trophic_range.keys())
            
            # 7. 计算T1.5-T5.5的承载力
            for t_range in sorted([t for t in by_trophic_range.keys() if t >= 1.5]):
                tx_species = by_trophic_range[t_range]
                
                # 检查是否有可捕食的猎物
                min_prey_level = max(1.0, t_range - 1.5)
                max_prey_level = t_range - 0.5
                has_prey = any(
                    min_prey_level <= prey_level <= max_prey_level
                    for prey_level in existing_trophic_levels
                )
                
                # 基础承载力
                base_capacity = trophic_capacities.get(t_range, t1_base_capacity * 0.001)
                
                if not has_prey and t_range >= 2.0:
                    # 没有猎物 → 严重饥荒，承载力大幅下降
                    # 但不是完全为0，允许杂食/机会主义生存
                    base_capacity *= 0.05  # 降至5%
                    logger.debug(
                        f"[食物链断裂] T{t_range} 无猎物，承载力降至5%"
                    )
                
                # Tx物种之间共享承载力
                tx_total_suitability = sum(suitability for _, suitability in tx_species)
                for species, suitability in tx_species:
                    if tx_total_suitability > 0:
                        species_share = suitability / tx_total_suitability
                        species_capacity = base_capacity * species_share
                    else:
                        species_capacity = base_capacity / len(tx_species) if tx_species else 0
                    
                    # 应用物种特定修正
                    species_capacity *= self._get_species_suitability_for_tile(species, tile)
                    species_capacity *= self._get_body_size_modifier(species, is_producer=False)
                    
                    tile_capacities[(tile_id, species.id)] = max(1000, species_capacity)
        
        # 记录日志
        logger.info(f"[营养级承载力] 计算完成，{len(tile_capacities)}个地块×物种组合")
        return tile_capacities
    
    def _get_species_suitability_for_tile(self, species: Species, tile: MapTile) -> float:
        """计算物种对地块的基础适宜度 (v2.0 收紧版)
        
        【v2.0 改进】
        - 温度范围：5-10°C（极窄）
        - 温度惩罚：0.4/度
        - 湿度惩罚：4.0系数
        """
        # 温度适应性 (v2.0 收紧)
        heat_res = species.abstract_traits.get("耐热性", 5)
        cold_res = species.abstract_traits.get("耐寒性", 5)
        
        # 最优温度和容忍范围
        optimal_temp = 15.0 + (heat_res - cold_res) * 2.0
        tolerance_range = (cold_res + heat_res) * 1.0  # coef=1.0，5-10°C范围
        
        min_temp = optimal_temp - tolerance_range / 2
        max_temp = optimal_temp + tolerance_range / 2
        
        if min_temp <= tile.temperature <= max_temp:
            temp_score = 1.0
        else:
            diff = min(abs(tile.temperature - min_temp), abs(tile.temperature - max_temp))
            # 每度扣0.4，超过2.5度归零
            temp_score = max(0.0, 1.0 - diff * 0.4)
        
        # 湿度适应性 (v2.0 收紧)
        drought_pref = species.abstract_traits.get("耐旱性", 5)
        best_humidity = 1.0 - (drought_pref * 0.08)
        hum_diff = abs(tile.humidity - best_humidity)
        humidity_score = max(0.0, 1.0 - hum_diff * 4.0)  # 系数从1.0增加到4.0
        
        # 综合评分 (保证最低0.1避免除零)
        return max(0.1, (temp_score * 0.5 + humidity_score * 0.5))
    
    def _get_trophic_range(self, trophic_level: float) -> float:
        """将精确营养级映射到0.5间隔的范围
        
        标准5级食物链 + 0.5间隔的精细分类：
        ┌───────────┬─────────────────────────────────────────┐
        │ 范围      │ 生态角色                                │
        ├───────────┼─────────────────────────────────────────┤
        │ 1.0-1.49  │ T1 生产者（光合/化能自养）              │
        │ 1.5-1.99  │ T1.5 分解者/腐食者                      │
        │ 2.0-2.49  │ T2 初级消费者（草食/滤食）              │
        │ 2.5-2.99  │ T2.5 杂食（偏向植物）                   │
        │ 3.0-3.49  │ T3 次级消费者（捕食草食动物）           │
        │ 3.5-3.99  │ T3.5 杂食（偏向肉食）                   │
        │ 4.0-4.49  │ T4 三级消费者（捕食小型捕食者）         │
        │ 4.5-4.99  │ T4.5 高级捕食者                         │
        │ 5.0+      │ T5 顶级捕食者（食物链终端）             │
        └───────────┴─────────────────────────────────────────┘
        
        Args:
            trophic_level: 精确营养级 (1.0-5.5)
            
        Returns:
            范围基准值 (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5)
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
        
        【重要】使用相对生物量指数，而不是绝对克数
        因为微生物的绝对生物量很小（纳克级），但种群数量巨大
        我们用 "种群 × 体重^0.75" 作为相对指数（类似 Kleiber 定律）
        
        Args:
            by_trophic_range: 按营养级分组的物种
            species_habitats: 物种栖息地映射
            tile_id: 当前地块ID
            
        Returns:
            {trophic_range: relative_biomass_index}
        """
        biomass_pools: dict[float, float] = {}
        
        for t_range, species_list in by_trophic_range.items():
            total_biomass = 0.0
            
            for species, suitability in species_list:
                # 获取物种的总种群
                pop = species.morphology_stats.get("population", 0) or 0
                weight = species.morphology_stats.get("body_weight_g", 1.0) or 1.0
                
                # 【修复】使用相对生物量指数
                # 对于微生物：1亿个体 × (1e-9)^0.75 ≈ 1亿 × 5.6e-7 ≈ 56
                # 这给出了一个合理的相对数值，避免绝对值太小
                # 同时保持体重的生态学意义（更重的生物代谢需求更高）
                weight_factor = max(weight, 1e-12) ** 0.75  # Kleiber 指数
                tile_biomass = pop * weight_factor * suitability
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
        
        标准5级食物链捕食关系：
        ┌────────┬─────────────────┬──────────────────────────────┐
        │ 捕食者 │ 可捕食范围      │ 主要猎物                     │
        ├────────┼─────────────────┼──────────────────────────────┤
        │ T2     │ T1.0 - T1.5     │ 植物、藻类、分解者           │
        │ T2.5   │ T1.0 - T2.0     │ 植物 + 小型草食动物（杂食）  │
        │ T3     │ T1.5 - T2.5     │ 草食动物、杂食动物           │
        │ T3.5   │ T2.0 - T3.0     │ 草食 + 小型捕食者            │
        │ T4     │ T2.5 - T3.5     │ 次级消费者                   │
        │ T4.5   │ T3.0 - T4.0     │ 次级 + 三级消费者            │
        │ T5     │ T3.5 - T4.5     │ 各级捕食者                   │
        │ T5.5   │ T4.0 - T5.0     │ 三级消费者 + 顶级捕食者      │
        └────────┴─────────────────┴──────────────────────────────┘
        
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
        
        # 记录捕食日志
        logger.debug(
            f"[捕食范围] T{predator_trophic:.1f} 可捕食 T{min_prey_level:.1f}-T{max_prey_level:.1f}"
        )
        
        # 汇总所有可捕食范围内的相对生物量指数
        for prey_level, prey_biomass in biomass_pools.items():
            if min_prey_level <= prey_level <= max_prey_level:
                # 检查该营养级是否真的有物种
                if prey_level in by_trophic_range and by_trophic_range[prey_level]:
                    available_biomass += prey_biomass
                    logger.debug(
                        f"[捕食] T{predator_trophic:.1f} 获取 T{prey_level:.1f} 生物量指数: {prey_biomass:.2e}"
                    )
        
        # 生态效率（Lindeman效率）：约10-15%
        # 这包括：可食用部分比例、捕获成功率、消化吸收效率
        # 使用15%作为基础效率（给消费者更多生存空间）
        ECOLOGICAL_EFFICIENCY = 0.15
        
        result = available_biomass * ECOLOGICAL_EFFICIENCY
        logger.debug(
            f"[生态效率] T{predator_trophic:.1f} 可用生物量指数: {available_biomass:.2e} × {ECOLOGICAL_EFFICIENCY:.0%} = {result:.2e}"
        )
        
        return result
    
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
        """使用改进的逻辑斯谛模型计算种群增长。
        
        【平衡修复】
        1. 添加微生物/快繁殖物种的增长加成
        2. 衰退时提高繁殖效率（生存本能）
        3. 修复承载力接近时增长效率过低的问题
        
        闭式解公式: P(t) = K / (1 + ((K - P0) / P0) * e^(-r * t))
        """
        MAX_SAFE_POPULATION = 9_007_199_254_740_991
        current_pop = max(0, min(int(current_pop), MAX_SAFE_POPULATION))
        carrying_capacity = max(1, min(int(carrying_capacity), MAX_SAFE_POPULATION))
        survival_rate = max(0.0, min(1.0, float(survival_rate)))
        resource_saturation = max(0.0, float(resource_saturation))
        
        if current_pop <= 0:
            return 0
        
        # 【改进v6】从配置加载繁殖参数
        try:
            from ...core.config import PROJECT_ROOT
            from ...repositories.environment_repository import environment_repository
            ui_cfg = environment_repository.load_ui_config(PROJECT_ROOT / "data/settings.json")
            repro_cfg = ui_cfg.reproduction
            # 繁殖参数
            growth_rate_per_speed = repro_cfg.growth_rate_per_repro_speed
            size_bonus_microbe = repro_cfg.size_bonus_microbe
            size_bonus_tiny = repro_cfg.size_bonus_tiny
            size_bonus_small = repro_cfg.size_bonus_small
            repro_bonus_weekly = repro_cfg.repro_bonus_weekly
            repro_bonus_monthly = repro_cfg.repro_bonus_monthly
            repro_bonus_halfyear = repro_cfg.repro_bonus_halfyear
            survival_mod_base = repro_cfg.survival_modifier_base
            survival_mod_rate = repro_cfg.survival_modifier_rate
            instinct_threshold = repro_cfg.survival_instinct_threshold
            instinct_bonus = repro_cfg.survival_instinct_bonus
            t2_efficiency = repro_cfg.t2_birth_efficiency
            t3_efficiency = repro_cfg.t3_birth_efficiency
            t4_efficiency = repro_cfg.t4_birth_efficiency
            saturation_penalty = repro_cfg.resource_saturation_penalty_mild
            saturation_floor = repro_cfg.resource_saturation_floor
        except Exception:
            # 默认值
            growth_rate_per_speed = 0.4
            size_bonus_microbe = 2.0
            size_bonus_tiny = 1.5
            size_bonus_small = 1.2
            repro_bonus_weekly = 1.8
            repro_bonus_monthly = 1.4
            repro_bonus_halfyear = 1.2
            survival_mod_base = 0.4
            survival_mod_rate = 1.2
            instinct_threshold = 0.5
            instinct_bonus = 0.8
            t2_efficiency = 0.9
            t3_efficiency = 0.7
            t4_efficiency = 0.5
            saturation_penalty = 0.4
            saturation_floor = 0.2
        
        # 1. 基础增长率（基于繁殖速度属性）
        repro_speed = species.abstract_traits.get("繁殖速度", 5)
        base_growth_multiplier = 1.0 + (repro_speed * growth_rate_per_speed)
        
        # 2. 体型/世代加成
        body_length = species.morphology_stats.get("body_length_cm", 10.0)
        generation_time = species.morphology_stats.get("generation_time_days", 365)
        
        # 体型加成：越小增长越快
        if body_length < 0.01:  # 微生物（<0.1mm）
            size_bonus = size_bonus_microbe
        elif body_length < 0.1:  # 小型生物（0.1mm-1mm）
            size_bonus = size_bonus_tiny
        elif body_length < 1.0:  # 小型生物（1mm-1cm）
            size_bonus = size_bonus_small
        else:
            size_bonus = 1.0
        
        # 繁殖速度加成：世代越短增长越快
        if generation_time < 7:  # <1周
            repro_bonus = repro_bonus_weekly
        elif generation_time < 30:  # <1月
            repro_bonus = repro_bonus_monthly
        elif generation_time < 180:  # <半年
            repro_bonus = repro_bonus_halfyear
        else:
            repro_bonus = 1.0
        
        # 综合繁殖加成（取最大值，避免双重加成过高）
        fertility_bonus = max(size_bonus, repro_bonus)
        base_growth_multiplier *= fertility_bonus
        
        # 【时代缩放】早期时代（太古宙/元古宙）繁殖极快
        # 每回合代表几千万年，单细胞生物可繁衍天文数字的代数
        current_turn = getattr(self, '_current_turn_index', 0)
        time_config = get_time_config(current_turn)
        time_scaling = time_config["scaling_factor"]
        
        if time_scaling > 1.0:
            # 使用平方根缓和极端值：太古宙 sqrt(40)≈6.3x, 元古宙 sqrt(100)=10x
            effective_scaling = max(1.0, time_scaling ** 0.5)
            base_growth_multiplier *= effective_scaling
            
            if time_scaling > 1.5:
                logger.debug(
                    f"[时代缩放] {species.common_name} 处于 {time_config['era_name']}，"
                    f"繁殖倍率={effective_scaling:.1f}x"
                )
        
        # 【新增v4】新物种繁殖率加成
        # 新分化物种在前几回合获得繁殖率加成，体现适应性优势
        try:
            from ...models.config import EcologyBalanceConfig
            from ...repositories.environment_repository import environment_repository
            from ...core.config import PROJECT_ROOT
            ui_cfg = environment_repository.load_ui_config(PROJECT_ROOT / "data/settings.json")
            eco_cfg = ui_cfg.ecology_balance
            
            if eco_cfg.enable_new_species_advantage:
                current_turn = getattr(self, '_current_turn_index', 0)
                species_created_turn = getattr(species, 'created_turn', 0) or 0
                species_age = current_turn - species_created_turn
                
                if species_age == 0:
                    # 新分化物种第1回合：最大繁殖率加成
                    new_species_boost = eco_cfg.new_species_reproduction_boost
                    base_growth_multiplier *= new_species_boost
                    logger.debug(
                        f"[新种繁殖加成] {species.common_name} T0: "
                        f"繁殖率×{new_species_boost:.2f}"
                    )
                elif species_age == 1:
                    # 第2回合：中等加成
                    new_species_boost = 1.0 + (eco_cfg.new_species_reproduction_boost - 1.0) * 0.5
                    base_growth_multiplier *= new_species_boost
                elif species_age == 2:
                    # 第3回合：轻微加成
                    new_species_boost = 1.0 + (eco_cfg.new_species_reproduction_boost - 1.0) * 0.25
                    base_growth_multiplier *= new_species_boost
        except Exception as e:
            # 配置加载失败时忽略新物种加成
            pass
        
        # 【改进v6】营养级效率调整 - 从配置读取
        # 【v11】重新设计：消费者不再受惩罚，反而在猎物充足时获得加成
        trophic_level = getattr(species, 'trophic_level', 1.0) or 1.0
        
        if trophic_level >= 4.0:
            # 顶级捕食者（T4+）受效率惩罚（食物链顶端，能量传递效率低）
            base_growth_multiplier *= t4_efficiency
            logger.debug(f"[营养级效率] {species.common_name} (T{trophic_level:.1f}) 应用顶级捕食者惩罚 {t4_efficiency:.1%}")
        elif trophic_level >= 3.0:
            # 高级消费者（T3）受中等效率惩罚
            base_growth_multiplier *= t3_efficiency
            logger.debug(f"[营养级效率] {species.common_name} (T{trophic_level:.1f}) 应用高营养级惩罚 {t3_efficiency:.1%}")
        elif trophic_level >= 2.0:
            # 【v13】初级消费者：保持基础繁殖效率，不额外加成
            # 消费者通过捕食获得能量，繁殖依赖猎物充足度
            logger.debug(f"[消费者] {species.common_name} (T{trophic_level:.1f}) 基础繁殖效率")
        else:
            # 【v13大幅强化】T1 生产者：生态金字塔基础，极速繁殖
            # 生产者（藻类、细菌、原生植物）是 r 策略物种，繁殖速度极快
            # 它们的数量应该由消费者捕食来控制，而不是繁殖效率限制
            producer_boost = 5.0  # 500% 繁殖效率加成（5倍基础速度）
            base_growth_multiplier *= producer_boost
            logger.debug(f"[生产者爆发] {species.common_name} (T{trophic_level:.1f}) 生产者繁殖加成 +400%")
        
        # 3. 生存率修正
        survival_modifier = survival_mod_base + survival_rate * survival_mod_rate
        
        # 4. 【优化v7】高死亡率繁殖效率调整
        # 设计理念：极端环境下，物种繁殖能力应该下降而非上升
        # 原因：高死亡率意味着能量消耗在生存而非繁殖
        death_rate = 1.0 - survival_rate
        
        # 加载高死亡率惩罚参数
        try:
            mortality_penalty_threshold = repro_cfg.mortality_penalty_threshold
            mortality_penalty_rate = repro_cfg.mortality_penalty_rate
            extreme_mortality_threshold = repro_cfg.extreme_mortality_threshold
        except Exception:
            mortality_penalty_threshold = 0.4
            mortality_penalty_rate = 0.3
            extreme_mortality_threshold = 0.7
        
        # 【v13】低死亡率繁殖加成 - 生产者获得巨大加成
        # 生产者在环境适宜时应该爆发式增长，消费者则依赖捕食效率
        LOW_MORTALITY_THRESHOLD = 0.50  # 死亡率低于50%时开始给予加成
        
        if death_rate < LOW_MORTALITY_THRESHOLD:
            # 根据营养级分配不同的加成
            if trophic_level < 2.0:
                # 【v13】生产者：环境适宜时爆发式增长（最高+300%）
                # 这模拟了藻类大爆发、细菌繁殖等现象
                low_mortality_bonus = (LOW_MORTALITY_THRESHOLD - death_rate) / LOW_MORTALITY_THRESHOLD * 3.0
                logger.debug(
                    f"[生产者爆发] {species.common_name} 死亡率{death_rate:.1%}，"
                    f"繁殖效率+{low_mortality_bonus:.0%}"
                )
            elif trophic_level < 3.0:
                # 初级消费者：猎物丰富时繁殖效率提高（最高+30%）
                low_mortality_bonus = (LOW_MORTALITY_THRESHOLD - death_rate) / LOW_MORTALITY_THRESHOLD * 0.30
                logger.debug(
                    f"[消费者加成] {species.common_name} 死亡率{death_rate:.1%}，"
                    f"繁殖效率+{low_mortality_bonus:.0%}"
                )
            else:
                # 高级消费者：加成更小（最高+15%）
                low_mortality_bonus = (LOW_MORTALITY_THRESHOLD - death_rate) / LOW_MORTALITY_THRESHOLD * 0.15
            
            survival_modifier *= (1.0 + low_mortality_bonus)
        
        # 【核心修改】高死亡率惩罚优先于生存本能
        if death_rate > extreme_mortality_threshold:
            # 极端死亡率：繁殖效率直接减半
            extreme_penalty = 0.5
            survival_modifier *= extreme_penalty
            logger.info(f"[极端压力] {species.common_name} 死亡率{death_rate:.1%}超过阈值，繁殖效率减半")
        elif death_rate > mortality_penalty_threshold:
            # 高死亡率：按比例降低繁殖效率
            # 死亡率超过阈值每10%，繁殖效率降低 mortality_penalty_rate
            penalty_factor = 1.0 - (death_rate - mortality_penalty_threshold) * mortality_penalty_rate * 10
            penalty_factor = max(0.3, penalty_factor)  # 最低保留30%效率
            survival_modifier *= penalty_factor
            logger.debug(f"[高压力惩罚] {species.common_name} 死亡率{death_rate:.1%}，繁殖效率×{penalty_factor:.2f}")
        elif death_rate > instinct_threshold:
            # 中等死亡率：轻微的生存本能加成（但比原来更温和）
            survival_instinct = 1.0 + (death_rate - instinct_threshold) * instinct_bonus * 0.5  # 加成减半
            survival_modifier *= survival_instinct
            logger.debug(f"[生存本能] {species.common_name} 死亡率{death_rate:.1%}，繁殖加成×{survival_instinct:.2f}")
        
        # 5. 资源压力修正（使用配置参数）
        if resource_saturation <= 1.0:
            resource_modifier = 1.0
        elif resource_saturation <= 2.0:
            resource_modifier = 1.0 - (resource_saturation - 1.0) * saturation_penalty
        else:
            resource_modifier = max(saturation_floor, 0.6 - (resource_saturation - 2.0) * 0.15)
        
        # 综合增长倍数
        # 【v8新增】应用资源繁荣加成
        growth_multiplier = base_growth_multiplier * survival_modifier * resource_modifier * self.resource_boost
        
        # 【新增v12】生态拟真模块集成 (Ecological Realism)
        # 从 context 获取语义驱动的繁殖率修正（Allee效应、环境波动、共生等）
        eco_realism_data = getattr(self, '_ecological_realism_data', None)
        if eco_realism_data:
            lineage_code = species.lineage_code
            eco_repro_modifier = 1.0
            
            # Allee 效应：小种群繁殖惩罚
            allee_results = eco_realism_data.get("allee_results", {})
            allee_data = allee_results.get(lineage_code, {})
            allee_modifier = allee_data.get("reproduction_modifier", 1.0)
            if allee_modifier < 1.0:
                eco_repro_modifier *= allee_modifier
                logger.debug(f"[生态拟真] {species.common_name} Allee效应修正: ×{allee_modifier:.2f}")
            
            # 环境波动修正
            env_modifiers = eco_realism_data.get("env_modifiers", {})
            env_mod = env_modifiers.get(lineage_code, 1.0)
            if env_mod != 1.0:
                eco_repro_modifier *= env_mod
                logger.debug(f"[生态拟真] {species.common_name} 环境波动修正: ×{env_mod:.2f}")
            
            # 互利共生收益（提高繁殖率）
            mutualism_benefits = eco_realism_data.get("mutualism_benefits", {})
            mutualism = mutualism_benefits.get(lineage_code, 0.0)
            if mutualism > 0:
                eco_repro_modifier *= (1.0 + mutualism)
                logger.debug(f"[生态拟真] {species.common_name} 共生收益修正: ×{1.0 + mutualism:.2f}")
            
            growth_multiplier *= eco_repro_modifier
        
        # 限制单回合增长倍数（从配置读取）
        try:
            growth_min = repro_cfg.growth_multiplier_min
            growth_max = repro_cfg.growth_multiplier_max
            overshoot_decay = repro_cfg.overshoot_decay_rate
        except Exception:
            growth_min = 0.6
            growth_max = 15.0
            overshoot_decay = 0.25
        
        growth_multiplier = max(growth_min, min(growth_max, growth_multiplier))
        
        # 6. 使用改进的逻辑斯谛模型计算新种群
        P0 = float(current_pop)
        K = float(carrying_capacity)
        
        if P0 >= K:
            # 已超过承载力，应用衰减
            overshoot = P0 - K
            new_pop = K + overshoot * (1.0 - overshoot_decay)
        else:
            # 低于承载力，应用增长
            utilization = P0 / K  # 0 - 1
            
            # 【修复】改进增长效率曲线
            # 原来：growth_efficiency = 1.0 - utilization（线性）
            # 问题：接近承载力时效率趋近0
            # 修复：使用S型曲线，保证最低20%效率
            # utilization = 0 -> efficiency = 1.0
            # utilization = 0.5 -> efficiency = 0.65
            # utilization = 0.9 -> efficiency = 0.30
            # utilization = 1.0 -> efficiency = 0.20
            growth_efficiency = 0.20 + 0.80 * (1.0 - utilization ** 0.7)
            
            # 计算实际增长
            actual_multiplier = 1.0 + (growth_multiplier - 1.0) * growth_efficiency
            new_pop = P0 * actual_multiplier
            
            # 允许小幅超过承载力（110%），模拟短期过载
            new_pop = min(new_pop, K * 1.1)
        
        # 7. 边界检查
        new_pop = max(0, min(new_pop, MAX_SAFE_POPULATION))
        
        if math.isinf(new_pop) or math.isnan(new_pop):
            logger.warning(f"[种群计算] 检测到异常值，重置为当前值: {current_pop}")
            new_pop = current_pop
        
        result = int(new_pop)
        
        change_ratio = result / max(current_pop, 1)
        if change_ratio > 2.0 or change_ratio < 0.5:
            logger.debug(
                f"[种群变化] {species.common_name}: {current_pop:,} -> {result:,} "
                f"(倍数={change_ratio:.2f}, K={carrying_capacity:,}, 繁殖加成={fertility_bonus:.1f}x)"
            )
        
        return result
