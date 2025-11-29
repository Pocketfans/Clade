"""板块构造系统集成模块

将板块构造系统集成到主游戏演化流程中。
提供适配器将板块系统的数据与主系统对接。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Sequence, Any

from .tectonic_system import TectonicSystem
from .species_tracker import SimpleSpecies, SimpleHabitat, HabitatType
from .models import TectonicStepResult, TectonicEvent, IsolationEvent, ContactEvent

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.environment import MapTile

logger = logging.getLogger(__name__)


class TectonicIntegration:
    """板块构造系统集成器
    
    负责：
    1. 初始化和管理板块系统
    2. 将主系统物种转换为板块系统格式
    3. 将板块系统的地形变化应用到主系统地块
    4. 将板块系统的事件转换为主系统格式
    """
    
    def __init__(self, width: int, height: int, seed: int = 12345):
        """
        初始化集成器
        
        Args:
            width: 地图宽度
            height: 地图高度
            seed: 随机种子
        """
        self.width = width
        self.height = height
        self.seed = seed
        
        # 板块系统
        self.tectonic = TectonicSystem(width=width, height=height, seed=seed)
        
        # 缓存
        self._species_cache: dict[int, SimpleSpecies] = {}
        self._habitat_cache: list[SimpleHabitat] = []
        
        logger.info(f"[板块集成] 初始化完成: {width}x{height}, 种子={seed}")
    
    def step(
        self,
        species_list: Sequence[Any],  # Species from main system
        habitat_data: list[dict],  # 栖息地数据
        map_tiles: Sequence[Any],  # MapTile from main system
        pressure_modifiers: dict[str, float] | None = None,
    ) -> TectonicIntegrationResult:
        """
        执行一步板块运动并返回集成结果
        
        Args:
            species_list: 主系统物种列表
            habitat_data: 栖息地数据 [{"tile_id": int, "species_id": int, "population": float}]
            map_tiles: 主系统地块列表
            pressure_modifiers: 环境压力
            
        Returns:
            TectonicIntegrationResult
        """
        pressure_modifiers = pressure_modifiers or {}
        
        # 1. 转换物种数据
        simple_species = self._convert_species(species_list)
        
        # 2. 转换栖息地数据
        simple_habitats = self._convert_habitats(habitat_data)
        
        # 3. 执行板块运动
        result = self.tectonic.step(
            pressure_modifiers=pressure_modifiers,
            species_list=simple_species,
            habitats=simple_habitats,
        )
        
        # 4. 生成集成结果
        integration_result = TectonicIntegrationResult(
            turn_index=result.turn_index,
            terrain_changes=[],
            tectonic_events=[],
            isolation_events=result.isolation_events,
            contact_events=result.contact_events,
            wilson_phase=self.tectonic.get_wilson_phase(),
            pressure_feedback=result.pressure_feedback,
        )
        
        # 5. 转换地形变化为主系统格式
        for tc in result.terrain_changes:
            integration_result.terrain_changes.append({
                "tile_id": tc.tile_id,
                "x": tc.x,
                "y": tc.y,
                "old_elevation": tc.old_elevation,
                "new_elevation": tc.new_elevation,
                "cause": tc.cause,
                "delta": tc.elevation_delta,
                "old_temperature": tc.old_temperature,
                "new_temperature": tc.new_temperature,
                "temp_delta": tc.temperature_delta,
            })
        
        # 6. 转换事件为主系统格式
        for event in result.events:
            integration_result.tectonic_events.append({
                "type": event.event_type,
                "x": event.x,
                "y": event.y,
                "tile_id": event.tile_id,
                "magnitude": event.magnitude,
                "radius": event.affected_radius,
                "description": event.description,
            })
        
        logger.info(
            f"[板块集成] 回合 {result.turn_index}: "
            f"地形变化 {len(result.terrain_changes)}, "
            f"事件 {len(result.events)}, "
            f"威尔逊阶段 {integration_result.wilson_phase['phase']}"
        )
        
        return integration_result
    
    def _convert_species(self, species_list: Sequence[Any]) -> list[SimpleSpecies]:
        """将主系统物种转换为板块系统格式"""
        result = []
        
        for sp in species_list:
            # 获取物种属性
            sp_id = getattr(sp, "id", 0)
            lineage = getattr(sp, "lineage_code", f"SP{sp_id:04d}")
            name = getattr(sp, "name", f"物种{sp_id}")
            trophic = getattr(sp, "trophic_level", 2.0)
            habitat = getattr(sp, "habitat_type", "terrestrial")
            
            # 计算迁移能力
            mobility = getattr(sp, "mobility", 0.5)
            flight = getattr(sp, "can_fly", False)
            dispersal = min(1.0, mobility * 0.5 + (0.3 if flight else 0))
            
            simple_sp = SimpleSpecies(
                id=sp_id,
                lineage_code=lineage,
                name=name,
                trophic_level=trophic,
                habitat_type=habitat,
                dispersal_ability=dispersal,
            )
            result.append(simple_sp)
            self._species_cache[sp_id] = simple_sp
        
        return result
    
    def _convert_habitats(self, habitat_data: list[dict]) -> list[SimpleHabitat]:
        """将栖息地数据转换为板块系统格式"""
        result = []
        
        for h in habitat_data:
            simple_h = SimpleHabitat(
                tile_id=h.get("tile_id", 0),
                species_id=h.get("species_id", 0),
                population=h.get("population", 0.0),
            )
            result.append(simple_h)
        
        self._habitat_cache = result
        return result
    
    def apply_terrain_changes(
        self,
        map_tiles: Sequence[Any],
        changes: list[dict],
    ) -> int:
        """
        将地形变化应用到主系统地块
        
        Args:
            map_tiles: 主系统地块列表（会被修改）
            changes: 地形变化列表
            
        Returns:
            应用的变化数量
        """
        tile_map = {getattr(t, "id", i): t for i, t in enumerate(map_tiles)}
        applied = 0
        
        for change in changes:
            tile_id = change["tile_id"]
            new_elevation = change["new_elevation"]
            
            tile = tile_map.get(tile_id)
            if tile and hasattr(tile, "elevation"):
                tile.elevation = new_elevation
                applied += 1
        
        return applied
    
    def get_isolation_species_ids(
        self,
        isolation_events: list[IsolationEvent],
    ) -> list[int]:
        """获取发生隔离的物种ID列表"""
        return [e.species_id for e in isolation_events]
    
    def get_contact_species_pairs(
        self,
        contact_events: list[ContactEvent],
    ) -> list[tuple[int, int, str]]:
        """获取发生接触的物种对和交互类型"""
        return [
            (e.species_a_id, e.species_b_id, e.interaction_type)
            for e in contact_events
        ]
    
    def get_statistics(self) -> dict[str, Any]:
        """获取板块系统统计信息"""
        return self.tectonic.get_statistics()
    
    def get_wilson_phase(self) -> dict[str, Any]:
        """获取威尔逊周期信息"""
        return self.tectonic.get_wilson_phase()
    
    def get_volcanoes(self) -> list[dict]:
        """获取火山列表"""
        return [v.to_dict() for v in self.tectonic.get_volcanoes()]
    
    def get_plates(self) -> list[dict]:
        """获取板块列表"""
        return [p.to_dict() for p in self.tectonic.get_plates()]
    
    def trigger_volcanic_eruption(
        self,
        intensity: int = 5,
        target_region: tuple[int, int] | None = None,
    ) -> list[dict]:
        """手动触发火山喷发"""
        events = self.tectonic.trigger_volcanic_eruption(
            pressure_type="volcanic_eruption",
            intensity=intensity,
            target_region=target_region,
        )
        return [e.to_dict() for e in events]
    
    def save_state(self, path: str) -> None:
        """保存板块系统状态"""
        self.tectonic.save(path)
    
    @classmethod
    def load_state(cls, path: str) -> "TectonicIntegration":
        """加载板块系统状态"""
        tectonic = TectonicSystem.load(path)
        integration = cls(
            width=tectonic.width,
            height=tectonic.height,
            seed=tectonic.seed,
        )
        integration.tectonic = tectonic
        return integration


class TectonicIntegrationResult:
    """板块集成结果"""
    
    def __init__(
        self,
        turn_index: int,
        terrain_changes: list[dict],
        tectonic_events: list[dict],
        isolation_events: list[IsolationEvent],
        contact_events: list[ContactEvent],
        wilson_phase: dict,
        pressure_feedback: dict[str, float],
    ):
        self.turn_index = turn_index
        self.terrain_changes = terrain_changes
        self.tectonic_events = tectonic_events
        self.isolation_events = isolation_events
        self.contact_events = contact_events
        self.wilson_phase = wilson_phase
        self.pressure_feedback = pressure_feedback
    
    @property
    def has_phase_change(self) -> bool:
        """是否发生了威尔逊周期阶段变化"""
        return any(e["type"] == "wilson_phase_change" for e in self.tectonic_events)
    
    @property
    def earthquake_count(self) -> int:
        """地震数量"""
        return sum(1 for e in self.tectonic_events if e["type"] == "earthquake")
    
    @property
    def volcano_eruption_count(self) -> int:
        """火山喷发数量"""
        return sum(1 for e in self.tectonic_events if "volcanic" in e["type"])
    
    def get_major_events_summary(self) -> list[str]:
        """获取主要事件摘要"""
        summary = []
        
        if self.has_phase_change:
            summary.append(f"威尔逊周期进入{self.wilson_phase['phase']}阶段")
        
        if self.earthquake_count > 0:
            summary.append(f"发生{self.earthquake_count}次地震")
        
        if self.volcano_eruption_count > 0:
            summary.append(f"发生{self.volcano_eruption_count}次火山喷发")
        
        if self.isolation_events:
            summary.append(f"{len(self.isolation_events)}个物种发生地理隔离")
        
        if self.contact_events:
            summary.append(f"{len(self.contact_events)}对物种发生接触")
        
        return summary
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "turn_index": self.turn_index,
            "terrain_changes_count": len(self.terrain_changes),
            "tectonic_events": self.tectonic_events,
            "isolation_events": [e.to_dict() for e in self.isolation_events],
            "contact_events": [e.to_dict() for e in self.contact_events],
            "wilson_phase": self.wilson_phase,
            "pressure_feedback": self.pressure_feedback,
            "summary": self.get_major_events_summary(),
        }


# 便捷函数：创建集成器
def create_tectonic_integration(
    width: int = 128,
    height: int = 40,
    seed: int | None = None,
) -> TectonicIntegration:
    """创建板块构造集成器"""
    import random
    if seed is None:
        seed = random.randint(1, 999999)
    
    return TectonicIntegration(width=width, height=height, seed=seed)

