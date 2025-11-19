from __future__ import annotations

from typing import Sequence

from ..schemas.responses import MajorPressureEvent, MapChange, MigrationEvent
from ..simulation.species import MortalityResult


class MigrationAdvisor:
    """基于规则引擎的迁徙决策系统。
    
    根据死亡率、压力类型、地图变化判断物种是否需要迁徙。
    """

    def __init__(self, 
                 pressure_migration_threshold: float = 0.35,  # 降低压力驱动阈值
                 saturation_threshold: float = 0.9,          # 降低资源饱和阈值
                 overflow_growth_threshold: float = 1.2,     # 降低溢出增长阈值
                 overflow_pressure_threshold: float = 0.7,   # 降低溢出资源压力阈值
                 min_population: int = 500) -> None:
        """初始化迁移顾问
        
        调整后的逻辑：
        - 压力驱动（逃离）：降低门槛(35%)，更容易触发
        - 资源饱和（扩散）：降低门槛(0.9)，鼓励早期扩散
        - 人口溢出（扩张）：降低门槛(120%)，鼓励种群扩张
        """
        self.pressure_migration_threshold = pressure_migration_threshold
        self.saturation_threshold = saturation_threshold
        self.overflow_growth_threshold = overflow_growth_threshold
        self.overflow_pressure_threshold = overflow_pressure_threshold
        self.min_population = min_population

    def plan(
        self,
        species: Sequence[MortalityResult],
        pressures: dict[str, float],
        major_events: Sequence[MajorPressureEvent],
        map_changes: Sequence[MapChange],
    ) -> list[MigrationEvent]:
        """基于规则生成迁徙建议。
        
        迁徙/扩散条件（三种类型）：
        1. 压力驱动迁徙：死亡率高 + 环境压力
        2. 资源饱和扩散：资源压力高 + 种群稳定
        3. 人口溢出：种群暴涨 + 资源不足
        """
        if not species:
            return []
        
        events: list[MigrationEvent] = []
        has_major_pressure = len(major_events) > 0 or len(pressures) > 0
        
        for result in species:
            migration_type = None
            origin = ""
            destination = ""
            rationale = ""
            
            # 类型2：资源饱和扩散
            if result.resource_pressure > self.saturation_threshold:
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
