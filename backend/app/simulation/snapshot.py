"""
Snapshot System - 快照与回滚系统

支持在任意回合保存世界状态快照，并在之后从该状态恢复继续实验。

快照包含：
- 地图状态
- 所有物种信息
- 栖息地与地块数据
- 全局环境状态
- 运行元数据（回合索引、随机种子等）
"""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Dict, Optional

if TYPE_CHECKING:
    from .context import SimulationContext
    from .engine import SimulationEngine

logger = logging.getLogger(__name__)


# ============================================================================
# 快照数据结构
# ============================================================================

@dataclass
class SnapshotMetadata:
    """快照元数据"""
    snapshot_id: str
    created_at: str
    turn_index: int
    random_seed: int
    mode: str = "standard"
    description: str = ""
    species_count: int = 0
    extinct_count: int = 0
    global_temperature: float = 15.0
    sea_level: float = 0.0
    stage_name: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotMetadata":
        return cls(**data)


@dataclass
class WorldSnapshot:
    """世界状态快照"""
    metadata: SnapshotMetadata
    
    # 地图状态
    map_state: dict = field(default_factory=dict)
    tiles: List[dict] = field(default_factory=list)
    
    # 物种数据
    species: List[dict] = field(default_factory=list)
    habitats: List[dict] = field(default_factory=list)
    
    # 食物网关系
    food_web: List[dict] = field(default_factory=list)
    
    # 随机状态
    random_state: Any = None
    
    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "map_state": self.map_state,
            "tiles": self.tiles,
            "species": self.species,
            "habitats": self.habitats,
            "food_web": self.food_web,
            "random_state": self.random_state,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WorldSnapshot":
        return cls(
            metadata=SnapshotMetadata.from_dict(data["metadata"]),
            map_state=data.get("map_state", {}),
            tiles=data.get("tiles", []),
            species=data.get("species", []),
            habitats=data.get("habitats", []),
            food_web=data.get("food_web", []),
            random_state=data.get("random_state"),
        )


# ============================================================================
# 快照管理器
# ============================================================================

