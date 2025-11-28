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
                 pressure_migration_threshold: float = 0.25,  # 【修复】从0.35降到0.25，更容易触发
                 saturation_threshold: float = 0.85,          # 【修复】从0.9降到0.85
                 overflow_growth_threshold: float = 1.15,     # 【修复】从1.2降到1.15
                 overflow_pressure_threshold: float = 0.6,    # 【修复】从0.7降到0.6
                 min_population: int = 100,                   # 【修复】从500降到100，微生物更容易迁徙
                 prey_scarcity_threshold: float = 0.3,        # 猎物稀缺阈值（触发追踪迁徙）
                 chronic_decline_threshold: float = 0.15,     # 【新增】慢性衰退阈值
                 chronic_decline_turns: int = 2,              # 【新增】触发慢性衰退迁徙的连续回合数
                 enable_actual_migration: bool = True) -> None:
        """初始化迁移顾问
        
        【平衡修复】降低所有迁徙阈值，增加慢性衰退迁徙机制
        
        调整后的逻辑：
        - 压力驱动（逃离）：门槛25%，物种开始死亡就考虑迁徙
        - 资源饱和（扩散）：门槛0.85，鼓励早期扩散
        - 人口溢出（扩张）：门槛115%，轻微增长就扩张
        - 猎物追踪：消费者追踪猎物分布
        - 【新增】慢性衰退迁徙：连续多回合死亡率>繁殖率时触发
        
        Args:
            prey_scarcity_threshold: 猎物稀缺阈值，当低于此值时触发追踪迁徙
            chronic_decline_threshold: 慢性衰退阈值（死亡率），超过此值开始计数
            chronic_decline_turns: 连续多少回合慢性衰退触发生存迁徙
            enable_actual_migration: 是否实际执行迁徙
        """
        self.pressure_migration_threshold = pressure_migration_threshold
        self.saturation_threshold = saturation_threshold
        self.overflow_growth_threshold = overflow_growth_threshold
        self.overflow_pressure_threshold = overflow_pressure_threshold
        self.min_population = min_population
        self.prey_scarcity_threshold = prey_scarcity_threshold
        self.chronic_decline_threshold = chronic_decline_threshold
        self.chronic_decline_turns = chronic_decline_turns
        self.enable_actual_migration = enable_actual_migration
        
        # 地块死亡率数据缓存
        self._tile_mortality_cache: dict[str, dict[int, float]] = {}  # {lineage_code: {tile_id: death_rate}}
        
        # 猎物密度数据缓存（用于消费者追踪猎物）
        self._prey_density_cache: dict[str, float] = {}  # {lineage_code: prey_density}
        
        # 【新增】慢性衰退追踪（连续死亡率记录）
        self._decline_streak: dict[str, int] = {}  # {lineage_code: consecutive_decline_turns}
    
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
        # 注意：不清空 _decline_streak，需要跨回合追踪
    
    def clear_all_caches(self) -> None:
        """清空所有缓存（存档切换时调用，确保数据隔离）"""
        self._tile_mortality_cache.clear()
        self._prey_density_cache.clear()
        self._decline_streak.clear()
    
    def update_decline_streak(self, lineage_code: str, death_rate: float, growth_rate: float) -> None:
        """更新物种的慢性衰退计数
        
        当死亡率超过阈值且大于繁殖恢复率时，计数+1
        否则计数归零
        
        Args:
            lineage_code: 物种谱系编码
            death_rate: 本回合死亡率
            growth_rate: 本回合繁殖增长率（存活后的增长倍数）
        """
        # 判断是否处于衰退：死亡率 > 阈值 且 死亡 > 繁殖恢复
        is_declining = (
            death_rate >= self.chronic_decline_threshold and 
            (1.0 - death_rate) * growth_rate < 1.0  # 净增长 < 1 意味着在衰退
        )
        
        if is_declining:
            self._decline_streak[lineage_code] = self._decline_streak.get(lineage_code, 0) + 1
        else:
            self._decline_streak[lineage_code] = 0
    
    def get_decline_streak(self, lineage_code: str) -> int:
        """获取物种的连续衰退回合数"""
        return self._decline_streak.get(lineage_code, 0)
    
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
        
        【平衡修复】放宽迁徙条件，增加慢性衰退迁徙：
        - 类型-1（最高优先级）：猎物追踪迁徙 - 消费者追踪猎物密集区域
        - 类型-0.5（新增）：慢性衰退迁徙 - 连续多回合衰退时触发生存迁徙
        - 类型0：地块梯度迁徙 - 从高死亡率地块迁往低死亡率地块
        - 类型1：压力驱动迁徙 - 死亡率达阈值（无需major_events）
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
        # 【修复】不再强制要求major_events，任何压力都可以触发迁徙
        # has_major_pressure = len(major_events) > 0 or len(pressures) > 0
        
        for result in species:
            lineage_code = result.species.lineage_code
            
            # 跳过处于迁徙冷却期的物种
            if lineage_code in cooldown_species:
                continue
            
            migration_type = None
            origin = ""
            destination = ""
            rationale = ""
            
            sp = result.species
            trophic_level = getattr(sp, 'trophic_level', 1.0)
            is_consumer = trophic_level >= 2.0  # T2+ 是消费者
            
            # 【体型自适应】微生物的最小种群要求更低
            body_length = sp.morphology_stats.get("body_length_cm", 1.0)
            effective_min_pop = self.min_population
            if body_length < 0.1:  # 微生物
                effective_min_pop = max(10, self.min_population // 10)
            elif body_length < 1.0:  # 小型生物
                effective_min_pop = max(50, self.min_population // 5)
            
            # 【最高优先级】类型-1：猎物追踪迁徙
            # 消费者（T2+）当猎物稀缺时，主动追踪猎物密集区域
            if is_consumer and result.survivors >= effective_min_pop:
                prey_density = self._prey_density_cache.get(lineage_code, 1.0)
                
                # 当猎物密度低于阈值时，触发追踪迁徙
                if prey_density < self.prey_scarcity_threshold:
                    migration_type = "prey_tracking"
                    origin, destination, rationale = self._determine_prey_tracking_migration(
                        result, prey_density
                    )
            
            # 【新增】类型-0.5：慢性衰退迁徙（生存本能）
            # 当物种连续多回合处于衰退状态时，触发生存迁徙
            if not migration_type:
                decline_streak = self.get_decline_streak(lineage_code)
                if decline_streak >= self.chronic_decline_turns and result.survivors >= effective_min_pop:
                    migration_type = "survival_migration"
                    origin = "当前衰退栖息地"
                    destination = "寻找新的生存空间"
                    rationale = (
                        f"种群已连续{decline_streak}回合衰退（死亡率{result.death_rate:.1%}），"
                        f"触发生存迁徙以寻找更适宜的栖息地"
                    )
            
            # 类型0：地块梯度迁徙
            # 当不同地块的死亡率差异显著时，从高死亡率地块迁往低死亡率地块
            if not migration_type:
                gradient, high_area, low_area = self._analyze_tile_mortality_gradient(lineage_code)
                # 【修复】降低梯度阈值从0.20到0.15
                if gradient >= 0.15 and result.survivors >= effective_min_pop:
                    migration_type = "tile_gradient"
                    origin = high_area
                    destination = low_area
                    rationale = f"地块间死亡率差异{gradient:.0%}，从高风险区域迁往低风险区域"
            
            # 类型2：资源饱和扩散
            if not migration_type and result.resource_pressure > self.saturation_threshold:
                if result.survivors >= effective_min_pop:
                    migration_type = "saturation_dispersal"
                    origin, destination, rationale = self._determine_migration(
                        result, pressures, major_events, migration_type
                    )
            
            # 类型3：人口溢出
            if not migration_type and result.initial_population > 0:
                growth_rate = result.survivors / result.initial_population
                if growth_rate > self.overflow_growth_threshold and result.resource_pressure > self.overflow_pressure_threshold:
                    if result.survivors >= effective_min_pop:
                        migration_type = "population_overflow"
                        origin, destination, rationale = self._determine_migration(
                            result, pressures, major_events, migration_type
                        )
            
            # 类型1：压力驱动迁徙
            # 【修复】移除 has_major_pressure 的硬性要求，只要死亡率达标就触发
            if not migration_type and result.death_rate >= self.pressure_migration_threshold:
                if result.survivors >= effective_min_pop:
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
