from __future__ import annotations

from typing import Sequence, TYPE_CHECKING

from ...schemas.responses import MajorPressureEvent, MapChange, MigrationEvent
from ...simulation.species import MortalityResult

if TYPE_CHECKING:
    from ...simulation.tile_based_mortality import TileBasedMortalityEngine


class MigrationAdvisor:
    """基于规则引擎的迁徙决策系统。
    
    【核心改进1】地块级死亡率差异：
    - 从高死亡率地块迁往低死亡率地块
    - 迁徙方向更精确，基于实际环境条件
    
    【核心改进2】消费者追踪猎物机制：
    - T2+ 消费者会主动追踪猎物分布
    - 当猎物迁移或消失时，消费者会跟随迁徙
    - 避免高营养级物种困在没有食物的区域
    
    注意：当前版本只生成迁徙建议，不实际执行迁徙。
    实际的栖息地变化需要由 MapStateManager 执行（未来功能）。
    """

    def __init__(self, 
                 pressure_migration_threshold: float = 0.35,  # 降低压力驱动阈值
                 saturation_threshold: float = 0.9,          # 降低资源饱和阈值
                 overflow_growth_threshold: float = 1.2,     # 降低溢出增长阈值
                 overflow_pressure_threshold: float = 0.7,   # 降低溢出资源压力阈值
                 min_population: int = 500,
                 prey_scarcity_threshold: float = 0.3,       # 猎物稀缺阈值（触发追踪迁徙）
                 enable_actual_migration: bool = True) -> None:  # P1: 改为默认执行迁徙
        """初始化迁移顾问
        
        调整后的逻辑：
        - 压力驱动（逃离）：降低门槛(35%)，更容易触发
        - 资源饱和（扩散）：降低门槛(0.9)，鼓励早期扩散
        - 人口溢出（扩张）：降低门槛(120%)，鼓励种群扩张
        - 猎物追踪（新增）：消费者追踪猎物分布
        
        Args:
            prey_scarcity_threshold: 猎物稀缺阈值，当低于此值时触发追踪迁徙
            enable_actual_migration: P1改进 - 是否实际执行迁徙（默认True）
                True: 生成建议并通过habitat_manager实际修改栖息地分布
                False: 仅生成建议（兼容旧系统）
        """
        self.pressure_migration_threshold = pressure_migration_threshold
        self.saturation_threshold = saturation_threshold
        self.overflow_growth_threshold = overflow_growth_threshold
        self.overflow_pressure_threshold = overflow_pressure_threshold
        self.min_population = min_population
        self.prey_scarcity_threshold = prey_scarcity_threshold
        self.enable_actual_migration = enable_actual_migration
        
        # 【新增】地块死亡率数据缓存
        self._tile_mortality_cache: dict[str, dict[int, float]] = {}  # {lineage_code: {tile_id: death_rate}}
        
        # 【新增】猎物密度数据缓存（用于消费者追踪猎物）
        self._prey_density_cache: dict[str, float] = {}  # {lineage_code: prey_density}
    
    def set_tile_mortality_data(
        self, 
        lineage_code: str, 
        tile_death_rates: dict[int, float]
    ) -> None:
        """设置物种在各地块的死亡率数据
        
        由 TileBasedMortalityEngine 调用，提供地块级死亡率
        
        Args:
            lineage_code: 物种谱系编码
            tile_death_rates: {tile_id: death_rate}
        """
        self._tile_mortality_cache[lineage_code] = tile_death_rates
    
    def set_prey_density_data(
        self,
        lineage_code: str,
        prey_density: float
    ) -> None:
        """设置消费者的猎物密度数据
        
        用于判断消费者是否需要追踪猎物迁徙
        
        Args:
            lineage_code: 物种谱系编码
            prey_density: 当前栖息地的猎物密度 (0.0-1.0)
        """
        self._prey_density_cache[lineage_code] = prey_density
    
    def clear_tile_mortality_cache(self) -> None:
        """清空地块死亡率缓存（每回合开始时调用）"""
        self._tile_mortality_cache.clear()
        self._prey_density_cache.clear()
    
    def _analyze_tile_mortality_gradient(self, lineage_code: str) -> tuple[float, str, str]:
        """分析物种在各地块的死亡率梯度
        
        Returns:
            (死亡率差异, 高死亡率区域描述, 低死亡率区域描述)
            如果没有地块数据，返回 (0.0, "", "")
        """
        tile_rates = self._tile_mortality_cache.get(lineage_code, {})
        
        if len(tile_rates) < 2:
            return 0.0, "", ""
        
        # 找出最高和最低死亡率的地块
        sorted_tiles = sorted(tile_rates.items(), key=lambda x: x[1])
        
        lowest_tile_id, lowest_rate = sorted_tiles[0]
        highest_tile_id, highest_rate = sorted_tiles[-1]
        
        mortality_gradient = highest_rate - lowest_rate
        
        # 如果梯度太小，不值得迁徙
        if mortality_gradient < 0.15:
            return mortality_gradient, "", ""
        
        # 生成区域描述（未来可以基于实际地块biome）
        high_desc = f"地块{highest_tile_id}区域（死亡率{highest_rate:.1%}）"
        low_desc = f"地块{lowest_tile_id}区域（死亡率{lowest_rate:.1%}）"
        
        return mortality_gradient, high_desc, low_desc

    def plan(
        self,
        species: Sequence[MortalityResult],
        pressures: dict[str, float],
        major_events: Sequence[MajorPressureEvent],
        map_changes: Sequence[MapChange],
        current_turn: int = 0,
        cooldown_species: set[str] | None = None,
    ) -> list[MigrationEvent]:
        """基于规则生成迁徙建议。
        
        【核心改进】消费者追踪猎物 + 地块级死亡率差异 + 迁徙冷却：
        - 类型-1（最高优先级）：猎物追踪迁徙 - 消费者追踪猎物密集区域
        - 类型0：地块梯度迁徙 - 从高死亡率地块迁往低死亡率地块
        - 类型1：压力驱动迁徙 - 死亡率高 + 环境压力
        - 类型2：资源饱和扩散 - 资源压力高 + 种群稳定
        - 类型3：人口溢出 - 种群暴涨 + 资源不足
        
        Args:
            species: 物种死亡率计算结果列表
            pressures: 环境压力字典
            major_events: 重大事件列表
            map_changes: 地图变化列表
            current_turn: 当前回合（用于日志）
            cooldown_species: 处于冷却期的物种代码集合（跳过这些物种）
        """
        if not species:
            return []
        
        if cooldown_species is None:
            cooldown_species = set()
        
        events: list[MigrationEvent] = []
        has_major_pressure = len(major_events) > 0 or len(pressures) > 0
        
        for result in species:
            lineage_code = result.species.lineage_code
            
            # 【新增】跳过处于迁徙冷却期的物种
            if lineage_code in cooldown_species:
                continue
            
            migration_type = None
            origin = ""
            destination = ""
            rationale = ""
            
            sp = result.species
            trophic_level = getattr(sp, 'trophic_level', 1.0)
            is_consumer = trophic_level >= 2.0  # T2+ 是消费者
            
            # 【最高优先级】类型-1：猎物追踪迁徙
            # 消费者（T2+）当猎物稀缺时，主动追踪猎物密集区域
            if is_consumer and result.survivors >= self.min_population:
                prey_density = self._prey_density_cache.get(lineage_code, 1.0)
                
                # 当猎物密度低于阈值时，触发追踪迁徙
                if prey_density < self.prey_scarcity_threshold:
                    migration_type = "prey_tracking"
                    origin, destination, rationale = self._determine_prey_tracking_migration(
                        result, prey_density
                    )
            
            # 【新增】类型0：地块梯度迁徙
            # 当不同地块的死亡率差异显著时，从高死亡率地块迁往低死亡率地块
            if not migration_type:
                gradient, high_area, low_area = self._analyze_tile_mortality_gradient(lineage_code)
                if gradient >= 0.20 and result.survivors >= self.min_population:
                    # 死亡率梯度超过20%，触发地块梯度迁徙
                    migration_type = "tile_gradient"
                    origin = high_area
                    destination = low_area
                    rationale = f"地块间死亡率差异{gradient:.0%}，从高风险区域迁往低风险区域"
            
            # 类型2：资源饱和扩散
            if not migration_type and result.resource_pressure > self.saturation_threshold:
                if result.survivors >= self.min_population:
                    migration_type = "saturation_dispersal"
                    origin, destination, rationale = self._determine_migration(
                        result, pressures, major_events, migration_type
                    )
            
            # 类型3：人口溢出
            if not migration_type and result.initial_population > 0:
                growth_rate = result.survivors / result.initial_population
                if growth_rate > self.overflow_growth_threshold and result.resource_pressure > self.overflow_pressure_threshold:
                    if result.survivors >= self.min_population:
                        migration_type = "population_overflow"
                        origin, destination, rationale = self._determine_migration(
                            result, pressures, major_events, migration_type
                        )
            
            # 类型1：压力驱动迁徙
            if not migration_type and result.death_rate >= self.pressure_migration_threshold:
                if result.survivors >= self.min_population and has_major_pressure:
                    migration_type = "pressure_driven"
                    origin, destination, rationale = self._determine_migration(
                        result, pressures, major_events, migration_type
                    )
            
            if migration_type:
                events.append(
                    MigrationEvent(
                        lineage_code=result.species.lineage_code,
                        origin=origin,
                        destination=destination,
                        rationale=rationale,
                    )
                )
        
        return events
    
    def _determine_prey_tracking_migration(
        self,
        result: MortalityResult,
        current_prey_density: float
    ) -> tuple[str, str, str]:
        """确定消费者追踪猎物的迁徙方向
        
        Args:
            result: 死亡率计算结果
            current_prey_density: 当前栖息地的猎物密度
            
        Returns:
            (origin, destination, rationale)
        """
        species = result.species
        trophic_level = getattr(species, 'trophic_level', 2.0)
        
        # 根据营养级确定猎物类型描述
        if trophic_level >= 5.0:
            prey_type = "大型猎物（三级消费者）"
        elif trophic_level >= 4.0:
            prey_type = "中型猎物（次级消费者）"
        elif trophic_level >= 3.0:
            prey_type = "草食动物（初级消费者）"
        else:
            prey_type = "生产者（植物/藻类）"
        
        origin = "猎物稀缺的当前栖息地"
        destination = f"追踪{prey_type}密集区域"
        rationale = (
            f"当前猎物密度仅{current_prey_density:.1%}，"
            f"作为T{trophic_level:.1f}消费者需追踪猎物迁徙以维持食物来源"
        )
        
        return origin, destination, rationale
    
    def _determine_migration(
        self,
        result: MortalityResult,
        pressures: dict[str, float],
        major_events: Sequence[MajorPressureEvent],
        migration_type: str = "pressure_driven",
    ) -> tuple[str, str, str]:
        """根据迁徙类型和压力确定迁徙方向和理由。
        
        Args:
            migration_type: "pressure_driven" | "saturation_dispersal" | "population_overflow"
        """
        # 资源饱和扩散
        if migration_type == "saturation_dispersal":
            return (
                "当前栖息地",
                "资源竞争较小的邻近区域",
                f"资源压力{result.resource_pressure:.2f}，种群向低竞争生态位扩散"
            )
        
        # 人口溢出
        if migration_type == "population_overflow":
            growth_rate = result.survivors / max(result.initial_population, 1)
            return (
                "高密度核心区",
                "低密度边缘区域",
                f"种群增长{(growth_rate-1)*100:.0f}%，溢出到周边空白生态位"
            )
        
        # 压力驱动迁徙（原有逻辑）
        species = result.species
        desc = species.description.lower()
        
        # 分析当前栖息地类型
        if any(kw in desc for kw in ("海洋", "浅海", "水域", "海")):
            origin = "沿海/浅海区域"
        elif any(kw in desc for kw in ("深海", "热液", "深水")):
            origin = "深海区域"
        elif any(kw in desc for kw in ("陆地", "平原", "森林", "草原")):
            origin = "陆地栖息地"
        else:
            origin = "原栖息地"
        
        # 根据压力决定目的地
        if "temperature" in pressures or "极寒" in str(major_events):
            # 温度压力：向温暖或稳定区域迁徙
            if "耐寒性" in species.abstract_traits and species.abstract_traits["耐寒性"] < 5:
                destination = "温暖低纬度区域"
                rationale = f"死亡率{result.death_rate:.1%}，耐寒性不足，向温暖区域迁徙避险"
            else:
                destination = "高纬度冷水区域"
                rationale = f"死亡率{result.death_rate:.1%}，利用耐寒优势迁往竞争较小的冷区"
        elif "drought" in pressures or "干旱" in str(major_events):
            destination = "湿润水域/深海"
            rationale = f"死亡率{result.death_rate:.1%}，干旱压力下向水源充足区域迁徙"
        elif "flood" in pressures or "洪水" in str(major_events):
            destination = "高地/山地避难所"
            rationale = f"死亡率{result.death_rate:.1%}，洪水威胁下向地势较高区域转移"
        elif "volcano" in pressures:
            destination = "远离火山活动的安全区"
            rationale = f"死亡率{result.death_rate:.1%}，火山活动威胁，迁往地质稳定区"
        else:
            # 通用压力：根据生态位重叠度决定
            if result.niche_overlap > 0.6:
                destination = "竞争较小的边缘生态位"
                rationale = f"死亡率{result.death_rate:.1%}，生态位重叠{result.niche_overlap:.2f}，转移至竞争较小区域"
            else:
                destination = "资源更丰富的新栖息地"
                rationale = f"死亡率{result.death_rate:.1%}，寻找资源更充足的替代栖息地"
        
        return origin, destination, rationale