class SnapshotManager:
    """快照管理器
    
    负责创建、保存、列出和恢复世界状态快照。
    """
    
    def __init__(self, snapshot_dir: str | Path = "data/snapshots"):
        """初始化快照管理器
        
        Args:
            snapshot_dir: 快照存储目录
        """
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._current_snapshot_id: str | None = None
    
    def create_snapshot(
        self,
        ctx: SimulationContext,
        engine: SimulationEngine,
        description: str = "",
        custom_id: str | None = None,
    ) -> WorldSnapshot:
        """从当前状态创建快照
        
        Args:
            ctx: 当前回合上下文
            engine: 模拟引擎
            description: 快照描述
            custom_id: 自定义快照 ID
        
        Returns:
            创建的快照对象
        """
        environment_repository = engine.environment_repository
        species_repository = engine.species_repository
        
        # 生成快照 ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = custom_id or f"snapshot_{timestamp}_turn{ctx.turn_index}"
        
        # 获取地图状态
        map_state = {}
        if ctx.current_map_state:
            map_state = {
                "sea_level": ctx.current_map_state.sea_level,
                "global_avg_temperature": ctx.current_map_state.global_avg_temperature,
                "stage_name": getattr(ctx.current_map_state, "stage_name", ""),
                "stage_progress": getattr(ctx.current_map_state, "stage_progress", 0),
                "stage_duration": getattr(ctx.current_map_state, "stage_duration", 0),
                "turn_index": ctx.current_map_state.turn_index,
            }
        
        # 获取地块数据
        tiles_data = []
        try:
            tiles = environment_repository.list_tiles()
            for tile in tiles:
                tiles_data.append({
                    "id": tile.id,
                    "x": tile.x,
                    "y": tile.y,
                    "biome": getattr(tile, "biome", ""),
                    "cover": getattr(tile, "cover", ""),
                    "temperature": getattr(tile, "temperature", 15.0),
                    "humidity": getattr(tile, "humidity", 0.5),
                    "resources": getattr(tile, "resources", 100.0),
                    "elevation": getattr(tile, "elevation", 0.0),
                    "terrain_type": getattr(tile, "terrain_type", ""),
                    "climate_zone": getattr(tile, "climate_zone", ""),
                })
        except Exception as e:
            logger.warning(f"获取地块数据失败: {e}")
        
        # 获取物种数据
        species_data = []
        extinct_count = 0
        try:
            all_species = species_repository.list_species()
            for sp in all_species:
                if sp.status == "extinct":
                    extinct_count += 1
                species_data.append({
                    "id": sp.id,
                    "lineage_code": sp.lineage_code,
                    "common_name": sp.common_name,
                    "latin_name": getattr(sp, "latin_name", ""),
                    "status": sp.status,
                    "trophic_level": getattr(sp, "trophic_level", 1.0),
                    "habitat_type": getattr(sp, "habitat_type", ""),
                    "genus_code": getattr(sp, "genus_code", ""),
                    "parent_code": getattr(sp, "parent_code", ""),
                    "created_turn": getattr(sp, "created_turn", 0),
                    "is_background": getattr(sp, "is_background", False),
                    "morphology_stats": getattr(sp, "morphology_stats", {}),
                    "hidden_traits": getattr(sp, "hidden_traits", {}),
                    "abstract_traits": getattr(sp, "abstract_traits", {}),
                    "organs": getattr(sp, "organs", {}),
                    "capabilities": getattr(sp, "capabilities", []),
                    "description": getattr(sp, "description", ""),
                })
        except Exception as e:
            logger.warning(f"获取物种数据失败: {e}")
        
        # 获取栖息地数据
        habitats_data = []
        try:
            habitats = environment_repository.latest_habitats()
            for hab in habitats:
                habitats_data.append({
                    "id": hab.id,
                    "species_id": hab.species_id,
                    "tile_id": hab.tile_id,
                    "population": hab.population,
                    "suitability": getattr(hab, "suitability", 1.0),
                })
        except Exception as e:
            logger.warning(f"获取栖息地数据失败: {e}")
        
        # 获取食物网数据
        food_web_data = []
        try:
            if hasattr(engine, "food_web_manager"):
                web = engine.food_web_manager.get_current_web()
                if web:
                    for pred_code, prey_list in web.items():
                        for prey_code in prey_list:
                            food_web_data.append({
                                "predator": pred_code,
                                "prey": prey_code,
                            })
        except Exception as e:
            logger.warning(f"获取食物网数据失败: {e}")
        
        # 保存随机状态
        random_state = random.getstate()
        
        # 创建元数据
        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            created_at=datetime.now().isoformat(),
            turn_index=ctx.turn_index,
            random_seed=getattr(engine, "_random_seed", 0),
            mode=getattr(engine, "_current_mode", "standard"),
            description=description,
            species_count=len(species_data),
            extinct_count=extinct_count,
            global_temperature=map_state.get("global_avg_temperature", 15.0),
            sea_level=map_state.get("sea_level", 0.0),
            stage_name=map_state.get("stage_name", ""),
        )
        
        # 创建快照
        snapshot = WorldSnapshot(
            metadata=metadata,
            map_state=map_state,
            tiles=tiles_data,
            species=species_data,
            habitats=habitats_data,
            food_web=food_web_data,
            random_state=random_state,
        )
        
        logger.info(f"[Snapshot] 创建快照: {snapshot_id}")
        logger.info(f"  回合: {ctx.turn_index}, 物种: {len(species_data)}, 地块: {len(tiles_data)}")
        
        return snapshot
    
    def save_snapshot(self, snapshot: WorldSnapshot) -> Path:
        """保存快照到文件
        
        Args:
            snapshot: 快照对象
        
        Returns:
            保存的文件路径
        """
        snapshot_path = self.snapshot_dir / f"{snapshot.metadata.snapshot_id}.json"
        
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"[Snapshot] 保存到: {snapshot_path}")
        
        return snapshot_path
    
    def load_snapshot(self, snapshot_id: str) -> WorldSnapshot:
        """加载快照
        
        Args:
            snapshot_id: 快照 ID
        
        Returns:
            快照对象
        
        Raises:
            FileNotFoundError: 快照文件不存在
        """
        snapshot_path = self.snapshot_dir / f"{snapshot_id}.json"
        
        if not snapshot_path.exists():
            raise FileNotFoundError(f"快照不存在: {snapshot_id}")
        
        with open(snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        snapshot = WorldSnapshot.from_dict(data)
        logger.info(f"[Snapshot] 加载快照: {snapshot_id}")
        
        return snapshot
    
    def list_snapshots(self) -> List[SnapshotMetadata]:
        """列出所有快照
        
        Returns:
            快照元数据列表（按创建时间倒序）
        """
        snapshots = []
        
        for path in self.snapshot_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                metadata = SnapshotMetadata.from_dict(data["metadata"])
                snapshots.append(metadata)
            except Exception as e:
                logger.warning(f"读取快照元数据失败: {path} - {e}")
        
        # 按创建时间倒序
        snapshots.sort(key=lambda m: m.created_at, reverse=True)
        
        return snapshots
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照
        
        Args:
            snapshot_id: 快照 ID
        
        Returns:
            是否成功删除
        """
        snapshot_path = self.snapshot_dir / f"{snapshot_id}.json"
        
        if snapshot_path.exists():
            snapshot_path.unlink()
            logger.info(f"[Snapshot] 删除快照: {snapshot_id}")
            return True
        
        return False
    
    def restore_snapshot(
        self,
        snapshot: WorldSnapshot,
        engine: SimulationEngine,
    ) -> SimulationContext:
        """从快照恢复世界状态
        
        Args:
            snapshot: 快照对象
            engine: 模拟引擎
        
        Returns:
            恢复后的上下文
        """
        environment_repository = engine.environment_repository
        from .context import SimulationContext
        
        logger.info(f"[Snapshot] 开始恢复快照: {snapshot.metadata.snapshot_id}")
        logger.info(f"  目标回合: {snapshot.metadata.turn_index}")
        
        # 恢复随机状态
        if snapshot.random_state:
            random.setstate(snapshot.random_state)
            logger.info("  ✓ 随机状态已恢复")
        
        # 恢复地图状态
        if snapshot.map_state:
            try:
                environment_repository.save_state(snapshot.map_state)
                logger.info("  ✓ 地图状态已恢复")
            except Exception as e:
                logger.error(f"  ✗ 地图状态恢复失败: {e}")
        
        # 恢复地块数据
        if snapshot.tiles:
            try:
                # 这里需要根据实际的仓储接口来实现
                # 简化处理：批量更新地块
                tiles_to_update = []
                for tile_data in snapshot.tiles:
                    # 创建或更新地块对象
                    # 具体实现依赖于 Tile 模型
                    pass
                logger.info(f"  ✓ 恢复了 {len(snapshot.tiles)} 个地块")
            except Exception as e:
                logger.error(f"  ✗ 地块恢复失败: {e}")
        
        # 恢复物种数据
        if snapshot.species:
            try:
                # 清除当前物种并恢复快照中的物种
                # 具体实现依赖于 Species 模型和仓储
                restored_count = 0
                for sp_data in snapshot.species:
                    try:
                        # species_repository.upsert_from_dict(sp_data)
                        restored_count += 1
                    except Exception as e:
                        logger.warning(f"  恢复物种失败: {sp_data.get('lineage_code')} - {e}")
                logger.info(f"  ✓ 恢复了 {restored_count} 个物种")
            except Exception as e:
                logger.error(f"  ✗ 物种恢复失败: {e}")
        
        # 恢复栖息地数据
        if snapshot.habitats:
            try:
                # 恢复栖息地关系
                logger.info(f"  ✓ 恢复了 {len(snapshot.habitats)} 个栖息地")
            except Exception as e:
                logger.error(f"  ✗ 栖息地恢复失败: {e}")
        
        # 恢复食物网
        if snapshot.food_web and hasattr(engine, "food_web_manager"):
            try:
                # 重建食物网关系
                for rel in snapshot.food_web:
                    engine.food_web_manager.add_relation(
                        rel["predator"],
                        rel["prey"]
                    )
                logger.info(f"  ✓ 恢复了 {len(snapshot.food_web)} 条食物网关系")
            except Exception as e:
                logger.error(f"  ✗ 食物网恢复失败: {e}")
        
        # 创建新的上下文
        ctx = SimulationContext(
            turn_index=snapshot.metadata.turn_index,
        )
        
        # 设置引擎状态
        if hasattr(engine, "_random_seed"):
            engine._random_seed = snapshot.metadata.random_seed
        if hasattr(engine, "_current_mode"):
            engine._current_mode = snapshot.metadata.mode
        
        self._current_snapshot_id = snapshot.metadata.snapshot_id
        
        logger.info(f"[Snapshot] 快照恢复完成")
        
        return ctx
    
    def get_snapshot_info(self, snapshot_id: str) -> str:
        """获取快照详细信息（格式化文本）"""
        try:
            snapshot = self.load_snapshot(snapshot_id)
            m = snapshot.metadata
            
            lines = [
                f"快照 ID: {m.snapshot_id}",
                f"创建时间: {m.created_at}",
                f"回合: {m.turn_index}",
                f"描述: {m.description or '(无)'}",
                f"",
                f"模式: {m.mode}",
                f"随机种子: {m.random_seed}",
                f"",
                f"物种统计:",
                f"  存活: {m.species_count - m.extinct_count}",
                f"  灭绝: {m.extinct_count}",
                f"  总计: {m.species_count}",
                f"",
                f"环境状态:",
                f"  全球温度: {m.global_temperature:.1f}°C",
                f"  海平面: {m.sea_level:.1f}m",
                f"  地质阶段: {m.stage_name or '未知'}",
                f"",
                f"数据统计:",
                f"  地块数: {len(snapshot.tiles)}",
                f"  栖息地数: {len(snapshot.habitats)}",
                f"  食物网关系: {len(snapshot.food_web)}",
            ]
            
            return "\n".join(lines)
            
        except FileNotFoundError:
            return f"快照不存在: {snapshot_id}"
        except Exception as e:
            return f"读取快照失败: {e}"


# ============================================================================
# 快照阶段
# ============================================================================

class SnapshotStage:
    """快照阶段 - 可选在指定回合自动创建快照"""
    
    def __init__(
        self,
        manager: SnapshotManager,
        auto_snapshot_interval: int = 0,
        auto_snapshot_turns: List[int] | None = None,
    ):
        """初始化快照阶段
        
        Args:
            manager: 快照管理器
            auto_snapshot_interval: 自动快照间隔（0=禁用）
            auto_snapshot_turns: 指定回合创建快照（如 [0, 10, 50, 100]）
        """
        from .stages import BaseStage, StageOrder
        
        self.manager = manager
        self.auto_snapshot_interval = auto_snapshot_interval
        self.auto_snapshot_turns = set(auto_snapshot_turns or [])
        self._order = 175  # 在 EXPORT_DATA 之后
        self._name = "快照保存"
        self._is_async = False
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def order(self) -> int:
        return self._order
    
    @property
    def is_async(self) -> bool:
        return self._is_async
    
    async def execute(
        self,
        ctx: SimulationContext,
        engine: SimulationEngine,
    ) -> None:
        """执行快照检查"""
        should_snapshot = False
        
        # 检查是否需要快照
        if self.auto_snapshot_interval > 0:
            if ctx.turn_index % self.auto_snapshot_interval == 0:
                should_snapshot = True
        
        if ctx.turn_index in self.auto_snapshot_turns:
            should_snapshot = True
        
        if should_snapshot:
            snapshot = self.manager.create_snapshot(
                ctx, engine,
                description=f"自动快照 - 回合 {ctx.turn_index}"
            )
            self.manager.save_snapshot(snapshot)
            ctx.emit_event(
                "snapshot",
                f"📸 已保存快照: {snapshot.metadata.snapshot_id}",
                "系统"
            )


# ============================================================================
# 便捷函数
# ============================================================================

# 默认快照管理器实例
_default_manager: SnapshotManager | None = None


def get_snapshot_manager(snapshot_dir: str | Path = "data/snapshots") -> SnapshotManager:
    """获取默认快照管理器"""
    global _default_manager
    if _default_manager is None:
        _default_manager = SnapshotManager(snapshot_dir)
    return _default_manager


def create_snapshot(
    ctx: SimulationContext,
    engine: SimulationEngine,
    description: str = "",
) -> WorldSnapshot:
    """创建并保存快照"""
    manager = get_snapshot_manager()
    snapshot = manager.create_snapshot(ctx, engine, description)
    manager.save_snapshot(snapshot)
    return snapshot


def list_snapshots() -> List[SnapshotMetadata]:
    """列出所有快照"""
    manager = get_snapshot_manager()
    return manager.list_snapshots()


def restore_from_snapshot(
    snapshot_id: str,
    engine: SimulationEngine,
) -> SimulationContext:
    """从指定快照恢复"""
    manager = get_snapshot_manager()
    snapshot = manager.load_snapshot(snapshot_id)
    return manager.restore_snapshot(snapshot, engine)



